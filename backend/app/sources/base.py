import logging
from abc import ABC, abstractmethod
from datetime import date

from ..database import get_db_context

logger = logging.getLogger(__name__)


def format_relative_day(
    d: date, today: date | None = None, allow_future: bool = False
) -> str:
    """Format a date as a relative day label for the activity feed.

    allow_future=False clamps future dates to "今日" so feeds can never
    render "-1日前" for clock skew or stray future timestamps. Use
    allow_future=True for sources where upcoming items are legitimate
    (e.g. calendar events).
    """
    if today is None:
        today = date.today()
    diff = (today - d).days
    if diff < 0:
        if not allow_future:
            return "今日"
        ahead = -diff
        return "明日" if ahead == 1 else f"{ahead}日後"
    if diff == 0:
        return "今日"
    if diff == 1:
        return "1日前"
    return f"{diff}日前"


class SourceAdapter(ABC):
    """Base class for all data source adapters."""

    source_id: str
    display_name: str

    @abstractmethod
    async def is_configured(self) -> bool:
        """Check if this source has valid credentials/config."""
        ...

    @abstractmethod
    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        """Fetch raw data from external API, store in source-specific table.
        Returns (records_fetched, records_stored).
        """
        ...

    @abstractmethod
    async def aggregate(self) -> None:
        """Aggregate raw data into activity_records table."""
        ...

    @abstractmethod
    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        """Return recent activities for the activity feed.
        Each dict has: time, icon, text, detail, color.
        """
        ...

    async def get_last_timestamp(self) -> int | None:
        """Get the last successful ingest timestamp from ingest_log."""
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                "SELECT last_timestamp FROM ingest_log WHERE source = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
                (self.source_id,),
            )
            if rows and rows[0][0]:
                return rows[0][0]
        return None
