from __future__ import annotations

import asyncio
import json
from openai import AsyncOpenAI
from .base import LLMProvider, SYSTEM_PROMPT
from ..tools import TOOL_SCHEMAS_OPENAI, run_tool

RETRY_ATTEMPTS = 2
RETRY_BASE_DELAY = 0.6  # seconds


async def _with_retries(coro_factory):
    """
    Retry a transient API failure once with a short backoff. Only retries
    - the final exception is always re-raised if every attempt fails, so
    real errors (bad API key, model not found, etc.) still surface instead
    of being silently swallowed.
    """
    last_exc: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await coro_factory()
        except Exception as e:  # noqa: BLE001 - intentionally broad, we re-raise
            last_exc = e
            if attempt < RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (attempt + 1))
    assert last_exc is not None
    raise last_exc


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        if not api_key:
            raise ValueError("Missing API key for selected LLM provider.")
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def answer(self, user_text: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        first = await _with_retries(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOL_SCHEMAS_OPENAI,
            tool_choice="auto",
            temperature=0.2,
        ))
        msg = first.choices[0].message

        if not msg.tool_calls:
            print("[LLM] answered directly, no tool call")
            return (msg.content or "I could not generate a response.").strip()

        print(f"[LLM] requested {len(msg.tool_calls)} tool call(s): "
              f"{[tc.function.name for tc in msg.tool_calls]}")

        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await run_tool(tc.function.name, args)
            print(f"[TOOL RESULT] {tc.function.name} -> {str(result)[:150]}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        final = await _with_retries(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        ))
        return (final.choices[0].message.content or "I could not generate a response.").strip()

    async def answer_without_tools(self, user_text: str) -> str:
        """Fallback: answer without any tool definitions, forcing the model
        to respond directly. Used when the normal tool-calling path fails
        due to a malformed tool-call generation on the API side."""
        print("[LLM] answering without tools (fallback)")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        resp = await _with_retries(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        ))
        return (resp.choices[0].message.content or "I could not generate a response.").strip()
