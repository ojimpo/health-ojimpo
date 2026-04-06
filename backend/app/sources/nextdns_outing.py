"""NextDNS Outing Estimation — cellular query ratio as outing proxy.

Uses iPhone's cellular vs total DNS queries to estimate daily outing level.
Home = Wi-Fi (cellular=0), Out = mobile network (cellular > 0).
"""

import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter

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

        all_records = []
        async with httpx.AsyncClient(timeout=30) as client:
            current = start
            while current <= end:
                day_str = current.isoformat()
                next_day = (current + timedelta(days=1)).isoformat()

                cellular, total = await self._fetch_day(
                    client, headers, profile, device_id, day_str, next_day
                )
                if total > 0:
                    all_records.append((day_str, cellular, total))
                current += timedelta(days=1)

        stored = 0
        async with get_db_context() as db:
            for day, cellular, total in all_records:
                await db.execute(
                    """INSERT OR REPLACE INTO nextdns_outing
                    (date, cellular_queries, total_queries) VALUES (?, ?, ?)""",
                    (day, cellular, total),
                )
                stored += 1
            await db.commit()

        logger.info("NextDNS outing: stored %d records", stored)
        return len(all_records), stored

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
        device_id: str, day: str, next_day: str,
    ) -> tuple[int, int]:
        """Fetch cellular and total query counts for a single day."""
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
            return 0, 0

        cellular = 0
        total = 0
        for entry in data.get("data", []):
            queries = entry.get("queries", 0)
            total += queries
            if entry.get("network", {}).get("cellular"):
                cellular += queries

        return cellular, total

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
                        THEN ROUND(CAST(cellular_queries AS REAL) / total_queries * 100, 1)
                        ELSE 0
                    END,
                    '%',
                    json_object('cellular', cellular_queries, 'total', total_queries)
                FROM nextdns_outing"""
            )
            # Activity: cellular query count for ACTIVITY stacked chart
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'nextdns_outing_activity',
                    'outing_activity',
                    0,
                    cellular_queries,
                    'queries',
                    NULL
                FROM nextdns_outing
                WHERE cellular_queries > 0"""
            )
            await db.commit()
        logger.info("NextDNS outing aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, cellular_queries, total_queries FROM nextdns_outing
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                cellular, total = row[1], row[2]
                pct = round(cellular / total * 100) if total > 0 else 0

                activities.append({
                    "time": time_str,
                    "icon": "🚶",
                    "text": f"外出 {pct}%",
                    "detail": f"cellular: {cellular}/{total}" if include_detail else None,
                    "color": "#66BB6A",
                    "sort_date": row[0],
                })

            return activities
