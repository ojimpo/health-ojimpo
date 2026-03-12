import logging
from datetime import datetime, timezone

import httpx

from ..config import settings
from .http_retry import request_with_retry

logger = logging.getLogger(__name__)

ADMIN_API_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"


async def fetch_daily_usage(
    starting_at: str,
    ending_at: str | None = None,
) -> list[dict]:
    """Fetch daily token usage from Anthropic Admin API.

    Args:
        starting_at: RFC 3339 timestamp (e.g. "2026-01-01T00:00:00Z")
        ending_at: RFC 3339 timestamp, defaults to now

    Returns:
        List of dicts with keys: date, uncached_input_tokens, cached_input_tokens,
        cache_creation_tokens, output_tokens, total_tokens
    """
    if not ending_at:
        ending_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {
        "x-api-key": settings.anthropic_admin_api_key,
        "anthropic-version": "2023-06-01",
    }

    all_buckets: list[dict] = []
    page: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params: dict = {
                "starting_at": starting_at,
                "ending_at": ending_at,
                "bucket_width": "1d",
                "limit": 31,
            }
            if page:
                params["page"] = page

            resp = await request_with_retry(client, ADMIN_API_URL, headers, params)
            data = resp.json()

            for bucket in data.get("data", []):
                all_buckets.append(_parse_bucket(bucket))

            if data.get("has_more") and data.get("next_page"):
                page = data["next_page"]
            else:
                break

    return all_buckets


def _parse_bucket(bucket: dict) -> dict:
    """Parse a single time bucket into our storage format."""
    # Extract date from starting_at (RFC 3339 → YYYY-MM-DD)
    start = bucket["starting_at"]
    date_str = start[:10]  # "2026-03-11T00:00:00Z" → "2026-03-11"

    # Sum all results in this bucket (there may be multiple if grouped)
    uncached_input = 0
    cached_input = 0
    cache_creation = 0
    output = 0

    for result in bucket.get("results", []):
        uncached_input += result.get("uncached_input_tokens", 0)
        cached_input += result.get("cache_read_input_tokens", 0)
        creation = result.get("cache_creation", {})
        cache_creation += creation.get("ephemeral_5m_input_tokens", 0)
        cache_creation += creation.get("ephemeral_1h_input_tokens", 0)
        output += result.get("output_tokens", 0)

    total = uncached_input + cached_input + cache_creation + output

    return {
        "date": date_str,
        "uncached_input_tokens": uncached_input,
        "cached_input_tokens": cached_input,
        "cache_creation_tokens": cache_creation,
        "output_tokens": output,
        "total_tokens": total,
    }
