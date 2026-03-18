from dataclasses import dataclass
from enum import Enum


class AlertType(str, Enum):
    single_high_risk = "single_high_risk"
    batch_drift = "batch_drift"
    hallucination_surge = "hallucination_surge"
    rag_degradation = "rag_degradation"


class AlertStatus(str, Enum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    suppressed = "suppressed"


@dataclass(frozen=True)
class AlertEvent:
    id: str
    org_id: str
    status: AlertStatus
