"""Tests for app.services.aggregation — chart data and card assembly."""
from datetime import date, timedelta

import pytest

from app.models.enums import TimeRange
from app.services.aggregation import (
    _compute_point_status,
    _get_category_cards,
    _get_chart_data,
    _map_category,
)
from app.services.scoring import calculate_source_score
from .conftest import add_record, add_source

PAST = date(2026, 6, 1)
THRESHOLDS = {"score_normal_threshold": 70, "score_caution_threshold": 40}


def days_before(d: date, n: int) -> str:
    return (d - timedelta(days=n)).isoformat()


# --- _map_category ---


def test_map_category_passthrough_and_alias():
    assert _map_category("music") == "music"
    assert _map_category("fitness") == "exercise"
    assert _map_category("sleep") == "sleep"


# --- _compute_point_status ---


def test_point_status_thresholds():
    h, c, hs, cs = _compute_point_status(
        {"music": 80, "reading": 60}, {"music"}, {"music", "reading"}, THRESHOLDS
    )
    assert (h, hs) == ("NORMAL", 80.0)
    assert (c, cs) == ("RICH", 70.0)


def test_point_status_missing_activity_counts_as_zero():
    # An eligible activity category with no score contributes 0 to the average.
    _, c, _, cs = _compute_point_status({"music": 80}, set(), {"music", "reading"}, THRESHOLDS)
    assert cs == 40.0
    assert c == "MODERATE"


def test_point_status_empty_is_none():
    h, c, hs, cs = _compute_point_status({}, set(), set(), THRESHOLDS)
    assert (h, c, hs, cs) == (None, None, None, None)


def test_point_status_boundaries():
    h, _, _, _ = _compute_point_status({"m": 70}, {"m"}, set(), THRESHOLDS)
    assert h == "NORMAL"
    h, _, _, _ = _compute_point_status({"m": 40}, {"m"}, set(), THRESHOLDS)
    assert h == "CAUTION"
    h, _, _, _ = _compute_point_status({"m": 39.9}, {"m"}, set(), THRESHOLDS)
    assert h == "CRITICAL"


# --- chart data ---


async def test_chart_daily_point_count_and_labels(test_db):
    await add_source("src", "music", base_value=70, decay_half_life=7.0)
    await add_record(PAST.isoformat(), "src", "music", 10)
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    assert len(points) == 31  # for_date-30 .. for_date inclusive
    assert points[-1].date == f"{PAST.month}/{PAST.day}"
    assert points[0].date == "5/2"


async def test_chart_weekly_buckets_for_one_year(test_db):
    await add_source("src", "music", base_value=70, decay_half_life=7.0)
    await add_record(PAST.isoformat(), "src", "music", 10)
    points = await _get_chart_data(TimeRange.ONE_YEAR, PAST)
    assert len(points) == 53  # 365/7 -> 53 week starts


async def test_chart_decay_source_matches_source_score(test_db):
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     decay_half_life=7.0)
    for i in range(20):
        await add_record(days_before(PAST, i), "src", "music", 5 + (i % 3))
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    expected, _, _ = await calculate_source_score("src", PAST)
    assert points[-1].music == pytest.approx(round(expected, 1))


async def test_chart_state_category_uses_fixed_daily_baseline(test_db):
    # sleep uses the fixed daily baseline 80, not source_settings.base_value.
    await add_source("oura", "sleep", base_value=999, aggregation_period=7,
                     score_method="daily_avg", display_type="state")
    await add_record(PAST.isoformat(), "oura", "sleep", 80)
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    assert points[-1].sleep == pytest.approx(100.0)


async def test_chart_excludes_source_before_first_record(test_db):
    await add_source("src", "music", base_value=70, decay_half_life=7.0)
    mid = PAST - timedelta(days=10)
    await add_record(mid.isoformat(), "src", "music", 10)
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    # Before the source's first record: no health status at all
    assert points[0].health_status is None
    assert points[-1].health_status is not None


async def test_chart_card_only_source_not_stacked(test_db):
    await add_source("src", "cd", base_value=70, decay_half_life=7.0,
                     display_type="card_only")
    for i in range(10):
        await add_record(days_before(PAST, i), "src", "cd", 10)
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    assert points[-1].cd == 0


async def test_chart_non_decay_coefficient_multiplies_score(test_db):
    # scoring.py と同じ向きで係数が掛かること（以前は基準側に掛かり逆方向に効いていた）
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     spontaneity_coefficient=0.6)
    await add_record(PAST.isoformat(), "src", "music", 10)
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    # daily base = 10, raw 10 -> 100% * 0.6
    assert points[-1].music == pytest.approx(60.0)


async def test_chart_uses_minutes_when_positive(test_db):
    # Non-decay sources aggregate minutes if set, else raw_value.
    await add_source("src", "music", base_value=70, aggregation_period=7)
    await add_record(PAST.isoformat(), "src", "music", 999, minutes=10)
    points = await _get_chart_data(TimeRange.ONE_MONTH, PAST)
    # daily base = 70/7 = 10 -> minutes 10 == 100%
    assert points[-1].music == pytest.approx(100.0)


# --- category cards ---


async def test_category_cards_average_sources_and_week_change(test_db):
    await add_source("a", "vitality", base_value=70, aggregation_period=7,
                     classification="event")
    await add_source("b", "vitality", base_value=70, aggregation_period=7,
                     classification="event")
    for i in range(7):
        await add_record(days_before(PAST, i), "a", "vitality", 10)   # 100
        await add_record(days_before(PAST, i), "b", "vitality", 5)    # 50
        await add_record(days_before(PAST, i + 7), "a", "vitality", 5)  # prev 50
        await add_record(days_before(PAST, i + 7), "b", "vitality", 5)  # prev 50
    cards = await _get_category_cards(PAST)
    assert len(cards) == 1
    card = cards[0]
    assert card.key == "vitality"
    assert card.current == pytest.approx(75.0)
    assert card.previous == pytest.approx(50.0)
    assert card.change == pytest.approx(25.0)
