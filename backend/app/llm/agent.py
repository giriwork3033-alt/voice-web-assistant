from __future__ import annotations

from .llm import get_llm_provider

async def answer_query(user_text: str) -> str:
    """Send every query to the selected LLM. The LLM decides whether to answer directly or call tools."""
    try:
        provider = get_llm_provider()
        return await provider.answer(user_text)
    except Exception as e:
        error_str = str(e).lower()
        # Groq sometimes generates malformed tool-call XML instead of
        # valid JSON, causing a 400 "Failed to call a function" error.
        # Rather than showing raw error text to the user, retry once
        # without tools so the model answers directly.
        if "failed to call a function" in error_str or "tool_use_failed" in error_str:
            print(f"[LLM] tool call failed ({type(e).__name__}), retrying without tools")
            try:
                provider = get_llm_provider()
                return await provider.answer_without_tools(user_text)
            except Exception:
                pass
        print(f"[LLM] unrecoverable error: {type(e).__name__}: {e}")
        return "Sorry, something went wrong on my end. Please try again."
