import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _run_all_ingest():
    from .services.ingest import run_all_ingest

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run_all_ingest())
    except Exception:
        logger.exception("Scheduled ingest failed")
    finally:
        loop.close()


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_all_ingest,
        "interval",
        hours=settings.fetch_interval_hours,
        id="all_sources_ingest",
    )
    _scheduler.start()
    logger.info(
        "Scheduler started: ingest every %d hours", settings.fetch_interval_hours
    )


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get_next_run_time() -> str | None:
    if not _scheduler:
        return None
    job = _scheduler.get_job("all_sources_ingest")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
