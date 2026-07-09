import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent } from "livekit-client";

/**
 * EXPERIMENTAL. See backend/avatar_liveavatar.py's docstring for known
 * current reliability issues with this API. This component is additive -
 * your existing <TalkingAvatar /> keeps working regardless of whether
 * this does, and the two are not wired together.
 *
 * TIME-BOX: give this at most 2-3 hours end to end. If the session never
 * reaches "connected" or no video track ever arrives in that time, that's
 * a legitimate finding for your report, not a reason to keep debugging
 * into your deadline.
 *
 * Setup: npm install livekit-client
 *
 * Known UX gap if you run this alongside <TalkingAvatar />: both will
 * play the same speech audio (one locally, one via the avatar's LiveKit
 * audio track) - mute one of the two when demoing both side by side.
 */
export default function LiveAvatarPanel({ audioBase64, apiBaseUrl = "" }) {
  const videoRef = useRef(null);
  const roomRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | connecting | connected | error
  const [errorMsg, setErrorMsg] = useState("");

  const startSession = async () => {
    setStatus("connecting");
    setErrorMsg("");
    try {
      const res = await fetch(`${apiBaseUrl}/avatar/session/start`, { method: "POST" });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      if (!data.livekit_url || !data.livekit_token) {
        throw new Error("Response missing livekit_url/livekit_token - check the raw response logged by the backend and adjust avatar_liveavatar.py's field names.");
      }

      const room = new Room();
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === "video" && videoRef.current) {
          track.attach(videoRef.current);
        }
        if (track.kind === "audio") {
          const audioEl = document.createElement("audio");
          audioEl.autoplay = true;
          track.attach(audioEl);
          document.body.appendChild(audioEl);
        }
      });

      await room.connect(data.livekit_url, data.livekit_token);
      setStatus("connected");
    } catch (err) {
      console.error("LiveAvatar session failed:", err);
      setErrorMsg(String(err.message || err));
      setStatus("error");
    }
  };

  const stopSession = async () => {
    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }
    try {
      await fetch(`${apiBaseUrl}/avatar/session/close`, { method: "POST" });
    } catch (err) {
      console.error("Failed to close avatar session:", err);
    }
    setStatus("idle");
  };

  useEffect(() => {
    return () => {
      if (roomRef.current) roomRef.current.disconnect();
    };
  }, []);

  useEffect(() => {
    if (status !== "connected" || !audioBase64) return;
    fetch(`${apiBaseUrl}/avatar/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio_base64: audioBase64 }),
    }).catch((err) => console.error("avatar/speak failed:", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioBase64, status]);

  return (
    <div style={{ maxWidth: 360, margin: "0 auto", display: "flex", flexDirection: "column", gap: 8 }}>
      <video ref={videoRef} autoPlay playsInline style={{ width: "100%", borderRadius: 12, background: "#000" }} />
      <div style={{ fontSize: 13, color: "#6b6b68" }}>
        Status: {status}
        {errorMsg ? ` - ${errorMsg}` : ""}
      </div>
      {status === "idle" && <button onClick={startSession}>Start LiveAvatar session (experimental)</button>}
      {status === "connected" && <button onClick={stopSession}>End session</button>}
    </div>
  );
}
