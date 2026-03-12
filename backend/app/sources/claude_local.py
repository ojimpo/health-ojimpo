import logging
from datetime import date, datetime, timezone

from ..database import get_db_context
from ..services.claude_local import fetch_daily_usage
from .base import SourceAdapter

logger = logging.getLogger(__name__)


class ClaudeLocalAdapter(SourceAdapter):
    source_id = "claude"
    display_name = "Claude Code"

    async def is_configured(self) -> bool:
        from ..services.claude_local import CLAUDE_DIR
        return CLAUDE_DIR.exists() and any(CLAUDE_DIR.rglob("*.jsonl"))

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        records = fetch_daily_usage()

        if from_date:
            records = [r for r in records if r["date"] >= from_date]

        stored = 0
        async with get_db_context() as db:
            for r in records:
                try:
                    await db.execute(
                        """INSERT OR REPLACE INTO claude_local_usage
                        (date, input_tokens, cache_creation_tokens, cache_read_tokens,
                         output_tokens, total_tokens)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            r["date"],
                            r["input_tokens"],
                            r["cache_creation_tokens"],
                            r["cache_read_tokens"],
                            r["output_tokens"],
                            r["total_tokens"],
                        ),
                    )
                    stored += 1
                except Exception:
                    logger.exception("Error storing Claude local usage for %s", r["date"])
            await db.commit()

        logger.info("Stored %d Claude Code local usage records", stored)
        return len(records), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'claude',
                    'coding',
                    0,
                    ROUND(total_tokens / 1000.0, 1),
                    'k tokens',
                    json_object(
                        'input', input_tokens,
                        'cache_creation', cache_creation_tokens,
                        'cache_read', cache_read_tokens,
                        'output', output_tokens,
                        'total', total_tokens
                    )
                FROM claude_local_usage
                """,
            )
            await db.commit()
        logger.info("Claude Code local usage aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, total_tokens, output_tokens
                FROM claude_local_usage
                ORDER BY date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                if diff == 0:
                    time_str = "今日"
                elif diff == 1:
                    time_str = "1日前"
                else:
                    time_str = f"{diff}日前"

                total_k = round(row[1] / 1000)
                output_k = round(row[2] / 1000)

                activities.append({
                    "time": time_str,
                    "icon": "🤖",
                    "text": f"Claude Code {total_k:,}kトークン使用",
                    "detail": f"出力: {output_k:,}k" if include_detail else None,
                    "color": "#D4A574",
                    "sort_date": row[0],
                })

            return activities
