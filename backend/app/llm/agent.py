from __future__ import annotations

from .llm import get_llm_provider

async def answer_query(user_text: str) -> tuple[str, str]:
    """Send every query to the selected LLM. Returns (answer_text, source)
    where source describes where the answer came from - general knowledge,
    a specific tool, or an error/fallback path."""
    try:
        provider = get_llm_provider()
        return await provider.answer(user_text), provider
    except Exception as e:
        error_str = str(e).lower()
        if "failed to call a function" in error_str or "tool_use_failed" in error_str:
            print(f"[LLM] tool call failed ({type(e).__name__}), retrying without tools")
            try:
                provider = get_llm_provider()
                return await provider.answer_without_tools(user_text), provider
            except Exception:
                pass
        print(f"[LLM] unrecoverable error: {type(e).__name__}: {e}")
        return "Sorry, something went wrong on my end. Please try again.", "error"