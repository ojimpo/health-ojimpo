import logging
from datetime import date

from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class ClaudeLocalAdapter(SourceAdapter):
    """Claude Codeのセッション時間（分）をwebhook経由で集計するアダプタ。

    旧トークンベース集計から切り替え。各クライアントマシン（arigato-nas含む）の
    Stopフックが日次の作業分数をPOSTしてくる。host列でディザンビゲートし、
    aggregate時にdate単位で合算する。
    """

    source_id = "claude"
    display_name = "Claude Code"

    async def is_configured(self) -> bool:
        # webhookで受信するため常にconfigured扱い
        return True

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        # 外部fetchはなし。webhook経由でstore_webhook_dataが呼ばれる。
        return 0, 0

    async def store_webhook_data(
        self, webhook_date: str, minutes: float, host: str = "unknown"
    ) -> None:
        """ホスト別の日次作業分数を保存（同date+host内で最大値を採用）。

        フックは1日のうち何度も呼ばれうるが、毎回当日全体の累積分数を計算して
        送ってくる前提なので、追加ではなく最大値で更新する（リトライ・重複耐性）。
        """
        async with get_db_context() as db:
            await db.execute(
                """INSERT INTO claude_session_minutes (date, host, minutes, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(date, host) DO UPDATE SET
                    minutes = MAX(claude_session_minutes.minutes, excluded.minutes),
                    updated_at = excluded.updated_at""",
                (webhook_date, host, minutes),
            )
            await db.commit()
        logger.info(
            "claude session: host=%s date=%s minutes=%.1f stored",
            host, webhook_date, minutes,
        )

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute("DELETE FROM activity_records WHERE source = 'claude'")
            await db.execute(
                """INSERT INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'claude',
                    'coding',
                    ROUND(SUM(minutes), 1),
                    ROUND(SUM(minutes), 1),
                    'min',
                    json_object('hosts', json_group_array(json_object('host', host, 'minutes', ROUND(minutes, 1))))
                FROM claude_session_minutes
                GROUP BY date
                """,
            )
            await db.commit()
        logger.info("Claude session aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, ROUND(SUM(minutes), 1) AS total_min, COUNT(DISTINCT host) AS host_count
                FROM claude_session_minutes
                GROUP BY date
                ORDER BY date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                mins = round(row[1] or 0)
                hours = mins // 60
                m = mins % 60
                if hours > 0:
                    dur = f"{hours}時間{m}分"
                else:
                    dur = f"{m}分"

                host_count = row[2] or 0
                detail = f"{host_count}端末" if include_detail and host_count > 1 else None

                activities.append({
                    "time": time_str,
                    "icon": "🤖",
                    "text": f"Claude Code {dur}",
                    "detail": detail,
                    "color": "#D4A574",
                    "sort_date": row[0],
                })

            return activities
