import logging
from datetime import date, timedelta

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter

logger = logging.getLogger(__name__)


class KashidashiAdapter(SourceAdapter):
    source_id = "kashidashi"
    display_name = "kashidashi (図書館)"

    async def is_configured(self) -> bool:
        return bool(settings.kashidashi_base_url)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        """Fetch returned books from kashidashi API and write to activity_records."""
        base_url = settings.kashidashi_base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{base_url}/api/items")
                resp.raise_for_status()
                items = resp.json()
        except Exception:
            logger.exception("Failed to fetch from kashidashi API")
            return 0, 0

        # Count returned items per date
        daily_counts: dict[str, int] = {}
        for item in items:
            returned_at = item.get("returned_at")
            if not returned_at:
                continue
            d = returned_at[:10]  # YYYY-MM-DD
            if from_date and d < from_date:
                continue
            daily_counts[d] = daily_counts.get(d, 0) + 1

        stored = 0
        async with get_db_context() as db:
            for d, count in daily_counts.items():
                await db.execute(
                    """INSERT OR REPLACE INTO activity_records
                    (date, source, category, minutes, raw_value, raw_unit, metadata)
                    VALUES (?, 'kashidashi', 'reading', ?, ?, '冊', NULL)""",
                    (d, count, count),
                )
                stored += 1
            await db.commit()

        logger.info("kashidashi: stored %d daily records from %d items", stored, len(items))
        return len(items), stored

    async def aggregate(self) -> None:
        # Already written directly to activity_records in fetch_and_store
        pass

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, raw_value FROM activity_records
                WHERE source = 'kashidashi'
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                if diff == 0:
                    time_str = "今日"
                elif diff == 1:
                    time_str = "1日前"
                else:
                    time_str = f"{diff}日前"

                count = int(row[1])
                activities.append({
                    "time": time_str,
                    "icon": "📚",
                    "text": f"図書{count}冊を返却",
                    "detail": None,
                    "color": "#ADFF2F",
                    "sort_date": row[0],
                })

            return activities
