"""Tests for app.services.scoring — score calculation per method."""
import math
from datetime import date, timedelta

import pytest

from app.services.scoring import (
    calculate_scores,
    calculate_source_score,
    get_effective_baseline,
    get_source_first_dates,
)
from .conftest import add_baseline_history, add_record, add_source

# A fixed past date so the "today bonus" branch stays out of the way.
PAST = date(2026, 6, 1)


def days_before(d: date, n: int) -> str:
    return (d - timedelta(days=n)).isoformat()


# --- legacy windowed sum (decay_half_life = NULL) ---


async def test_windowed_sum_full_week_at_baseline(test_db):
    await add_source("src", "music", base_value=70, aggregation_period=7)
    for i in range(7):
        await add_record(days_before(PAST, i), "src", "music", 10)
    score, raw, base = await calculate_source_score("src", PAST)
    assert score == pytest.approx(100.0)
    assert raw == pytest.approx(70.0)
    assert base == 70


async def test_windowed_sum_prorates_partial_days_for_baseline_classification(test_db):
    # baseline classification: 3 of 7 days with data -> base shrinks to 3/7
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     classification="baseline")
    for i in range(3):
        await add_record(days_before(PAST, i), "src", "music", 10)
    score, _, _ = await calculate_source_score("src", PAST)
    assert score == pytest.approx(100.0)  # 30 / (70 * 3/7) * 100


async def test_windowed_sum_event_classification_no_prorate(test_db):
    await add_source("src", "movie", base_value=70, aggregation_period=7,
                     classification="event")
    for i in range(3):
        await add_record(days_before(PAST, i), "src", "movie", 10)
    score, _, _ = await calculate_source_score("src", PAST)
    assert score == pytest.approx(30 / 70 * 100)


async def test_spontaneity_coefficient_multiplies_score(test_db):
    await add_source("src", "sns", base_value=70, aggregation_period=7,
                     spontaneity_coefficient=0.6)
    for i in range(7):
        await add_record(days_before(PAST, i), "src", "sns", 10)
    score, _, _ = await calculate_source_score("src", PAST)
    assert score == pytest.approx(60.0)


async def test_windowed_sum_ignores_records_outside_window(test_db):
    await add_source("src", "music", base_value=70, aggregation_period=7)
    await add_record(days_before(PAST, 8), "src", "music", 999)
    await add_record(days_before(PAST, 0), "src", "music", 35)
    score, raw, _ = await calculate_source_score("src", PAST)
    assert raw == pytest.approx(35.0)
    # prorate: 1 of 7 days with data
    assert score == pytest.approx(35 / (70 / 7) * 100)


async def test_zero_base_value_returns_zero(test_db):
    await add_source("src", "music", base_value=0, aggregation_period=7)
    await add_record(PAST.isoformat(), "src", "music", 10)
    score, _, _ = await calculate_source_score("src", PAST)
    assert score == 0.0


# --- exponential decay ---


async def test_decay_single_record_today_weight_one(test_db):
    # A single record on for_date has weight exp(0) = 1.
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     decay_half_life=7.0)
    await add_record(PAST.isoformat(), "src", "music", 50)
    score, raw, _ = await calculate_source_score("src", PAST)
    norm = (70 / 7) * (7.0 / math.log(2))
    assert score == pytest.approx(50 / norm * 100)
    assert raw == pytest.approx(50.0)


async def test_decay_half_life_halves_weight(test_db):
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     decay_half_life=7.0)
    await add_record(days_before(PAST, 7), "src", "music", 50)
    score, _, _ = await calculate_source_score("src", PAST)
    norm = (70 / 7) * (7.0 / math.log(2))
    assert score == pytest.approx(50 * 0.5 / norm * 100)


