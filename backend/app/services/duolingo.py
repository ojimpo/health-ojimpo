"""Duolingo public profile client (no auth required).

Duolingo exposes a public endpoint that returns a user's profile by username/ID:
  GET https://www.duolingo.com/2017-06-30/users?username=<name>&fields=users{totalXp,streak,...}
This needs no login — just the username (or numeric id). It does NOT expose
per-day history publicly (xpGains/calendar/timeLearning come back empty), so the
adapter tracks the daily totalXp snapshot and derives each day's gained XP as the
delta between snapshots. Duolingo exposes no study-time publicly, so XP is later
converted to approximate minutes (see config.duolingo_xp_per_minute).

Duolingo rejects the default httpx User-Agent, so we send a browser-like one.
"""
import logging

import httpx

logger = logging.getLogger(__name__)

DUOLINGO_USERS_API = "https://www.duolingo.com/2017-06-30/users"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def fetch_profile(user: str) -> dict | None:
    """Fetch public profile by username (numeric ids also resolve via this param).

    Returns {"id", "username", "total_xp", "streak"} or None if not found.
    """
    params = {
        "username": user,
        "fields": "users{id,username,name,totalXp,streak}",
    }
    headers = {"User-Agent": BROWSER_UA}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(DUOLINGO_USERS_API, params=params, headers=headers)
        resp.raise_for_status()
        users = resp.json().get("users") or []

    if not users:
        return None
    u = users[0]
    return {
        "id": u.get("id"),
        "username": u.get("username"),
        "name": u.get("name"),
        "total_xp": int(u.get("totalXp") or 0),
        "streak": int(u.get("streak") or 0),
    }
