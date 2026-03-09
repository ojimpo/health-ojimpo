import asyncio
import logging
from datetime import datetime, timezone

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


async def fetch_recent_tracks(
    user: str,
    api_key: str,
    from_ts: int | None = None,
    to_ts: int | None = None,
    page: int = 1,
    limit: int = 200,
) -> dict:
    """Fetch a single page of recent tracks from Last.fm API."""
    params = {
        "method": "user.getRecentTracks",
        "user": user,
        "api_key": api_key,
        "format": "json",
        "limit": limit,
        "page": page,
        "extended": 0,
    }
    if from_ts is not None:
        params["from"] = from_ts
    if to_ts is not None:
        params["to"] = to_ts

    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(4):
            resp = await client.get(LASTFM_API_URL, params=params)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                logger.warning("Rate limited, waiting %d seconds", retry_after)
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code in (500, 502, 503):
                wait = 2 ** attempt
                logger.warning("Server error %d, retrying in %ds (attempt %d)", resp.status_code, wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        # Final attempt failed
        resp.raise_for_status()
        return resp.json()


async def fetch_all_tracks(
    from_ts: int | None = None,
) -> list[dict]:
    """Fetch all tracks from Last.fm, paginating through all pages."""
    user = settings.lastfm_user
    api_key = settings.lastfm_api_key
    all_tracks = []
    page = 1

    first_page = await fetch_recent_tracks(user, api_key, from_ts=from_ts, page=1)
    total_pages = int(
        first_page.get("recenttracks", {}).get("@attr", {}).get("totalPages", 1)
    )
    tracks = first_page.get("recenttracks", {}).get("track", [])
    all_tracks.extend(_filter_tracks(tracks))
    logger.info("Page 1/%d fetched (%d tracks)", total_pages, len(tracks))

    for page in range(2, total_pages + 1):
        await asyncio.sleep(0.2)  # Rate limiting: 200ms between requests
        try:
            data = await fetch_recent_tracks(
                user, api_key, from_ts=from_ts, page=page
            )
            tracks = data.get("recenttracks", {}).get("track", [])
            all_tracks.extend(_filter_tracks(tracks))
            if page % 50 == 0:
                logger.info(
                    "Page %d/%d fetched (total: %d tracks)",
                    page,
                    total_pages,
                    len(all_tracks),
                )
        except Exception:
            logger.exception("Error fetching page %d", page)
            await asyncio.sleep(5)  # Back off on error
            continue

    return all_tracks


def _filter_tracks(tracks: list[dict]) -> list[dict]:
    """Filter out 'now playing' tracks that have no date."""
    return [
        t
        for t in tracks
        if not (t.get("@attr", {}).get("nowplaying") == "true")
        and t.get("date")
    ]


def parse_scrobble(track: dict) -> dict | None:
    """Parse a Last.fm track into our storage format."""
    date_info = track.get("date")
    if not date_info:
        return None

    uts = int(date_info.get("uts", 0))
    if uts == 0:
        return None

    dt = datetime.fromtimestamp(uts, tz=timezone.utc)

    return {
        "track_name": track.get("name", ""),
        "artist_name": track.get("artist", {}).get("#text", "")
        if isinstance(track.get("artist"), dict)
        else str(track.get("artist", "")),
        "album_name": track.get("album", {}).get("#text", "")
        if isinstance(track.get("album"), dict)
        else str(track.get("album", "")),
        "scrobbled_at": uts,
        "scrobbled_date": dt.strftime("%Y-%m-%d"),
        "duration_seconds": settings.default_track_duration_seconds,
    }