async def test_decay_steady_pace_scores_near_100(test_db):
    # Maintaining exactly base_value/period per day should sit near 100.
    # (Discrete sum slightly exceeds the continuous-integral norm.)
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     decay_half_life=7.0)
    for i in range(36):  # lookback is 5x half_life
        await add_record(days_before(PAST, i), "src", "music", 10)
    score, _, _ = await calculate_source_score("src", PAST)
    assert 100 <= score <= 110


async def test_decay_ignores_records_beyond_lookback(test_db):
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     decay_half_life=7.0)
    await add_record(days_before(PAST, 36), "src", "music", 99999)
    score, raw, _ = await calculate_source_score("src", PAST)
    assert score == 0.0
    assert raw == 0.0


# --- daily_avg ---


async def test_daily_avg_scores_average_against_base(test_db):
    await add_source("oura", "sleep", base_value=80, aggregation_period=7,
                     score_method="daily_avg", display_type="state")
    await add_record(days_before(PAST, 0), "oura", "sleep", 80)
    await add_record(days_before(PAST, 1), "oura", "sleep", 90)
    score, raw, _ = await calculate_source_score("oura", PAST)
    assert raw == pytest.approx(85.0)
    assert score == pytest.approx(85 / 80 * 100)


async def test_daily_avg_excludes_stress_category(test_db):
    await add_source("oura", "sleep", base_value=80, aggregation_period=7,
                     score_method="daily_avg", display_type="state")
    await add_record(PAST.isoformat(), "oura", "sleep", 80)
    await add_record(PAST.isoformat(), "oura", "stress", 999)
    score, _, _ = await calculate_source_score("oura", PAST)
    assert score == pytest.approx(100.0)


async def test_daily_avg_applies_category_weights(test_db):
    await add_source("oura", "sleep", base_value=80, aggregation_period=7,
                     score_method="daily_avg", display_type="state",
                     category_weights='{"readiness": 0.6, "sleep": 0.4}')
    await add_record(PAST.isoformat(), "oura", "sleep", 100)
    await add_record(PAST.isoformat(), "oura", "readiness", 50)
    score, raw, _ = await calculate_source_score("oura", PAST)
    expected_daily = 100 * 0.4 + 50 * 0.6
    assert raw == pytest.approx(expected_daily)
    assert score == pytest.approx(expected_daily / 80 * 100)


async def test_daily_avg_no_data_returns_zero(test_db):
    await add_source("oura", "sleep", base_value=80, score_method="daily_avg")
    score, raw, _ = await calculate_source_score("oura", PAST)
    assert score == 0.0
    assert raw == 0.0


# --- today bonus ---


async def test_today_data_added_as_bonus_windowed(test_db):
    today = date.today()
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     classification="event")
    for i in range(1, 8):  # yesterday back 7 days = main window
        await add_record(days_before(today, i), "src", "music", 10)
    score_without_today, _, _ = await calculate_source_score("src", today)
    assert score_without_today == pytest.approx(100.0)

    await add_record(today.isoformat(), "src", "music", 7)
    score_with_today, raw, _ = await calculate_source_score("src", today)
    assert raw == pytest.approx(77.0)
    assert score_with_today == pytest.approx(110.0)


async def test_today_data_added_as_bonus_decay(test_db):
    today = date.today()
    await add_source("src", "music", base_value=70, aggregation_period=7,
                     decay_half_life=7.0)
    await add_record(today.isoformat(), "src", "music", 50)
    score, raw, _ = await calculate_source_score("src", today)
    norm = (70 / 7) * (7.0 / math.log(2))
    assert score == pytest.approx(50 / norm * 100)
    assert raw == pytest.approx(50.0)


async def test_daily_avg_today_only_data_still_scores(test_db):
    # 基準窓（昨日以前）が空でも、当日データがあればスコアに反映される
    today = date.today()
    await add_source("oura", "sleep", base_value=80, aggregation_period=7,
                     score_method="daily_avg", display_type="state")
    await add_record(today.isoformat(), "oura", "sleep", 80)
    score, raw, _ = await calculate_source_score("oura", today)
    assert raw == pytest.approx(80.0)
    assert score == pytest.approx(100.0)


