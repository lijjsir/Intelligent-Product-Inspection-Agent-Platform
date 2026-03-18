from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    pass_ = "pass"
    fail = "fail"
    uncertain = "uncertain"
    manual_required = "manual_required"


@dataclass(frozen=True)
class InspectionResult:
    id: str
    task_id: str
    verdict: Verdict
