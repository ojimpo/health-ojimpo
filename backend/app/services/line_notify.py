import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


async def send_line_notification(user_id: str, message: str) -> None:
    """Send a push message to a LINE user via Messaging API."""
    token = settings.line_channel_access_token
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            LINE_PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "to": user_id,
                "messages": [{"type": "text", "text": message}],
            },
        )
        if resp.status_code != 200:
            logger.error("LINE push failed: %d %s", resp.status_code, resp.text)
            resp.raise_for_status()

    logger.info("LINE notification sent to %s", user_id[:8] + "...")
