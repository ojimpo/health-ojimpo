import logging
from datetime import date, datetime, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class SyncGatewayAdapter(SourceAdapter):
    """Adapter for sources stored in sync-gateway (Filmarks, 読書メーター)."""

    def __init__(
        self,
        source_slug: str,
        source_id: str,
        display_name: str,
        category: str,
        icon: str,
        color: str,
        raw_unit: str,
        activity_text: str,
        value_field: str | None = None,
    ):
        self.source_slug = source_slug
        self.source_id = source_id
        self.display_name = display_name
        self._category = category
        self._icon = icon
        self._color = color
        self._raw_unit = raw_unit
        self._activity_text = activity_text
        # When set, sum this numeric field (from payload or top-level) per day
        # instead of counting records. e.g. studyplus emits one record/day with
        # payload.minutes, and we want the daily total minutes — not "1".
        self._value_field = value_field

    async def is_configured(self) -> bool:
        return bool(settings.sync_gateway_base_url)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        base_url = settings.sync_gateway_base_url.rstrip("/")

        # Use last_timestamp for incremental fetch
        params: dict = {"source": self.source_slug, "limit": 500}
        last_ts = await self.get_last_timestamp()
        if last_ts:
            dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
            params["from"] = dt.isoformat()

        try:
            records = []
            async with httpx.AsyncClient(timeout=15) as client:
                while True:
                    resp = await client.get(f"{base_url}/api/v1/records", params=params)
                    resp.raise_for_status()
                    batch = resp.json()
                    if not batch:
                        break
                    records.extend(batch)
                    if len(batch) < 500:
                        break
                    # API returns ingested_at DESC; paginate by setting 'to' to oldest item
                    params["to"] = batch[-1]["ingested_at"]
        except Exception:
            logger.exception("Failed to fetch from sync-gateway for %s", self.source_slug)
            return 0, 0

        # Group by event_date. Default: count records (1 book = 1, 1 movie = 1).
        # value_field mode: sum a numeric field (e.g. studyplus minutes per day).
        daily_values: dict[str, float] = {}
        for rec in records:
            event_date = rec.get("event_date")
            if not event_date:
                continue
            d = event_date[:10]  # YYYY-MM-DD
            if from_date and d < from_date:
                continue
            if self._value_field:
                payload = rec.get("payload") or {}
                raw = payload.get(self._value_field, rec.get(self._value_field, 0))
                try:
                    daily_values[d] = daily_values.get(d, 0.0) + float(raw or 0)
                except (TypeError, ValueError):
                    continue
            else:
                daily_values[d] = daily_values.get(d, 0.0) + 1

        stored = 0
        async with get_db_context() as db:
            for d, value in daily_values.items():
                # For count mode keep integer values; round summed minutes to 1 decimal.
                v = round(value, 1) if self._value_field else value
                await db.execute(
                    """INSERT OR REPLACE INTO activity_records
                    (date, source, category, minutes, raw_value, raw_unit, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)""",
                    (d, self.source_id, self._category, v, v, self._raw_unit),
                )
                stored += 1
            await db.commit()

        logger.info(
            "%s: stored %d daily records from %d items",
            self.source_id, stored, len(records),
        )
        return len(records), stored

    async def aggregate(self) -> None:
        # Already written directly to activity_records in fetch_and_store
        pass

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        # Try to get detailed info from sync-gateway API
        activities = await self._get_detailed_activities(limit, include_detail)
        if activities is not None:
            return activities

        # Fallback: use activity_records counts
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, raw_value FROM activity_records
                WHERE source = ?
                ORDER BY date DESC LIMIT ?""",
                (self.source_id, limit),
            )

            result = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)
                count = int(row[1])
                result.append({
                    "time": time_str,
                    "icon": self._icon,
                    "text": f"{self._activity_text}{count}{self._raw_unit}",
                    "detail": None,
                    "color": self._color,
                    "sort_date": row[0],
                })
            return result

    async def _get_detailed_activities(
        self, limit: int, include_detail: bool
    ) -> list[dict] | None:
        """Fetch individual records from sync-gateway for rich activity feed."""
        base_url = settings.sync_gateway_base_url.rstrip("/")
        params = {"source": self.source_slug, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base_url}/api/v1/records", params=params)
                resp.raise_for_status()
                records = resp.json()
        except Exception:
            logger.debug("Could not fetch detailed activities from sync-gateway for %s", self.source_slug)
            return None

        activities = []
        today = date.today()
        for rec in records:
            event_date = rec.get("event_date")
            if not event_date:
                continue
            d = date.fromisoformat(event_date[:10])
            time_str = format_relative_day(d, today)

            title = rec.get("title", "")
            author = rec.get("author", "")
            detail = f"{author}" if include_detail and author else None

            # value_field mode (e.g. studyplus): surface the daily total in the detail.
            if self._value_field:
                payload = rec.get("payload") or {}
                v = payload.get(self._value_field, rec.get(self._value_field))
                if v is not None:
                    minutes_label = f"{round(float(v))}{self._raw_unit}"
                    detail = f"{detail} / {minutes_label}" if detail else minutes_label

            activities.append({
                "time": time_str,
                "icon": self._icon,
                "text": title if (include_detail and title) else self._activity_text,
                "detail": detail,
                "color": self._color,
                "sort_date": event_date[:10],
            })

        return activities
