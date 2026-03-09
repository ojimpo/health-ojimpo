import logging
from datetime import date, timedelta

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter

logger = logging.getLogger(__name__)

OURA_API_BASE = "https://api.ouraring.com/v2/usercollection"


class OuraAdapter(SourceAdapter):
    source_id = "oura"
    display_name = "Oura Ring"

    async def is_configured(self) -> bool:
        return bool(settings.oura_personal_access_token)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        token = settings.oura_personal_access_token
        if not from_date:
            from_date = (date.today() - timedelta(days=30)).isoformat()

        headers = {"Authorization": f"Bearer {token}"}
        fetched = 0
        stored = 0

        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch daily readiness
            try:
                resp = await client.get(
                    f"{OURA_API_BASE}/daily_readiness",
                    headers=headers,
                    params={"start_date": from_date},
                )
                resp.raise_for_status()
                readiness_data = resp.json().get("data", [])
            except Exception:
                logger.exception("Failed to fetch Oura readiness")
                readiness_data = []

            # Fetch daily sleep
            try:
                resp = await client.get(
                    f"{OURA_API_BASE}/daily_sleep",
                    headers=headers,
                    params={"start_date": from_date},
                )
                resp.raise_for_status()
                sleep_data = resp.json().get("data", [])
            except Exception:
                logger.exception("Failed to fetch Oura sleep")
                sleep_data = []

            # Fetch daily stress
            try:
                resp = await client.get(
                    f"{OURA_API_BASE}/daily_stress",
                    headers=headers,
                    params={"start_date": from_date},
                )
                resp.raise_for_status()
                stress_data = resp.json().get("data", [])
            except Exception:
                logger.exception("Failed to fetch Oura stress")
                stress_data = []

        # Merge data by date
        daily_data: dict[str, dict] = {}
        for item in readiness_data:
            d = item.get("day", "")
            if d:
                daily_data.setdefault(d, {})["readiness_score"] = item.get("score")
                fetched += 1
        for item in sleep_data:
            d = item.get("day", "")
            if d:
                daily_data.setdefault(d, {})["sleep_score"] = item.get("score")
                daily_data[d]["sleep_total_seconds"] = item.get("total_sleep_duration")
                fetched += 1
        for item in stress_data:
            d = item.get("day", "")
            if d:
                daily_data.setdefault(d, {})["stress_level"] = item.get("stress_high", 0)
                fetched += 1

        # Store in oura_daily
        async with get_db_context() as db:
            for d, data in daily_data.items():
                await db.execute(
                    """INSERT OR REPLACE INTO oura_daily
                    (date, readiness_score, sleep_score, stress_level, sleep_total_seconds)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        d,
                        data.get("readiness_score"),
                        data.get("sleep_score"),
                        str(data.get("stress_level", "")),
                        data.get("sleep_total_seconds"),
                    ),
                )
                stored += 1
            await db.commit()

        logger.info("Oura: stored %d daily records", stored)
        return fetched, stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            # Readiness → activity_records (source=oura, category=readiness)
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'oura', 'readiness', 0, readiness_score, 'score', NULL
                FROM oura_daily WHERE readiness_score IS NOT NULL"""
            )
            # Sleep → activity_records (source=oura, category=sleep)
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'oura', 'sleep', COALESCE(sleep_total_seconds / 60.0, 0), sleep_score, 'score', NULL
                FROM oura_daily WHERE sleep_score IS NOT NULL"""
            )
            # Stress → activity_records (source=oura, category=stress)
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'oura', 'stress', 0, CAST(stress_level AS REAL), 'minutes', NULL
                FROM oura_daily WHERE stress_level IS NOT NULL AND stress_level != ''"""
            )
            await db.commit()
        logger.info("Oura aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, readiness_score, sleep_score FROM oura_daily
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                readiness = row[1]
                sleep = row[2]
                parts = []
                if readiness is not None:
                    parts.append(f"Readiness {readiness}")
                if sleep is not None:
                    parts.append(f"Sleep {sleep}")

                activities.append({
                    "time": time_str,
                    "icon": "😴",
                    "text": " / ".join(parts) if parts else "データなし",
                    "detail": None,
                    "color": "#BD93F9",
                    "sort_date": row[0],
                })

            return activities
