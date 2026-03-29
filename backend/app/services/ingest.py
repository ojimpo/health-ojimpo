import logging

from ..database import get_db_context
from ..sources.registry import get_adapter, get_configured_adapters

logger = logging.getLogger(__name__)


async def run_ingest_pipeline(source_id: str = "lastfm", from_date: str | None = None):
    """Generic ingestion pipeline: fetch → store → aggregate for any source."""
    adapter = get_adapter(source_id)
    if not adapter:
        logger.error("Unknown source: %s", source_id)
        return

    if not await adapter.is_configured():
        logger.warning("Source %s is not configured, skipping", source_id)
        return

    logger.info("Starting %s ingest pipeline", source_id)

    # Create ingest log entry
    async with get_db_context() as db:
        cursor = await db.execute(
            "INSERT INTO ingest_log (source, started_at, status) VALUES (?, datetime('now'), 'running')",
            (source_id,),
        )
        log_id = cursor.lastrowid
        await db.commit()

    try:
        fetched, stored = await adapter.fetch_and_store(from_date)
        await adapter.aggregate()

        # Get last timestamp for ingest log
        last_ts = await adapter.get_last_timestamp()

        async with get_db_context() as db:
            await db.execute(
                """UPDATE ingest_log
                SET completed_at = datetime('now'), status = 'completed',
                    records_fetched = ?, records_stored = ?, last_timestamp = ?
                WHERE id = ?""",
                (fetched, stored, last_ts, log_id),
            )
            # Auto-activate source on successful ingest
            if stored > 0:
                await db.execute(
                    "UPDATE source_settings SET status = 'active' WHERE id = ? AND status = 'coming_soon'",
                    (source_id,),
                )
            await db.commit()

        logger.info("%s ingest pipeline completed successfully", source_id)

    except Exception as e:
        logger.exception("%s ingest pipeline failed", source_id)
        async with get_db_context() as db:
            await db.execute(
                """UPDATE ingest_log
                SET completed_at = datetime('now'), status = 'failed', error_message = ?
                WHERE id = ?""",
                (str(e), log_id),
            )
            await db.commit()


async def run_all_ingest():
    """Run ingest for all configured sources."""
    adapters = await get_configured_adapters()
    for adapter in adapters:
        try:
            await run_ingest_pipeline(adapter.source_id)
        except Exception:
            logger.exception("Failed to ingest %s", adapter.source_id)

    # Check for status transitions and send notifications
    try:
        from .notification import check_and_notify
        await check_and_notify()
    except Exception:
        logger.exception("Notification check failed")
