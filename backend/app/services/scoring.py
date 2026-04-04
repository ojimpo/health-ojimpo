import json
import logging
import math
from datetime import date, timedelta

from ..database import get_db_context
from ..models.enums import CulturalStatus, HealthStatus

logger = logging.getLogger(__name__)


async def get_thresholds() -> dict:
    """Get threshold settings from DB."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT key, value FROM global_settings WHERE key LIKE '%threshold'"
        )
        return {row[0]: float(row[1]) for row in rows}


async def get_effective_baseline(source_id: str, for_date: str) -> tuple[float, int, float | None]:
    """Get the effective baseline value, aggregation period, and decay half_life for a source.

    Returns (base_value, aggregation_period_days, decay_half_life).
    decay_half_life is None when the source uses the legacy windowed-sum method.
    """
    async with get_db_context() as db:
        # Check baseline_history first
        rows = await db.execute_fetchall(
            """SELECT base_value FROM baseline_history
            WHERE source_id = ? AND effective_from <= ?
            ORDER BY effective_from DESC LIMIT 1""",
            (source_id, for_date),
        )
        if rows:
            base_value = float(rows[0][0])
        else:
            # Fall back to source_settings default
            rows = await db.execute_fetchall(
                "SELECT base_value FROM source_settings WHERE id = ?",
                (source_id,),
            )
            base_value = float(rows[0][0]) if rows else 100.0

        # Get aggregation period and decay_half_life
        rows = await db.execute_fetchall(
            "SELECT aggregation_period, decay_half_life FROM source_settings WHERE id = ?",
            (source_id,),
        )
        period = int(rows[0][0]) if rows else 7
        half_life = float(rows[0][1]) if rows and rows[0][1] is not None else None

        return base_value, period, half_life


async def calculate_source_score(
    source_id: str, for_date: date
) -> tuple[float, float, float]:
    """Calculate score for a single source.

    Returns (score, raw_total, base_value).

    When for_date is today, uses "yesterday window + today bonus" approach:
    the main window covers yesterday back to (period) days, and any data
    recorded today is added on top. This prevents incomplete today data
    from dragging down the score while still reflecting new activity immediately.

    Scoring methods (determined by source_settings.score_method + decay_half_life):
    - 'daily_avg': score = (avg_daily_value / base_value) * 100 * coeff
      Excludes 'stress' category (lower-is-better). decay_half_life ignored.
    - 'sum' + decay_half_life set: exponential decay weighted sum
      norm = (base_value / aggregation_period) * (half_life / ln2)
      score = weighted_sum / norm * 100 * coeff
    - 'sum' + decay_half_life NULL: legacy windowed sum (fallback)
      score = (period_total / base_value) * 100 * coeff
    """
    # When calculating for today, shift the window to end at yesterday
    # so that incomplete today data doesn't penalize the score.
    # Today's data is added as a bonus on top.
    is_today = for_date == date.today()
    window_end = for_date - timedelta(days=1) if is_today else for_date

    date_str = window_end.isoformat()
    today_str = for_date.isoformat() if is_today else None
    base_value, period, half_life = await get_effective_baseline(source_id, date_str)

    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT spontaneity_coefficient, classification, score_method FROM source_settings WHERE id = ?",
            (source_id,),
        )
        coeff = float(rows[0][0]) if rows else 1.0
        classification = rows[0][1] if rows else "baseline"
        score_method = rows[0][2] if rows else "sum"

        if score_method == "daily_avg":
            start_date = (window_end - timedelta(days=period - 1)).isoformat()
            # Average daily values (exclude stress: lower-is-better)
            # Optionally apply per-category weights (e.g. Oura: readiness 0.6, sleep 0.4)
            weight_rows = await db.execute_fetchall(
                "SELECT category_weights FROM source_settings WHERE id = ?",
                (source_id,),
            )
            raw_weights = weight_rows[0][0] if weight_rows and weight_rows[0][0] else None
            weights = json.loads(raw_weights) if raw_weights else None

            rows = await db.execute_fetchall(
                """SELECT date, category,
                          SUM(raw_value) as val
                FROM activity_records
                WHERE source = ? AND date >= ? AND date <= ? AND category != 'stress'
                GROUP BY date, category""",
                (source_id, start_date, date_str),
            )
            if not rows or base_value <= 0:
                return 0.0, 0.0, base_value

            daily_totals: dict[str, float] = {}
            for row in rows:
                d, cat, val = row[0], row[1], float(row[2])
                w = weights.get(cat, 1.0) if weights else 1.0
                daily_totals[d] = daily_totals.get(d, 0.0) + val * w

            # For today: include today's data in the average if it exists (bonus)
            if today_str:
                today_rows = await db.execute_fetchall(
                    """SELECT date, category, SUM(raw_value) as val
                    FROM activity_records
                    WHERE source = ? AND date = ? AND category != 'stress'
                    GROUP BY date, category""",
                    (source_id, today_str),
                )
                for row in today_rows:
                    d, cat, val = row[0], row[1], float(row[2])
                    w = weights.get(cat, 1.0) if weights else 1.0
                    daily_totals[d] = daily_totals.get(d, 0.0) + val * w

            daily_avg = sum(daily_totals.values()) / len(daily_totals)
            score = (daily_avg / base_value) * 100 * coeff
            return score, daily_avg, base_value

        if half_life is not None:
            # Exponential decay: fetch up to 5× half_life days of history
            lookback = int(half_life * 5)
            start_date = (window_end - timedelta(days=lookback)).isoformat()

            rows = await db.execute_fetchall(
                """SELECT date, SUM(raw_value) as val
                FROM activity_records
                WHERE source = ? AND date >= ? AND date <= ?
                GROUP BY date""",
                (source_id, start_date, date_str),
            )
            # Include today's data as bonus if available
            if today_str:
                today_rows = await db.execute_fetchall(
                    """SELECT date, SUM(raw_value) as val
                    FROM activity_records
                    WHERE source = ? AND date = ?
                    GROUP BY date""",
                    (source_id, today_str),
                )
                rows = list(rows) + list(today_rows)

        else:
            # Legacy windowed sum
            start_date = (window_end - timedelta(days=period - 1)).isoformat()
            rows = await db.execute_fetchall(
                """SELECT COALESCE(SUM(raw_value), 0) as total_value,
                          COUNT(DISTINCT date) as days_with_data
                FROM activity_records
                WHERE source = ? AND date >= ? AND date <= ?""",
                (source_id, start_date, date_str),
            )
            raw_total = float(rows[0][0]) if rows else 0.0
            days_with_data = int(rows[0][1]) if rows else 0

            # Add today's data as bonus if available
            if today_str:
                today_rows = await db.execute_fetchall(
                    """SELECT COALESCE(SUM(raw_value), 0) as total_value,
                              COUNT(DISTINCT date) as has_data
                    FROM activity_records
                    WHERE source = ? AND date = ?""",
                    (source_id, today_str),
                )
                today_total = float(today_rows[0][0]) if today_rows else 0.0
                today_has_data = int(today_rows[0][1]) if today_rows else 0
                raw_total += today_total
                days_with_data += today_has_data

            if base_value <= 0:
                return 0.0, raw_total, base_value

            if classification != "event" and days_with_data > 0 and days_with_data < period:
                adjusted_base = base_value * (days_with_data / period)
            else:
                adjusted_base = base_value

            score = (raw_total / adjusted_base) * 100 * coeff
            return score, raw_total, base_value

    if base_value <= 0 or half_life is None:
        return 0.0, 0.0, base_value

    # Compute exponentially weighted sum
    # weight(t) = exp(-ln2 * days_ago / half_life)
    ln2 = math.log(2)
    weighted_sum = 0.0
    raw_total = 0.0
    for row in rows:
        days_ago = (for_date - date.fromisoformat(row[0])).days
        weight = math.exp(-ln2 * days_ago / half_life)
        val = float(row[1])
        weighted_sum += val * weight
        raw_total += val

    # Normalize: steady-state sum when maintaining (base_value / period) per day
    # = rate * half_life / ln2
    norm_base = (base_value / period) * (half_life / ln2)
    score = (weighted_sum / norm_base) * 100 * coeff
    return score, raw_total, base_value


async def calculate_scores(for_date: date | None = None) -> dict:
    """Calculate all scores for a given date.

    Returns dict with health_status, cultural_status, and per-source scores.
    """
    if for_date is None:
        for_date = date.today()

    thresholds = await get_thresholds()

    async with get_db_context() as db:
        # Get all active baseline sources
        baseline_rows = await db.execute_fetchall(
            "SELECT id FROM source_settings WHERE status = 'active' AND classification IN ('baseline', 'both', 'health_only')"
        )
        # Get all active activity sources
        activity_rows = await db.execute_fetchall(
            "SELECT id FROM source_settings WHERE status = 'active' AND display_type = 'activity'"
        )

    # Calculate baseline score (health indicator)
    baseline_scores = []
    for row in baseline_rows:
        score, _, _ = await calculate_source_score(row[0], for_date)
        baseline_scores.append(score)

    baseline_avg = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0

    # Calculate activity volume score (cultural indicator)
    activity_scores = []
    for row in activity_rows:
        score, _, _ = await calculate_source_score(row[0], for_date)
        activity_scores.append(score)

    activity_total = sum(activity_scores)
    # Cultural status is based on percentage of expected baseline total
    expected_total = len(activity_scores) * 100 if activity_scores else 1
    cultural_pct = (activity_total / expected_total) * 100

    # Determine statuses
    health_normal = thresholds.get("health_normal_threshold", 70)
    health_caution = thresholds.get("health_caution_threshold", 40)
    cultural_rich = thresholds.get("cultural_rich_threshold", 70)
    cultural_moderate = thresholds.get("cultural_moderate_threshold", 40)

    if baseline_avg >= health_normal:
        health_status = HealthStatus.NORMAL
    elif baseline_avg >= health_caution:
        health_status = HealthStatus.CAUTION
    else:
        health_status = HealthStatus.CRITICAL

    if cultural_pct >= cultural_rich:
        cultural_status = CulturalStatus.RICH
    elif cultural_pct >= cultural_moderate:
        cultural_status = CulturalStatus.MODERATE
    else:
        cultural_status = CulturalStatus.LOW

    return {
        "baseline_avg": round(baseline_avg, 1),
        "health_status": health_status,
        "cultural_pct": round(cultural_pct, 1),
        "cultural_status": cultural_status,
        "activity_total": round(activity_total, 1),
    }
