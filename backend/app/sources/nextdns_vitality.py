"""NextDNS Vitality Index — proxy for libido/vitality via adult content DNS queries.

Privacy design:
- Domain list is in code but DB stores ONLY aggregate daily query count.
- No domain names are stored, logged, or exposed via API.
- Dashboard displays abstract "Vitality Index" score.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

NEXTDNS_API_BASE = "https://api.nextdns.io"

# Abstract domain set — only aggregate counts are stored
_VITALITY_DOMAINS = {
    "missav.ai",
    "tktube.com",
    "spankbang.com",
    "dmm.co.jp",
    "fanza.com",
    "fantia.jp",
    "pornhub.com",
    "xvideos.com",
    "xhamster.com",
    "xnxx.com",
    "dlsite.com",
    "iwara.tv",
    "nhentai.net",
    "hanime.tv",
}


class NextDNSVitalityAdapter(SourceAdapter):
    source_id = "nextdns_vitality"
    display_name = "Vitality Index"

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

        start = date.fromisoformat(from_date)
        end = date.today()

        all_records = []
        async with httpx.AsyncClient(timeout=30) as client:
            current = start
            while current <= end:
                day_str = current.isoformat()
                next_day = (current + timedelta(days=1)).isoformat()

                total = await self._fetch_day_total(client, headers, profile, day_str, next_day)
                if total > 0:
                    all_records.append((day_str, total))
                current += timedelta(days=1)

        stored = 0
        async with get_db_context() as db:
            for day, total in all_records:
                await db.execute(
                    """INSERT OR REPLACE INTO nextdns_vitality
                    (date, queries) VALUES (?, ?)""",
                    (day, total),
                )
                stored += 1
            await db.commit()

        logger.info("NextDNS vitality: stored %d records", stored)
        return len(all_records), stored

    async def _fetch_day_total(
        self, client: httpx.AsyncClient, headers: dict, profile: str,
        day: str, next_day: str,
    ) -> int:
        """Fetch total vitality domain queries for a single day. Returns aggregate only."""
        total = 0
        cursor = None
        while True:
            params = {
                "from": day,
                "to": next_day,
                "limit": 500,
                "root": "true",
            }
            if cursor:
                params["cursor"] = cursor

            try:
                resp = await client.get(
                    f"{NEXTDNS_API_BASE}/profiles/{profile}/analytics/domains",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.exception("Failed to fetch NextDNS domains for %s", day)
                break

            for entry in data.get("data", []):
                domain = entry.get("domain", "")
                root = entry.get("root", domain)
                if root in _VITALITY_DOMAINS or domain in _VITALITY_DOMAINS:
                    total += entry.get("queries", 0)

            cursor = data.get("meta", {}).get("pagination", {}).get("cursor")
            if not cursor:
                break

        return total

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'nextdns_vitality',
                    'vitality',
                    0,
                    queries,
                    'queries',
                    NULL
                FROM nextdns_vitality"""
            )
            await db.commit()
        logger.info("NextDNS vitality aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, queries FROM nextdns_vitality
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                activities.append({
                    "time": time_str,
                    "icon": "💚",
                    "text": f"Vitality {int(row[1])}",
                    "detail": None,  # Never expose domain details
                    "color": "#D4A574",
                    "sort_date": row[0],
                })

            return activities
