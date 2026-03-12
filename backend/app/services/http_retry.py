import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def request_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    params: dict | None = None,
    max_retries: int = 4,
) -> httpx.Response:
    """Make a GET request with exponential backoff retry for 429/5xx."""
    for attempt in range(max_retries):
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", str(2**attempt)))
            logger.warning("Rate limited, waiting %ds (attempt %d)", retry_after, attempt + 1)
            await asyncio.sleep(retry_after)
            continue
        if resp.status_code in (500, 502, 503):
            wait = 2**attempt
            logger.warning(
                "Server error %d, retrying in %ds (attempt %d)",
                resp.status_code,
                wait,
                attempt + 1,
            )
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp
