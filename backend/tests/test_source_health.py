"""Tests for the weekly source health report + migration re-run guard."""
from datetime import date

from app import database
from app.services.source_health import build_report, format_report

from .conftest import add_record, add_source

TODAY = date(2026, 7, 8)


async def _add_ingest_log(source: str, status: str, error: str | None = None):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO ingest_log (source, started_at, completed_at, status, error_message)
            VALUES (?, datetime('now'), datetime('now'), ?, ?)""",
            (source, status, error),
        )
        await db.commit()


async def _add_oauth_token(source_id: str):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO oauth_tokens (source_id, access_token, refresh_token, expires_at)
            VALUES (?, 'at', 'rt', 0)""",
            (source_id,),
        )
        await db.commit()


async def _no_token(source_id: str):
    return None


async def _valid_token(source_id: str):
    return "token"


async def test_ok_source(test_db):
    await add_source("lastfm", "music", classification="baseline")
    await add_record(TODAY.isoformat(), "lastfm", "music", 10)
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_stale_baseline_source_warns(test_db):
    await add_source("lastfm", "music", classification="baseline")
    await add_record("2026-07-01", "lastfm", "music", 10)  # 7日前 > 3日
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "warn"
    assert "7日前" in report[0]["detail"]


async def test_stale_event_source_tolerated(test_db):
    await add_source("steam", "game", classification="event")
    await add_record("2026-07-01", "steam", "game", 1)  # 7日前 <= 45日
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_broken_oauth_token(test_db):
    await add_source("gcal_private", "calendar", classification="event")
    await add_record(TODAY.isoformat(), "gcal_private", "calendar", 1)
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "broken"
    assert "トークン失効" in report[0]["detail"]
    # 再認証URLがレポート本文に含まれる
    assert "/api/oauth/gcal_private/authorize" in format_report(report, today=TODAY)


async def test_valid_oauth_token_is_ok(test_db):
    await add_source("gcal_private", "calendar", classification="event")
    await add_record(TODAY.isoformat(), "gcal_private", "calendar", 1)
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_valid_token)
    assert report[0]["level"] == "ok"


async def test_failed_ingest_is_broken(test_db):
    await add_source("steam", "game", classification="event")
    await add_record(TODAY.isoformat(), "steam", "game", 1)
    await _add_ingest_log("steam", "failed", "boom")
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "broken"
    assert "boom" in report[0]["detail"]


async def test_prefixed_record_sources(test_db):
    """stravaのようにactivity_recordsへ別名（strava_ride等）で入るソース。"""
    await add_source("strava", "exercise", classification="baseline")
    await add_record(TODAY.isoformat(), "strava_ride", "exercise", 30)
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_broken_sorted_first(test_db):
    await add_source("lastfm", "music", classification="baseline")
    await add_record(TODAY.isoformat(), "lastfm", "music", 10)
    await add_source("gcal_private", "calendar", classification="event")
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert [r["id"] for r in report] == ["gcal_private", "lastfm"]


async def test_migrations_do_not_rerun(test_db):
    """再init_dbでUPDATE/DELETE系マイグレーション（027等）が再実行されないこと。

    以前はエラーの出ないマイグレーションが起動のたびに再実行され、
    claude/githubのactivity_recordsが毎回消えていた。
    """
    await add_record(TODAY.isoformat(), "claude", "coding", 100)
    await database.init_db()
    async with database.get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT COUNT(*) FROM activity_records WHERE source = 'claude'"
        )
    assert rows[0][0] == 1
