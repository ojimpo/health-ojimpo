import logging
from datetime import date

from ..config import settings
from ..database import get_db_context
from ..services.duolingo import fetch_xp_summaries, resolve_user_id
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class DuolingoAdapter(SourceAdapter):
    source_id = "duolingo"
    display_name = "語学 (Duolingo)"

    async def is_configured(self) -> bool:
        return bool(settings.duolingo_jwt and resolve_user_id())

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        try:
            summaries = await fetch_xp_summaries(start_date=from_date)
        except Exception:
            logger.exception("Failed to fetch Duolingo xp_summaries")
            return 0, 0

        stored = 0
        async with get_db_context() as db:
            for s in summaries:
                await db.execute(
                    """INSERT INTO duolingo_daily (date, minutes, gained_xp, num_sessions)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        minutes = excluded.minutes,
                        gained_xp = excluded.gained_xp,
                        num_sessions = excluded.num_sessions""",
                    (s["date"], s["minutes"], s["gained_xp"], s["num_sessions"]),
                )
                stored += 1
            await db.commit()

        logger.info("Duolingo: stored %d daily summaries", stored)
        return len(summaries), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute("DELETE FROM activity_records WHERE source = 'duolingo'")
            await db.execute(
                """INSERT INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'duolingo', 'study',
                       ROUND(minutes, 1), ROUND(minutes, 1), '分', NULL
                FROM duolingo_daily
                WHERE minutes > 0"""
            )
            await db.commit()
        logger.info("Duolingo daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, minutes, gained_xp, num_sessions
                FROM duolingo_daily
                WHERE minutes > 0
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

        activities = []
        today = date.today()
        for row in rows:
            d = date.fromisoformat(row[0])
            time_str = format_relative_day(d, today)
            minutes = round(row[1]) if row[1] else 0
            gained_xp = int(row[2] or 0)
            detail = f"{gained_xp}XP" if include_detail and gained_xp else None
            activities.append({
                "time": time_str,
                "icon": "🦉",
                "text": f"Duolingoで{minutes}分学習",
                "detail": detail,
                "color": "#58CC02",
                "sort_date": row[0],
            })
        return activities
