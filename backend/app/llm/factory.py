from __future__ import annotations

from .base import LLMProvider
from ..config import settings

def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider

    if provider == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(settings.google_api_key, settings.gemini_model)

    if provider == "groq":
        from .openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url="https://api.groq.com/openai/v1",
        )

    if provider == "openai":
        from .openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}. Use gemini, groq, or openai.")
