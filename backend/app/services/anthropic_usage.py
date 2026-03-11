import asyncio
import logging
from datetime import datetime, timezone

import httpx

from ..config import settings

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

            resp = await _request_with_retry(client, params, headers)
            data = resp.json()

            for bucket in data.get("data", []):
                all_buckets.append(_parse_bucket(bucket))

            if data.get("has_more") and data.get("next_page"):
                page = data["next_page"]
            else:
                break

    logger.info("Fetched %d daily usage buckets from Anthropic", len(all_buckets))
    return all_buckets


async def _request_with_retry(
    client: httpx.AsyncClient,
    params: dict,
    headers: dict,
    max_retries: int = 4,
) -> httpx.Response:
    """Make a GET request with exponential backoff retry."""
    for attempt in range(max_retries):
        resp = await client.get(ADMIN_API_URL, params=params, headers=headers)
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
    # Final attempt
    resp.raise_for_status()
    return resp


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
