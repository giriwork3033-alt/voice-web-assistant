from __future__ import annotations

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from .base import LLMProvider, SYSTEM_PROMPT
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

    async def answer(self, user_text: str) -> str:
        try:
            first = self.client.models.generate_content(
                model=self.model,
                contents=user_text,
                config=self.config,
            )
        except ClientError as e:
            return f"LLM provider error: {e.status_code}. Quota or API issue. Try another provider like Groq."

        calls = []
        try:
            for part in first.candidates[0].content.parts:
                if getattr(part, "function_call", None):
                    calls.append(part.function_call)
        except Exception:
            calls = []

        if not calls:
            return (first.text or "I could not generate a response.").strip()

        tool_parts = []
        for call in calls:
            result = await run_tool(call.name, dict(call.args or {}))
            tool_parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))

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
            return (final.text or "I could not generate a response.").strip()
        except ClientError as e:
            return f"LLM provider error: {e.status_code}. Tool ran, but final response failed."
