import logging
from datetime import date, timedelta

from ..database import get_db_context
from ..models.enums import CulturalStatus, HealthStatus, TimeRange
from ..models.schemas import (
    CategoryCard,
    ChartDataPoint,
    DashboardResponse,
    PresentationInfo,
    RecentActivity,
    SharedViewResponse,
    StateCard,
    StatusInfo,
    TrendComment,
)
from ..sources.registry import SOURCE_ADAPTERS
from .scoring import calculate_scores, calculate_source_score, get_thresholds
from .trend import generate_trend_comments

logger = logging.getLogger(__name__)

HEALTH_MESSAGES = {
    HealthStatus.NORMAL: "健康的な状態です。いつも通り接して大丈夫です",
    HealthStatus.CAUTION: "少し注意が必要です。気にかけてください",
    HealthStatus.CRITICAL: "文化活動が大幅に低下しています。連絡を取ってみてください",
}

CULTURAL_MESSAGES = {
    CulturalStatus.RICH: "文化的活動が豊かです",
    CulturalStatus.MODERATE: "文化的活動は普通です",
    CulturalStatus.LOW: "文化的活動がほぼ停止しています",
}

FRIENDLY_MESSAGES = {
    HealthStatus.NORMAL: "健康だと思われるのでいつも通り接して大丈夫です。",
    HealthStatus.CAUTION: "少し気にかけてあげてください。さりげなく連絡してみるのもいいかもしれません。",
    HealthStatus.CRITICAL: "文化活動が大幅に低下しています。連絡を取ってみてください。",
}

# Map category values to ChartDataPoint fields
ACTIVITY_CATEGORIES = ["music", "exercise", "reading", "movie", "sns", "coding", "calendar"]
STATE_CATEGORIES = ["sleep", "readiness", "stress", "weight"]

# Category display labels
CATEGORY_LABELS = {
    "music": "音楽",
    "exercise": "運動",
    "reading": "読書",
    "movie": "映画",
    "sns": "SNS",
    "coding": "コーディング",
    "calendar": "予定",
    "live": "音楽ライブ",
    "shopping": "買い物",
    "fitness": "フィットネス",
}

# Category colors
CATEGORY_COLORS = {
    "music": "#00F0FF",
    "exercise": "#FF3366",
    "reading": "#ADFF2F",
    "movie": "#FF9500",
    "sns": "#FF9500",
    "coding": "#50FA7B",
    "calendar": "#FFB86C",
    "live": "#FF79C6",
    "shopping": "#8BE9FD",
    "fitness": "#50FA7B",
}


def _get_range_params(time_range: TimeRange) -> tuple[int, str]:
    match time_range:
        case TimeRange.ONE_MONTH:
            return 30, "daily"
        case TimeRange.THREE_MONTHS:
            return 90, "weekly"
        case TimeRange.ONE_YEAR:
            return 365, "monthly"


# State categories that Oura writes but aren't in source_settings individually.
# Daily baselines: sleep/readiness are 0-100 scores (80 = healthy), stress in minutes.
_STATE_DAILY_BASELINES = {
    "sleep": 80.0,
    "readiness": 80.0,
    "stress": 30.0,
}


async def _get_category_classifications() -> tuple[set[str], set[str]]:
    """Get baseline and activity category sets from source_settings.

    Returns (baseline_categories, activity_categories).
    """
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT category, classification, display_type FROM source_settings WHERE status = 'active'"
        )
    baseline_cats: set[str] = set()
    activity_cats: set[str] = set()
    for cat, classification, display_type in rows:
        mapped = _map_category(cat)
        if classification in ("baseline", "both"):
            baseline_cats.add(mapped)
        if display_type == "activity":
            activity_cats.add(mapped)
    return baseline_cats, activity_cats


def _compute_point_status(
    scores: dict[str, float],
    baseline_cats: set[str],
    activity_cats: set[str],
    thresholds: dict[str, float],
) -> tuple[str | None, str | None]:
    """Compute health and cultural status for a single chart data point."""
    # Health status: average of baseline category scores
    baseline_vals = [scores[k] for k in baseline_cats if k in scores]
    baseline_avg = sum(baseline_vals) / len(baseline_vals) if baseline_vals else None

    # Cultural status: average of activity category scores (100 = baseline met)
    activity_vals = [scores.get(k, 0) for k in activity_cats]
    cultural_pct = sum(activity_vals) / len(activity_vals) if activity_vals else None

    health = None
    if baseline_avg is not None:
        hn = thresholds.get("health_normal_threshold", 70)
        hc = thresholds.get("health_caution_threshold", 40)
        if baseline_avg >= hn:
            health = "NORMAL"
        elif baseline_avg >= hc:
            health = "CAUTION"
        else:
            health = "CRITICAL"

    cultural = None
    if cultural_pct is not None:
        cr = thresholds.get("cultural_rich_threshold", 70)
        cm = thresholds.get("cultural_moderate_threshold", 40)
        if cultural_pct >= cr:
            cultural = "RICH"
        elif cultural_pct >= cm:
            cultural = "MODERATE"
        else:
            cultural = "LOW"

    return health, cultural


