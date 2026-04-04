"""Stash Vitality — local media manager play/o history as vitality proxy.

Fetches play_history and o_history from Stash GraphQL API,
aggregates into daily counts, and merges into the vitality category.
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter

logger = logging.getLogger(__name__)

# GraphQL query to fetch all scenes with play history
SCENES_QUERY = """
query($page: Int!) {
  findScenes(
    scene_filter: { play_count: { modifier: GREATER_THAN, value: 0 } }
    filter: { sort: "last_played_at", direction: DESC, per_page: 100, page: $page }
  ) {
    count
    scenes {
      play_history
      o_history
    }
  }
}
"""


class StashVitalityAdapter(SourceAdapter):
    source_id = "stash_vitality"
    display_name = "Vitality (Stash)"

    async def is_configured(self) -> bool:
        return bool(settings.stash_api_key)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        if not from_date:
            last_ts = await self.get_last_timestamp()
            if last_ts:
                dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
                from_date = dt.strftime("%Y-%m-%d")
            else:
                from_date = "2025-01-01"

        headers = {
            "Content-Type": "application/json",
            "ApiKey": settings.stash_api_key,
        }

        plays_by_day: dict[str, int] = defaultdict(int)
        o_by_day: dict[str, int] = defaultdict(int)

        async with httpx.AsyncClient(timeout=30) as client:
            page = 1
            total_scenes = 0
            while True:
                try:
                    resp = await client.post(
                        f"{settings.stash_api_url}/graphql",
                        headers=headers,
                        json={"query": SCENES_QUERY, "variables": {"page": page}},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.exception("Failed to fetch Stash scenes (page %d)", page)
                    break

                result = data.get("data", {}).get("findScenes", {})
                scenes = result.get("scenes", [])
                count = result.get("count", 0)

                if not scenes:
                    break

                for scene in scenes:
                    for ts in scene.get("play_history", []):
                        day = ts[:10]
                        if day >= from_date:
                            plays_by_day[day] += 1
                    for ts in scene.get("o_history", []):
                        day = ts[:10]
                        if day >= from_date:
                            o_by_day[day] += 1

                total_scenes += len(scenes)
                if total_scenes >= count:
                    break
                page += 1

        # Store daily counts
        all_days = set(plays_by_day.keys()) | set(o_by_day.keys())
        stored = 0
        async with get_db_context() as db:
            for day in all_days:
                await db.execute(
                    """INSERT OR REPLACE INTO stash_vitality
                    (date, play_count, o_count) VALUES (?, ?, ?)""",
                    (day, plays_by_day.get(day, 0), o_by_day.get(day, 0)),
                )
                stored += 1
            await db.commit()

        logger.info("Stash vitality: stored %d daily records from %d scenes", stored, total_scenes)
        return total_scenes, stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'stash_vitality',
                    'vitality',
                    0,
                    play_count,
                    'plays',
                    CASE WHEN o_count > 0 THEN json_object('o_count', o_count) ELSE NULL END
                FROM stash_vitality"""
            )
            await db.commit()
        logger.info("Stash vitality aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, play_count, o_count FROM stash_vitality
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                activities.append({
                    "time": time_str,
                    "icon": "💚",
                    "text": f"Vitality {row[1]}",
                    "detail": None,  # Keep abstract
                    "color": "#50FA7B",
                    "sort_date": row[0],
                })

            return activities
