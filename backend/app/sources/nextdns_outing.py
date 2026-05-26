"""NextDNS Outing Estimation — non-home network ratio as outing proxy.

Uses iPhone's DNS query origin to estimate daily outing level.
Home judgment: network.cellular=false AND geo.city IN OUTING_HOME_CITIES.
Everything else (cellular, office Wi-Fi, café Wi-Fi, hotels) counts as outing.
This handles the case where the user is connected to office Wi-Fi all day —
cellular alone would underestimate outing for typical commuters.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

NEXTDNS_API_BASE = "https://api.nextdns.io"

# Mobile device name to filter (matched case-insensitive)
MOBILE_DEVICE_NAME = "sorairo-iphone"


class NextDNSOutingAdapter(SourceAdapter):
    source_id = "nextdns_outing"
    display_name = "外出推定 (NextDNS)"

    async def is_configured(self) -> bool:
        return bool(settings.nextdns_api_key and settings.nextdns_profile_id)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        if not from_date:
            last_ts = await self.get_last_timestamp()
            if last_ts:
                dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
                from_date = dt.strftime("%Y-%m-%d")
            else:
                from_date = (date.today() - timedelta(days=30)).isoformat()

        headers = {"X-Api-Key": settings.nextdns_api_key}
        profile = settings.nextdns_profile_id

        # Find mobile device ID
        device_id = await self._find_device_id(headers, profile)
        if not device_id:
            logger.warning("NextDNS outing: mobile device '%s' not found", MOBILE_DEVICE_NAME)
            return 0, 0

        start = date.fromisoformat(from_date)
        end = date.today()

        home_cities = self._home_cities()
        all_records = []
        async with httpx.AsyncClient(timeout=30) as client:
            current = start
            while current <= end:
                day_str = current.isoformat()
                next_day = (current + timedelta(days=1)).isoformat()

                cellular, outing, home, total = await self._fetch_day(
                    client, headers, profile, device_id, day_str, next_day, home_cities
                )
                if total > 0:
                    all_records.append((day_str, cellular, outing, home, total))
                current += timedelta(days=1)

        stored = 0
        async with get_db_context() as db:
            for day, cellular, outing, home, total in all_records:
                await db.execute(
                    """INSERT OR REPLACE INTO nextdns_outing
                    (date, cellular_queries, outing_queries, home_queries, total_queries)
                    VALUES (?, ?, ?, ?, ?)""",
                    (day, cellular, outing, home, total),
                )
                stored += 1
            await db.commit()

        logger.info("NextDNS outing: stored %d records", stored)
        return len(all_records), stored

    def _home_cities(self) -> set[str]:
        raw = settings.outing_home_cities or ""
        return {c.strip() for c in raw.split(",") if c.strip()}

    async def _find_device_id(self, headers: dict, profile: str) -> str | None:
        """Find the device ID for the mobile device."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(
                    f"{NEXTDNS_API_BASE}/profiles/{profile}/analytics/devices",
                    headers=headers,
                    params={"from": "-7d", "to": "now"},
                )
                resp.raise_for_status()
                for device in resp.json().get("data", []):
                    if device.get("name", "").lower() == MOBILE_DEVICE_NAME:
                        return device["id"]
            except Exception:
                logger.exception("Failed to fetch NextDNS devices")
        return None

    async def _fetch_day(
        self, client: httpx.AsyncClient, headers: dict, profile: str,
        device_id: str, day: str, next_day: str, home_cities: set[str],
    ) -> tuple[int, int, int, int]:
        """Fetch query counts for a single day.

        Returns (cellular, outing, home, total).
        - cellular: queries from cellular networks (legacy metric).
        - home: queries from non-cellular IPs whose geo.city is in home_cities.
        - outing: all other queries (cellular + non-home Wi-Fi).
        """
        try:
            resp = await client.get(
                f"{NEXTDNS_API_BASE}/profiles/{profile}/analytics/ips",
                headers=headers,
                params={
                    "from": day,
                    "to": next_day,
                    "device": device_id,
                    "limit": 100,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("Failed to fetch NextDNS IPs for %s", day)
            return 0, 0, 0, 0

        cellular = 0
        outing = 0
        home = 0
        total = 0
        for entry in data.get("data", []):
            queries = entry.get("queries", 0)
            total += queries
            network = entry.get("network", {}) or {}
            is_cellular = bool(network.get("cellular"))
            if is_cellular:
                cellular += queries
            city = (entry.get("geo", {}) or {}).get("city", "")
            is_home = (not is_cellular) and (city in home_cities) if home_cities else False
            if is_home:
                home += queries
            else:
                outing += queries

        return cellular, outing, home, total

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            # State: outing percentage (0-100) for CONDITION tab
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'nextdns_outing',
                    'outing',
                    0,
                    CASE WHEN total_queries > 0
                        THEN ROUND(CAST(outing_queries AS REAL) / total_queries * 100, 1)
                        ELSE 0
                    END,
                    '%',
                    json_object(
                        'cellular', cellular_queries,
                        'outing', outing_queries,
                        'home', home_queries,
                        'total', total_queries
                    )
                FROM nextdns_outing"""
            )
            # Activity: outing query count for ACTIVITY stacked chart
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'nextdns_outing_activity',
                    'outing_activity',
                    0,
                    outing_queries,
                    'queries',
                    NULL
                FROM nextdns_outing
                WHERE outing_queries > 0"""
            )
            await db.commit()
        logger.info("NextDNS outing aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, cellular_queries, outing_queries, home_queries, total_queries
                FROM nextdns_outing
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                cellular, outing, home, total = row[1], row[2], row[3], row[4]
                pct = round(outing / total * 100) if total > 0 else 0

                activities.append({
                    "time": time_str,
                    "icon": "🚶",
                    "text": f"外出 {pct}%",
                    "detail": (
                        f"outing: {outing}/{total} (cellular: {cellular}, home: {home})"
                        if include_detail else None
                    ),
                    "color": "#66BB6A",
                    "sort_date": row[0],
                })

            return activities
