from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    green = "GREEN"
    yellow = "YELLOW"
    orange = "ORANGE"
    red = "RED"


@dataclass(frozen=True)
class StabilityReport:
    id: str
    task_id: str
    risk_score: float
    risk_level: RiskLevel
