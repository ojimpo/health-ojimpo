"""Tests for app.routers.records — read-only raw activity_records endpoint."""
import pytest
from fastapi import HTTPException

from app.routers.records import get_records
from .conftest import add_record


async def test_records_date_range_filter(test_db):
    await add_record("2026-06-01", "lastfm", "music", 10)
    await add_record("2026-06-02", "lastfm", "music", 20)
    await add_record("2026-06-03", "lastfm", "music", 30)
    res = await get_records(from_date="2026-06-02", to_date="2026-06-03")
    assert res.total == 2
    assert [r.date for r in res.records] == ["2026-06-02", "2026-06-03"]
    assert res.truncated is False


async def test_records_source_and_category_filter(test_db):
    await add_record("2026-06-01", "lastfm", "music", 10)
    await add_record("2026-06-01", "strava", "exercise", 5)
    await add_record("2026-06-01", "oura", "sleep", 80)
    res = await get_records(from_date="2026-06-01", to_date="2026-06-01", source="lastfm")
    assert res.total == 1 and res.records[0].source == "lastfm"
    res = await get_records(
        from_date="2026-06-01", to_date="2026-06-01", category="exercise"
    )
    assert res.total == 1 and res.records[0].category == "exercise"
    res = await get_records(
        from_date="2026-06-01", to_date="2026-06-01",
        source="oura", category="sleep",
    )
    assert res.total == 1 and res.records[0].raw_value == 80


async def test_records_limit_and_truncated(test_db):
    for i in range(1, 11):
        await add_record(f"2026-06-{i:02d}", "lastfm", "music", i)
    res = await get_records(from_date="2026-06-01", to_date="2026-06-30", limit=4)
    assert res.total == 10
    assert res.returned == 4
    assert len(res.records) == 4
    assert res.truncated is True


async def test_records_group_by_month(test_db):
    await add_record("2026-05-30", "lastfm", "music", 10, minutes=3)
    await add_record("2026-05-31", "lastfm", "music", 20, minutes=6)
    await add_record("2026-06-01", "lastfm", "music", 40, minutes=12)
    res = await get_records(
        from_date="2026-05-01", to_date="2026-06-30", group_by="month"
    )
    assert res.records == []
    assert [a.period for a in res.aggregates] == ["2026-05", "2026-06"]
    may = res.aggregates[0]
    assert may.raw_value == 30 and may.minutes == 9 and may.days == 2
    june = res.aggregates[1]
    assert june.raw_value == 40 and june.days == 1


async def test_records_group_by_splits_sources(test_db):
    await add_record("2026-06-01", "lastfm", "music", 10)
    await add_record("2026-06-01", "strava", "exercise", 5)
    res = await get_records(
        from_date="2026-06-01", to_date="2026-06-30", group_by="week"
    )
    assert res.total == 2
    assert {(a.source, a.category) for a in res.aggregates} == {
        ("lastfm", "music"),
        ("strava", "exercise"),
    }


async def test_records_invalid_dates(test_db):
    with pytest.raises(HTTPException) as exc:
        await get_records(from_date="not-a-date", to_date="2026-06-01")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await get_records(from_date="2026-06-02", to_date="2026-06-01")
    assert exc.value.status_code == 400
