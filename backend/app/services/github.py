import asyncio
import logging
from collections import defaultdict

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"


async def fetch_daily_commits(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Fetch daily commit counts using GitHub Events API + Search API fallback.

    Args:
        since: Date string "YYYY-MM-DD" (inclusive)
        until: Date string "YYYY-MM-DD" (exclusive)

    Returns:
        List of dicts: {date, commits, repos}
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    daily: dict[str, dict] = defaultdict(lambda: {"commits": 0, "repos": set()})

    if since and until:
        # Use Search Commits API for specific date ranges (supports historical data)
        await _fetch_via_search(headers, since, until, daily)
    else:
        # Use Events API for recent activity (simpler, covers last 90 days)
        await _fetch_via_events(headers, daily)

    # Filter by date range if specified
    results = []
    for date_str in sorted(daily.keys()):
        if since and date_str < since:
            continue
        if until and date_str >= until:
            continue
        entry = daily[date_str]
        if entry["commits"] > 0:
            results.append({
                "date": date_str,
                "commits": entry["commits"],
                "repos": sorted(entry["repos"]),
            })

    logger.info("Fetched %d days of GitHub commit data", len(results))
    return results


async def _fetch_via_events(
    headers: dict,
    daily: dict,
) -> None:
    """Fetch commits from Events API (last 90 days, max 300 events)."""
    user = settings.github_user
    async with httpx.AsyncClient(timeout=30) as client:
        page = 1
        while page <= 10:  # Max 10 pages × 100 = 1000, but API caps at 300
            resp = await _request_with_retry(
                client,
                f"{GITHUB_API_URL}/users/{user}/events",
                headers,
                params={"per_page": 100, "page": page},
            )
            events = resp.json()
            if not events:
                break

            for event in events:
                if event.get("type") != "PushEvent":
                    continue
                date_str = event["created_at"][:10]
                payload = event.get("payload", {})
                commit_count = payload.get("distinct_size", 0)
                repo_name = event.get("repo", {}).get("name", "")

                daily[date_str]["commits"] += commit_count
                if repo_name:
                    daily[date_str]["repos"].add(repo_name)

            if len(events) < 100:
                break
            page += 1


async def _fetch_via_search(
    headers: dict,
    since: str,
    until: str,
    daily: dict,
) -> None:
    """Fetch commits from Search API for a specific date range."""
    user = settings.github_user
    query = f"author:{user} author-date:{since}..{until}"

    async with httpx.AsyncClient(timeout=30) as client:
        page = 1
        while True:
            resp = await _request_with_retry(
                client,
                f"{GITHUB_API_URL}/search/commits",
                headers,
                params={"q": query, "sort": "author-date", "order": "desc", "per_page": 100, "page": page},
            )
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                commit = item.get("commit", {})
                author = commit.get("author", {})
                date_str = author.get("date", "")[:10]
                repo_name = item.get("repository", {}).get("full_name", "")

                if date_str:
                    daily[date_str]["commits"] += 1
                    if repo_name:
                        daily[date_str]["repos"].add(repo_name)

            total = data.get("total_count", 0)
            if page * 100 >= total or len(items) < 100:
                break
            page += 1
            await asyncio.sleep(2.1)  # Search API: 30 req/min limit


async def _request_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    params: dict | None = None,
    max_retries: int = 4,
) -> httpx.Response:
    """Make a GET request with exponential backoff retry."""
    for attempt in range(max_retries):
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", str(2 ** attempt)))
            logger.warning("Rate limited, waiting %ds (attempt %d)", retry_after, attempt + 1)
            await asyncio.sleep(retry_after)
            continue
        if resp.status_code in (500, 502, 503):
            wait = 2 ** attempt
            logger.warning("Server error %d, retrying in %ds (attempt %d)", resp.status_code, wait, attempt + 1)
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp
