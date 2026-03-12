import logging

from .base import SourceAdapter

logger = logging.getLogger(__name__)

SOURCE_ADAPTERS: dict[str, SourceAdapter] = {}


def register_adapters():
    """Initialize all available adapters."""
    from .lastfm import LastfmAdapter
    from .kashidashi import KashidashiCDAdapter
    from .oura import OuraAdapter
    from .intervals_icu import IntervalsAdapter
    from .screen_time import ScreenTimeAdapter
    from .strava import StravaAdapter, StravaCommuteAdapter, StravaRideAdapter
    from .google_calendar import GoogleCalendarAdapter
    from .gmail import GmailAdapter
    from .claude_local import ClaudeLocalAdapter
    from .github import GitHubAdapter
    from .openai_usage import OpenAIUsageAdapter
    from .sync_gateway import SyncGatewayAdapter

    adapters = [
        LastfmAdapter(),
        KashidashiCDAdapter(),
        OuraAdapter(),
        IntervalsAdapter(),
        ScreenTimeAdapter("instagram"),
        ScreenTimeAdapter("twitter"),
        StravaAdapter(),
        StravaCommuteAdapter(),
        StravaRideAdapter(),
        GoogleCalendarAdapter("gcal_holiday"),
        GoogleCalendarAdapter("gcal_live"),
        GmailAdapter(),
        SyncGatewayAdapter("filmarks", "filmarks", "映画 (Filmarks)", "movie", "🎬", "#FF9500", "本", "映画を視聴 "),
        SyncGatewayAdapter("bookmeter", "bookmeter", "読書メーター", "reading", "📖", "#ADFF2F", "冊", "本を読了 "),
        ClaudeLocalAdapter(),
        GitHubAdapter(),
        OpenAIUsageAdapter(),
    ]
    for adapter in adapters:
        SOURCE_ADAPTERS[adapter.source_id] = adapter
    logger.info("Registered %d source adapters", len(SOURCE_ADAPTERS))


def get_adapter(source_id: str) -> SourceAdapter | None:
    return SOURCE_ADAPTERS.get(source_id)


async def get_configured_adapters() -> list[SourceAdapter]:
    """Return only adapters that have valid credentials."""
    result = []
    for adapter in SOURCE_ADAPTERS.values():
        if await adapter.is_configured():
            result.append(adapter)
    return result
