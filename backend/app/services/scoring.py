"""Score calculation.

Each source is scored as a percentage of its baseline (100 = baseline met,
no upper cap), by one of three methods selected via source_settings:

- ``daily_avg``: average of daily values vs base_value (Oura-style state
  scores). ``decay_half_life`` is ignored; 'stress' category is excluded
  (lower-is-better).
- ``sum`` + ``decay_half_life`` set: exponentially decay-weighted sum,
  normalized so that maintaining base_value/period per day scores ~100.
- ``sum`` + ``decay_half_life`` NULL: legacy windowed sum over
  aggregation_period days (kept as fallback).

Aggregation: per-source scores are averaged within each category
(category = one indicator), then category scores are capped at
``CATEGORY_SCORE_CAP`` and averaged into the health / cultural axes.
See ``calculate_scores``.

Sources whose measurement is known to be broken are left out of their
category's average (see ``services/measurement_state.py``). A low score is
never a reason to exclude — only positive evidence of a broken measurement
is — so a genuine drop in activity still shows up as a low score.
"""
import json
import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta

from ..database import get_db_context
from ..models.enums import CulturalStatus, HealthStatus
from . import measurement_state

logger = logging.getLogger(__name__)

LN2 = math.log(2)

DEFAULT_NORMAL_THRESHOLD = 70
DEFAULT_CAUTION_THRESHOLD = 40

# Per-category cap applied only when aggregating into the health/cultural
# axes. Count-type sources burst (e.g. 343 photos in a day = 23 weeks of
# baseline) and, via decay, one such day can dominate an axis for a month.
# Chart stacks and category cards keep showing the uncapped score — the
# burst itself is real information; only the axis must not be hijacked.
CATEGORY_SCORE_CAP = 200.0


# --- thresholds / status mapping ---


