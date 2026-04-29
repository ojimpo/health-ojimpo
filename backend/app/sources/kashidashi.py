import logging
from datetime import date, timedelta

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class KashidashiCDAdapter(SourceAdapter):
    source_id = "kashidashi_cd"
    display_name = "CD貸出 (kashidashi)"

    async def is_configured(self) -> bool:
        return bool(settings.kashidashi_base_url)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        """Fetch CD items from kashidashi API and count by borrowed_date."""
        base_url = settings.kashidashi_base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{base_url}/api/items")
                resp.raise_for_status()
                items = resp.json()
        except Exception:
            logger.exception("Failed to fetch from kashidashi API")
            return 0, 0

        # Filter CD items only, count by borrowed_date
        daily_counts: dict[str, int] = {}
        cd_count = 0
        for item in items:
            if item.get("type") != "cd":
                continue
            cd_count += 1
            d = item.get("borrowed_date")
            if not d:
                continue
            if from_date and d < from_date:
                continue
            daily_counts[d] = daily_counts.get(d, 0) + 1

        stored = 0
        async with get_db_context() as db:
            for d, count in daily_counts.items():
                await db.execute(
                    """INSERT OR REPLACE INTO activity_records
                    (date, source, category, minutes, raw_value, raw_unit, metadata)
                    VALUES (?, 'kashidashi_cd', 'cd', ?, ?, '枚', NULL)""",
                    (d, count, count),
                )
                stored += 1
            await db.commit()

        logger.info("kashidashi_cd: stored %d daily records from %d CD items", stored, cd_count)
        return cd_count, stored

    async def aggregate(self) -> None:
        pass

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, raw_value FROM activity_records
                WHERE source = 'kashidashi_cd'
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                count = int(row[1])
                activities.append({
                    "time": time_str,
                    "icon": "💿",
                    "text": f"CD{count}枚を貸出",
                    "detail": None,
                    "color": "#FF79C6",
                    "sort_date": row[0],
                })

            return activities
