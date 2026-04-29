import logging
from datetime import date

from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

SOURCE_CONFIG = {
    "instagram": {
        "display_name": "Instagram",
        "category": "sns",
        "icon": "📸",
        "color": "#FF9500",
    },
    "twitter": {
        "display_name": "Twitter",
        "category": "sns",
        "icon": "🐦",
        "color": "#1DA1F2",
    },
}


class ScreenTimeAdapter(SourceAdapter):
    """Adapter for screen time data received via iOS Shortcut webhook."""

    def __init__(self, source_id: str):
        self.source_id = source_id
        config = SOURCE_CONFIG.get(source_id, {})
        self.display_name = config.get("display_name", source_id)
        self._category = config.get("category", "sns")
        self._icon = config.get("icon", "📱")
        self._color = config.get("color", "#FFFFFF")

    async def is_configured(self) -> bool:
        # Screen time sources are always "configured" — they receive data via webhook
        return True

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        # No external fetch — data arrives via POST /api/ingest/webhook
        return 0, 0

    async def store_webhook_data(self, webhook_date: str, minutes: float) -> None:
        """Store screen time data received from iOS Shortcut webhook. Additive per day."""
        async with get_db_context() as db:
            await db.execute(
                """INSERT INTO screen_time_daily (date, source, minutes)
                VALUES (?, ?, ?)
                ON CONFLICT(date, source) DO UPDATE SET minutes = minutes + excluded.minutes""",
                (webhook_date, self.source_id, minutes),
            )
            await db.commit()
        logger.info("%s: added screen time %.1f min for %s", self.source_id, minutes, webhook_date)

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, source, ?, minutes, minutes, 'minutes', NULL
                FROM screen_time_daily WHERE source = ?""",
                (self._category, self.source_id),
            )
            await db.commit()
        logger.info("%s aggregation completed", self.source_id)

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, minutes FROM screen_time_daily
                WHERE source = ?
                ORDER BY date DESC LIMIT ?""",
                (self.source_id, limit),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                mins = round(row[1])
                hours = mins // 60
                m = mins % 60
                if hours > 0:
                    dur = f"{hours}時間{m}分"
                else:
                    dur = f"{m}分"

                activities.append({
                    "time": time_str,
                    "icon": self._icon,
                    "text": f"{self.display_name} {dur}",
                    "detail": None,
                    "color": self._color,
                    "sort_date": row[0],
                })

            return activities
