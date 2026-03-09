from enum import Enum


class HealthStatus(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    CRITICAL = "CRITICAL"


class CulturalStatus(str, Enum):
    RICH = "RICH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class Classification(str, Enum):
    BASELINE = "baseline"
    EVENT = "event"
    BOTH = "both"


class DisplayType(str, Enum):
    ACTIVITY = "activity"
    STATE = "state"


class SourcePhase(str, Enum):
    MVP = "mvp"
    PHASE2 = "phase2"
    PHASE3 = "phase3"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    COMING_SOON = "coming_soon"


class TimeRange(str, Enum):
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    ONE_YEAR = "1y"
