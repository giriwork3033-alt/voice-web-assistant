from __future__ import annotations

from .llm import get_llm_provider
from .llm.base import ProviderResponse


def _normalize_response(response: object) -> ProviderResponse:
    """Normalize legacy string/tuple providers to the structured response."""
    if isinstance(response, dict):
        return {
            "answer": str(response.get("answer", "I could not generate a response.")),
            "source": str(response.get("source", "general knowledge")),
            "refSites": response.get("refSites", []),
        }

    if isinstance(response, tuple) and len(response) >= 2:
        return {
            "answer": str(response[0]),
            "source": str(response[1]),
            "refSites": [],
        }

    return {
        "answer": str(response),
        "source": "general knowledge",
        "refSites": [],
    }


async def answer_query(user_text: str) -> ProviderResponse:
    """Send a query to the selected LLM and normalize its response."""
    try:
        provider = get_llm_provider()
        return _normalize_response(await provider.answer(user_text))
    except Exception as e:
        error_str = str(e).lower()
        if "failed to call a function" in error_str or "tool_use_failed" in error_str:
            print(f"[LLM] tool call failed ({type(e).__name__}), retrying without tools")
            try:
                provider = get_llm_provider()
                return _normalize_response(await provider.answer_without_tools(user_text))
            except Exception:
                pass
        print(f"[LLM] unrecoverable error: {type(e).__name__}: {e}")
        return {
            "answer": "Sorry, something went wrong on my end. Please try again.",
            "source": "error",
            "refSites": [],
        }