async def get_thresholds() -> dict:
    """Get threshold settings from DB."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT key, value FROM global_settings WHERE key LIKE '%threshold'"
        )
        return {row[0]: float(row[1]) for row in rows}


def health_status_from_score(score: float, thresholds: dict) -> HealthStatus:
    if score >= thresholds.get("score_normal_threshold", DEFAULT_NORMAL_THRESHOLD):
        return HealthStatus.NORMAL
    if score >= thresholds.get("score_caution_threshold", DEFAULT_CAUTION_THRESHOLD):
        return HealthStatus.CAUTION
    return HealthStatus.CRITICAL


def cultural_status_from_score(score: float, thresholds: dict) -> CulturalStatus:
    if score >= thresholds.get("score_normal_threshold", DEFAULT_NORMAL_THRESHOLD):
        return CulturalStatus.RICH
    if score >= thresholds.get("score_caution_threshold", DEFAULT_CAUTION_THRESHOLD):
        return CulturalStatus.MODERATE
    return CulturalStatus.LOW


# --- source metadata ---


@dataclass
class SourceMeta:
    """Effective scoring parameters of a source at a given date."""

    base_value: float = 100.0
    period: int = 7
    half_life: float | None = None
    coeff: float = 1.0
    classification: str = "baseline"
    score_method: str = "sum"
    weights: dict[str, float] | None = None


async def _load_source_meta(db, source_id: str, for_date_str: str) -> SourceMeta:
    """Load source_settings and apply the baseline effective at for_date_str."""
    meta = SourceMeta()
    rows = await db.execute_fetchall(
        """SELECT base_value, aggregation_period, decay_half_life,
                  spontaneity_coefficient, classification, score_method, category_weights
        FROM source_settings WHERE id = ?""",
        (source_id,),
    )
    if rows:
        r = rows[0]
        meta.base_value = float(r[0])
        meta.period = int(r[1])
        meta.half_life = float(r[2]) if r[2] is not None else None
        meta.coeff = float(r[3])
        meta.classification = r[4]
        meta.score_method = r[5]
        meta.weights = json.loads(r[6]) if r[6] else None

    history = await db.execute_fetchall(
        """SELECT base_value FROM baseline_history
        WHERE source_id = ? AND effective_from <= ?
        ORDER BY effective_from DESC LIMIT 1""",
        (source_id, for_date_str),
    )
    if history:
        meta.base_value = float(history[0][0])
    return meta


async def get_effective_baseline(source_id: str, for_date: str) -> tuple[float, int, float | None]:
    """Get the effective baseline value, aggregation period, and decay half_life.

    decay_half_life is None when the source uses the legacy windowed-sum method.
    """
    async with get_db_context() as db:
        meta = await _load_source_meta(db, source_id, for_date)
    return meta.base_value, meta.period, meta.half_life


async def get_source_first_dates() -> dict[str, str]:
    """Return the first activity_records.date per source (ISO string).

    Sources without any records are absent from the dict. Used to exclude
    sources from past-date status aggregation when they hadn't started
    producing data yet — otherwise their zero contribution drags scores down.
    """
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT source, MIN(date) FROM activity_records GROUP BY source"
        )
    return {row[0]: row[1] for row in rows if row[1]}


# --- per-method scoring (pure math) ---


def decay_score(
    daily_values: list[tuple[str, float]],
    for_date: date,
    base_value: float,
    period: int,
    half_life: float,
    coeff: float,
) -> float:
    """Exponentially decay-weighted score.

    weight(t) = 2^(-days_ago / half_life). Normalized to the steady-state
    weighted sum of maintaining base_value/period per day
    (= rate * half_life / ln2), so keeping the baseline pace scores ~100.
    """
    weighted_sum = 0.0
    for d, val in daily_values:
        days_ago = (for_date - date.fromisoformat(d)).days
        weighted_sum += val * math.exp(-LN2 * days_ago / half_life)
    norm_base = (base_value / period) * (half_life / LN2)
    return (weighted_sum / norm_base) * 100 * coeff


# --- per-method scoring (DB-backed) ---
#
# Each helper returns (score, raw_total). The window normally ends at
# window_end; when scoring today, window_end is yesterday and today_str is
# set — today's (incomplete) data is added on top as a bonus so it never
# drags the score down but still shows up immediately.


async def _fetch_daily_sums(
    db, source_id: str, start: str, end: str, extra_day: str | None
) -> list[tuple[str, float]]:
    """Daily raw_value sums in [start, end], plus extra_day (today bonus)."""
    rows = await db.execute_fetchall(
        """SELECT date, SUM(raw_value) FROM activity_records
        WHERE source = ? AND date >= ? AND date <= ?
        GROUP BY date""",
        (source_id, start, end),
    )
    result = [(r[0], float(r[1])) for r in rows]
    if extra_day:
        rows = await db.execute_fetchall(
            """SELECT date, SUM(raw_value) FROM activity_records
            WHERE source = ? AND date = ?
            GROUP BY date""",
            (source_id, extra_day),
        )
        result += [(r[0], float(r[1])) for r in rows]
    return result


async def _score_daily_avg(
    db, source_id: str, meta: SourceMeta, window_end: str, today_str: str | None
) -> tuple[float, float]:
    """score = (avg daily value / base_value) * 100 * coeff.

    Excludes 'stress' (lower-is-better). Optional per-category weights
    (e.g. Oura: readiness 0.6, sleep 0.4) are applied before averaging.
    """
    start = (date.fromisoformat(window_end) - timedelta(days=meta.period - 1)).isoformat()
    rows = list(await db.execute_fetchall(
        """SELECT date, category, SUM(raw_value) FROM activity_records
        WHERE source = ? AND date >= ? AND date <= ? AND category != 'stress'
        GROUP BY date, category""",
        (source_id, start, window_end),
    ))
    if today_str:
        rows += list(await db.execute_fetchall(
            """SELECT date, category, SUM(raw_value) FROM activity_records
            WHERE source = ? AND date = ? AND category != 'stress'
            GROUP BY date, category""",
            (source_id, today_str),
        ))
    if not rows or meta.base_value <= 0:
        return 0.0, 0.0

    daily_totals: dict[str, float] = {}
    for d, cat, val in rows:
        w = meta.weights.get(cat, 1.0) if meta.weights else 1.0
        daily_totals[d] = daily_totals.get(d, 0.0) + float(val) * w

    daily_avg = sum(daily_totals.values()) / len(daily_totals)
    return (daily_avg / meta.base_value) * 100 * meta.coeff, daily_avg


async def _score_decay(
    db, source_id: str, meta: SourceMeta, for_date: date, window_end: str, today_str: str | None
) -> tuple[float, float]:
    """Exponential decay weighted sum; sees up to 5x half_life days back."""
    lookback = int(meta.half_life * 5)
    start = (date.fromisoformat(window_end) - timedelta(days=lookback)).isoformat()
    daily = await _fetch_daily_sums(db, source_id, start, window_end, today_str)
    if meta.base_value <= 0:
        return 0.0, 0.0
    score = decay_score(daily, for_date, meta.base_value, meta.period, meta.half_life, meta.coeff)
    return score, float(sum(v for _, v in daily))


async def _score_windowed(
    db, source_id: str, meta: SourceMeta, window_end: str, today_str: str | None
) -> tuple[float, float]:
    """Legacy windowed sum over aggregation_period days.

    For non-event sources with partial data coverage, the baseline is
    prorated by days_with_data/period so sparse-but-on-pace activity
    still scores 100.
    """
    start = (date.fromisoformat(window_end) - timedelta(days=meta.period - 1)).isoformat()
    rows = await db.execute_fetchall(
        """SELECT COALESCE(SUM(raw_value), 0), COUNT(DISTINCT date)
        FROM activity_records
        WHERE source = ? AND date >= ? AND date <= ?""",
        (source_id, start, window_end),
    )
    raw_total = float(rows[0][0]) if rows else 0.0
    days_with_data = int(rows[0][1]) if rows else 0

    if today_str:
        rows = await db.execute_fetchall(
            """SELECT COALESCE(SUM(raw_value), 0), COUNT(DISTINCT date)
            FROM activity_records WHERE source = ? AND date = ?""",
            (source_id, today_str),
        )
        raw_total += float(rows[0][0]) if rows else 0.0
        days_with_data += int(rows[0][1]) if rows else 0

    if meta.base_value <= 0:
        return 0.0, raw_total

    if meta.classification != "event" and 0 < days_with_data < meta.period:
        adjusted_base = meta.base_value * (days_with_data / meta.period)
    else:
        adjusted_base = meta.base_value

    return (raw_total / adjusted_base) * 100 * meta.coeff, raw_total


async def calculate_source_score(
    source_id: str, for_date: date
) -> tuple[float, float, float]:
    """Calculate score for a single source. Returns (score, raw_total, base_value).

    When for_date is today, the main window ends at yesterday and today's
    data is added as a bonus (see the per-method helpers).
    """
    is_today = for_date == date.today()
    window_end = (for_date - timedelta(days=1) if is_today else for_date).isoformat()
    today_str = for_date.isoformat() if is_today else None

    async with get_db_context() as db:
        meta = await _load_source_meta(db, source_id, window_end)
        if meta.score_method == "daily_avg":
            score, raw = await _score_daily_avg(db, source_id, meta, window_end, today_str)
        elif meta.half_life is not None:
            score, raw = await _score_decay(db, source_id, meta, for_date, window_end, today_str)
        else:
            score, raw = await _score_windowed(db, source_id, meta, window_end, today_str)
    return score, raw, meta.base_value


# --- axis aggregation ---


async def calculate_scores(for_date: date | None = None) -> dict:
    """Calculate all scores for a given date.

    Returns dict with health_status, cultural_status, and axis scores.

    Aggregation: per-source scores are first averaged within each category
    (a category = one indicator), then category scores are averaged across
    health/cultural axes. This prevents indicators with multiple sources
    (e.g. vitality = nextdns + stash) from double-counting.
    """
    if for_date is None:
        for_date = date.today()

    thresholds = await get_thresholds()
    first_dates = await get_source_first_dates()
    for_date_str = for_date.isoformat()

    async with get_db_context() as db:
        baseline_rows = await db.execute_fetchall(
            "SELECT id, category FROM source_settings WHERE status = 'active' AND classification IN ('baseline', 'both', 'health_only')"
        )
        activity_rows = await db.execute_fetchall(
            "SELECT id, category FROM source_settings WHERE status = 'active' AND display_type IN ('activity', 'card_only')"
        )

    def started(row) -> bool:
        return (first_dates.get(row[0]) or "9999") <= for_date_str

    # A source can appear on both axes (e.g. classification=baseline and
    # display_type=activity) — compute its score only once.
    score_cache: dict[str, float] = {}

    async def source_score(source_id: str) -> float:
        if source_id not in score_cache:
            score_cache[source_id], _, _ = await calculate_source_score(source_id, for_date)
        return score_cache[source_id]

    baseline_cats: dict[str, list[tuple[str, float]]] = {}
    for source_id, category in filter(started, baseline_rows):
        baseline_cats.setdefault(category, []).append((source_id, await source_score(source_id)))

    activity_cats: dict[str, list[tuple[str, float]]] = {}
    for source_id, category in filter(started, activity_rows):
        activity_cats.setdefault(category, []).append((source_id, await source_score(source_id)))

    # 計測が壊れていると分かっているソースは平均から除く。除外の条件は「値が低い」
    # ことではなく壊れている証拠なので、本物の活動低下は0点のまま軸に残る。
    # 全ソースが壊れたカテゴリは計測不能として軸から外れる。
    broken = await measurement_state.get_broken_sources()
    baseline_scores, health_unmeasured = measurement_state.category_scores(baseline_cats, broken)
    activity_scores, cultural_unmeasured = measurement_state.category_scores(activity_cats, broken)

    baseline_cat_scores = [min(v, CATEGORY_SCORE_CAP) for v in baseline_scores.values()]
    activity_cat_scores = [min(v, CATEGORY_SCORE_CAP) for v in activity_scores.values()]

    baseline_avg = sum(baseline_cat_scores) / len(baseline_cat_scores) if baseline_cat_scores else 0
    cultural_pct = sum(activity_cat_scores) / len(activity_cat_scores) if activity_cat_scores else 0
    activity_total = sum(activity_cat_scores)

    return {
        "baseline_avg": round(baseline_avg, 1),
        "health_status": health_status_from_score(baseline_avg, thresholds),
        "cultural_pct": round(cultural_pct, 1),
        "cultural_status": cultural_status_from_score(cultural_pct, thresholds),
        "activity_total": round(activity_total, 1),
        # 計測できているカテゴリが足りているか。False のときスコアは当てにならないので、
        # 通知や表示側はこの数字を根拠に断定してはいけない。
        "health_measurable": measurement_state.axis_is_measurable(len(baseline_cat_scores)),
        "cultural_measurable": measurement_state.axis_is_measurable(len(activity_cat_scores)),
        "health_unmeasured": health_unmeasured,
        "cultural_unmeasured": cultural_unmeasured,
    }
