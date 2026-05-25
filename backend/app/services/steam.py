import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_STORE_API_BASE = "https://store.steampowered.com/api"


async def fetch_recently_played() -> list[dict]:
    """Fetch games played in last 2 weeks.

    Returns list of dicts: {appid, name, playtime_forever (minutes), playtime_2weeks (minutes)}
    """
    url = f"{STEAM_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v1/"
    params = {
        "key": settings.steam_api_key,
        "steamid": settings.steam_id64,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    games = data.get("response", {}).get("games", [])
    return [
        {
            "appid": g["appid"],
            "name": g.get("name", f"appid:{g['appid']}"),
            "playtime_forever": int(g.get("playtime_forever", 0)),
            "playtime_2weeks": int(g.get("playtime_2weeks", 0)),
        }
        for g in games
    ]


async def fetch_release_date(appid: int) -> str | None:
    """Fetch a game's release date from the Steam Store API.

    Returns ISO date string "YYYY-MM-DD" or None if not parseable.
    The store API returns localized strings like "2026年5月18日"; we attempt
    multiple formats and fall back to None on failure.
    """
    url = f"{STEAM_STORE_API_BASE}/appdetails"
    params = {"appids": appid, "filters": "release_date", "cc": "jp", "l": "japanese"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Steam Store API failed for appid=%s", appid)
        return None

    entry = data.get(str(appid), {})
    if not entry.get("success"):
        return None
    rd = entry.get("data", {}).get("release_date", {})
    if rd.get("coming_soon"):
        return None
    raw = rd.get("date", "")
    return _parse_release_date(raw)


def _parse_release_date(raw: str) -> str | None:
    """Convert Steam release_date string to ISO YYYY-MM-DD.

    Handles formats like "2026年5月18日", "May 18, 2026", "18 May, 2026".
    """
    import re
    from datetime import datetime

    if not raw:
        return None

    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    for fmt in ("%b %d, %Y", "%d %b, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None
