from __future__ import annotations

from agent.router.executors.chat_executor import ChatExecutor
from agent.router.manager_state import ManagerState


def test_memory_sources_text_includes_object_scoped_confirmed_memories():
    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="最近一次质检任务有没有新的讨论内容",
        normalized_query="最近一次质检任务有没有新的讨论内容",
        org_id="org-1",
        memory_sources=[
            {
                "memory_id": "mem-task-1",
                "scope": "inspection_task",
                "title": "screw 边缘识别需加强光照条件",
                "summary": "最近一次质检任务需要关注 screw 边缘识别，光照条件不足会影响判定稳定性。",
            }
        ],
    )

    text = ChatExecutor._memory_sources_text(state)

    assert "Object-scoped confirmed memories" in text
    assert "mem-task-1" in text
    assert "screw 边缘识别需加强光照条件" in text
