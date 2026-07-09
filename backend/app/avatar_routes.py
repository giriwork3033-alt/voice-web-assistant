from __future__ import annotations

"""
EXPERIMENTAL, additive routes for the LiveAvatar integration. See
avatar_liveavatar.py's module docstring for the current known reliability
caveats and the recommended time-box before relying on this.

Wire this into your existing main.py with:

    from .avatar_routes import router as avatar_router
    app.include_router(avatar_router)

Nothing here touches /ask-text, /voice, or _build_response - if this
integration doesn't pan out, your existing pipeline and the illustrated
TalkingAvatar.jsx are completely unaffected.
"""

import base64

from fastapi import APIRouter

from .avatar_liveavatar import LiveAvatarSession

router = APIRouter(prefix="/avatar", tags=["avatar-experimental"])

_session: LiveAvatarSession | None = None


@router.post("/session/start")
async def avatar_session_start():
    global _session
    _session = LiveAvatarSession()
    try:
        info = await _session.create_and_start()
        return info
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@router.post("/session/close")
async def avatar_session_close():
    global _session
    if _session is not None:
        await _session.close()
        _session = None
    return {"status": "closed"}


@router.post("/speak")
async def avatar_speak(payload: dict):
    if _session is None:
        return {"error": "No active avatar session. Call /avatar/session/start first."}
    audio_base64 = payload.get("audio_base64", "")
    if not audio_base64:
        return {"error": "audio_base64 is required."}
    try:
        mp3_bytes = base64.b64decode(audio_base64)
        await _session.speak(mp3_bytes)
        return {"status": "sent"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
