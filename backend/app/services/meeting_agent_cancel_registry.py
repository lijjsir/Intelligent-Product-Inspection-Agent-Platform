from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class MeetingAgentCancelRegistry:
    _cancelled: set[tuple[str, str]] = field(default_factory=set)
    _instance: ClassVar["MeetingAgentCancelRegistry" | None] = None

    @classmethod
    def instance(cls) -> "MeetingAgentCancelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def cancel(self, room_id: str, workflow_run_id: str) -> bool:
        key = (str(room_id), str(workflow_run_id))
        self._cancelled.add(key)
        return True

    def is_cancelled(self, room_id: str, workflow_run_id: str) -> bool:
        return (str(room_id), str(workflow_run_id)) in self._cancelled

    def clear(self, room_id: str, workflow_run_id: str) -> None:
        self._cancelled.discard((str(room_id), str(workflow_run_id)))


meeting_agent_cancel_registry = MeetingAgentCancelRegistry.instance()
