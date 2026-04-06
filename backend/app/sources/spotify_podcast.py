import logging
from datetime import date, timedelta

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

        headers = {"Authorization": f"Bearer {token}"}
        cutoff = from_date or (date.today() - timedelta(days=90)).isoformat()

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Get all followed shows
            shows = []
            url = f"{SPOTIFY_API_BASE}/me/shows"
            params = {"limit": 50}
            while url:
                try:
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.exception("Failed to fetch Spotify shows")
                    break
                shows.extend(data.get("items", []))
                url = data.get("next")
                params = None  # next URL includes params

            logger.info("Spotify Podcast: %d followed shows", len(shows))

            # 2. For each show, check recent episodes for fully_played
            total_checked = 0
            stored = 0
            for show_item in shows:
                show = show_item.get("show")
                if not show:
                    continue
                show_id = show["id"]
                show_name = show.get("name", "")

                ep_url = f"{SPOTIFY_API_BASE}/shows/{show_id}/episodes"
                ep_params = {"limit": 50}

                while ep_url:
                    try:
                        resp = await client.get(ep_url, headers=headers, params=ep_params)
                        resp.raise_for_status()
                        ep_data = resp.json()
                    except Exception:
                        logger.exception("Failed to fetch episodes for %s", show_name)
                        break

                    episodes = [e for e in ep_data.get("items", []) if e is not None]
                    if not episodes:
                        break

                    past_cutoff = False
                    for ep in episodes:
                        release_date = ep.get("release_date", "")
                        if release_date < cutoff:
                            past_cutoff = True
                            break

                        total_checked += 1
                        rp = ep.get("resume_point", {})
                        if not rp.get("fully_played"):
                            continue

                        # Store fully_played episode with release_date as played_date
                        async with get_db_context() as db:
                            try:
                                await db.execute(
                                    """INSERT OR IGNORE INTO spotify_podcast_plays
                                    (episode_id, episode_name, show_name, duration_ms, played_at, played_date)
                                    VALUES (?, ?, ?, ?, ?, ?)""",
                                    (
                                        ep["id"],
                                        ep.get("name", ""),
                                        show_name,
                                        ep.get("duration_ms", 0),
                                        release_date,
                                        release_date,
                                    ),
                                )
                                await db.commit()
                                stored += 1
                            except Exception:
                                logger.exception("Error storing podcast: %s", ep.get("name"))

                    if past_cutoff:
                        break
                    ep_url = ep_data.get("next")
                    ep_params = None

        logger.info("Spotify Podcast: checked %d episodes, stored %d new", total_checked, stored)
        return total_checked, stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
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
