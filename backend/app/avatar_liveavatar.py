from __future__ import annotations

"""
EXPERIMENTAL, ADDITIVE integration with HeyGen's LiveAvatar (CUSTOM mode)
for a real photorealistic, real-time speaking avatar over WebRTC.

STATUS AS OF WRITING: LiveAvatar's own support forum shows recent (within
the last month) reports of `/v1/sessions/start` returning a 500 Internal
Server Error, and the CUSTOM-mode audio websocket returning
"400006 - Session is not in correct state" races right after starting a
session. This module is written against LiveAvatar's documented CUSTOM
mode flow, but has NOT been tested end-to-end against the live API - no
credentials or network access to api.liveavatar.com were available while
writing it. Field names for `/v1/sessions/start`'s response in particular
were not fully confirmed; check https://docs.liveavatar.com/reference
before relying on them.

This is ADDITIVE by design: your existing TalkingAvatar.jsx illustrated
avatar and your whole STT -> Groq -> guardrails -> TTS pipeline are
completely untouched by this file. If this doesn't work, you lose nothing
you already have.

TIME-BOX: give this at most 2-3 hours end to end (get an API key, set env
vars, get a session to start, get one "speak" call to actually render
video). If `/v1/sessions/start` or the audio websocket aren't behaving in
that window, stop and use this code plus the forum reports above as your
report's honest "what's needed for production, and why it wasn't feasible
in the time available" answer - that's a legitimate engineering finding,
not a failure to hide.

Setup:
  pip install httpx websockets --break-system-packages
  Set in .env: LIVEAVATAR_API_KEY=..., LIVEAVATAR_AVATAR_ID=...
  (sign up at app.liveavatar.com to get both)
"""

import asyncio
import base64
import io
import json
import os
import uuid
from typing import Optional

import httpx
import imageio_ffmpeg
import websockets
from pydub import AudioSegment

AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

LIVEAVATAR_API_KEY = os.getenv("LIVEAVATAR_API_KEY", "")
LIVEAVATAR_AVATAR_ID = os.getenv("LIVEAVATAR_AVATAR_ID", "")
LIVEAVATAR_BASE_URL = "https://api.liveavatar.com"

# Real-time avatar/voice protocols (ElevenLabs' own LiveAvatar integration,
# OpenAI/Azure/xAI realtime voice APIs) universally expect raw PCM16 audio,
# not a compressed container like MP3. 24000 Hz mono is what ElevenLabs'
# LiveAvatar integration docs specify explicitly; if audio still sounds
# wrong after this fix, try 16000 as the next most common alternative.
PCM_SAMPLE_RATE = 24000


def _mp3_to_pcm16(mp3_bytes: bytes, sample_rate: int = PCM_SAMPLE_RATE) -> bytes:
    """Decode an MP3 (e.g. Edge-TTS output) to raw 16-bit PCM, mono, at
    the given sample rate - the format real-time avatar audio channels
    actually expect, unlike a compressed MP3 file."""
    segment = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
    segment = segment.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
    return segment.raw_data


class LiveAvatarSession:
    """
    One LiveAvatar CUSTOM-mode session: creates it, starts it, holds the
    websocket used to send already-generated TTS audio for the avatar to
    lip-sync to, and returns the LiveKit room details the frontend needs
    to actually display the video.
    """

    def __init__(self):
        self.session_id: Optional[str] = None
        self.session_token: Optional[str] = None
        self.ws_url: Optional[str] = None
        self.livekit_url: Optional[str] = None
        self.livekit_token: Optional[str] = None
        self._ws = None
        self._listener_task: Optional[asyncio.Task] = None

    async def create_and_start(self) -> dict:
        if not LIVEAVATAR_API_KEY or not LIVEAVATAR_AVATAR_ID:
            raise RuntimeError("LIVEAVATAR_API_KEY and LIVEAVATAR_AVATAR_ID must be set.")

        async with httpx.AsyncClient(timeout=20) as client:
            token_resp = await client.post(
                f"{LIVEAVATAR_BASE_URL}/v1/sessions/token",
                headers={"X-API-KEY": LIVEAVATAR_API_KEY, "Content-Type": "application/json"},
                # "LITE" is confirmed valid in the current API reference for
                # bring-your-own-stack sessions. Some docs pages refer to a
                # "CUSTOM mode" for the websocket-driven flow used below -
                # if this call rejects "LITE", check the reference for the
                # current expected value.
                json={"mode": "LITE", "avatar_id": LIVEAVATAR_AVATAR_ID},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()["data"]
            self.session_id = token_data["session_id"]
            self.session_token = token_data["session_token"]

            # Confirmed from LiveAvatar's own forum: the session token is
            # sent as a Bearer token here, not X-API-KEY.
            start_resp = await client.post(
                f"{LIVEAVATAR_BASE_URL}/v1/sessions/start",
                headers={
                    "Authorization": f"Bearer {self.session_token}",
                    "Content-Type": "application/json",
                },
                json={},
            )
            start_resp.raise_for_status()
            start_data = start_resp.json()["data"]

            self.ws_url = start_data["ws_url"]
            # Confirmed from a real 200 response: the client join token is
            # under "livekit_client_token" (there's also a separate
            # "livekit_agent_token" for the avatar side, not used here).
            self.livekit_url = start_data.get("livekit_url")
            self.livekit_token = start_data.get("livekit_client_token")
            max_duration = start_data.get("max_session_duration")
            print(f"[LiveAvatar] /v1/sessions/start raw response: {start_data}")
            if max_duration:
                print(f"[LiveAvatar] session will auto-expire after {max_duration} seconds")

        return {
            "session_id": self.session_id,
            "livekit_url": self.livekit_url,
            "livekit_token": self.livekit_token,
        }

    async def connect_ws(self):
        if not self.ws_url:
            raise RuntimeError("Call create_and_start() before connect_ws().")
        self._ws = await websockets.connect(self.ws_url)
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        """
        Logs every event LiveAvatar sends back over the websocket. This is
        your visibility into the "Session is not in correct state" and
        similar errors reported on LiveAvatar's forum - without reading
        this stream, sending audio can silently fail with no indication
        anything went wrong on your end.
        """
        try:
            async for raw in self._ws:
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"[LiveAvatar] non-JSON message: {raw}")
                    continue
                if event.get("type") == "error":
                    print(f"[LiveAvatar] ERROR EVENT: {event}")
                else:
                    print(f"[LiveAvatar] event: {event}")
        except websockets.ConnectionClosed as e:
            print(f"[LiveAvatar] websocket closed: {e}")

    async def speak(self, mp3_bytes: bytes):
        """Send already-generated TTS audio for the avatar to lip-sync to.

        Converts MP3 -> raw PCM16 first (see _mp3_to_pcm16 above) - sending
        the raw MP3 bytes directly produced a short burst of noise rather
        than speech, consistent with the receiving side expecting PCM
        samples rather than a compressed file.
        """
        if self._ws is None:
            await self.connect_ws()
        pcm_bytes = await asyncio.to_thread(_mp3_to_pcm16, mp3_bytes)
        audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
        event = {
            "type": "agent.speak",
            "event_id": str(uuid.uuid4()),
            "audio": audio_b64,
        }
        await self._ws.send(json.dumps(event))

    async def close(self):
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
