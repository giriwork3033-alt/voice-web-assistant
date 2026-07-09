# Jarvis — Voice Web Assistant

A voice-in, voice-out AI assistant: record a question (or type one), it decides for itself
whether it needs to call a live tool to answer, applies layered safety guardrails, and speaks
the answer back — with an optional real-time speaking avatar on top.

## Architecture

```
Mic / typed text
  -> React frontend (MediaRecorder + fetch)
  -> FastAPI backend
  -> faster-whisper (local speech-to-text, voice input only)
  -> Guardrails: keyword backstop -> safety-classification model (input)
  -> LLM provider (Groq / OpenAI / Gemini, swappable) with native tool calling
       -> Open-Meteo (live weather) and/or DDGS (live web search), only when the
          model itself decides live data is needed - never hardcoded routing
  -> Guardrails: keyword backstop (output) + in-band refusal in the system prompt
  -> Edge-TTS (text-to-speech)
  -> Browser plays the audio
       -> optionally: illustrated SVG avatar (always on) or the experimental
          HeyGen LiveAvatar photorealistic avatar (see Avatar section below)
```

## Run backend

```bash
cd Jarvis
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows. macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# create backend/.env (see "Required keys" below) - never commit this file
cd ..
uvicorn backend.app.main:app --reload
```

Run uvicorn from the `Jarvis` project root (not from inside `backend`) — the app is imported
as the `backend.app` package. Swagger UI is at `http://127.0.0.1:8000/docs`.

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Required keys (`backend/.env`)

Core, needed for the assistant itself:
- `LLM_PROVIDER` — `groq` (default/primary), `openai`, or `gemini`. Swappable with no code changes.
- `GROQ_API_KEY` / `GROQ_MODEL` — used when `LLM_PROVIDER=groq`. Free tier, fast inference, chosen as primary.
- `OPENAI_API_KEY` / `OPENAI_MODEL` — used when `LLM_PROVIDER=openai`.
- `GOOGLE_API_KEY` / `GEMINI_MODEL` — used when `LLM_PROVIDER=gemini`.
- `ALLOWED_ORIGINS` — CORS origins for the frontend (defaults to `http://localhost:5173`).
- `WHISPER_MODEL_SIZE` — faster-whisper model size (e.g. `base`). Local, free, no key needed.
- `EDGE_TTS_VOICE` — voice name for Edge-TTS. Local/free, no key needed.

No key needed at all for weather (Open-Meteo) or search (DDGS) — both are free, public APIs.

Optional, only for the experimental photorealistic avatar (see below):
- `LIVEAVATAR_API_KEY` / `LIVEAVATAR_AVATAR_ID` — from app.liveavatar.com.

## Guardrails

Three layers, in order:
1. **Keyword/regex backstop** on user input — zero latency, zero cost, catches blunt cases and
   is the fallback if the layer below is unreachable.
2. **Dedicated safety-classification model** (`openai/gpt-oss-safeguard-20b` on Groq) checked on
   user input only — catches rephrasing/typos a keyword list would miss, without adding a second
   model call on every response.
3. **In-band refusal instruction** in the main LLM's own system prompt, as a second line of
   defense on output, plus a fast keyword check on the assistant's own answer before it's spoken.

## Avatar

Two tiers, both real and working, not just described:

- **Illustrated avatar (`TalkingAvatar.jsx`)** — always on, zero added latency. An SVG face whose
  mouth opens and closes in real time from a Web Audio API AnalyserNode reading the actual TTS
  audio's live amplitude as it plays. Blinks on a randomized timer.
- **LiveAvatar (`LiveAvatarPanel.jsx`, `avatar_liveavatar.py`, `avatar_routes.py`) — experimental.**
  A real, working integration with HeyGen's LiveAvatar API for a photorealistic, real-time
  speaking avatar streamed over WebRTC. Verified live end-to-end (session connects, correct
  lip-sync event lifecycle, zero errors) with proper MP3->PCM16 audio conversion. Requires its
  own API key/credits and is additive — the illustrated avatar keeps working regardless of
  whether this does. See code comments in `avatar_liveavatar.py` for the current known caveats
  around the vendor's free-tier session limits.

## Notes

- Text mode (`/ask-text`) works independently of voice and is faster for testing.
- One retry with backoff on transient LLM API failures; failures still surface, they aren't
  silently swallowed.
- The LLM provider client is cached and reused across requests rather than rebuilt per call.
- `backend/.env` is git-ignored — never commit real API keys.
