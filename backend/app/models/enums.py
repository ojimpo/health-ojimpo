from enum import Enum


class HealthStatus(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    CRITICAL = "CRITICAL"


class CulturalStatus(str, Enum):
    RICH = "RICH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class TimeRange(str, Enum):
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    ONE_YEAR = "1y"
