import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..database import get_db_context
from ..services.oauth import get_valid_token, has_token
from .base import SourceAdapter

logger = logging.getLogger(__name__)

STRAVA_API_BASE = "https://www.strava.com/api/v3"


class StravaAdapter(SourceAdapter):
    source_id = "strava"
    display_name = "Strava"

    async def is_configured(self) -> bool:
        return await has_token("strava")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        token = await get_valid_token("strava")
        if not token:
            logger.warning("Strava: no valid token")
            return 0, 0

        if from_date:
            after = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        else:
            last_ts = await self.get_last_timestamp()
            after = (last_ts + 1) if last_ts else int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())

        headers = {"Authorization": f"Bearer {token}"}
        all_activities = []
        page = 1

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                try:
                    resp = await client.get(
                        f"{STRAVA_API_BASE}/athlete/activities",
                        headers=headers,
                        params={"after": after, "page": page, "per_page": 100},
                    )
                    resp.raise_for_status()
                    activities = resp.json()
                except Exception:
                    logger.exception("Failed to fetch Strava activities page %d", page)
                    break

                if not activities:
                    break
                all_activities.extend(activities)
                page += 1

        stored = 0
        async with get_db_context() as db:
            for act in all_activities:
                try:
                    await db.execute(
                        """INSERT OR REPLACE INTO strava_activities
                        (id, activity_type, name, distance_meters, moving_time_seconds,
                         elapsed_time_seconds, total_elevation_gain, commute,
                         start_date, start_date_local, timezone, gear_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            act["id"],
                            act.get("type", ""),
                            act.get("name", ""),
                            act.get("distance", 0),
                            act.get("moving_time", 0),
                            act.get("elapsed_time", 0),
                            act.get("total_elevation_gain", 0),
                            1 if act.get("commute") else 0,
                            act.get("start_date", ""),
                            act.get("start_date_local", ""),
                            act.get("timezone", ""),
                            act.get("gear_id"),
                        ),
                    )
                    stored += 1
                except Exception:
                    logger.exception("Error storing Strava activity %s", act.get("id"))
            await db.commit()

        logger.info("Strava: stored %d activities", stored)
        return len(all_activities), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            # 1) strava (exercise, minutes): all non-commute activities — baseline
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    SUBSTR(start_date_local, 1, 10),
                    'strava',
                    'exercise',
                    ROUND(SUM(moving_time_seconds) / 60.0, 1),
                    ROUND(SUM(moving_time_seconds) / 60.0, 1),
                    'min',
                    NULL
                FROM strava_activities
                WHERE NOT (activity_type = 'Ride' AND commute = 1)
                GROUP BY SUBSTR(start_date_local, 1, 10)"""
            )
            # 2) strava_commute (commute, minutes): commute rides — baseline
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    SUBSTR(start_date_local, 1, 10),
                    'strava_commute',
                    'commute',
                    ROUND(SUM(moving_time_seconds) / 60.0, 1),
                    ROUND(SUM(moving_time_seconds) / 60.0, 1),
                    'min',
                    NULL
                FROM strava_activities
                WHERE activity_type = 'Ride' AND commute = 1
                GROUP BY SUBSTR(start_date_local, 1, 10)"""
            )
            # 3) strava_ride (exercise, km): non-commute Ride distance — event bonus
            #    Double-counts with strava minutes; rewards long rides
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    SUBSTR(start_date_local, 1, 10),
                    'strava_ride',
                    'exercise',
                    0,
                    ROUND(SUM(distance_meters) / 1000.0, 1),
                    'km',
                    NULL
                FROM strava_activities
                WHERE activity_type = 'Ride' AND commute = 0
                GROUP BY SUBSTR(start_date_local, 1, 10)"""
            )
            await db.commit()
        logger.info("Strava aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT SUBSTR(start_date_local, 1, 10) as d,
                    SUM(distance_meters) / 1000.0 as km,
                    SUM(moving_time_seconds) / 60.0 as mins,
                    COUNT(*) as count,
                    SUM(total_elevation_gain) as elev
                FROM strava_activities
                WHERE NOT (activity_type = 'Ride' AND commute = 1)
                GROUP BY d
                ORDER BY d DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                km = row[1]
                mins = row[2]
                elev = row[4] or 0

                hours = int(mins) // 60
                m = int(mins) % 60
                dur = f"{hours}時間{m}分" if hours > 0 else f"{m}分"

                elev_str = f" ({int(elev)}m↑)" if elev > 0 else ""
                activities.append({
                    "time": time_str,
                    "icon": "🚴",
                    "text": f"運動 {km:.1f}km{elev_str}",
                    "detail": f"{dur}" if include_detail else None,
                    "color": "#FF3366",
                    "sort_date": row[0],
                })

            return activities


class StravaCommuteAdapter(SourceAdapter):
    """Virtual adapter for strava_commute — data written by StravaAdapter.aggregate()."""

    source_id = "strava_commute"
    display_name = "通勤 (Strava)"

    async def is_configured(self) -> bool:
        return await has_token("strava")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        return 0, 0  # StravaAdapter handles fetching

    async def aggregate(self) -> None:
        pass  # StravaAdapter handles aggregation

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT SUBSTR(start_date_local, 1, 10) as d,
                    SUM(distance_meters) / 1000.0 as km,
                    SUM(moving_time_seconds) / 60.0 as mins,
                    COUNT(*) as count
                FROM strava_activities
                WHERE activity_type = 'Ride' AND commute = 1
                GROUP BY d
                ORDER BY d DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                hours = int(row[2]) // 60
                m = int(row[2]) % 60
                dur = f"{hours}時間{m}分" if hours > 0 else f"{m}分"

                activities.append({
                    "time": time_str,
                    "icon": "🚲",
                    "text": f"通勤 {row[1]:.1f}km ({dur})",
                    "detail": f"{int(row[3])}回" if include_detail else None,
                    "color": "#FF79C6",
                    "sort_date": row[0],
                })

            return activities


class StravaRideAdapter(SourceAdapter):
    """Virtual adapter for strava_ride — data written by StravaAdapter.aggregate()."""

    source_id = "strava_ride"
    display_name = "ライド (Strava)"

    async def is_configured(self) -> bool:
        return await has_token("strava")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        return 0, 0

    async def aggregate(self) -> None:
        pass

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        return []  # Covered by StravaAdapter feed
