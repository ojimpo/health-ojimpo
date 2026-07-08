import logging
from datetime import date, timedelta

import httpx

from ..config import settings
from ..database import get_db_context
from ..services.oauth import get_valid_token, has_token
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

GCAL_API_BASE = "https://www.googleapis.com/calendar/v3"

SOURCE_CONFIG = {
    "gcal_private": {
        "display_name": "プライベート予定",
        "category": "calendar",
        "icon": "🏖️",
        "color": "#FF3366",
        "calendar_id": settings.gcal_private_calendar_id,
    },
    "gcal_live": {
        "display_name": "ライブ",
        "category": "live",
        "icon": "🎵",
        "color": "#7C3AED",
        "calendar_id": settings.gcal_live_calendar_id,
    },
}


class GoogleCalendarAdapter(SourceAdapter):

    def __init__(self, source_id: str):
        self.source_id = source_id
        config = SOURCE_CONFIG.get(source_id, {})
        self.display_name = config.get("display_name", source_id)
        self._category = config.get("category", "calendar")
        self._icon = config.get("icon", "📅")
        self._color = config.get("color", "#FFB86C")
        self._calendar_id = config.get("calendar_id", "primary")

    async def is_configured(self) -> bool:
        # Both gcal sources share the same Google OAuth token
        return await has_token("gcal_private") or await has_token("gcal_live")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        # Try to get token from either gcal source
        token = await get_valid_token(self.source_id)
        if not token:
            other = "gcal_live" if self.source_id == "gcal_private" else "gcal_private"
            token = await get_valid_token(other)
        if not token:
            # (0,0)で正常終了するとingest_logがcompletedになり障害が埋もれる
            # （2026-05-02〜07-08にトークン失効で2ヶ月無音停止した実績あり）
            raise RuntimeError("Google OAuth token invalid or refresh failed — re-authorization required")

        if not from_date:
            from_date = (date.today() - timedelta(days=90)).isoformat()

        headers = {"Authorization": f"Bearer {token}"}
        all_events = []

        async with httpx.AsyncClient(timeout=30) as client:
            page_token = None
            while True:
                params = {
                    "timeMin": f"{from_date}T00:00:00Z",
                    "timeMax": f"{date.today().isoformat()}T23:59:59Z",
                    "maxResults": 250,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                }
                if page_token:
                    params["pageToken"] = page_token

                # 取得失敗時に部分結果で続行すると、後段の「fetchに無いイベントの
                # 削除」が窓内のイベントを誤って消すためraiseで中断する
                resp = await client.get(
                    f"{GCAL_API_BASE}/calendars/{self._calendar_id}/events",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                events = data.get("items", [])
                all_events.extend(events)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        stored = 0
        fetched_ids = []
        async with get_db_context() as db:
            for event in all_events:
                event_id = event.get("id", "")
                summary = event.get("summary", "")
                start = event.get("start", {})
                start_date = start.get("date") or start.get("dateTime", "")[:10]
                end = event.get("end", {})
                end_date = end.get("date") or end.get("dateTime", "")[:10]

                try:
                    await db.execute(
                        """INSERT OR REPLACE INTO gcal_events
                        (id, source, summary, start_date, end_date, calendar_id)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (event_id, self.source_id, summary, start_date, end_date, self._calendar_id),
                    )
                    fetched_ids.append(event_id)
                    stored += 1
                except Exception:
                    logger.exception("Error storing calendar event %s", event_id)

            # Delete events that are within the fetched window but no longer in Google Calendar
            if fetched_ids:
                placeholders = ",".join("?" * len(fetched_ids))
                await db.execute(
                    f"""DELETE FROM gcal_events
                    WHERE source = ? AND start_date >= ? AND start_date <= ?
                    AND id NOT IN ({placeholders})""",
                    [self.source_id, from_date, date.today().isoformat()] + fetched_ids,
                )
            else:
                # No events returned: clear everything in the window
                await db.execute(
                    """DELETE FROM gcal_events
                    WHERE source = ? AND start_date >= ? AND start_date <= ?""",
                    (self.source_id, from_date, date.today().isoformat()),
                )
            await db.commit()

        logger.info("%s: stored %d events", self.source_id, stored)
        return len(all_events), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                "SELECT start_date, end_date FROM gcal_events WHERE source = ?",
                (self.source_id,),
            )

            # 複数日イベント（旅行等）は期間中の各日に1件ずつ計上する。
            # 終日イベントのend_dateはGoogle API上exclusiveなので1日引く。
            # 時刻ありで日付をまたぐだけの予定（深夜解散等）は開始日のみになる
            counts: dict[str, int] = {}
            for start_s, end_s in rows:
                try:
                    start = date.fromisoformat(start_s)
                    end = date.fromisoformat(end_s) if end_s else start
                except ValueError:
                    logger.warning("%s: skipping event with bad dates %r-%r", self.source_id, start_s, end_s)
                    continue
                last = max(start, end - timedelta(days=1))
                # 誤登録された異常に長い予定でスコアが溢れないよう30日で打ち切り
                last = min(last, start + timedelta(days=29))
                d = start
                while d <= last:
                    key = d.isoformat()
                    counts[key] = counts.get(key, 0) + 1
                    d += timedelta(days=1)

            # Full rebuild: delete all existing records then re-insert from gcal_events
            await db.execute(
                "DELETE FROM activity_records WHERE source = ?",
                (self.source_id,),
            )
            await db.executemany(
                """INSERT INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                VALUES (?, ?, ?, 0, ?, '回', NULL)""",
                [(d, self.source_id, self._category, c) for d, c in sorted(counts.items())],
            )
            await db.commit()
        logger.info("%s aggregation completed", self.source_id)

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT start_date, summary FROM gcal_events
                WHERE source = ?
                ORDER BY start_date DESC LIMIT ?""",
                (self.source_id, limit),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today, allow_future=True)

                activities.append({
                    "time": time_str,
                    "icon": self._icon,
                    "text": row[1] if include_detail else self.display_name,
                    "detail": None,
                    "color": self._color,
                    "sort_date": row[0],
                })

            return activities
