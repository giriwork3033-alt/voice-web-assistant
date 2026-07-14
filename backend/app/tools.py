from __future__ import annotations

import asyncio
import os
import time

import httpx
from ddgs import DDGS


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

HTTP_HEADERS = {
    "User-Agent": "voice-web-assistant/1.0",
    "Accept": "application/json",
}

_WEATHER_CACHE_TTL = 300       # 5 minutes
_LOCATION_CACHE_TTL = 86_400   # 24 hours

_weather_cache: dict[str, tuple[str, float]] = {}
_location_cache: dict[str, tuple[float, float, str, float]] = {}


# -------------------------------------------------------------------
# Open-Meteo geocoding
# -------------------------------------------------------------------

async def _geocode_city(city: str) -> tuple[float, float, str] | None:
    cache_key = city.lower().strip()

    cached = _location_cache.get(cache_key)

    if cached:
        lat, lon, label, cached_time = cached

        if time.time() - cached_time < _LOCATION_CACHE_TTL:
            print(f"[TOOL] Location cache hit for '{city}'")
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


# -------------------------------------------------------------------
# Primary provider: Open-Meteo
# -------------------------------------------------------------------

async def _get_weather_open_meteo(city: str) -> str | None:
    """
    Return weather text on success.

    Return None when Open-Meteo is unavailable, rate-limited,
    or fails, so WeatherAPI can be used as fallback.
    """

    try:
       if not location:
        print(f"[TOOL] Open-Meteo could not geocode '{city}'")
        return None

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

        async with httpx.AsyncClient(
            timeout=12,
            headers=HTTP_HEADERS,
        ) as client:
            response = await client.get(url, params=params)

        if response.status_code == 429:
            print(
                "[TOOL] Open-Meteo rate limited. "
                f"Response: {response.text}"
            )
            return None

        if response.status_code >= 500:
            print(
                f"[TOOL] Open-Meteo server error "
                f"{response.status_code}: {response.text}"
            )
            return None

        response.raise_for_status()

        current = response.json().get("current")

        if not current:
            print("[TOOL] Open-Meteo returned no current weather data")
            return None

        return (
            f"Current weather in {label}: "
            f"temperature {current.get('temperature_2m')}°C, "
            f"feels like {current.get('apparent_temperature')}°C, "
            f"humidity {current.get('relative_humidity_2m')}%, "
            f"wind speed {current.get('wind_speed_10m')} km/h."
        )

    except httpx.TimeoutException:
        print("[TOOL] Open-Meteo request timed out")
        return None

    except httpx.HTTPError as error:
        print(f"[TOOL] Open-Meteo HTTP error: {error}")
        return None

    except Exception as error:
        print(
            f"[TOOL] Open-Meteo unexpected error: "
            f"{type(error).__name__}: {error}"
        )
        return None


# -------------------------------------------------------------------
# Secondary provider: WeatherAPI
# -------------------------------------------------------------------

async def _get_weather_weatherapi(city: str) -> str | None:
    if not WEATHER_API_KEY:
        print("[TOOL] WEATHER_API_KEY is missing")
        return None

    url = "https://api.weatherapi.com/v1/current.json"

    params = {
        "key": WEATHER_API_KEY,
        "q": city,
        "aqi": "no",
    }

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url, params=params)

        if response.status_code == 400:
            print(f"[TOOL] WeatherAPI invalid location: {response.text}")
            return f"Could not find weather information for {city}."

        if response.status_code in (401, 403):
            print(f"[TOOL] WeatherAPI key error: {response.text}")
            return None

        if response.status_code == 429:
            print(f"[TOOL] WeatherAPI quota exceeded: {response.text}")
            return None

        if response.status_code >= 500:
            print(
                f"[TOOL] WeatherAPI server error "
                f"{response.status_code}: {response.text}"
            )
            return None

        response.raise_for_status()

        data = response.json()
        location = data.get("location", {})
        current = data.get("current", {})

        if not current:
            print("[TOOL] WeatherAPI returned no current weather data")
            return None

        label = ", ".join(
            value
            for value in [
                location.get("name"),
                location.get("region"),
                location.get("country"),
            ]
            if value
        )

        condition = (
            current.get("condition", {}).get("text")
            or "unknown conditions"
        )

        return (
            f"Current weather in {label}: "
            f"{condition}, "
            f"temperature {current.get('temp_c')}°C, "
            f"feels like {current.get('feelslike_c')}°C, "
            f"humidity {current.get('humidity')}%, "
            f"wind speed {current.get('wind_kph')} km/h."
        )

    except httpx.TimeoutException:
        print("[TOOL] WeatherAPI request timed out")
        return None

    except httpx.HTTPError as error:
        print(f"[TOOL] WeatherAPI HTTP error: {error}")
        return None

    except Exception as error:
        print(
            f"[TOOL] WeatherAPI unexpected error: "
            f"{type(error).__name__}: {error}"
        )
        return None


# -------------------------------------------------------------------
# Public weather tool
# -------------------------------------------------------------------

async def get_weather(city: str) -> str:
    city = (city or "").strip()

    if not city:
        return "City was not provided."

    cache_key = city.lower()

    cached = _weather_cache.get(cache_key)

    if cached:
        result, cached_time = cached

        if time.time() - cached_time < _WEATHER_CACHE_TTL:
            print(f"[TOOL] Weather cache hit for '{city}'")
            return result

        _weather_cache.pop(cache_key, None)

    print(f"[TOOL] Trying Open-Meteo for '{city}'")

    result = await _get_weather_open_meteo(city)

    if result is None:
        print(f"[TOOL] Falling back to WeatherAPI for '{city}'")
        result = await _get_weather_weatherapi(city)

    if result is None:
        return (
            "Both weather providers are temporarily unavailable. "
            "Please try again shortly."
        )

    _weather_cache[cache_key] = (
        result,
        time.time(),
    )

    return result


# -------------------------------------------------------------------
# Web search tool
# -------------------------------------------------------------------

async def web_search(query: str) -> str:
    query = (query or "").strip()

    if not query:
        return "Search query was empty."

    try:
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

        return "\n".join(rows) if rows else "No useful search results found."

    except Exception as error:
        print(
            f"[TOOL ERROR] Web search failed: "
            f"{type(error).__name__}: {error}"
        )
        return "Search is temporarily unavailable."


# -------------------------------------------------------------------
# Tool schemas
# -------------------------------------------------------------------

TOOL_SCHEMAS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current live weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, for example New Delhi",
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


# -------------------------------------------------------------------
# Tool runner
# -------------------------------------------------------------------

async def run_tool(name: str, args: dict) -> str:
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