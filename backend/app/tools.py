from __future__ import annotations

import asyncio
import time

import httpx
from ddgs import DDGS


# Weather cache: city -> (result, timestamp)
_weather_cache: dict[str, tuple[str, float]] = {}

# Geocoding cache: city -> (latitude, longitude, label, timestamp)
_location_cache: dict[str, tuple[float, float, str, float]] = {}

_CACHE_TTL = 300  # 5 minutes
_LOCATION_CACHE_TTL = 86_400  # 24 hours

HTTP_HEADERS = {
    "User-Agent": "voice-web-assistant/1.0",
    "Accept": "application/json",
}


async def _geocode_city(city: str) -> tuple[float, float, str] | None:
    """Convert a city name into latitude and longitude."""

    cache_key = city.lower().strip()

    # Check location cache
    cached = _location_cache.get(cache_key)
    if cached:
        lat, lon, label, cached_time = cached

        if time.time() - cached_time < _LOCATION_CACHE_TTL:
            print(f"[TOOL] location cache hit for '{city}'")
            return lat, lon, label

        _location_cache.pop(cache_key, None)

    url = "https://geocoding-api.open-meteo.com/v1/search"

    params = {
        "name": city,
        "count": 1,
        "language": "en",
        "format": "json",
    }

    async with httpx.AsyncClient(
        timeout=12,
        headers=HTTP_HEADERS,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()

    results = response.json().get("results") or []

    if not results:
        return None

    item = results[0]

    label = ", ".join(
        value
        for value in [
            item.get("name"),
            item.get("admin1"),
            item.get("country"),
        ]
        if value
    )

    lat = float(item["latitude"])
    lon = float(item["longitude"])

    _location_cache[cache_key] = (
        lat,
        lon,
        label,
        time.time(),
    )

    return lat, lon, label


async def get_weather(city: str) -> str:
    """Get current weather using Open-Meteo."""

    city = (city or "").strip()

    if not city:
        return "City was not provided."

    cache_key = city.lower()

    # Check weather cache
    cached = _weather_cache.get(cache_key)

    if cached:
        cached_result, cached_time = cached

        if time.time() - cached_time < _CACHE_TTL:
            print(f"[TOOL] weather cache hit for '{city}'")
            return cached_result

        _weather_cache.pop(cache_key, None)

    try:
        location = await _geocode_city(city)
    except httpx.HTTPStatusError as error:
        print(
            f"[TOOL ERROR] Geocoding HTTP error: "
            f"{error.response.status_code} {error.response.text}"
        )
        return "The location service is temporarily unavailable."
    except httpx.HTTPError as error:
        print(f"[TOOL ERROR] Geocoding connection error: {error}")
        return "The location service is temporarily unavailable."

    if not location:
        return f"Could not find weather location for {city}."

    lat, lon, label = location

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "wind_speed_10m,"
            "weather_code"
        ),
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(
            timeout=12,
            headers=HTTP_HEADERS,
        ) as client:

            for attempt in range(3):
                response = await client.get(url, params=params)

                if response.status_code == 429:
                    print(
                        f"[TOOL] Open-Meteo returned 429. "
                        f"Response: {response.text}"
                    )

                    # Do not sleep after the final attempt
                    if attempt == 2:
                        break

                    retry_after = response.headers.get("Retry-After")

                    try:
                        wait_seconds = (
                            int(retry_after)
                            if retry_after
                            else 5 * (2**attempt)
                        )
                    except ValueError:
                        wait_seconds = 5 * (2**attempt)

                    print(
                        f"[TOOL] Retrying in {wait_seconds}s "
                        f"(attempt {attempt + 1}/3)"
                    )

                    await asyncio.sleep(wait_seconds)
                    continue

                response.raise_for_status()

                data = response.json()
                current = data.get("current")

                if not current:
                    return "Weather data was unavailable for that location."

                temperature = current.get("temperature_2m")
                feels_like = current.get("apparent_temperature")
                humidity = current.get("relative_humidity_2m")
                wind_speed = current.get("wind_speed_10m")

                result = (
                    f"Current weather in {label}: "
                    f"temperature {temperature}°C, "
                    f"feels like {feels_like}°C, "
                    f"humidity {humidity}%, "
                    f"wind speed {wind_speed} km/h."
                )

                _weather_cache[cache_key] = (
                    result,
                    time.time(),
                )

                return result

    except httpx.HTTPStatusError as error:
        print(
            f"[TOOL ERROR] Weather HTTP error: "
            f"{error.response.status_code} {error.response.text}"
        )
        return "The weather service is temporarily unavailable."

    except httpx.TimeoutException:
        print("[TOOL ERROR] Weather request timed out.")
        return "The weather service timed out. Please try again."

    except httpx.HTTPError as error:
        print(f"[TOOL ERROR] Weather connection error: {error}")
        return "The weather service is temporarily unavailable."

    return (
        "The weather provider is currently rate-limiting requests. "
        "Please try again later."
    )


async def web_search(query: str) -> str:
    """Search the public web using DuckDuckGo."""

    query = (query or "").strip()

    if not query:
        return "Search query was empty."

    try:
        # DDGS is synchronous, so run it outside the async event loop.
        results = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=3))
        )

        rows = []

        for result in results:
            title = result.get("title", "Untitled")
            body = result.get("body", "")
            href = result.get("href", "")

            rows.append(
                f"{title}: {body} Source: {href}"
            )

        if not rows:
            return "No useful search results found."

        return "\n".join(rows)

    except Exception as error:
        print(
            f"[TOOL ERROR] Web search failed: "
            f"{type(error).__name__}: {error}"
        )
        return "Search is temporarily unavailable."


TOOL_SCHEMAS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get the current live weather for a city."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, for example Delhi",
                    }
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for current or public information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The web search query",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


async def run_tool(name: str, args: dict) -> str:
    """Execute a tool and return a clean result to the LLM."""

    print(f"[TOOL CALL] {name}({args})")

    try:
        if name == "get_weather":
            result = await get_weather(
                str(args.get("city", ""))
            )

        elif name == "web_search":
            result = await web_search(
                str(args.get("query", ""))
            )

        else:
            result = f"Unknown tool: {name}"

        print(f"[TOOL RESULT] {name} -> {result[:200]}")

        return result

    except Exception as error:
        print(
            f"[TOOL ERROR] {name} failed: "
            f"{type(error).__name__}: {error}"
        )

        return (
            f"The {name} service is temporarily unavailable. "
            "Please try again shortly."
        )