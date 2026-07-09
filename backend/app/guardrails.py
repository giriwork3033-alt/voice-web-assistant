from __future__ import annotations

"""
Guardrails, in two layers:

1. Fast keyword/pattern backstop (`_keyword_flag`) - zero latency, zero cost,
   runs even if there's no network or no GROQ_API_KEY. Catches the bluntest,
   most blatant cases and is the fallback if layer 2 is unreachable.

2. Dedicated safety-classification model (`_classify_with_safeguard`) - uses
   Groq's openai/gpt-oss-safeguard-20b, a model purpose-built for policy
   classification, instead of a keyword list or the main chat model judging
   its own safety. This is what actually catches rephrasing, typos, and
   indirect phrasing the keyword layer would miss.

Only user INPUT goes through both layers. The assistant's OUTPUT only goes
through the fast keyword layer - not a second safeguard-model call - because
the main LLM's system prompt (see llm.py) already instructs it to refuse
unsafe requests itself. That keeps guardrails to one extra network round
trip per request instead of two, which matters for a voice assistant where
every extra call is audible latency.

Design tradeoff worth calling out explicitly: if the safeguard model can't
be reached (network issue, quota, bad response), we fall back to the
keyword layer's verdict rather than blocking every request - fail-open on
infra problems, not fail-open on safety. If you'd rather fail closed
(refuse everything when the classifier is down), flip the `return True` in
`is_safe_input`'s fallback branch to `return False`.
"""

import json
import re

from .config import settings

SAFE_REFUSAL = "Sorry, I can't help with that request."

# ---------------------------------------------------------------------------
# Layer 1: fast keyword/pattern backstop
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS = [
    r"\bhow (?:do|can) i (?:make|build|construct) a bomb\b",
    r"\bmake a bomb\b",
    r"\bbuild a bomb\b",
    r"\bmolotov\b",
    r"\bkill (?:myself|him|her|them)\b",
    r"\bsuicide (?:method|instructions)\b",
    r"\bhow to hack\b",
    r"\bsteal (?:a |someone'?s )?credit card\b",
    r"\bchild (?:porn|sexual abuse)\b",
    r"\brape\b",
    r"\bterroris[tm]\b",
    r"\bschool shooting\b",
    r"\bhow to synthesi[sz]e (?:meth|fentanyl)\b",
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)


def _keyword_flag(text: str) -> bool:
    """True if text trips the fast pattern backstop."""
    if not text or not text.strip():
        return False
    return bool(_BLOCKED_RE.search(text))


# ---------------------------------------------------------------------------
# Layer 2: dedicated safety-classification model (input only)
# ---------------------------------------------------------------------------

_SAFEGUARD_MODEL = "openai/gpt-oss-safeguard-20b"

_SAFETY_POLICY = """You are a strict content-safety classifier for a public-facing voice assistant.

Classify USER_INPUT as a violation if it does any of the following:
- Requests instructions to build or use weapons, explosives, or tools intended to cause mass harm.
- Requests methods, encouragement, or instructions for suicide or self-harm.
- Requests, describes, or references child sexual abuse material in any form, or sexual content involving minors.
- Requests instructions to commit violent crimes (e.g. terrorism) against people.
- Contains hate speech advocating violence or discrimination against a protected group.
- Requests help committing fraud, hacking, or other clearly illegal acts against a specific victim.

General knowledge questions - including about history, science, weather, current events, or even
sensitive topics discussed factually and without operational intent - are NOT violations.

Respond with ONLY a JSON object and nothing else:
{"violation": 0 or 1, "category": "<short category or null>", "rationale": "<one short sentence>"}

USER_INPUT: {input}
"""


async def _classify_with_safeguard(text: str) -> bool | None:
    """
    Returns True if flagged unsafe, False if judged safe, or None if the
    classifier couldn't be reached (no key, network error, bad response),
    so the caller can fall back to the keyword layer instead of blocking
    everything on an infra hiccup.
    """
    if not settings.groq_api_key:
        return None
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await client.chat.completions.create(
            model=_SAFEGUARD_MODEL,
            messages=[{"role": "user", "content": _SAFETY_POLICY.replace("{input}", text)}],
            temperature=0,
        )
        content = (resp.choices[0].message.content or "").strip()
        # The model should return bare JSON, but extract defensively in case
        # it wraps the object in prose or a code fence despite instructions.
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        return bool(data.get("violation"))
    except Exception as e:
        print(f"Safety classifier unavailable, falling back to keyword filter: {type(e).__name__}: {e}")
        return None


async def is_safe_input(text: str) -> bool:
    """Full check for user input: keyword layer, then the safeguard model."""
    if not text or not text.strip():
        return True
    if _keyword_flag(text):
        return False
    verdict = await _classify_with_safeguard(text)
    if verdict is None:
        # Classifier unreachable, and the keyword layer above already
        # passed this text - let it through rather than refusing every
        # request just because the classifier had an outage.
        return True
    return not verdict


def is_safe_output(text: str) -> bool:
    """
    Fast, no-network check for the assistant's own answer before it's
    spoken. Deliberately does not call the safeguard model again - see
    module docstring for why. This is a backstop against a tool result or
    a jailbroken completion slipping something through, not the primary
    defense (the system prompt + is_safe_input are).
    """
    return not _keyword_flag(text)
