import logging
from datetime import date, datetime, timezone

from ..config import settings
from ..database import get_db_context
from ..services.lastfm import fetch_all_tracks, parse_scrobble
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class LastfmAdapter(SourceAdapter):
    source_id = "lastfm"
    display_name = "Last.fm"

    async def is_configured(self) -> bool:
        return bool(settings.lastfm_api_key and settings.lastfm_user)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        from_ts = None
        prev_ts = None
        if from_date:
            dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            from_ts = int(dt.timestamp())
        else:
            last_ts = prev_ts = await self.get_last_timestamp()
            if last_ts:
                # 起点ちょうどからだと、遅れて届いた古い時刻の scrobble を
                # 飛び越えて二度と取らない（2026-09-18〜10-04 に 12 件発生）
                from_ts = last_ts + 1 - settings.lastfm_lookback_hours * 3600

        tracks, failed_pages = await fetch_all_tracks(from_ts=from_ts)
        logger.info("Fetched %d tracks from Last.fm", len(tracks))

        stored = 0
        last_ts = 0
        async with get_db_context() as db:
            for track in tracks:
                parsed = parse_scrobble(track)
                if not parsed:
                    continue
                try:
                    await db.execute(
                        """INSERT OR IGNORE INTO lastfm_scrobbles
                        (track_name, artist_name, album_name, scrobbled_at, scrobbled_date, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            parsed["track_name"],
                            parsed["artist_name"],
                            parsed["album_name"],
                            parsed["scrobbled_at"],
                            parsed["scrobbled_date"],
                            parsed["duration_seconds"],
                        ),
                    )
                    stored += 1
                    last_ts = max(last_ts, parsed["scrobbled_at"])
                except Exception:
                    logger.exception("Error storing scrobble: %s", parsed["track_name"])
            await db.commit()

        # 取りこぼしたページがあるときは進めない。進めると次回はその先から
        # 取りに行くので、落ちたページの scrobble が二度と入らない。
        if failed_pages:
            logger.warning(
                "Last.fm: %d page(s) failed, keeping the previous last_timestamp",
                failed_pages,
            )
        elif last_ts:
            # 遡って取り直した回に起点が巻き戻らないよう、前回値を下回らせない
            self.last_ingested_timestamp = max(last_ts, prev_ts or 0)

        logger.info("Stored %d new scrobbles", stored)
        return len(tracks), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    scrobbled_date,
                    'lastfm',
                    'music',
                    ROUND(SUM(COALESCE(duration_seconds, ?)) / 60.0, 1),
                    ROUND(SUM(COALESCE(duration_seconds, ?)) / 60.0, 1),
                    'minutes',
                    NULL
                FROM lastfm_scrobbles
                GROUP BY scrobbled_date""",
                (settings.default_track_duration_seconds, settings.default_track_duration_seconds),
            )
            await db.commit()
        logger.info("Last.fm daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT scrobbled_date, COUNT(*) as tracks, SUM(duration_seconds) as total_secs
                FROM lastfm_scrobbles
                GROUP BY scrobbled_date
                ORDER BY scrobbled_date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                tracks = row[1]
                total_min = round(row[2] / 60) if row[2] else 0
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
