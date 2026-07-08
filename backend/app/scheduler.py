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


def _send_subjective_question():
    from .services.subjective import send_daily_question

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(send_daily_question())
    except Exception:
        logger.exception("Subjective question send failed")
    finally:
        loop.close()


def _send_source_health_report():
    from .services.source_health import send_weekly_report

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(send_weekly_report())
    except Exception:
        logger.exception("Source health report send failed")
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
    # コンテナはUTC。デフォルト12:00 UTC = 21:00 JST
    _scheduler.add_job(
        _send_subjective_question,
        "cron",
        hour=settings.subjective_push_hour_utc,
        minute=0,
        id="subjective_daily_question",
    )
    # 週次ソースヘルスレポート。主観フィードバック質問(:00)と被らないよう:05
    _scheduler.add_job(
        _send_source_health_report,
        "cron",
        day_of_week=settings.health_report_weekday,
        hour=settings.health_report_hour_utc,
        minute=5,
        id="source_health_weekly_report",
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