async def _get_daily_baselines() -> dict[str, float]:
    """Get daily baseline per category (sum of base_value/period*coeff for each active source).

    Returns {category: daily_expected_value} where 100% = baseline met.
    """
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            """SELECT category, base_value, aggregation_period, spontaneity_coefficient
            FROM source_settings WHERE status = 'active'"""
        )
    baselines: dict[str, float] = {}
    for cat, base_val, period, coeff in rows:
        cat = _map_category(cat)
        daily = float(base_val) / max(int(period), 1) * float(coeff)
        baselines[cat] = baselines.get(cat, 0) + daily

    # State categories use explicit baselines (source_settings is per-source, not per-category)
    baselines.update(_STATE_DAILY_BASELINES)

    return baselines


def _normalize_to_scores(
    cat_data: dict[str, float],
    daily_baselines: dict[str, float],
    bucket_days: int,
) -> dict[str, float]:
    """Normalize raw minutes to scores (100 = baseline) for a time bucket."""
    result = {}
    for cat, raw in cat_data.items():
        daily_base = daily_baselines.get(cat, 0)
        expected = daily_base * bucket_days
        if expected > 0:
            result[cat] = (raw / expected) * 100
        else:
            result[cat] = raw  # no baseline; pass through
    return result


async def _get_chart_data(
    time_range: TimeRange, for_date: date | None = None
) -> list[ChartDataPoint]:
    """Generate chart data points normalized to scores (100 = baseline)."""
    if for_date is None:
        for_date = date.today()

    days_back, granularity = _get_range_params(time_range)
    start_date = for_date - timedelta(days=days_back)
    daily_baselines = await _get_daily_baselines()
    thresholds = await get_thresholds()
    baseline_cats, activity_cats = await _get_category_classifications()

    async with get_db_context() as db:
        if granularity == "daily":
            rows = await db.execute_fetchall(
                """SELECT date, category, SUM(CASE WHEN minutes > 0 THEN minutes ELSE raw_value END) as total_minutes
                FROM activity_records
                WHERE source IN (SELECT id FROM source_settings WHERE status = 'active')
                  AND date >= ? AND date <= ?
                GROUP BY date, category
                ORDER BY date""",
                (start_date.isoformat(), for_date.isoformat()),
            )

            data_map: dict[str, dict[str, float]] = {}
            for row in rows:
                d = row[0]
                cat = _map_category(row[1])
                data_map.setdefault(d, {})[cat] = data_map.get(d, {}).get(cat, 0) + float(row[2])

            points = []
            current = start_date
            while current <= for_date:
                d = current.isoformat()
                cat_data = data_map.get(d, {})
                scores = _normalize_to_scores(cat_data, daily_baselines, 1)
                h, c = _compute_point_status(scores, baseline_cats, activity_cats, thresholds)
                points.append(_make_chart_point(
                    f"{current.month}/{current.day}", scores, h, c
                ))
                current += timedelta(days=1)
            return points

        elif granularity == "weekly":
            points = []
            week_start = start_date
            while week_start <= for_date:
                week_end = min(week_start + timedelta(days=6), for_date)
                bucket_days = (week_end - week_start).days + 1
                rows = await db.execute_fetchall(
                    """SELECT category, SUM(CASE WHEN minutes > 0 THEN minutes ELSE raw_value END) as total_minutes
                    FROM activity_records
                    WHERE source IN (SELECT id FROM source_settings WHERE status = 'active')
                      AND date >= ? AND date <= ?
                    GROUP BY category""",
                    (week_start.isoformat(), week_end.isoformat()),
                )
                cat_data = {}
                for row in rows:
                    cat = _map_category(row[0])
                    cat_data[cat] = cat_data.get(cat, 0) + float(row[1])

                scores = _normalize_to_scores(cat_data, daily_baselines, bucket_days)
                h, c = _compute_point_status(scores, baseline_cats, activity_cats, thresholds)
                points.append(_make_chart_point(
                    f"{week_start.month}/{week_start.day}", scores, h, c
                ))
                week_start += timedelta(days=7)
            return points

        else:  # monthly
            points = []
            current_month = start_date.replace(day=1)
            while current_month <= for_date:
                next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
                month_end = next_month - timedelta(days=1)
                end = min(month_end, for_date)
                bucket_days = (end - current_month).days + 1
                rows = await db.execute_fetchall(
                    """SELECT category, SUM(CASE WHEN minutes > 0 THEN minutes ELSE raw_value END) as total_minutes
                    FROM activity_records
                    WHERE source IN (SELECT id FROM source_settings WHERE status = 'active')
                      AND date >= ? AND date <= ?
                    GROUP BY category""",
                    (current_month.isoformat(), end.isoformat()),
                )
                cat_data = {}
                for row in rows:
                    cat = _map_category(row[0])
                    cat_data[cat] = cat_data.get(cat, 0) + float(row[1])

                scores = _normalize_to_scores(cat_data, daily_baselines, bucket_days)
                h, c = _compute_point_status(scores, baseline_cats, activity_cats, thresholds)
                points.append(_make_chart_point(
                    f"{current_month.month}月", scores, h, c
                ))
                current_month = next_month
            return points


