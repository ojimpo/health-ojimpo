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

    host は人間が読む端末名、instance_id はその端末の世代（migration 049）。
    端末を組み直すとクライアント側のstateが消えて新しいinstance_idになるので、
    名前を変えずに世代を分けられる。合算はdate単位なので世代が増えても影響しない。
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
        self,
        webhook_date: str,
        minutes: float,
        host: str = "unknown",
        version: str | None = None,
        instance_id: str | None = None,
    ) -> None:
        """ホスト別の日次作業分数を保存（同date+host+instance内で最大値を採用）。

        フックは1日のうち何度も呼ばれうるが、毎回当日全体の累積分数を計算して
        送ってくる前提なので、追加ではなく最大値で更新する（リトライ・重複耐性）。

        client_version は分数と違い常に上書きする（端末のスクリプト版は最新の
        申告が正しい。NULL = versionを送らない旧スクリプト）。

        instance_id 未指定（v2以前のクライアント）は host 名をそのまま世代IDとして
        扱う。migration 049 が既存行に入れた値と同じなので、端末を更新するまでは
        従来どおり1世代のまま動き続ける。
        """
        instance = instance_id or host
        async with get_db_context() as db:
            await db.execute(
                """INSERT INTO claude_session_minutes
                (date, host, instance_id, minutes, updated_at, client_version)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
                ON CONFLICT(date, host, instance_id) DO UPDATE SET
                    minutes = MAX(claude_session_minutes.minutes, excluded.minutes),
                    updated_at = excluded.updated_at,
                    client_version = excluded.client_version""",
                (webhook_date, host, instance, minutes, version),
            )
            await db.commit()
        logger.info(
            "claude session: host=%s instance=%s date=%s minutes=%.1f version=%s stored",
            host, instance, webhook_date, minutes, version or "v1",
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
                    ROUND(SUM(host_minutes), 1),
                    ROUND(SUM(host_minutes), 1),
                    'min',
                    json_object('hosts', json_group_array(json_object('host', host, 'minutes', ROUND(host_minutes, 1))))
                FROM (
                    -- 世代交代の日は同じ端末が2 instance分の行を持つ。metadataは
                    -- 端末ごとに1エントリで見せたいので、先にhostで畳んでおく
                    SELECT date, host, SUM(minutes) AS host_minutes
                    FROM claude_session_minutes
                    GROUP BY date, host
                )
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