# --- baseline history ---


async def test_baseline_history_overrides_default(test_db):
    await add_source("src", "music", base_value=70, aggregation_period=7)
    await add_baseline_history("src", "2026-05-01", 140)

    base_before, _, _ = await get_effective_baseline("src", "2026-04-30")
    base_after, _, _ = await get_effective_baseline("src", "2026-05-01")
    assert base_before == 70
    assert base_after == 140


async def test_baseline_history_latest_entry_wins(test_db):
    await add_source("src", "music", base_value=70)
    await add_baseline_history("src", "2026-01-01", 100)
    await add_baseline_history("src", "2026-05-01", 200)
    base, _, _ = await get_effective_baseline("src", "2026-06-01")
    assert base == 200


# --- calculate_scores aggregation ---


async def test_calculate_scores_averages_sources_within_category(test_db):
    # Two sources in one category: category score = mean of source scores.
    await add_source("a", "vitality", base_value=70, aggregation_period=7,
                     classification="baseline")
    await add_source("b", "vitality", base_value=70, aggregation_period=7,
                     classification="baseline")
    for i in range(7):
        await add_record(days_before(PAST, i), "a", "vitality", 10)   # 100
        await add_record(days_before(PAST, i), "b", "vitality", 5)    # 50
    result = await calculate_scores(PAST)
    assert result["baseline_avg"] == pytest.approx(75.0)
    assert result["health_status"].value == "NORMAL"


async def test_calculate_scores_thresholds(test_db):
    await add_source("a", "music", base_value=70, aggregation_period=7,
                     classification="baseline", display_type="activity")
    for i in range(7):
        await add_record(days_before(PAST, i), "a", "music", 3)  # 21/70 = 30
    result = await calculate_scores(PAST)
    assert result["baseline_avg"] == pytest.approx(30.0)
    assert result["health_status"].value == "CRITICAL"
    assert result["cultural_status"].value == "LOW"


async def test_calculate_scores_excludes_sources_without_data_yet(test_db):
    # A source whose first record is after for_date must not drag the average.
    await add_source("a", "music", base_value=70, aggregation_period=7,
                     classification="baseline")
    await add_source("late", "reading", base_value=70, aggregation_period=7,
                     classification="baseline")
    for i in range(7):
        await add_record(days_before(PAST, i), "a", "music", 10)
    await add_record((PAST + timedelta(days=30)).isoformat(), "late", "reading", 10)
    result = await calculate_scores(PAST)
    assert result["baseline_avg"] == pytest.approx(100.0)


async def test_calculate_scores_caps_category_contribution(test_db):
    # A bursty category contributes at most CATEGORY_SCORE_CAP to each axis;
    # the per-source score itself stays uncapped (charts/cards show it raw).
    await add_source("burst", "photo", base_value=7, aggregation_period=7,
                     classification="baseline", display_type="activity")
    await add_source("calm", "music", base_value=70, aggregation_period=7,
                     classification="baseline", display_type="activity")
    for i in range(7):
        await add_record(days_before(PAST, i), "burst", "photo", 10)  # 70/7 = 1000
        await add_record(days_before(PAST, i), "calm", "music", 10)   # 70/70 = 100
    result = await calculate_scores(PAST)
    assert result["baseline_avg"] == pytest.approx(150.0)  # (200 + 100) / 2
    assert result["cultural_pct"] == pytest.approx(150.0)
    score, _, _ = await calculate_source_score("burst", PAST)
    assert score == pytest.approx(1000.0)


async def test_get_source_first_dates(test_db):
    await add_source("a", "music")
    await add_record("2026-01-05", "a", "music", 1)
    await add_record("2026-01-03", "a", "music", 1)
    first = await get_source_first_dates()
    assert first == {"a": "2026-01-03"}
