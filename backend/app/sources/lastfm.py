import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

# Last.fm の取り込みは scrobble-gateway に一本化した（2026-10-05）。
# ここは Last.fm API を叩かず、scrobble-gateway の内部 REST から日ごとの再生件数
# （UTC）だけを受け取って lastfm_daily_plays に入れる。scrobble の完全な履歴は
# 持たない。旧実装（services/lastfm.py と lastfm_scrobbles）はロールバック期間が
# 終わるまで残してある。


class LastfmAdapter(SourceAdapter):
    source_id = "lastfm"
    display_name = "Last.fm"

    async def is_configured(self) -> bool:
        return bool(settings.scrobble_gateway_url)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        today = datetime.now(timezone.utc).date()
        if from_date is None:
            from_date = (today - timedelta(days=settings.lastfm_daily_lookback_days)).isoformat()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.scrobble_gateway_url.rstrip('/')}/daily-plays",
                params={"from": from_date, "to": today.isoformat()},
            )
            resp.raise_for_status()
            body = resp.json()

        if not body.get("fullHistorySynced"):
            # 初回の全件取得が終わる前の値で上書きすると、過去の日が欠けて見える
            raise RuntimeError("scrobble-gateway has not finished its full history sync yet")

        days = {d["date"]: int(d["plays"]) for d in body.get("days", [])}
        async with get_db_context() as db:
            # 窓の中は丸ごと置き換える。gateway が返さない日は「0件」なので、
            # 残しておくと消えた scrobble の分が数え続けられる
            await db.execute(
                "DELETE FROM lastfm_daily_plays WHERE date >= ? AND date <= ?",
                (from_date, today.isoformat()),
            )
            await db.executemany(
                "INSERT INTO lastfm_daily_plays (date, plays) VALUES (?, ?)",
                list(days.items()),
            )
            await db.commit()

        newest = body.get("newestScrobbleAt")
        if newest:
            self.last_ingested_timestamp = int(
                datetime.fromisoformat(newest.replace("Z", "+00:00")).timestamp()
            )
        logger.info("Last.fm: stored %d daily counts from scrobble-gateway (%s..)", len(days), from_date)
        return len(days), len(days)

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'lastfm',
                    'music',
                    ROUND(plays * ? / 60.0, 1),
                    ROUND(plays * ? / 60.0, 1),
                    'minutes',
                    NULL
                FROM lastfm_daily_plays""",
                (settings.default_track_duration_seconds, settings.default_track_duration_seconds),
            )
            await db.commit()
        logger.info("Last.fm daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, plays FROM lastfm_daily_plays
                WHERE plays > 0
                ORDER BY date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                tracks = row[1]
                total_min = round(tracks * settings.default_track_duration_seconds / 60)
                hours = total_min // 60
                mins = total_min % 60
                if hours > 0:
                    duration_str = f"{hours}時間{mins}分"
                else:
                    duration_str = f"{mins}分"

                activities.append({
                    "time": time_str,
                    "icon": "♫",
                    "text": f"音楽を{duration_str}再生",
                    "detail": f"{tracks}トラック再生" if include_detail else None,
                    "color": "#00F0FF",
                    "sort_date": row[0],
                })

            return activities
