import logging
from datetime import date, timedelta

from ..database import get_db_context

logger = logging.getLogger(__name__)


async def generate_trend_comments(for_date: date | None = None) -> list[dict]:
    """Generate rule-based trend comments by comparing recent periods across all active sources."""
    if for_date is None:
        for_date = date.today()

    comments = []

    async with get_db_context() as db:
        current_start = (for_date - timedelta(days=6)).isoformat()
        prev_start = (for_date - timedelta(days=13)).isoformat()
        prev_end = (for_date - timedelta(days=7)).isoformat()

        # Per-source trends: current week vs previous week
        source_rows = await db.execute_fetchall(
            "SELECT id, name FROM source_settings WHERE status = 'active' AND display_type = 'activity'"
        )

        async def weekly_minutes(start: str, end: str) -> dict[str, float]:
            rows = await db.execute_fetchall(
                """SELECT source, COALESCE(SUM(minutes), 0) FROM activity_records
                WHERE date >= ? AND date <= ? GROUP BY source""",
                (start, end),
            )
            return {r[0]: float(r[1]) for r in rows}

        current_by_source = await weekly_minutes(current_start, for_date.isoformat())
        prev_by_source = await weekly_minutes(prev_start, prev_end)

        for sid, sname in source_rows:
            s_cur = current_by_source.get(sid, 0.0)
            s_prev = prev_by_source.get(sid, 0.0)

            if s_prev > 0:
                change_pct = ((s_cur - s_prev) / s_prev) * 100
                # Extract short name (before parentheses)
                short_name = sname.split(" (")[0] if " (" in sname else sname
                if change_pct > 20:
                    comments.append(
                        {"text": f"{short_name}が回復傾向にあります", "type": "positive"}
                    )
                elif change_pct < -30:
                    comments.append(
                        {"text": f"{short_name}が先週より減少しています", "type": "warning"}
                    )
                else:
                    comments.append(
                        {"text": f"{short_name}は安定しています", "type": "neutral"}
                    )
            elif s_cur == 0 and s_prev == 0:
                pass  # No data at all, skip
            elif s_cur > 0:
                short_name = sname.split(" (")[0] if " (" in sname else sname
                comments.append(
                    {"text": f"{short_name}の活動が検出されました", "type": "positive"}
                )

        # Check for consecutive weeks of decline (total activity)
        weeks_declining = 0
        check_date = for_date
        for _ in range(4):
            w_start = (check_date - timedelta(days=6)).isoformat()
            w_end = check_date.isoformat()
            pw_start = (check_date - timedelta(days=13)).isoformat()
            pw_end = (check_date - timedelta(days=7)).isoformat()

            w_rows = await db.execute_fetchall(
                """SELECT COALESCE(SUM(minutes), 0) FROM activity_records
                WHERE source IN (SELECT id FROM source_settings WHERE status = 'active' AND display_type = 'activity')
                  AND date >= ? AND date <= ?""",
                (w_start, w_end),
            )
            pw_rows = await db.execute_fetchall(
                """SELECT COALESCE(SUM(minutes), 0) FROM activity_records
                WHERE source IN (SELECT id FROM source_settings WHERE status = 'active' AND display_type = 'activity')
                  AND date >= ? AND date <= ?""",
                (pw_start, pw_end),
            )
            w_total = float(w_rows[0][0])
            pw_total = float(pw_rows[0][0])
            if pw_total > 0 and w_total < pw_total:
                weeks_declining += 1
            else:
                break
            check_date -= timedelta(days=7)

        if weeks_declining >= 3:
            comments.append(
                {"text": f"文化活動総量が{weeks_declining}週連続で低下しています", "type": "warning"}
            )
        elif weeks_declining >= 2:
            comments.append(
                {"text": "文化活動がやや減少傾向にあります", "type": "warning"}
            )

    if not comments:
        comments.append({"text": "データを蓄積中です", "type": "neutral"})

    return comments
