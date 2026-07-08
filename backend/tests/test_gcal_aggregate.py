"""Tests for Google Calendar aggregate: 複数日イベントの日割り展開。"""
from app import database
from app.sources.google_calendar import GoogleCalendarAdapter


async def _add_event(event_id: str, source: str, start: str, end: str):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO gcal_events (id, source, summary, start_date, end_date, calendar_id)
            VALUES (?, ?, 'test', ?, ?, 'cal')""",
            (event_id, source, start, end),
        )
        await db.commit()


async def _records(source: str) -> list[tuple]:
    async with database.get_db_context() as db:
        return [
            tuple(r)
            for r in await db.execute_fetchall(
                "SELECT date, raw_value FROM activity_records WHERE source = ? ORDER BY date",
                (source,),
            )
        ]


async def test_single_day_timed_event(test_db):
    # 時刻ありの当日予定: start == end
    await _add_event("e1", "gcal_private", "2026-07-01", "2026-07-01")
    await GoogleCalendarAdapter("gcal_private").aggregate()
    assert await _records("gcal_private") == [("2026-07-01", 1.0)]


async def test_single_day_allday_event(test_db):
    # 終日1日予定: Google APIのend.dateはexclusiveなので翌日になる
    await _add_event("e1", "gcal_private", "2026-07-01", "2026-07-02")
    await GoogleCalendarAdapter("gcal_private").aggregate()
    assert await _records("gcal_private") == [("2026-07-01", 1.0)]


async def test_multiday_trip_expands_to_each_day(test_db):
    # 高知旅行パターン: 4/29〜5/3(exclusive) = 4/29〜5/2の4日間
    await _add_event("e1", "gcal_private", "2026-04-29", "2026-05-03")
    await GoogleCalendarAdapter("gcal_private").aggregate()
    assert await _records("gcal_private") == [
        ("2026-04-29", 1.0),
        ("2026-04-30", 1.0),
        ("2026-05-01", 1.0),
        ("2026-05-02", 1.0),
    ]


async def test_overnight_timed_event_counts_start_day_only(test_db):
    # 深夜解散の飲み会等（時刻ありでend_dateが翌日）は開始日のみ
    await _add_event("e1", "gcal_private", "2026-03-08", "2026-03-09")
    await GoogleCalendarAdapter("gcal_private").aggregate()
    assert await _records("gcal_private") == [("2026-03-08", 1.0)]


async def test_overlapping_events_sum_per_day(test_db):
    await _add_event("e1", "gcal_private", "2026-07-04", "2026-07-06")  # 7/4-7/5
    await _add_event("e2", "gcal_private", "2026-07-04", "2026-07-04")  # 7/4のみ
    await GoogleCalendarAdapter("gcal_private").aggregate()
    assert await _records("gcal_private") == [("2026-07-04", 2.0), ("2026-07-05", 1.0)]


async def test_pathological_long_event_capped(test_db):
    # 誤登録の1年イベントは30日で打ち切り
    await _add_event("e1", "gcal_private", "2026-01-01", "2027-01-01")
    await GoogleCalendarAdapter("gcal_private").aggregate()
    records = await _records("gcal_private")
    assert len(records) == 30
    assert records[0][0] == "2026-01-01"
    assert records[-1][0] == "2026-01-30"


async def test_sources_do_not_interfere(test_db):
    await _add_event("e1", "gcal_private", "2026-07-01", "2026-07-01")
    await _add_event("e2", "gcal_live", "2026-07-02", "2026-07-02")
    await GoogleCalendarAdapter("gcal_private").aggregate()
    await GoogleCalendarAdapter("gcal_live").aggregate()
    assert await _records("gcal_private") == [("2026-07-01", 1.0)]
    assert await _records("gcal_live") == [("2026-07-02", 1.0)]
