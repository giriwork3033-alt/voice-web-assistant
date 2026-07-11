from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import edge_tts
from .config import settings

# ---------------------------------------------------------------------------
# Speech-to-text: Groq's hosted Whisper API (fast, GPU-accelerated)
# Falls back to local faster-whisper only if GROQ_API_KEY is missing.
# ---------------------------------------------------------------------------

async def speech_to_text(file_path: str) -> str:
    if settings.groq_api_key:
        return await _stt_groq(file_path)
    return await _stt_local(file_path)


async def _stt_groq(file_path: str) -> str:
    """Use Groq's hosted Whisper API. Typically 1-2s for short clips,
    vs 60-80s for local faster-whisper on a free-tier CPU."""
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.groq_api_key)
        with open(file_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                file=(file_path, audio_file.read()),
                model="whisper-large-v3",
                language="en",
                response_format="text",
            )
        text = (transcription or "").strip()
        print(f"[STT] Groq Whisper returned: '{text[:100]}'")
        return text
    except Exception as e:
        print(f"[STT] Groq Whisper failed ({type(e).__name__}: {e}), falling back to local")
        return await _stt_local(file_path)


async def _stt_local(file_path: str) -> str:
    """Local faster-whisper fallback. Only used if GROQ_API_KEY is missing."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(settings.whisper_model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(file_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        return text.strip()
    except Exception as e:
        print(f"[STT] Local whisper failed: {type(e).__name__}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Text-to-speech: Edge-TTS (unchanged, already fast at ~0.5-1s)
# ---------------------------------------------------------------------------

async def text_to_speech(text: str) -> str:
    if not text:
        return ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            out_path = Path(tmp.name)
        communicate = edge_tts.Communicate(text=text, voice=settings.edge_tts_voice)
        await communicate.save(str(out_path))
        data = out_path.read_bytes()
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return base64.b64encode(data).decode("utf-8")
    except Exception as e:
        print(f"TTS failed: {type(e).__name__}: {e}")
        return ""
