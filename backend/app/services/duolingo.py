"""Duolingo (unofficial) API client.

Duolingo has no official public API. We use the same JSON endpoint the web app
uses: GET /2017-06-30/users/{user_id}/xp_summaries — it returns per-day XP,
session counts, and (usually) totalSessionTime in seconds, which we convert to
study minutes.

Auth: a Bearer JWT taken from the browser's `jwt_token` cookie. The numeric
user id can be supplied explicitly or decoded from the JWT's `sub` claim.
Duolingo rejects the default httpx User-Agent, so we send a browser-like one.
"""
import base64
import json
import logging
from datetime import datetime, timezone, timedelta

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

DUOLINGO_API_BASE = "https://www.duolingo.com/2017-06-30"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
JST = timezone(timedelta(hours=9))


def _decode_jwt_sub(jwt: str) -> str | None:
    """Extract the `sub` (user id) claim from a JWT without verifying it."""
    try:
        payload_b64 = jwt.split(".")[1]
        # base64url, pad to multiple of 4
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        sub = payload.get("sub")
        return str(sub) if sub is not None else None
    except Exception:
        logger.warning("Could not decode Duolingo JWT sub claim")
        return None


def resolve_user_id() -> str | None:
    if settings.duolingo_user_id:
        return settings.duolingo_user_id
    if settings.duolingo_jwt:
        return _decode_jwt_sub(settings.duolingo_jwt)
    return None


async def fetch_xp_summaries(start_date: str | None = None) -> list[dict]:
    """Fetch daily XP summaries.

    Returns list of dicts: {date: 'YYYY-MM-DD', minutes, gained_xp, num_sessions}
    ordered ascending by date. `start_date` is an inclusive YYYY-MM-DD lower bound.
    """
    user_id = resolve_user_id()
    if not user_id or not settings.duolingo_jwt:
        return []

    url = f"{DUOLINGO_API_BASE}/users/{user_id}/xp_summaries"
    params: dict = {}
    if start_date:
        params["startDate"] = start_date
    headers = {
        "Authorization": f"Bearer {settings.duolingo_jwt}",
        "User-Agent": BROWSER_UA,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    summaries = data.get("summaries", []) or []
    out: list[dict] = []
    for s in summaries:
        epoch = s.get("date")
        if epoch is None:
            continue
        # `date` is epoch seconds at the user's local start-of-day; render in JST.
        d = datetime.fromtimestamp(int(epoch), tz=JST).date().isoformat()
        if start_date and d < start_date:
            continue

        gained_xp = int(s.get("gainedXp") or 0)
        num_sessions = int(s.get("numSessions") or 0)
        session_seconds = s.get("totalSessionTime")

        if session_seconds:
            minutes = round(float(session_seconds) / 60.0, 1)
        elif num_sessions:
            minutes = round(num_sessions * settings.duolingo_minutes_per_session, 1)
        elif gained_xp:
            # last-resort estimate: ~2 XP per minute
            minutes = round(gained_xp / 2.0, 1)
        else:
            minutes = 0.0

        out.append({
            "date": d,
            "minutes": minutes,
            "gained_xp": gained_xp,
            "num_sessions": num_sessions,
        })

    out.sort(key=lambda r: r["date"])
    return out
