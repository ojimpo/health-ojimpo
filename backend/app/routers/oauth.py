import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from ..services.oauth import store_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])


OAUTH_CONFIGS = {
    "strava": {
        "authorize_url": "https://www.strava.com/oauth/authorize",
        "token_url": "https://www.strava.com/oauth/token",
        "scope": "read,activity:read_all",
    },
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send",
    },
    "spotify": {
        "authorize_url": "https://accounts.spotify.com/authorize",
        "token_url": "https://accounts.spotify.com/api/token",
        "scope": "user-read-recently-played user-read-playback-position user-library-read",
    },
}


@router.get("/{source_id}/authorize")
async def oauth_authorize(source_id: str, request: Request):
    """Redirect user to OAuth2 authorization page."""
    if source_id == "strava":
        config = OAUTH_CONFIGS["strava"]
        client_id = settings.strava_client_id
        if not client_id:
            raise HTTPException(400, "STRAVA_CLIENT_ID not configured")
        redirect_uri = str(request.base_url).rstrip("/") + f"/api/oauth/strava/callback"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config["scope"],
            "state": "strava",
        }
        return RedirectResponse(f"{config['authorize_url']}?{urlencode(params)}")

    elif source_id == "spotify_podcast":
        config = OAUTH_CONFIGS["spotify"]
        client_id = settings.spotify_client_id
        if not client_id:
            raise HTTPException(400, "SPOTIFY_CLIENT_ID not configured")
        redirect_uri = "https://health.ojimpo.com/api/oauth/spotify/callback"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config["scope"],
            "state": "spotify_podcast",
        }
        return RedirectResponse(f"{config['authorize_url']}?{urlencode(params)}")

    elif source_id in ("gcal_private", "gcal_live", "gmail"):
        config = OAUTH_CONFIGS["google"]
        client_id = settings.google_client_id
        if not client_id:
            raise HTTPException(400, "GOOGLE_CLIENT_ID not configured")
        redirect_uri = "https://health.ojimpo.com/api/oauth/google/callback"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config["scope"],
            "access_type": "offline",
            "prompt": "consent",
            "state": source_id,
        }
        return RedirectResponse(f"{config['authorize_url']}?{urlencode(params)}")

    raise HTTPException(400, f"Unknown OAuth source: {source_id}")


@router.get("/strava/callback")
async def strava_callback(code: str, request: Request):
    """Handle Strava OAuth2 callback."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(OAUTH_CONFIGS["strava"]["token_url"], data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Strava OAuth callback failed")
        raise HTTPException(500, "Failed to exchange authorization code")

    await store_tokens("strava", {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in", 21600),
        "token_type": data.get("token_type", "Bearer"),
    })

    return RedirectResponse("/settings")


@router.get("/spotify/callback")
async def spotify_callback(code: str, state: str, request: Request):
    """Handle Spotify OAuth2 callback."""
    redirect_uri = "https://health.ojimpo.com/api/oauth/spotify/callback"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(OAUTH_CONFIGS["spotify"]["token_url"], data={
                "client_id": settings.spotify_client_id,
                "client_secret": settings.spotify_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Spotify OAuth callback failed")
        raise HTTPException(500, "Failed to exchange authorization code")

    await store_tokens("spotify_podcast", {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in", 3600),
        "token_type": data.get("token_type", "Bearer"),
        "scope": data.get("scope"),
    })

    return RedirectResponse("/settings")


@router.get("/google/callback")
async def google_callback(code: str, state: str, request: Request):
    """Handle Google OAuth2 callback. Stores tokens for gcal_holiday, gcal_live, and gmail."""
    redirect_uri = "https://health.ojimpo.com/api/oauth/google/callback"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(OAUTH_CONFIGS["google"]["token_url"], data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Google OAuth callback failed")
        raise HTTPException(500, "Failed to exchange authorization code")

    token_data = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in", 3600),
        "token_type": data.get("token_type", "Bearer"),
        "scope": data.get("scope"),
    }

    # Store tokens for all Google sources
    for source_id in ("gcal_private", "gcal_live", "gmail"):
        await store_tokens(source_id, token_data)

    return RedirectResponse("/settings")
