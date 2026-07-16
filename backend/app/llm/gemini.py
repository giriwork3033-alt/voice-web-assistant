from __future__ import annotations

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from .base import LLMProvider, ProviderResponse, RefSite, SYSTEM_PROMPT
from ..tools import run_tool

weather_decl = types.FunctionDeclaration(
    name="get_weather",
    description="Get current weather for a city using live weather data.",
    parameters={
        "type": "OBJECT",
        "properties": {"city": {"type": "STRING", "description": "City name"}},
        "required": ["city"],
    },
)

search_decl = types.FunctionDeclaration(
    name="web_search",
    description="Search the internet for current or public information.",
    parameters={
        "type": "OBJECT",
        "properties": {"query": {"type": "STRING", "description": "Search query"}},
        "required": ["query"],
    },
)

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError("Missing GOOGLE_API_KEY.")
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=[weather_decl, search_decl])],
            temperature=0.2,
        )

    async def answer(self, user_text: str) -> ProviderResponse:
        try:
            first = self.client.models.generate_content(
                model=self.model,
                contents=user_text,
                config=self.config,
            )
        except ClientError as e:
            return {
                "answer": f"LLM provider error: {e.status_code}. Quota or API issue. Try another provider like Groq.",
                "source": "error",
                "refSites": [],
            }

        calls = []
        try:
            for part in first.candidates[0].content.parts:
                if getattr(part, "function_call", None):
                    calls.append(part.function_call)
        except Exception:
            calls = []

        if not calls:
            return {
                "answer": (first.text or "I could not generate a response.").strip(),
                "source": "general knowledge",
                "refSites": [],
            }

        tool_parts = []
        tool_names: list[str] = []
        ref_sites: list[RefSite] = []
        for call in calls:
            result = await run_tool(call.name, dict(call.args or {}))
            tool_names.append(call.name)
            if isinstance(result, dict):
                tool_context = result["context"]
                ref_sites.extend(result["sources"])
            else:
                tool_context = result
            tool_parts.append(types.Part.from_function_response(name=call.name, response={"result": tool_context}))

        try:
            final = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(role="user", parts=[types.Part.from_text(text=user_text)]),
                    first.candidates[0].content,
                    types.Content(role="tool", parts=tool_parts),
                ],
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.2),
            )
            return {
                "answer": (final.text or "I could not generate a response.").strip(),
                "source": ", ".join(tool_names),
                "refSites": ref_sites,
            }
        except ClientError as e:
            return {
                "answer": f"LLM provider error: {e.status_code}. Tool ran, but final response failed.",
                "source": ", ".join(tool_names),
                "refSites": ref_sites,
            }
