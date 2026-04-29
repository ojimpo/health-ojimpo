import logging
from base64 import b64encode
from datetime import date, timedelta

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class IntervalsAdapter(SourceAdapter):
    source_id = "intervals"
    display_name = "intervals.icu"

    async def is_configured(self) -> bool:
        return bool(settings.intervals_api_key and settings.intervals_athlete_id)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        if not from_date:
            from_date = (date.today() - timedelta(days=30)).isoformat()

        athlete_id = settings.intervals_athlete_id
        api_key = settings.intervals_api_key
        auth = b64encode(f"API_KEY:{api_key}".encode()).decode()

        headers = {"Authorization": f"Basic {auth}"}
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    url,
                    headers=headers,
                    params={"oldest": from_date, "newest": date.today().isoformat()},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("Failed to fetch intervals.icu data")
            return 0, 0

        stored = 0
        async with get_db_context() as db:
            for item in data:
                d = item.get("id", "")  # intervals.icu uses date as ID
                if not d:
                    continue
                await db.execute(
                    """INSERT OR REPLACE INTO intervals_daily
                    (date, ctl, atl, tsb, ftp, weight)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (d, item.get("ctl"), item.get("atl"), item.get("rampRate"), item.get("ftp"), item.get("weight")),
                )
                stored += 1
            await db.commit()

        logger.info("intervals.icu: stored %d daily records", stored)
        return len(data), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'intervals', 'ctl', 0, COALESCE(ctl, 0), 'CTL', NULL
                FROM intervals_daily WHERE ctl IS NOT NULL"""
            )
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'intervals', 'weight', 0, weight, 'kg', NULL
                FROM intervals_daily WHERE weight IS NOT NULL"""
            )
            await db.commit()
        logger.info("intervals.icu aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, ctl, atl, ftp FROM intervals_daily
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                ctl = row[1]
                activities.append({
                    "time": time_str,
                    "icon": "💪",
                    "text": f"CTL {ctl:.0f}" if ctl else "データなし",
                    "detail": f"FTP {row[3]:.0f}" if include_detail and row[3] else None,
                    "color": "#50FA7B",
                    "sort_date": row[0],
                })

            return activities
