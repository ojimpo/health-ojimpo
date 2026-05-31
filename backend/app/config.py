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

    # Phase 3 - GitHub (commits/contributions)
    github_token: str = ""
    github_user: str = ""

    # Phase 3 - OpenAI Usage API (Codex usage)
    openai_admin_api_key: str = ""

    # Phase 2 - OAuth2 client credentials (tokens stored in DB)
    strava_client_id: str = ""
    strava_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # Google Calendar IDs (personal calendars)
    gcal_private_calendar_id: str = ""
    gcal_live_calendar_id: str = ""

    # NextDNS
    nextdns_api_key: str = ""
    nextdns_profile_id: str = ""
    # 外出推定で「自宅Wi-Fi」と判定する都市名（NextDNSのgeo.city一致、カンマ区切りで複数可）。
    # cellular=false かつこのリストに含まれる都市の IP のみ「自宅クエリ」扱い。
    outing_home_cities: str = ""

    # Stash (local media manager)
    stash_api_url: str = "http://localhost:9999"
    stash_api_key: str = ""

    # Steam Web API
    steam_api_key: str = ""
    steam_id64: str = ""

    # Duolingo (unofficial API) — 語学学習。ブラウザの jwt_token Cookie と数値 user_id を設定。
    duolingo_jwt: str = ""
    duolingo_user_id: str = ""
    # 1セッションあたりの推定学習分（totalSessionTime が取得できない場合のフォールバック）
    duolingo_minutes_per_session: float = 7.0

    # Notification - LINE Messaging API
    line_channel_access_token: str = ""
    line_channel_secret: str = ""
    line_bot_basic_id: str = ""
    personal_line_url: str = ""

    # Notification
    notification_enabled: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
