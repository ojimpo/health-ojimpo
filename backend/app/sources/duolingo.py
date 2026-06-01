import logging
from datetime import date

from ..config import settings
from ..database import get_db_context
from ..services.duolingo import fetch_profile
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class DuolingoAdapter(SourceAdapter):
    """Duolingo via the public profile API (ID-only, no auth).

    The public endpoint only exposes the current totalXp snapshot — there is no
    per-day history available without login. So each run records today's totalXp
    and derives the day's gained XP as the delta from the previous day's snapshot,
    converting XP to approximate minutes (no study-time is exposed publicly).

    Consequence: the first run only seeds a baseline (gained=0); real daily values
    appear from the next day onward. No historical backfill is possible ID-only.
    """

    source_id = "duolingo"
    display_name = "語学 (Duolingo)"

    async def is_configured(self) -> bool:
        return bool(settings.duolingo_user_id)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        try:
            prof = await fetch_profile(settings.duolingo_user_id)
        except Exception:
            logger.exception("Failed to fetch Duolingo profile")
            return 0, 0
        if not prof:
            logger.warning("Duolingo: no user found for %s", settings.duolingo_user_id)
            return 0, 0

        total_xp = prof["total_xp"]
        today = date.today().isoformat()
        xp_per_min = settings.duolingo_xp_per_minute or 3.0

        async with get_db_context() as db:
            # Previous day's end-of-day snapshot (latest total_xp before today).
            rows = await db.execute_fetchall(
                """SELECT total_xp FROM duolingo_daily
                WHERE date < ? AND total_xp IS NOT NULL
                ORDER BY date DESC LIMIT 1""",
                (today,),
            )
            prev_total = int(rows[0][0]) if rows and rows[0][0] is not None else None

            # First observation: baseline only (can't derive a delta yet).
            gained = 0 if prev_total is None else max(0, total_xp - prev_total)
            minutes = round(gained / xp_per_min, 1)

            await db.execute(
                """INSERT INTO duolingo_daily (date, minutes, gained_xp, num_sessions, total_xp)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(date) DO UPDATE SET
                    minutes = excluded.minutes,
                    gained_xp = excluded.gained_xp,
                    total_xp = excluded.total_xp""",
                (today, minutes, gained, total_xp),
            )
            await db.commit()

        logger.info(
            "Duolingo: totalXp=%d, streak=%d, today gained=%d xp (%.1f min)",
            total_xp, prof["streak"], gained, minutes,
        )
        return 1, 1

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
                """SELECT date, minutes, gained_xp FROM duolingo_daily
                WHERE minutes > 0
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

        activities = []
        today = date.today()
        for row in rows:
            d = date.fromisoformat(row[0])
            gained_xp = int(row[2] or 0)
            activities.append({
                "time": format_relative_day(d, today),
                "icon": "🦉",
                "text": f"Duolingoで{round(row[1])}分学習",
                "detail": f"{gained_xp}XP" if include_detail and gained_xp else None,
                "color": "#58CC02",
                "sort_date": row[0],
            })
        return activities
