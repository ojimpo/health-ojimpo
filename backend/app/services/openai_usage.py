import logging
from datetime import datetime, timezone

import httpx

from ..config import settings
from .http_retry import request_with_retry

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

            resp = await request_with_retry(client, OPENAI_USAGE_URL, headers, params)
            data = resp.json()

            for bucket in data.get("data", []):
                parsed = _parse_bucket(bucket)
                if parsed:
                    all_buckets.append(parsed)

            if data.get("has_more") and data.get("next_page"):
                page = data["next_page"]
            else:
                break

    return all_buckets


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