def _map_category(category: str) -> str:
    """Map category to ChartDataPoint field name. 'live' maps to 'calendar', 'shopping'/'fitness' to 'sns'."""
    if category in ACTIVITY_CATEGORIES or category in STATE_CATEGORIES:
        return category
    mapping = {
        "live": "calendar",
        "shopping": "sns",
        "fitness": "exercise",
    }
    return mapping.get(category, category)


def _make_chart_point(
    date_label: str,
    cat_data: dict[str, float],
    health_status: str | None = None,
    cultural_status: str | None = None,
) -> ChartDataPoint:
    """Create a ChartDataPoint from category data dict."""
    return ChartDataPoint(
        date=date_label,
        music=round(cat_data.get("music", 0), 1),
        exercise=round(cat_data.get("exercise", 0), 1),
        reading=round(cat_data.get("reading", 0), 1),
        movie=round(cat_data.get("movie", 0), 1),
        sns=round(cat_data.get("sns", 0), 1),
        coding=round(cat_data.get("coding", 0), 1),
        calendar=round(cat_data.get("calendar", 0), 1),
        sleep=round(cat_data["sleep"], 1) if "sleep" in cat_data else None,
        readiness=round(cat_data["readiness"], 1) if "readiness" in cat_data else None,
        stress=round(cat_data["stress"], 1) if "stress" in cat_data else None,
        weight=round(cat_data["weight"], 1) if "weight" in cat_data else None,
        health_status=health_status,
        cultural_status=cultural_status,
    )


async def _get_category_cards(for_date: date | None = None) -> list[CategoryCard]:
    """Get category cards grouped by category (merging sources with the same category)."""
    if for_date is None:
        for_date = date.today()

    async with get_db_context() as db:
        source_rows = await db.execute_fetchall(
            "SELECT id, category, color FROM source_settings WHERE status = 'active' AND display_type = 'activity'"
        )

    # Group sources by category
    cat_groups: dict[str, list[tuple[str, str]]] = {}  # category -> [(source_id, color)]
    for row in source_rows:
        source_id, category, color = row[0], row[1], row[2]
        cat_groups.setdefault(category, []).append((source_id, color))

    cards = []
    for category, sources in cat_groups.items():
        total_current = 0.0
        total_prev = 0.0
        color = sources[0][1]  # Use first source's color
        for source_id, _ in sources:
            score_current, _, _ = await calculate_source_score(source_id, for_date)
            score_prev, _, _ = await calculate_source_score(source_id, for_date - timedelta(days=7))
            total_current += score_current
            total_prev += score_prev

        n = len(sources)
        avg_current = total_current / n
        avg_prev = total_prev / n
        label = CATEGORY_LABELS.get(category, category)
        cards.append(CategoryCard(
            key=category,
            label=label,
            color=color,
            current=round(avg_current, 1),
            previous=round(avg_prev, 1),
            change=round(avg_current - avg_prev, 1),
        ))

    return cards


