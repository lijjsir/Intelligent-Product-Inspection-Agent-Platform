from __future__ import annotations

from typing import Awaitable, Callable

from agent.graph.nodes.finalizer import finalize
from agent.graph.nodes.knowledge import run_knowledge
from agent.graph.nodes.planner import plan
from agent.graph.nodes.reasoning import run_reasoning
from agent.graph.nodes.vision import run_vision
from agent.graph.state import InspectionState

Node = Callable[[InspectionState], Awaitable[InspectionState]]
EventHandler = Callable[[dict], Awaitable[None]]


class InspectionGraph:
    def __init__(self) -> None:
        """定义单次质检任务的固定图执行顺序。"""
        self._nodes: list[tuple[str, Node]] = [
            ("planner", plan),
            ("vision", run_vision),
            ("knowledge", run_knowledge),
            ("reasoning", run_reasoning),
            ("finalizer", finalize),
        ]

    async def run(self, state: InspectionState, on_event: EventHandler | None = None) -> InspectionState:
        """按顺序执行图节点，并在阶段开始和结束时向外发送事件。"""
        for name, node in self._nodes:
            if on_event:
                await on_event({"type": "stage_start", "stage": name})
            state = await node(state)
            if on_event:
                await on_event({"type": "stage_end", "stage": name, "timeline": state.get("timeline", [])[-1:]})
            if state.get("runtime_errors"):
                break
        return state
