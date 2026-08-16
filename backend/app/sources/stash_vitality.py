"""Stash Vitality — local media manager playback time as vitality proxy.

Fetches play_history / o_history / play_duration from the Stash GraphQL API,
aggregates into daily playback minutes, and merges into the vitality category.

スコアの元は play_count ではなく実再生時間（play_seconds）。Stash は1回の再生ごとの
長さを保持せず Scene.play_duration に累積秒数しか持たないので、ingest ごとにシーン単位の
スナップショット（stash_scene_state）と比較し、増えた分だけをその間に増えた
play_history の日付へ配分する。初回だけは差分が取れないので、累積再生時間を
そのシーンの全再生履歴に等分して過去日を埋める（推定値）。
"""

import logging
from collections import defaultdict
from datetime import date

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
                    for ts in scene.get("play_history") or []:
                        plays_by_day[ts[:10]] += 1
                    for ts in scene.get("o_history") or []:
                        o_by_day[ts[:10]] += 1

                scenes_all.extend(scenes)
                total_scenes += len(scenes)
                if total_scenes >= count:
                    break
                page += 1

        if not scenes_all:
            logger.warning("Stash vitality: no scenes fetched, skipping write")
            return 0, 0

        async with get_db_context() as db:
            state_rows = await db.execute_fetchall(
                "SELECT scene_id, play_duration, last_history_at FROM stash_scene_state"
            )
            prev_state = {r[0]: (float(r[1] or 0), r[2]) for r in state_rows}

            seconds_by_day = self._attribute_seconds(scenes_all, prev_state)

            # 回数は全期間を上書き、再生時間は差分を加算する
            for day in set(plays_by_day) | set(o_by_day):
                await db.execute(
                    """INSERT INTO stash_vitality (date, play_count, o_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        play_count = excluded.play_count,
                        o_count = excluded.o_count""",
                    (day, plays_by_day.get(day, 0), o_by_day.get(day, 0)),
                )
            for day, secs in seconds_by_day.items():
                await db.execute(
                    """INSERT INTO stash_vitality (date, play_count, o_count, play_seconds)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        play_seconds = stash_vitality.play_seconds + excluded.play_seconds""",
                    (day, plays_by_day.get(day, 0), o_by_day.get(day, 0), secs),
                )

            for scene in scenes_all:
                history = sorted(scene.get("play_history") or [])
                await db.execute(
                    """INSERT INTO stash_scene_state
                    (scene_id, play_duration, play_count, last_history_at, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(scene_id) DO UPDATE SET
                        play_duration = excluded.play_duration,
                        play_count = excluded.play_count,
                        last_history_at = excluded.last_history_at,
                        updated_at = excluded.updated_at""",
                    (
                        str(scene["id"]),
                        float(scene.get("play_duration") or 0),
                        len(history),
                        history[-1] if history else None,
                    ),
                )
            await db.commit()

        stored = len(set(plays_by_day) | set(o_by_day) | set(seconds_by_day))
        logger.info(
            "Stash vitality: stored %d daily records (%.1f min newly attributed) from %d scenes",
            stored,
            sum(seconds_by_day.values()) / 60,
            total_scenes,
        )
        return total_scenes, stored

    @staticmethod
    def _attribute_seconds(
        scenes: list[dict], prev_state: dict[str, tuple[float, str | None]]
    ) -> dict[str, float]:
        """Map newly watched seconds onto the days they were watched.

        play_duration はシーン単位の累積秒数なので、前回スナップショットとの差分が
        「前回 ingest 以降に観た秒数」になる。それを同じ期間に増えた play_history の
        日付へ等分する。スナップショットが無いシーン（初回）は差分が取れないため、
        累積値を全履歴に等分した推定値で過去日を埋める。
        """
        seconds_by_day: dict[str, float] = defaultdict(float)

        for scene in scenes:
            scene_id = str(scene["id"])
            history = sorted(scene.get("play_history") or [])
            duration = float(scene.get("play_duration") or 0)
            prev = prev_state.get(scene_id)

            if prev is None:
                if history and duration > 0:
                    per_play = duration / len(history)
                    for ts in history:
                        seconds_by_day[ts[:10]] += per_play
                continue

            prev_duration, prev_last = prev
            delta = duration - prev_duration
            if delta <= 0:
                # 履歴を消した/再スキャンした等。スナップショットだけ追随させる
                continue

            fresh = [ts for ts in history if prev_last is None or ts > prev_last]
            if fresh:
                per_play = delta / len(fresh)
                for ts in fresh:
                    seconds_by_day[ts[:10]] += per_play
            else:
                # 再生イベントは増えず時間だけ伸びた = 既存の再生の続きを観た
                anchor = scene.get("last_played_at") or (history[-1] if history else None)
                if anchor:
                    seconds_by_day[anchor[:10]] += delta

        return dict(seconds_by_day)

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'stash_vitality',
                    'vitality',
                    CAST(ROUND(play_seconds / 60.0) AS INTEGER),
                    ROUND(play_seconds / 60.0, 1),
                    'min',
                    json_object('play_count', play_count, 'o_count', o_count)
                FROM stash_vitality"""
            )
            await db.commit()
        logger.info("Stash vitality aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, play_seconds, o_count FROM stash_vitality
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
                    "text": f"Vitality {round((row[1] or 0) / 60)}min",
                    "detail": None,  # Keep abstract
                    "color": "#D4A574",
                    "sort_date": row[0],
                })

            return activities
