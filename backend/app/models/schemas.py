from __future__ import annotations

from pydantic import BaseModel

from .enums import CulturalStatus, HealthStatus


# --- Dashboard ---


class StatusInfo(BaseModel):
    status: str
    score: float
    message: str


class ChartDataPoint(BaseModel):
    date: str
    music: float = 0
    exercise: float = 0
    commute: float = 0
    reading: float = 0
    movie: float = 0
    sns: float = 0
    coding: float = 0
    calendar: float = 0
    live: float = 0
    shopping: float = 0
    vitality: float = 0
    sleep: float | None = None
    readiness: float | None = None
    stress: float | None = None
    weight: float | None = None
    health_status: str | None = None
    cultural_status: str | None = None
    health_score: float | None = None
    cultural_score: float | None = None


class CategoryCard(BaseModel):
    key: str
    label: str
    color: str
    current: float
    previous: float
    change: float


class StateCard(BaseModel):
    key: str
    label: str
    color: str
    current: float | None
    previous: float | None
    change: float | None


class TrendComment(BaseModel):
    text: str
    type: str  # "positive", "warning", "neutral"


class RecentActivity(BaseModel):
    time: str
    icon: str
    text: str
    detail: str | None = None
    color: str


class DashboardResponse(BaseModel):
    health_status: StatusInfo
    cultural_status: StatusInfo
    activity_chart: list[ChartDataPoint]
    condition_chart: list[ChartDataPoint]
    category_cards: list[CategoryCard]
    state_cards: list[StateCard]
    trend_comments: list[TrendComment]
    recent_activities: list[RecentActivity]


# --- Shared View ---


class PresentationInfo(BaseModel):
    accent_color: str
    bg_color: str
    is_critical: bool
    chart_saturation: float


class SharedViewResponse(BaseModel):
    health_status: StatusInfo
    cultural_status: StatusInfo
    activity_chart: list[ChartDataPoint]
    condition_chart: list[ChartDataPoint]
    category_cards: list[CategoryCard]
    trend_comments: list[TrendComment]
    recent_activities: list[RecentActivity]
    friendly_message: str
    presentation: PresentationInfo


# --- Settings ---


class BaselineHistoryItem(BaseModel):
    id: int | None = None
    effective_from: str
    base_value: float
    base_unit: str
    memo: str | None = None


class SourceSettingsResponse(BaseModel):
    id: str
    name: str
    category: str
    icon: str
    display_type: str
    classification: str
    phase: str
    status: str
    color: str
    show_personal: bool
    show_shared: bool
    aggregation_period: int
    base_value: float
    base_unit: str
    spontaneity_coefficient: float
    sort_order: int
    baseline_history: list[BaselineHistoryItem] = []


class SourceSettingsUpdate(BaseModel):
    show_personal: bool | None = None
    show_shared: bool | None = None
    display_type: str | None = None
    classification: str | None = None
    aggregation_period: int | None = None
    base_value: float | None = None
    base_unit: str | None = None
    spontaneity_coefficient: float | None = None


class BaselineCreate(BaseModel):
    effective_from: str
    base_value: float
    base_unit: str
    memo: str | None = None


class ThresholdsResponse(BaseModel):
    health_normal_threshold: float
    health_caution_threshold: float
    cultural_rich_threshold: float
    cultural_moderate_threshold: float


class ThresholdsUpdate(BaseModel):
    health_normal_threshold: float | None = None
    health_caution_threshold: float | None = None
    cultural_rich_threshold: float | None = None
    cultural_moderate_threshold: float | None = None


class SharedViewSettingsResponse(BaseModel):
    token: str
    enabled: bool
    url: str


class SharedViewSettingsUpdate(BaseModel):
    enabled: bool


# --- Ingest ---


class IngestTrigger(BaseModel):
    source: str = "lastfm"
    from_date: str | None = None


class IngestStatusResponse(BaseModel):
    last_run: str | None
    records_total: int
    status: str
    next_scheduled: str | None


# --- Notification ---


class EmailSubscribeRequest(BaseModel):
    email: str


class SubscriberResponse(BaseModel):
    id: int
    channel: str
    channel_id: str
    display_name: str | None
    verified: bool
    active: bool
    created_at: str
