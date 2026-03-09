import logging
from abc import ABC, abstractmethod

from ..database import get_db_context

logger = logging.getLogger(__name__)


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
