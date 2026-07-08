import logging
from datetime import date, timedelta

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter
from .oura import OURA_API_BASE

logger = logging.getLogger(__name__)


class OuraStepsAdapter(SourceAdapter):
    """Oura daily_activity の歩数を運動カテゴリの第2ソースとして取り込む。

    Strava（意図的な運動）と対になる「日常の身体活動」シグナル。
    activity_score は 86〜96 に圧縮されていて分散がないため、歩数を使う。
    """

    source_id = "oura_steps"
    display_name = "歩数 (Oura)"

    async def is_configured(self) -> bool:
        return bool(settings.oura_personal_access_token)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        token = settings.oura_personal_access_token
        if not from_date:
            from_date = (date.today() - timedelta(days=30)).isoformat()

        headers = {"Authorization": f"Bearer {token}"}
        params: dict = {
            "start_date": from_date,
            "end_date": date.today().isoformat(),
        }
        items: list[dict] = []
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{OURA_API_BASE}/daily_activity", headers=headers, params=params
                )
                resp.raise_for_status()
                payload = resp.json()
                items.extend(payload.get("data", []))
                next_token = payload.get("next_token")
                if not next_token:
                    break
                params = {"next_token": next_token}

        stored = 0
        async with get_db_context() as db:
            for item in items:
                d = item.get("day")
                if not d:
                    continue
                await db.execute(
                    """INSERT OR REPLACE INTO oura_activity_daily
                    (date, steps, activity_score, active_calories,
                     high_activity_minutes, medium_activity_minutes, low_activity_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        d,
                        item.get("steps"),
                        item.get("score"),
                        item.get("active_calories"),
                        round((item.get("high_activity_time") or 0) / 60, 1),
                        round((item.get("medium_activity_time") or 0) / 60, 1),
                        round((item.get("low_activity_time") or 0) / 60, 1),
                    ),
                )
                stored += 1
            await db.commit()

        logger.info("Oura steps: stored %d daily records", stored)
        return len(items), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'oura_steps', 'exercise', 0, steps, 'steps', NULL
                FROM oura_activity_daily WHERE steps IS NOT NULL"""
            )
            await db.commit()
        logger.info("Oura steps aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        # 毎日必ず1件出て他ソースを埋もれさせるため、活動フィードには出さない
        return []
