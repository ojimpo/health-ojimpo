from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Last.fm
    lastfm_api_key: str = ""
    lastfm_user: str = ""
    default_track_duration_seconds: int = 210  # 3.5 minutes

    # Site identity
    app_username: str = "user"
    app_domain: str = "localhost:8401"

    # Database
    database_path: str = "/app/data/health.db"

    # Scheduler
    fetch_interval_hours: int = 6

    # Phase 2 - Simple API sources
    oura_personal_access_token: str = ""
    intervals_api_key: str = ""
    intervals_athlete_id: str = ""
    kashidashi_base_url: str = ""

    # Phase 2 - Webhook
    webhook_secret: str = ""

    # Phase 3 - sync-gateway (Filmarks, 読書メーター)
    sync_gateway_base_url: str = ""

    # Phase 3 - Anthropic Admin API (Claude Code usage)
    anthropic_admin_api_key: str = ""

    # Phase 2 - OAuth2 client credentials (tokens stored in DB)
    strava_client_id: str = ""
    strava_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
