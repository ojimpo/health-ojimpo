import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..database import get_db_context
from ..services.oauth import get_valid_token, has_token
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
JST = timezone(timedelta(hours=9))


class SpotifySavedTracksAdapter(SourceAdapter):
    source_id = "spotify_saved"
    display_name = "好きな曲 (Spotify)"

    async def is_configured(self) -> bool:
        # Shares the spotify_podcast OAuth token (user-library-read scope).
        return await has_token("spotify_podcast")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        token = await get_valid_token("spotify_podcast")
        if not token:
            logger.warning("Spotify Saved: no valid token")
            return 0, 0

        headers = {"Authorization": f"Bearer {token}"}
        # Pagination stop. Saved Tracks come newest-first, so scheduled runs
        # only need to page back to the newest stored date (minus a margin);
        # a full 2-year backfill runs only when the table is empty.
        if from_date:
            cutoff = from_date
        else:
            async with get_db_context() as db:
                row = await db.execute_fetchall(
                    "SELECT MAX(saved_date) FROM spotify_saved_tracks"
                )
            newest = row[0][0] if row and row[0][0] else None
            if newest:
                cutoff = (date.fromisoformat(newest) - timedelta(days=3)).isoformat()
            else:
                cutoff = (date.today() - timedelta(days=730)).isoformat()

        total_checked = 0
        stored = 0
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{SPOTIFY_API_BASE}/me/tracks"
            params: dict | None = {"limit": 50}
            stop = False
            while url and not stop:
                try:
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.exception("Failed to fetch Spotify saved tracks")
                    break

                items = data.get("items", [])
                if not items:
                    break

                for it in items:
                    track = it.get("track")
                    added_at = it.get("added_at")
                    if not track or not added_at:
                        continue
                    # Saved Tracks are returned newest-first; convert added_at
                    # to JST date and stop paginating once older than cutoff.
                    saved_date = (
                        datetime.fromisoformat(added_at.replace("Z", "+00:00"))
                        .astimezone(JST)
                        .date()
                        .isoformat()
                    )
                    if saved_date < cutoff:
                        stop = True
                        break

                    total_checked += 1
                    artists = track.get("artists") or [{}]
                    async with get_db_context() as db:
                        try:
                            cur = await db.execute(
                                """INSERT OR IGNORE INTO spotify_saved_tracks
                                (track_id, track_name, artist_name, duration_ms, added_at, saved_date)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                                (
                                    track["id"],
                                    track.get("name", ""),
                                    artists[0].get("name", ""),
                                    track.get("duration_ms", 0),
                                    added_at,
                                    saved_date,
                                ),
                            )
                            await db.commit()
                            if cur.rowcount:
                                stored += 1
                        except Exception:
                            logger.exception("Error storing saved track: %s", track.get("name"))

                url = data.get("next")
                params = None  # next URL already carries the query params

        logger.info("Spotify Saved: checked %d tracks, stored %d new", total_checked, stored)
        return total_checked, stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                "DELETE FROM activity_records WHERE source = 'spotify_saved'"
            )
            await db.execute(
                """INSERT INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    saved_date,
                    'spotify_saved',
                    'like',
                    0,
                    COUNT(*),
                    '曲',
                    NULL
                FROM spotify_saved_tracks
                GROUP BY saved_date"""
            )
            await db.commit()
        logger.info("Spotify Saved daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT saved_date, COUNT(*) as cnt
                FROM spotify_saved_tracks
                GROUP BY saved_date
                ORDER BY saved_date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for saved_date, cnt in rows:
                d = date.fromisoformat(saved_date)
                detail = None
                if include_detail:
                    sample = await db.execute_fetchall(
                        """SELECT artist_name, track_name FROM spotify_saved_tracks
                        WHERE saved_date = ? ORDER BY added_at DESC LIMIT 1""",
                        (saved_date,),
                    )
                    if sample:
                        detail = f"{sample[0][0]} - {sample[0][1]}"

                activities.append({
                    "time": format_relative_day(d, today),
                    "icon": "❤️",
                    "text": f"{cnt}曲をLike",
                    "detail": detail,
                    "color": "#E0245E",
                    "sort_date": saved_date,
                })

            return activities
