from dataclasses import dataclass
from enum import Enum


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    reviewing = "reviewing"


@dataclass(frozen=True)
class InspectionTask:
    id: str
    org_id: str
    product_id: str
    spec_code: str
    status: TaskStatus
