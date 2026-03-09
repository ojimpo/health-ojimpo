import logging
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


async def get_effective_baseline(source_id: str, for_date: str) -> tuple[float, int]:
    """Get the effective baseline value and aggregation period for a source at a given date.

    Returns (base_value, aggregation_period_days).
    Falls back to source_settings defaults if no baseline_history entry exists.
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

        # Get aggregation period
        rows = await db.execute_fetchall(
            "SELECT aggregation_period FROM source_settings WHERE id = ?",
            (source_id,),
        )
        period = int(rows[0][0]) if rows else 7

        return base_value, period


async def calculate_source_score(
    source_id: str, for_date: date
) -> tuple[float, float, float]:
    """Calculate score for a single source.

    Returns (score, raw_total, base_value).
    score = (raw_total / base_value) * 100 * spontaneity_coefficient
    """
    date_str = for_date.isoformat()
    base_value, period = await get_effective_baseline(source_id, date_str)

    async with get_db_context() as db:
        # Get spontaneity coefficient
        rows = await db.execute_fetchall(
            "SELECT spontaneity_coefficient FROM source_settings WHERE id = ?",
            (source_id,),
        )
        coeff = float(rows[0][0]) if rows else 1.0

        # Sum raw_value over the aggregation period window
        start_date = (for_date - timedelta(days=period - 1)).isoformat()
        rows = await db.execute_fetchall(
            """SELECT COALESCE(SUM(minutes), 0) as total_minutes
            FROM activity_records
            WHERE source = ? AND date >= ? AND date <= ?""",
            (source_id, start_date, date_str),
        )
        raw_total = float(rows[0][0]) if rows else 0.0

    if base_value <= 0:
        return 0.0, raw_total, base_value

    score = (raw_total / base_value) * 100 * coeff
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
            "SELECT id FROM source_settings WHERE status = 'active' AND classification IN ('baseline', 'both')"
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
