import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

NEXTDNS_API_BASE = "https://api.nextdns.io"

# EC site domains to track (root domains)
SHOPPING_DOMAINS = {
    "amazon.co.jp",
    "amazon.com",
    "yodobashi.com",
    "rakuten.co.jp",
    "mercari.com",
    "kakaku.com",
}


class NextDNSShoppingAdapter(SourceAdapter):
    source_id = "nextdns_shopping"
    display_name = "買い物 (NextDNS)"

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

                records = await self._fetch_day(client, headers, profile, day_str, next_day)
                all_records.extend(records)
                current += timedelta(days=1)

        stored = 0
        async with get_db_context() as db:
            for day, domain, queries in all_records:
                await db.execute(
                    """INSERT OR REPLACE INTO nextdns_shopping
                    (date, domain, queries) VALUES (?, ?, ?)""",
                    (day, domain, queries),
                )
                stored += 1
            await db.commit()

        logger.info("NextDNS shopping: stored %d records across %d days", stored, (end - start).days + 1)
        return len(all_records), stored

    async def _fetch_day(
        self, client: httpx.AsyncClient, headers: dict, profile: str,
        day: str, next_day: str,
    ) -> list[tuple[str, str, int]]:
        """Fetch shopping domain queries for a single day."""
        records = []
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
                queries = entry.get("queries", 0)
                if root in SHOPPING_DOMAINS or domain in SHOPPING_DOMAINS:
                    display = root if root in SHOPPING_DOMAINS else domain
                    records.append((day, display, queries))

            cursor = data.get("meta", {}).get("pagination", {}).get("cursor")
            if not cursor:
                break

        return records

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'nextdns_shopping',
                    'shopping',
                    0,
                    SUM(queries),
                    'queries',
                    NULL
                FROM nextdns_shopping
                GROUP BY date"""
            )
            await db.commit()
        logger.info("NextDNS shopping aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, SUM(queries) as total,
                       GROUP_CONCAT(domain || ':' || queries, ', ') as breakdown
                FROM nextdns_shopping
                GROUP BY date
                ORDER BY date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                activities.append({
                    "time": time_str,
                    "icon": "🛒",
                    "text": f"ECサイト閲覧 {int(row[1])}回",
                    "detail": row[2] if include_detail else None,
                    "color": "#8BE9FD",
                    "sort_date": row[0],
                })

            return activities
