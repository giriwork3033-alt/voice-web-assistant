from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import answer_query
from .config import settings
from .guardrails import is_safe_input, is_safe_output, SAFE_REFUSAL
from .speech import speech_to_text, text_to_speech
from .anam_routes import router as anam_router

app = FastAPI(title="Voice Web Assistant", version="1.0.0")
app.include_router(anam_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider}

async def _build_response(transcript: str):
    import asyncio
    import time

    transcript = (transcript or "").strip()
    if not transcript:
        answer = "I couldn't understand the input. Please try again."
        print("The source of this information is n/a (empty input)")
        print(f"add the actual response:{answer}")
        return {
            "transcript": "",
            "answer": answer,
            "provider": settings.llm_provider,
            "source": "n/a (empty input)",
            "refSites": [],
            "audio_base64": await text_to_speech(answer),
        }

    t0 = time.time()

    safe_input_task = asyncio.create_task(is_safe_input(transcript))
    answer_task = asyncio.create_task(answer_query(transcript))
    safe_input, provider_response = await asyncio.gather(safe_input_task, answer_task)
    answer = provider_response["answer"]
    source = provider_response["source"]
    ref_sites = provider_response["refSites"]

    t1 = time.time()
    print(f"[TIMING] guardrails + LLM concurrently: {t1 - t0:.2f}s")

    if not safe_input:
        answer = SAFE_REFUSAL
        source = "guardrails (input)"
        ref_sites = []
    elif not is_safe_output(answer):
        answer = SAFE_REFUSAL
        source = "guardrails (output)"
        ref_sites = []

    audio = await text_to_speech(answer)
    t2 = time.time()
    print(f"[TIMING] TTS: {t2 - t1:.2f}s")
    print(f"[TIMING] TOTAL: {t2 - t0:.2f}s")
    print(f"The source of this information is {source}")
    print(f"add the actual response:{answer}")
    return {
        "transcript": transcript,
        "answer": answer,
        "provider": settings.llm_provider,
        "source": source,
        "refSites": ref_sites,
        "audio_base64": audio,
    }

@app.post("/ask-text")
async def ask_text(request: Request, text: Optional[str] = Form(None)):
    """
    Accepts both JSON {"text":"..."} and form field text=...
    This keeps Swagger and the existing React frontend working.
    """
    transcript = text
    content_type = request.headers.get("content-type", "")
    if transcript is None and "application/json" in content_type:
        try:
            body = await request.json()
            transcript = body.get("text", "") if isinstance(body, dict) else ""
        except Exception:
            transcript = ""
    return await _build_response(transcript or "")

@app.post("/voice")
async def voice(file: UploadFile = File(...)):
    import time
    t_upload = time.time()

    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        path = tmp.name

    t_stt_start = time.time()
    try:
        transcript = await speech_to_text(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    t_stt_end = time.time()
    print(f"[TIMING] file upload handling: {t_stt_start - t_upload:.2f}s")
    print(f"[TIMING] STT (faster-whisper): {t_stt_end - t_stt_start:.2f}s")

    return await _build_response(transcript)
