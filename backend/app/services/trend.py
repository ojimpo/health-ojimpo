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
        # Current week total vs previous week (all active sources)
        current_start = (for_date - timedelta(days=6)).isoformat()
        prev_start = (for_date - timedelta(days=13)).isoformat()
        prev_end = (for_date - timedelta(days=7)).isoformat()

        current_rows = await db.execute_fetchall(
            """SELECT COALESCE(SUM(minutes), 0) FROM activity_records
            WHERE source IN (SELECT id FROM source_settings WHERE status = 'active' AND display_type = 'activity')
              AND date >= ? AND date <= ?""",
            (current_start, for_date.isoformat()),
        )
        prev_rows = await db.execute_fetchall(
            """SELECT COALESCE(SUM(minutes), 0) FROM activity_records
            WHERE source IN (SELECT id FROM source_settings WHERE status = 'active' AND display_type = 'activity')
              AND date >= ? AND date <= ?""",
            (prev_start, prev_end),
        )

        current_total = float(current_rows[0][0]) if current_rows else 0
        prev_total = float(prev_rows[0][0]) if prev_rows else 0

        # Per-source trends
        source_rows = await db.execute_fetchall(
            "SELECT id, name, category FROM source_settings WHERE status = 'active' AND display_type = 'activity'"
        )

        for srow in source_rows:
            sid, sname, scat = srow[0], srow[1], srow[2]
            cur = await db.execute_fetchall(
                "SELECT COALESCE(SUM(minutes), 0) FROM activity_records WHERE source = ? AND date >= ? AND date <= ?",
                (sid, current_start, for_date.isoformat()),
            )
            prev = await db.execute_fetchall(
                "SELECT COALESCE(SUM(minutes), 0) FROM activity_records WHERE source = ? AND date >= ? AND date <= ?",
                (sid, prev_start, prev_end),
            )
            s_cur = float(cur[0][0])
            s_prev = float(prev[0][0])

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
