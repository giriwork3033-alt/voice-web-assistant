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
#from .avatar_routes import router as avatar_router



app = FastAPI(title="Voice Web Assistant", version="1.0.0")
#app.include_router(avatar_router)

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
        return {"transcript": "", "answer": answer, "audio_base64": await text_to_speech(answer)}

    t0 = time.time()

    # Run the guardrails input check and the LLM call concurrently rather
    # than sequentially - they don't depend on each other's result until
    # AFTER both finish. This trades a small amount of extra API cost (the
    # LLM still runs even on requests that end up refused) for meaningfully
    # lower latency: total time becomes roughly max(guardrails, LLM)
    # instead of their sum.
    safe_input_task = asyncio.create_task(is_safe_input(transcript))
    answer_task = asyncio.create_task(answer_query(transcript))
    safe_input, answer = await asyncio.gather(safe_input_task, answer_task)

    t1 = time.time()
    print(f"[TIMING] guardrails + LLM concurrently: {t1 - t0:.2f}s")

    if not safe_input:
        answer = SAFE_REFUSAL
    elif not is_safe_output(answer):
        answer = SAFE_REFUSAL

    audio = await text_to_speech(answer)
    t2 = time.time()
    print(f"[TIMING] TTS: {t2 - t1:.2f}s")
    print(f"[TIMING] TOTAL: {t2 - t0:.2f}s")

    return {"transcript": transcript, "answer": answer, "audio_base64": audio}

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
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    try:
        transcript = await speech_to_text(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return await _build_response(transcript)
