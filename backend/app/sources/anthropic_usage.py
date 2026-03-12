import logging
from datetime import date, datetime, timedelta, timezone

from ..config import settings
from ..database import get_db_context
from ..services.anthropic_usage import fetch_daily_usage
from .base import SourceAdapter

logger = logging.getLogger(__name__)


class AnthropicUsageAdapter(SourceAdapter):
    source_id = "claude"
    display_name = "Claude Code"

    async def is_configured(self) -> bool:
        return bool(settings.anthropic_admin_api_key)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        if from_date:
            starting_at = f"{from_date}T00:00:00Z"
        else:
            last_ts = await self.get_last_timestamp()
            if last_ts:
                dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
                starting_at = dt.strftime("%Y-%m-%dT00:00:00Z")
            else:
                # First run: fetch last 90 days
                dt = datetime.now(timezone.utc) - timedelta(days=90)
                starting_at = dt.strftime("%Y-%m-%dT00:00:00Z")

        buckets = await fetch_daily_usage(starting_at=starting_at)
        logger.info("Fetched %d daily usage buckets from Anthropic", len(buckets))

        stored = 0
        last_ts = 0
        async with get_db_context() as db:
            for bucket in buckets:
                if bucket["total_tokens"] == 0:
                    continue
                try:
                    await db.execute(
                        """INSERT OR REPLACE INTO anthropic_usage
                        (date, uncached_input_tokens, cached_input_tokens,
                         cache_creation_tokens, output_tokens, total_tokens)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            bucket["date"],
                            bucket["uncached_input_tokens"],
                            bucket["cached_input_tokens"],
                            bucket["cache_creation_tokens"],
                            bucket["output_tokens"],
                            bucket["total_tokens"],
                        ),
                    )
                    stored += 1
                    bucket_ts = int(
                        datetime.strptime(bucket["date"], "%Y-%m-%d")
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                    )
                    last_ts = max(last_ts, bucket_ts)
                except Exception:
                    logger.exception("Error storing usage for %s", bucket["date"])
            await db.commit()

        logger.info("Stored %d usage records", stored)
        return len(buckets), stored

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
                        'uncached_input', uncached_input_tokens,
                        'cached_input', cached_input_tokens,
                        'cache_creation', cache_creation_tokens,
                        'output', output_tokens,
                        'total', total_tokens
                    )
                FROM anthropic_usage
                """,
            )
            await db.commit()
        logger.info("Anthropic usage daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, total_tokens, output_tokens
                FROM anthropic_usage
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
