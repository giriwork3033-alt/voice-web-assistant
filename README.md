#Jarvis - Voice Web Assistant

A 2-day MVP voice assistant that accepts audio, uses AI tool-calling for live internet/weather data, applies safety guardrails, and speaks the answer back.

## Run backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# fill API keys
uvicorn app.main:app --reload --port 8000
```

## Run frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Required keys
- `OPENAI_API_KEY`: Whisper speech-to-text
- `GOOGLE_API_KEY`: Gemini tool-calling agent
- `OPENWEATHER_API_KEY`: live weather
- `ELEVENLABS_API_KEY`: spoken response
- `TAVILY_API_KEY`: optional general web search

## Architecture
Mic -> React MediaRecorder -> FastAPI -> Whisper STT -> Guardrails -> Gemini tool-calling -> Weather/Search tools -> Guardrails -> ElevenLabs TTS -> Browser audio.

## Notes
- Text mode is included for faster testing.
- If ElevenLabs key is missing, text still works but audio will be empty.
- If OpenAI key is missing, typed questions still work.
