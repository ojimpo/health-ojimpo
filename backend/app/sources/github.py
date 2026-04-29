import json
import logging
from datetime import date, datetime, timedelta, timezone

from ..config import settings
from ..database import get_db_context
from ..services.github import fetch_daily_commits
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)


class GitHubAdapter(SourceAdapter):
    source_id = "github"
    display_name = "GitHub"

    async def is_configured(self) -> bool:
        return bool(settings.github_token and settings.github_user)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        since = from_date
        until = None

        if not since:
            last_ts = await self.get_last_timestamp()
            if last_ts:
                dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
                since = dt.strftime("%Y-%m-%d")
            # No since = Events API will fetch last 90 days automatically

        if since:
            until = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        days = await fetch_daily_commits(since=since, until=until)
        logger.info("Fetched %d days of GitHub data", len(days))

        stored = 0
        last_ts = 0
        async with get_db_context() as db:
            for day in days:
                try:
                    await db.execute(
                        """INSERT OR REPLACE INTO github_commits
                        (date, commits, repos)
                        VALUES (?, ?, ?)""",
                        (
                            day["date"],
                            day["commits"],
                            json.dumps(day["repos"]),
                        ),
                    )
                    stored += 1
                    day_ts = int(
                        datetime.strptime(day["date"], "%Y-%m-%d")
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                    )
                    last_ts = max(last_ts, day_ts)
                except Exception:
                    logger.exception("Error storing GitHub data for %s", day["date"])
            await db.commit()

        logger.info("Stored %d GitHub commit records", stored)
        return len(days), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT
                    date,
                    'github',
                    'coding',
                    0,
                    commits,
                    'commits',
                    repos
                FROM github_commits
                """,
            )
            await db.commit()
        logger.info("GitHub daily aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, commits, repos
                FROM github_commits
                ORDER BY date DESC
                LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                time_str = format_relative_day(d, today)

                commits = row[1]
                repos = json.loads(row[2]) if row[2] else []
                repo_count = len(repos)

                activities.append({
                    "time": time_str,
                    "icon": "💻",
                    "text": f"GitHub {commits}コミット",
                    "detail": f"{repo_count}リポジトリ" if include_detail and repo_count else None,
                    "color": "#50FA7B",
                    "sort_date": row[0],
                })

            return activities
