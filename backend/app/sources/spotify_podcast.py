import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..database import get_db_context
from ..services.oauth import get_valid_token, has_token
from .base import SourceAdapter

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SpotifyPodcastAdapter(SourceAdapter):
    source_id = "spotify_podcast"
    display_name = "Podcasts (Spotify)"

    async def is_configured(self) -> bool:
        return await has_token("spotify_podcast")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        token = await get_valid_token("spotify_podcast")
        if not token:
            logger.warning("Spotify: no valid token")
            return 0, 0

        # Determine cursor: fetch plays after this timestamp
        if from_date:
            after_ms = int(
                datetime.strptime(from_date, "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .timestamp()
                * 1000
            )
        else:
            last_ts = await self.get_last_timestamp()
            if last_ts:
                after_ms = last_ts * 1000
            else:
                # First fetch: go back 30 days
                after_ms = int(
                    (datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000
                )

        headers = {"Authorization": f"Bearer {token}"}
        all_items = []

        async with httpx.AsyncClient(timeout=30) as client:
            # Paginate using 'after' cursor (oldest first)
            url = f"{SPOTIFY_API_BASE}/me/player/recently-played"
            params = {"limit": 50, "after": after_ms}

            while url:
                try:
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.exception("Failed to fetch Spotify recently-played")
                    break

                items = data.get("items", [])
                all_items.extend(items)

                # Follow 'next' cursor if available
                next_url = data.get("next")
                if next_url and len(items) == 50:
                    url = next_url
                    params = None  # next URL includes params
                else:
                    break

        # Filter to podcast episodes only
        episodes = []
        for item in all_items:
            track = item.get("track")
            if not track:
                continue
            # Episodes have type "episode", tracks have type "track"
            if track.get("type") != "episode":
                continue
            episodes.append({
                "episode_id": track["id"],
                "episode_name": track.get("name", ""),
                "show_name": track.get("show", {}).get("name", "") if track.get("show") else "",
                "duration_ms": track.get("duration_ms", 0),
                "played_at": item["played_at"],
            })

        stored = 0
        async with get_db_context() as db:
            for ep in episodes:
                played_date = ep["played_at"][:10]  # "2026-04-06T12:00:00.000Z" → "2026-04-06"
                try:
                    await db.execute(
                        """INSERT OR IGNORE INTO spotify_podcast_plays
                        (episode_id, episode_name, show_name, duration_ms, played_at, played_date)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            ep["episode_id"],
                            ep["episode_name"],
                            ep["show_name"],
                            ep["duration_ms"],
                            ep["played_at"],
                            played_date,
                        ),
                    )
                    stored += 1
                except Exception:
                    logger.exception("Error storing podcast play: %s", ep["episode_name"])
            await db.commit()

        logger.info("Spotify Podcast: fetched %d items, %d episodes stored", len(all_items), stored)
        return len(all_items), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            # Delete all and re-insert (幽霊データ対策)
            await db.execute(
                "DELETE FROM activity_records WHERE source = 'spotify_podcast'"
            )
            await db.execute(
                """INSERT INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    played_date,
                    'spotify_podcast',
                    'podcast',
                    ROUND(SUM(duration_ms) / 60000.0, 1),
                    ROUND(SUM(duration_ms) / 60000.0, 1),
                    'minutes',
                    NULL
                FROM spotify_podcast_plays
                GROUP BY played_date"""
            )
            await db.commit()
        logger.info("Spotify Podcast daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT played_date, COUNT(*) as episodes,
                    SUM(duration_ms) / 60000.0 as total_min
                FROM spotify_podcast_plays
                GROUP BY played_date
                ORDER BY played_date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                total_min = round(row[2]) if row[2] else 0
                hours = total_min // 60
                mins = total_min % 60
                duration_str = f"{hours}時間{mins}分" if hours > 0 else f"{mins}分"

                episodes = row[1]
                activities.append({
                    "time": time_str,
                    "icon": "🎙️",
                    "text": f"Podcastを{duration_str}聴取",
                    "detail": f"{episodes}エピソード" if include_detail else None,
                    "color": "#1DB954",
                    "sort_date": row[0],
                })

            return activities
