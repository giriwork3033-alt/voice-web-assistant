from __future__ import annotations

"""
Anam AI avatar integration routes.
Creates session tokens server-side so the API key never reaches the browser.
"""

import os
import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/anam", tags=["anam-avatar"])

ANAM_API_KEY = os.getenv("ANAM_API_KEY", "")
ANAM_API_URL = "https://api.anam.ai/v1/auth/session-token"

# Default stock avatar — replace with any avatar ID from your Anam dashboard
DEFAULT_AVATAR_ID = "30fa96d0-26c4-4e55-94a0-517025942e18"
DEFAULT_VOICE_ID = "6bfbe25a-979d-40f3-a92b-5394170af54b"


@router.post("/session-token")
async def anam_session_token():
    """Exchange our server-side API key for a short-lived Anam session token.
    The frontend uses this token to initialize the Anam SDK without ever
    seeing the real API key."""
    if not ANAM_API_KEY:
        return {"error": "ANAM_API_KEY is not set on the server."}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                ANAM_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ANAM_API_KEY}",
                },
                json={
                    "personaConfig": {
                        "name": "Assistant",
                        "avatarId": os.getenv("ANAM_AVATAR_ID", DEFAULT_AVATAR_ID),
                        "voiceId": os.getenv("ANAM_VOICE_ID", DEFAULT_VOICE_ID),
                        # CUSTOM brain type = Anam handles avatar rendering only,
                        # we handle LLM/tools/guardrails ourselves
                        "brainType": "CUSTOM",
                    }
                },
            )
            resp.raise_for_status()
            data = resp.json()
            print(f"[Anam] session token created successfully")
            return {"sessionToken": data.get("sessionToken")}
    except Exception as e:
        print(f"[Anam] session token error: {type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}"}
