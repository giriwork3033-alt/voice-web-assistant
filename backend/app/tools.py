from __future__ import annotations

import httpx
from ddgs import DDGS

async def _geocode_city(city: str) -> tuple[float, float, str] | None:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city, "count": 1, "language": "en", "format": "json"}
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        return None
    item = results[0]
    name = ", ".join([x for x in [item.get("name"), item.get("admin1"), item.get("country")] if x])
    return float(item["latitude"]), float(item["longitude"]), name

async def get_weather(city: str) -> str:
    """Get current weather using free Open-Meteo. No API key needed."""
    city = (city or "").strip()
    if not city:
        return "City was not provided."
    loc = await _geocode_city(city)
    if not loc:
        return f"Could not find weather location for {city}."
    lat, lon, label = loc
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
    cur = r.json().get("current", {})
    return (
        f"Current weather in {label}: temperature {cur.get('temperature_2m')}°C, "
        f"feels like {cur.get('apparent_temperature')}°C, humidity {cur.get('relative_humidity_2m')}%, "
        f"wind speed {cur.get('wind_speed_10m')} km/h."
    )

async def web_search(query: str) -> str:
    """Search public web using DuckDuckGo. No API key needed."""
    query = (query or "").strip()
    if not query:
        return "Search query was empty."
    try:
        # DDGS is sync; keep max small for low latency.
        results = DDGS().text(query, max_results=3)
        rows = []
        for r in results:
            title = r.get("title", "Untitled")
            body = r.get("body", "")
            href = r.get("href", "")
            rows.append(f"{title}: {body} Source: {href}")
        return "\n".join(rows) if rows else "No useful search results found."
    except Exception as e:
        return f"Search failed: {type(e).__name__}."

TOOL_SCHEMAS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city using live weather data.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current or public information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
]

async def run_tool(name: str, args: dict) -> str:
    print(f"[TOOL CALL] {name}({args})")
    if name == "get_weather":
        result = await get_weather(args.get("city", ""))
    elif name == "web_search":
        result = await web_search(args.get("query", ""))
    else:
        result = f"Unknown tool: {name}"
    print(f"[TOOL RESULT] {name} -> {result[:200]}")
    return result
