import logging
from datetime import date, timedelta

from ..database import get_db_context
from ..models.enums import CulturalStatus, HealthStatus, TimeRange
from ..models.schemas import (
    ACTIVITY_CATEGORIES,
    STATE_CATEGORIES,
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
from .scoring import (
    CATEGORY_SCORE_CAP,
    calculate_scores,
    calculate_source_score,
    cultural_status_from_score,
    decay_score,
    get_source_first_dates,
    get_thresholds,
    health_status_from_score,
)
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

# Category display labels
CATEGORY_LABELS = {
    "music": "音楽",
    "exercise": "運動",
    "reading": "読書",
    "movie": "映画",
    "sns": "SNS",
    "coding": "コード",
    "calendar": "予定",
    "live": "ライブ",
    "shopping": "買い物",
    "vitality": "活力",
    "outing_activity": "外出",
    "cd": "CD貸出",
    "podcast": "Podcast",
    "fitness": "フィットネス",
    "game": "ゲーム",
    "like": "Like",
    "study": "勉強",
    "photo": "写真",
}

def _get_range_params(time_range: TimeRange) -> tuple[int, str]:
    match time_range:
        case TimeRange.ONE_MONTH:
            return 30, "daily"
        case TimeRange.THREE_MONTHS:
            return 90, "daily"
        case TimeRange.ONE_YEAR:
            return 365, "weekly"


# State categories that Oura writes but aren't in source_settings individually.
# Daily baselines: sleep/readiness are 0-100 scores (80 = healthy), stress in minutes.
_STATE_DAILY_BASELINES = {
    "sleep": 80.0,
    "readiness": 80.0,
    "stress": 30.0,
    # outing's base_value(60) is a daily % baseline, not a 7-day total.
    # Without this, the chart divides it by aggregation_period and inflates ~7x.
    "outing": 60.0,
    # CTL is a daily fitness *level* (stock), not an N-day total (flow). base 50
    # is the reference CTL = 100 on the chart. Without this it gets divided by
    # aggregation_period(30) and inflates ~30x (CTL 22 → score ~1325).
    "ctl": 50.0,
}


async def _fetch_chart_source_meta(db) -> list[tuple]:
    """Fetch all active source metadata used for chart aggregation.

    Returns list of (id, category, base_value, period, coeff,
    half_life, score_method, classification, display_type).
    """
    rows = await db.execute_fetchall(
        """SELECT id, category, base_value, aggregation_period, spontaneity_coefficient,
                  decay_half_life, score_method, classification, display_type
        FROM source_settings WHERE status = 'active'"""
    )
    return [
        (
            r[0], r[1], float(r[2]), int(r[3]), float(r[4]),
            float(r[5]) if r[5] is not None else None,
            r[6], r[7], r[8],
        )
        for r in rows
    ]


def _resolve_chart_meta_for_date(
    sources: list[tuple], first_dates: dict[str, str], for_date_str: str
) -> tuple[dict[str, tuple], list[tuple[str, str]], set[str], set[str]]:
    """Compute (source_meta_eligible, decay_sources, baseline_cats, activity_cats)
    using only sources that had produced data on or before for_date_str.

    source_meta_eligible: dict source_id -> (chart_cat, base_value, period, coeff)
    for non-decay non-card_only sources, used for per-source score computation.

    Per-date filtering avoids depressing past scores with sources that
    didn't exist yet (e.g. NextDNS added in 2026-04 shouldn't penalise 2025).
    """
    source_meta_eligible: dict[str, tuple] = {}
    decay_sources: list[tuple[str, str]] = []
    baseline_cats: set[str] = set()
    activity_cats: set[str] = set()

    for source_id, category, base_value, period, coeff, half_life, score_method, classification, display_type in sources:
        first = first_dates.get(source_id)
        if not first or first > for_date_str:
            continue
        cat = _map_category(category)
        if display_type != "card_only":
            if half_life is not None and score_method != "daily_avg":
                decay_sources.append((source_id, cat))
            else:
                source_meta_eligible[source_id] = (cat, base_value, period, coeff)
        if classification in ("baseline", "both", "health_only"):
            baseline_cats.add(cat)
        if display_type == "activity":
            activity_cats.add(cat)

    return source_meta_eligible, decay_sources, baseline_cats, activity_cats


def _compute_point_status(
    scores: dict[str, float],
    baseline_cats: set[str],
    activity_cats: set[str],
    thresholds: dict[str, float],
) -> tuple[str | None, str | None, float | None, float | None]:
    """Compute health and cultural status for a single chart data point.

    Returns (health_status, cultural_status, health_score, cultural_score).
    """
    # Health status: average of baseline category scores. Category scores are
    # capped the same way as calculate_scores so the chart lines match the
    # axis scores (the stacked per-category values stay uncapped).
    baseline_vals = [min(scores[k], CATEGORY_SCORE_CAP) for k in baseline_cats if k in scores]
    baseline_avg = sum(baseline_vals) / len(baseline_vals) if baseline_vals else None

    # Cultural status: average of activity category scores (100 = baseline met)
    activity_vals = [min(scores.get(k, 0), CATEGORY_SCORE_CAP) for k in activity_cats]
    cultural_pct = sum(activity_vals) / len(activity_vals) if activity_vals else None

    health = (
        health_status_from_score(baseline_avg, thresholds).value
        if baseline_avg is not None else None
    )
    cultural = (
        cultural_status_from_score(cultural_pct, thresholds).value
        if cultural_pct is not None else None
    )

    return (
        health,
        cultural,
        round(baseline_avg, 1) if baseline_avg is not None else None,
        round(cultural_pct, 1) if cultural_pct is not None else None,
    )


def _make_decay_scorer(
    period: int,
    half_life: float,
    coeff: float,
    default_base: float,
    records: list[tuple[str, float]],
    baselines: list[tuple[str, float]],
    today: date,
):
    """Build a bucket_end -> score function for one decay source.

    Replicates calculate_source_score's decay path (yesterday-window +
    today bonus, effective baseline per date) against prefetched data,
    so charts don't need per-bucket DB queries.

    records: (iso_date, daily raw_value sum), ascending by date.
    baselines: baseline_history (effective_from, base_value), ascending.
    """
    lookback = int(half_life * 5)

    def score_at(bucket_end: date) -> float:
        is_today = bucket_end == today
        window_end = bucket_end - timedelta(days=1) if is_today else bucket_end
        window_end_str = window_end.isoformat()

        base_value = default_base
        for effective_from, value in baselines:
            if effective_from <= window_end_str:
                base_value = value
            else:
                break
        if base_value <= 0:
            return 0.0

        start_str = (window_end - timedelta(days=lookback)).isoformat()
        daily = [(d, v) for d, v in records if start_str <= d <= window_end_str]
        if is_today:
            today_str = bucket_end.isoformat()
            daily += [(d, v) for d, v in records if d == today_str]
        return decay_score(daily, bucket_end, base_value, period, half_life, coeff)

    return score_at


async def _build_decay_scorers(
    db, sources: list[tuple], range_start: date, for_date: date
) -> dict[str, object]:
    """Prefetch records + baseline history for all chart decay sources and
    return {source_id: score_at(bucket_end)} callables."""
    decay_srcs = [
        s for s in sources
        if s[5] is not None and s[6] != "daily_avg" and s[8] != "card_only"
    ]
    if not decay_srcs:
        return {}

    ids = [s[0] for s in decay_srcs]
    placeholders = ",".join(["?"] * len(ids))
    max_lookback = max(int(s[5] * 5) for s in decay_srcs)
    fetch_start = (range_start - timedelta(days=max_lookback + 1)).isoformat()

    rows = await db.execute_fetchall(
        f"""SELECT source, date, SUM(raw_value) FROM activity_records
        WHERE source IN ({placeholders}) AND date >= ? AND date <= ?
        GROUP BY source, date ORDER BY date""",
        (*ids, fetch_start, for_date.isoformat()),
    )
    records: dict[str, list[tuple[str, float]]] = {sid: [] for sid in ids}
    for sid, d, val in rows:
        records[sid].append((d, float(val)))

    rows = await db.execute_fetchall(
        f"""SELECT source_id, effective_from, base_value FROM baseline_history
        WHERE source_id IN ({placeholders}) ORDER BY effective_from""",
        tuple(ids),
    )
    baselines: dict[str, list[tuple[str, float]]] = {sid: [] for sid in ids}
    for sid, effective_from, value in rows:
        baselines[sid].append((effective_from, float(value)))

    today = date.today()
    return {
        s[0]: _make_decay_scorer(s[3], s[5], s[4], s[2], records[s[0]], baselines[s[0]], today)
        for s in decay_srcs
    }


async def _compute_bucket_category_scores(
    db,
    source_meta_eligible: dict[str, tuple],
    decay_sources: list[tuple[str, str]],
    decay_scorers: dict[str, object],
    bucket_start: date,
    bucket_end: date,
) -> dict[str, float]:
    """Compute per-category scores for a time bucket.

    For non-decay sources: (source, activity_records.category) raw totals are
    each normalized to baseline (100 = met) then averaged within each chart
    category. For decay sources: the prefetched decay scorer runs per source
    at bucket_end and is averaged within each chart category.

    State categories (sleep/readiness/stress) use fixed daily baselines
    (_STATE_DAILY_BASELINES) regardless of source_settings, since Oura
    writes 3 categories from one source.
    """
    bucket_days = (bucket_end - bucket_start).days + 1
    cat_source_scores: dict[str, list[float]] = {}

    # Non-decay: aggregate raw totals per (source, activity_records.category)
    if source_meta_eligible:
        ids = list(source_meta_eligible.keys())
        placeholders = ",".join(["?"] * len(ids))
        rows = await db.execute_fetchall(
            f"""SELECT source, category,
                      SUM(CASE WHEN minutes > 0 THEN minutes ELSE raw_value END) as total
            FROM activity_records
            WHERE source IN ({placeholders}) AND date >= ? AND date <= ?
            GROUP BY source, category""",
            tuple(ids) + (bucket_start.isoformat(), bucket_end.isoformat()),
        )

        for source_id, raw_cat, raw_total in rows:
            cat = _map_category(raw_cat)
            raw = float(raw_total)
            _, base_value, period, coeff = source_meta_eligible[source_id]

            # State categories use a fixed daily baseline (Oura emits 3 cats
            # from 1 source — source_settings.base_value only fits one).
            if cat in _STATE_DAILY_BASELINES:
                daily_base = _STATE_DAILY_BASELINES[cat]
                avg = raw / bucket_days if bucket_days > 0 else 0
                score = (avg / daily_base) * 100 if daily_base > 0 else 0
            else:
                expected = (base_value / max(period, 1)) * bucket_days
                score = (raw / expected) * 100 * coeff if expected > 0 else 0

            cat_source_scores.setdefault(cat, []).append(score)

    # Decay: per-source score at bucket end, averaged within category
    for source_id, cat in decay_sources:
        score = decay_scorers[source_id](bucket_end)
        cat_source_scores.setdefault(cat, []).append(score)

    return {c: sum(v) / len(v) for c, v in cat_source_scores.items()}


def _chart_buckets(
    time_range: TimeRange, for_date: date
) -> list[tuple[date, date, str]]:
    """Generate (bucket_start, bucket_end, label) tuples for a time range."""
    days_back, granularity = _get_range_params(time_range)
    start_date = for_date - timedelta(days=days_back)
    buckets = []
    if granularity == "daily":
        current = start_date
        while current <= for_date:
            buckets.append((current, current, f"{current.month}/{current.day}"))
            current += timedelta(days=1)
    else:  # weekly
        week_start = start_date
        while week_start <= for_date:
            week_end = min(week_start + timedelta(days=6), for_date)
            buckets.append((week_start, week_end, f"{week_start.month}/{week_start.day}"))
            week_start += timedelta(days=7)
    return buckets


async def _get_chart_data(
    time_range: TimeRange, for_date: date | None = None
) -> list[ChartDataPoint]:
    """Generate chart data points normalized to scores (100 = baseline).

    Per (source, category) pair: raw aggregation normalized by source-specific
    baseline. Within each category, source scores are averaged. Decay sources
    are scored at the last day of each bucket.
    """
    if for_date is None:
        for_date = date.today()

    first_dates = await get_source_first_dates()
    thresholds = await get_thresholds()
    buckets = _chart_buckets(time_range, for_date)

    points = []
    async with get_db_context() as db:
        sources_meta = await _fetch_chart_source_meta(db)
        decay_scorers = await _build_decay_scorers(db, sources_meta, buckets[0][0], for_date)
        for bucket_start, bucket_end, label in buckets:
            meta_eligible, decay_sources, baseline_cats, activity_cats = (
                _resolve_chart_meta_for_date(sources_meta, first_dates, bucket_end.isoformat())
            )
            scores = await _compute_bucket_category_scores(
                db, meta_eligible, decay_sources, decay_scorers, bucket_start, bucket_end
            )
            h, c, hs, cs = _compute_point_status(scores, baseline_cats, activity_cats, thresholds)
            points.append(_make_chart_point(label, scores, h, c, hs, cs))
    return points


def _map_category(category: str) -> str:
    """Map category to ChartDataPoint field name."""
    if category in ACTIVITY_CATEGORIES or category in STATE_CATEGORIES:
        return category
    mapping = {
        "fitness": "exercise",
    }
    return mapping.get(category, category)


def _make_chart_point(
    date_label: str,
    cat_data: dict[str, float],
    health_status: str | None = None,
    cultural_status: str | None = None,
    health_score: float | None = None,
    cultural_score: float | None = None,
) -> ChartDataPoint:
    """Create a ChartDataPoint from category data dict."""
    fields = {c: round(cat_data.get(c, 0), 1) for c in ACTIVITY_CATEGORIES}
    fields |= {
        c: (round(cat_data[c], 1) if c in cat_data else None)
        for c in STATE_CATEGORIES
    }
    return ChartDataPoint(
        date=date_label,
        health_status=health_status,
        cultural_status=cultural_status,
        health_score=health_score,
        cultural_score=cultural_score,
        **fields,
    )


async def _get_category_cards(for_date: date | None = None) -> list[CategoryCard]:
    """Get category cards grouped by category (merging sources with the same category)."""
    if for_date is None:
        for_date = date.today()

    async with get_db_context() as db:
        source_rows = await db.execute_fetchall(
            "SELECT id, category, color FROM source_settings WHERE status = 'active' AND display_type IN ('activity', 'card_only')"
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
    # Load active sources and their colors from DB
    async with get_db_context() as db:
        color_rows = await db.execute_fetchall(
            "SELECT id, color FROM source_settings WHERE status = 'active'"
        )
    source_colors = {row[0]: row[1] for row in color_rows}
    active_sources = set(source_colors.keys())

    all_activities = []

    for adapter in SOURCE_ADAPTERS.values():
        if adapter.source_id not in active_sources:
            continue
        if await adapter.is_configured():
            try:
                activities = await adapter.get_recent_activities(
                    limit=limit, include_detail=include_detail
                )
                # Override color from DB
                db_color = source_colors.get(adapter.source_id)
                if db_color:
                    for a in activities:
                        a["color"] = db_color
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
            unmeasured=[CATEGORY_LABELS.get(c, c) for c in scores["health_unmeasured"]],
            measurable=scores["health_measurable"],
        ),
        cultural_status=StatusInfo(
            status=cultural_status.value,
            score=scores["cultural_pct"],
            message=CULTURAL_MESSAGES[cultural_status],
            unmeasured=[CATEGORY_LABELS.get(c, c) for c in scores["cultural_unmeasured"]],
            measurable=scores["cultural_measurable"],
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
        # 友人向けにも計測不能は伝える。この画面は「様子がおかしくないか」を
        # 見てもらうためのものなので、外して黙っていると「見た限り元気そう」に
        # 化けてしまう。個別のカテゴリ名までは出さず、件数だけ渡す。
        health_status=StatusInfo(
            status=health_status.value,
            score=scores["baseline_avg"],
            message=HEALTH_MESSAGES[health_status],
            unmeasured=[CATEGORY_LABELS.get(c, c) for c in scores["health_unmeasured"]],
            measurable=scores["health_measurable"],
        ),
        cultural_status=StatusInfo(
            status=cultural_status.value,
            score=scores["cultural_pct"],
            message=CULTURAL_MESSAGES[cultural_status],
            unmeasured=[CATEGORY_LABELS.get(c, c) for c in scores["cultural_unmeasured"]],
            measurable=scores["cultural_measurable"],
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
