from __future__ import annotations

from .llm import get_llm_provider

async def answer_query(user_text: str) -> str:
    """Send every query to the selected LLM. The LLM decides whether to answer directly or call tools."""
    try:
        provider = get_llm_provider()
        return await provider.answer(user_text)
    except Exception as e:
        return f"Backend LLM error: {type(e).__name__}: {str(e)}"
