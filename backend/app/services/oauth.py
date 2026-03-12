import logging
import time

import httpx

from ..database import get_db_context

logger = logging.getLogger(__name__)


async def get_valid_token(source_id: str) -> str | None:
    """Get a valid access token, refreshing if expired."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT access_token, refresh_token, expires_at, token_type FROM oauth_tokens WHERE source_id = ?",
            (source_id,),
        )
        if not rows:
            return None

        access_token, refresh_token, expires_at, token_type = rows[0]

        # Check if expired (with 5-minute buffer)
        if expires_at and time.time() > (expires_at - 300):
            if refresh_token:
                new_token = await _refresh_token(source_id, refresh_token)
                if new_token:
                    return new_token
            logger.warning("Token expired and refresh failed for %s", source_id)
            return None

        return access_token


async def _refresh_token(source_id: str, refresh_token: str) -> str | None:
    """Refresh an OAuth2 token."""
    from ..config import settings

    # Determine token endpoint and client credentials based on source
    if source_id == "strava":
        token_url = "https://www.strava.com/oauth/token"
        client_id = settings.strava_client_id
        client_secret = settings.strava_client_secret
    elif source_id in ("gcal_holiday", "gcal_live", "gmail"):
        token_url = "https://oauth2.googleapis.com/token"
        client_id = settings.google_client_id
        client_secret = settings.google_client_secret
    else:
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(token_url, data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Failed to refresh token for %s", source_id)
        return None

    new_access = data.get("access_token")
    new_refresh = data.get("refresh_token", refresh_token)
    expires_in = data.get("expires_in", 3600)

    await store_tokens(source_id, {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_in": expires_in,
        "token_type": data.get("token_type", "Bearer"),
    })

    return new_access


async def store_tokens(source_id: str, token_data: dict):
    """Store OAuth2 tokens in the database."""
    expires_at = int(time.time()) + token_data.get("expires_in", 3600)
    async with get_db_context() as db:
        await db.execute(
            """INSERT OR REPLACE INTO oauth_tokens
            (source_id, access_token, refresh_token, token_type, expires_at, scope, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                source_id,
                token_data["access_token"],
                token_data.get("refresh_token"),
                token_data.get("token_type", "Bearer"),
                expires_at,
                token_data.get("scope"),
            ),
        )
        # Activate the source
        await db.execute(
            "UPDATE source_settings SET status = 'active' WHERE id = ?",
            (source_id,),
        )
        # Strava OAuth also activates the commute and ride sources
        if source_id == "strava":
            await db.execute(
                "UPDATE source_settings SET status = 'active' WHERE id IN ('strava_commute', 'strava_ride')",
            )
        await db.commit()
    logger.info("Stored OAuth2 tokens for %s", source_id)


async def has_token(source_id: str) -> bool:
    """Check if we have a stored token for a source."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT 1 FROM oauth_tokens WHERE source_id = ?",
            (source_id,),
        )
        return bool(rows)
