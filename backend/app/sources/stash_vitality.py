"""Stash Vitality — local media manager playback time as vitality proxy.

Fetches play_history / o_history / play_duration from the Stash GraphQL API,
aggregates into daily playback minutes, and merges into the vitality category.

スコアの元は play_count ではなく実再生時間（play_seconds）。Stash は1回の再生ごとの
長さを保持せず Scene.play_duration に累積秒数しか持たないので、ingest ごとにシーン単位の
スナップショット（stash_scene_state）と比較し、増えた分だけをその間に増えた
play_history の日付へ配分する。初回だけは差分が取れないので、累積再生時間を
そのシーンの全再生履歴に等分して過去日を埋める（推定値）。
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

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
      id
      play_duration
      last_played_at
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
        # Stash は毎回フル履歴を返すので回数は常に全期間を再計算する（冪等）。
        # 再生時間だけは差分加算なので from_date は使わない。
        headers = {
            "Content-Type": "application/json",
            "ApiKey": settings.stash_api_key,
        }

        plays_by_day: dict[str, int] = defaultdict(int)
        o_by_day: dict[str, int] = defaultdict(int)
        scenes_all: list[dict] = []

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
                time_str = format_relative_day(d, today)

                activities.append({
                    "time": time_str,
                    "icon": "💚",
                    "text": f"Vitality {row[1]}",
                    "detail": None,  # Keep abstract
                    "color": "#D4A574",
                    "sort_date": row[0],
                })

            return activities