async def _get_state_cards(for_date: date | None = None) -> list[StateCard]:
    """Get state cards for all active state-type sources."""
    if for_date is None:
        for_date = date.today()

    # Define expected state cards
    state_defs = [
        ("sleep", "Sleep Score", "#BD93F9"),
        ("readiness", "Readiness", "#00F0FF"),
        ("stress", "Stress", "#FF3366"),
        ("weight", "Weight", "#F8F8F2"),
    ]

    async with get_db_context() as db:
        # Get state data for the current period
        cards = []
        for key, label, color in state_defs:
            # Get latest value
            row = await db.execute_fetchall(
                """SELECT raw_value FROM activity_records
                WHERE category = ? AND date <= ?
                ORDER BY date DESC LIMIT 1""",
                (key, for_date.isoformat()),
            )
            current = float(row[0][0]) if row else None

            # Get previous period value (7 days ago)
            prev_date = (for_date - timedelta(days=7)).isoformat()
            row = await db.execute_fetchall(
                """SELECT raw_value FROM activity_records
                WHERE category = ? AND date <= ?
                ORDER BY date DESC LIMIT 1""",
                (key, prev_date),
            )
            previous = float(row[0][0]) if row else None

            change = round(current - previous, 1) if current is not None and previous is not None else None

            cards.append(StateCard(
                key=key, label=label, color=color,
                current=current, previous=previous, change=change,
            ))

    return cards


async def _get_recent_activities(
    limit: int = 8, include_detail: bool = True
) -> list[RecentActivity]:
    """Get merged recent activity feed from all active sources."""
    all_activities = []

    for adapter in SOURCE_ADAPTERS.values():
        if await adapter.is_configured():
            try:
                activities = await adapter.get_recent_activities(
                    limit=limit, include_detail=include_detail
                )
                all_activities.extend(activities)
            except Exception:
                logger.exception("Error getting recent activities from %s", adapter.source_id)

    # Sort by sort_date descending, take top `limit`
    all_activities.sort(key=lambda a: a.get("sort_date", ""), reverse=True)
    all_activities = all_activities[:limit]

    return [
        RecentActivity(
            time=a["time"], icon=a["icon"], text=a["text"],
            detail=a.get("detail"), color=a["color"],
        )
        for a in all_activities
    ]


async def get_dashboard_data(time_range: TimeRange) -> DashboardResponse:
    """Assemble complete dashboard response."""
    today = date.today()
    scores = await calculate_scores(today)

    health_status = scores["health_status"]
    cultural_status = scores["cultural_status"]

    chart_data = await _get_chart_data(time_range, today)
    category_cards = await _get_category_cards(today)
    state_cards = await _get_state_cards(today)
    trend_comments = await generate_trend_comments(today)
    recent = await _get_recent_activities(limit=8, include_detail=True)

    return DashboardResponse(
        health_status=StatusInfo(
            status=health_status.value,
            score=scores["baseline_avg"],
            message=HEALTH_MESSAGES[health_status],
        ),
        cultural_status=StatusInfo(
            status=cultural_status.value,
            score=scores["cultural_pct"],
            message=CULTURAL_MESSAGES[cultural_status],
        ),
        activity_chart=chart_data,
        condition_chart=chart_data,
        category_cards=category_cards,
        state_cards=state_cards,
        trend_comments=[TrendComment(**c) for c in trend_comments],
        recent_activities=recent,
    )


async def get_shared_view_data(time_range: TimeRange) -> SharedViewResponse:
    """Assemble shared view response with presentation matrix."""
    today = date.today()
    scores = await calculate_scores(today)

    health_status = scores["health_status"]
    cultural_status = scores["cultural_status"]

    chart_data = await _get_chart_data(time_range, today)
    category_cards = await _get_category_cards(today)
    trend_comments = await generate_trend_comments(today)
    recent = await _get_recent_activities(limit=5, include_detail=False)

    # Presentation matrix
    is_critical = health_status == HealthStatus.CRITICAL
    match health_status:
        case HealthStatus.NORMAL:
            accent_color = "#50FA7B"
        case HealthStatus.CAUTION:
            accent_color = "#FFB86C"
        case HealthStatus.CRITICAL:
            accent_color = "#FF1744"

    match cultural_status:
        case CulturalStatus.RICH:
            chart_saturation = 1.0
        case CulturalStatus.MODERATE:
            chart_saturation = 0.6
        case CulturalStatus.LOW:
            chart_saturation = 0.2

    bg_color = "#0A0000" if is_critical else "#07080F"

    return SharedViewResponse(
        health_status=StatusInfo(
            status=health_status.value,
            score=scores["baseline_avg"],
            message=HEALTH_MESSAGES[health_status],
        ),
        cultural_status=StatusInfo(
            status=cultural_status.value,
            score=scores["cultural_pct"],
            message=CULTURAL_MESSAGES[cultural_status],
        ),
        activity_chart=chart_data,
        condition_chart=chart_data,
        category_cards=category_cards,
        trend_comments=[TrendComment(**c) for c in trend_comments],
        recent_activities=recent,
        friendly_message=FRIENDLY_MESSAGES[health_status],
        presentation=PresentationInfo(
            accent_color=accent_color,
            bg_color=bg_color,
            is_critical=is_critical,
            chart_saturation=chart_saturation,
        ),
    )
