import asyncio
import logging
from datetime import datetime, timezone

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

OPENAI_USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"


async def fetch_daily_usage(
    start_time: int,
    end_time: int | None = None,
) -> list[dict]:
    """Fetch daily token usage from OpenAI Usage API.

    Args:
        start_time: Unix timestamp (inclusive)
        end_time: Unix timestamp (exclusive), defaults to now

    Returns:
        List of dicts with keys: date, input_tokens, output_tokens, total_tokens
    """
    if not end_time:
        end_time = int(datetime.now(timezone.utc).timestamp())

    headers = {
        "Authorization": f"Bearer {settings.openai_admin_api_key}",
        "Content-Type": "application/json",
    }

    all_buckets: list[dict] = []
    page: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params: dict = {
                "start_time": start_time,
                "end_time": end_time,
                "bucket_width": "1d",
                "limit": 31,
            }
            if page:
                params["page"] = page

            resp = await _request_with_retry(client, params, headers)
            data = resp.json()

            for bucket in data.get("data", []):
                parsed = _parse_bucket(bucket)
                if parsed:
                    all_buckets.append(parsed)

            if data.get("has_more") and data.get("next_page"):
                page = data["next_page"]
            else:
                break

    logger.info("Fetched %d daily usage buckets from OpenAI", len(all_buckets))
    return all_buckets


async def _request_with_retry(
    client: httpx.AsyncClient,
    params: dict,
    headers: dict,
    max_retries: int = 4,
) -> httpx.Response:
    """Make a GET request with exponential backoff retry."""
    for attempt in range(max_retries):
        resp = await client.get(OPENAI_USAGE_URL, params=params, headers=headers)
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


def _parse_bucket(bucket: dict) -> dict | None:
    """Parse a single time bucket into our storage format."""
    start_time = bucket.get("start_time")
    if not start_time:
        return None

    date_str = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y-%m-%d")

    input_tokens = 0
    output_tokens = 0

    for result in bucket.get("results", []):
        input_tokens += result.get("input_tokens", 0)
        input_tokens += result.get("input_cached_tokens", 0)
        output_tokens += result.get("output_tokens", 0)

    total = input_tokens + output_tokens
    if total == 0:
        return None

    return {
        "date": date_str,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
    }
