from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import edge_tts
from faster_whisper import WhisperModel
from .config import settings

_whisper_model: WhisperModel | None = None

def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        # int8 keeps it light for laptops. First run downloads the model.
        _whisper_model = WhisperModel(settings.whisper_model_size, device="cpu", compute_type="int8")
    return _whisper_model

async def speech_to_text(file_path: str) -> str:
    try:
        model = _get_whisper_model()
        segments, _ = model.transcribe(file_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        return text.strip()
    except Exception as e:
        print(f"STT failed: {type(e).__name__}: {e}")
        return ""

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
