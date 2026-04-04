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
    from .strava import StravaAdapter, StravaCommuteAdapter, StravaVoluntaryAdapter
    from .google_calendar import GoogleCalendarAdapter
    from .claude_local import ClaudeLocalAdapter
    from .github import GitHubAdapter
    from .openai_usage import OpenAIUsageAdapter
    from .sync_gateway import SyncGatewayAdapter
    from .nextdns_shopping import NextDNSShoppingAdapter
    from .nextdns_sns import NextDNSSNSAdapter
    from .nextdns_vitality import NextDNSVitalityAdapter
    from .stash_vitality import StashVitalityAdapter
    from .nextdns_outing import NextDNSOutingAdapter

    adapters = [
        LastfmAdapter(),
        KashidashiCDAdapter(),
        OuraAdapter(),
        IntervalsAdapter(),
        StravaAdapter(),
        StravaCommuteAdapter(),  # kept for backward compat, disabled in DB
        StravaVoluntaryAdapter(),
        GoogleCalendarAdapter("gcal_private"),
        GoogleCalendarAdapter("gcal_live"),
        SyncGatewayAdapter("filmarks", "filmarks", "映画 (Filmarks)", "movie", "🎬", "#FF9500", "本", "映画を視聴 "),
        SyncGatewayAdapter("bookmeter", "bookmeter", "読書メーター", "reading", "📖", "#ADFF2F", "冊", "本を読了 "),
        ClaudeLocalAdapter(),
        GitHubAdapter(),
        OpenAIUsageAdapter(),
        NextDNSShoppingAdapter(),
        NextDNSSNSAdapter(),
        NextDNSVitalityAdapter(),
        StashVitalityAdapter(),
        NextDNSOutingAdapter(),
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
