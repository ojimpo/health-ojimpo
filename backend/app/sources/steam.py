import logging
from datetime import date, timedelta

from ..config import settings
from ..database import get_db_context
from ..services.steam import fetch_recently_played, fetch_release_date
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

# Day-of-week weights for backfill distribution.
# Saturday is heavy (5x weekday), Sunday is 0, weekdays = 1.
# Captures the user's typical pattern: 平日そこそこ、土曜一日中、日曜オフ。
DOW_WEIGHTS = {
    0: 1,  # Monday
    1: 1,  # Tuesday
    2: 1,  # Wednesday
    3: 1,  # Thursday
    4: 1,  # Friday
    5: 5,  # Saturday
    6: 0,  # Sunday
}

MAX_BACKFILL_DAYS = 14  # Steam API only exposes playtime_2weeks reliably


class SteamAdapter(SourceAdapter):
    source_id = "steam"
    display_name = "ゲーム (Steam)"

    async def is_configured(self) -> bool:
        return bool(settings.steam_api_key and settings.steam_id64)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        try:
            games = await fetch_recently_played()
        except Exception:
            logger.exception("Failed to fetch Steam recently played")
            return 0, 0

        logger.info("Steam: %d recently played games", len(games))

        today = date.today()
        stored = 0

        async with get_db_context() as db:
            for game in games:
                appid = game["appid"]
                name = game["name"]
                playtime_forever = game["playtime_forever"]
                playtime_2weeks = game["playtime_2weeks"]

                rows = await db.execute_fetchall(
                    "SELECT last_playtime_forever, release_date, backfilled FROM steam_titles WHERE appid = ?",
                    (appid,),
                )
                if rows:
                    last_pt, release_date_db, backfilled = rows[0]
                else:
                    last_pt, release_date_db, backfilled = 0, None, 0

                if not backfilled:
                    release_date_str = release_date_db
                    if not release_date_str:
                        release_date_str = await fetch_release_date(appid)
                    release_date_obj = (
                        _parse_iso(release_date_str)
                        or (today - timedelta(days=MAX_BACKFILL_DAYS))
                    )

                    start_date = max(
                        release_date_obj, today - timedelta(days=MAX_BACKFILL_DAYS)
                    )
                    if start_date > today:
                        start_date = today

                    minutes_to_distribute = playtime_2weeks or playtime_forever
                    distributions = _weighted_distribute(
                        start_date, today, minutes_to_distribute
                    )
                    for d, mins in distributions:
                        await db.execute(
                            """INSERT INTO steam_playtime (date, appid, minutes)
                            VALUES (?, ?, ?)
                            ON CONFLICT(date, appid) DO UPDATE SET minutes = excluded.minutes""",
                            (d.isoformat(), appid, mins),
                        )
                        stored += 1

                    await db.execute(
                        """INSERT INTO steam_titles
                        (appid, name, release_date, last_playtime_forever, first_seen_date, backfilled, updated_at)
                        VALUES (?, ?, ?, ?, ?, 1, datetime('now'))
                        ON CONFLICT(appid) DO UPDATE SET
                            name = excluded.name,
                            release_date = COALESCE(steam_titles.release_date, excluded.release_date),
                            last_playtime_forever = excluded.last_playtime_forever,
                            backfilled = 1,
                            updated_at = datetime('now')""",
                        (appid, name, release_date_str, playtime_forever, today.isoformat()),
                    )
                    logger.info(
                        "Steam backfill: %s (appid=%s) %d min across [%s, %s]",
                        name, appid, minutes_to_distribute, start_date, today,
                    )
                else:
                    delta = playtime_forever - last_pt
                    if delta > 0:
                        await db.execute(
                            """INSERT INTO steam_playtime (date, appid, minutes)
                            VALUES (?, ?, ?)
                            ON CONFLICT(date, appid) DO UPDATE SET minutes = minutes + excluded.minutes""",
                            (today.isoformat(), appid, delta),
                        )
                        stored += 1
                        await db.execute(
                            """UPDATE steam_titles SET
                                last_playtime_forever = ?,
                                name = ?,
                                updated_at = datetime('now')
                            WHERE appid = ?""",
                            (playtime_forever, name, appid),
                        )
                        logger.info(
                            "Steam delta: %s (appid=%s) +%d min today",
                            name, appid, delta,
                        )
            await db.commit()

        return len(games), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute("DELETE FROM activity_records WHERE source = 'steam'")
            await db.execute(
                """INSERT INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'steam',
                    'game',
                    ROUND(SUM(minutes), 1),
                    ROUND(SUM(minutes), 1),
                    'minutes',
                    NULL
                FROM steam_playtime
                WHERE minutes > 0
                GROUP BY date"""
            )
            await db.commit()
        logger.info("Steam daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT sp.date, SUM(sp.minutes) as total_min,
                       GROUP_CONCAT(st.name, '|||') as titles
                FROM steam_playtime sp
                JOIN steam_titles st ON sp.appid = st.appid
                WHERE sp.minutes > 0
                GROUP BY sp.date
                ORDER BY sp.date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)
                total_min = round(row[1]) if row[1] else 0
                hours = total_min // 60
                mins = total_min % 60
                duration_str = (
                    f"{hours}時間{mins}分" if hours > 0 else f"{mins}分"
                )

                titles = row[2].split("|||") if row[2] else []
                seen: list[str] = []
                for t in titles:
                    if t not in seen:
                        seen.append(t)
                detail = "、".join(seen) if include_detail and seen else None

                activities.append({
                    "time": time_str,
                    "icon": "🎮",
                    "text": f"ゲームを{duration_str}プレイ",
                    "detail": detail,
                    "color": "#66C0F4",
                    "sort_date": row[0],
                })

            return activities


def _parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _weighted_distribute(
    start: date, end: date, total_minutes: int
) -> list[tuple[date, float]]:
    """Distribute total_minutes across [start, end] inclusive using DOW_WEIGHTS.

    Returns list of (date, minutes) only for days with weight > 0.
    """
    days = []
    cursor = start
    while cursor <= end:
        weight = DOW_WEIGHTS.get(cursor.weekday(), 1)
        days.append((cursor, weight))
        cursor += timedelta(days=1)

    total_weight = sum(w for _, w in days)
    if total_weight == 0:
        n = len(days)
        if n == 0:
            return []
        per = total_minutes / n
        return [(d, per) for d, _ in days]

    per_unit = total_minutes / total_weight
    return [
        (d, round(per_unit * w, 1)) for d, w in days if w > 0
    ]
