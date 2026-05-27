from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document

from agent.contracts.quality_contracts import NormalizedAttachment, NormalizedRequest
from agent.router.manager_loop import ManagerLoop
from agent.router.manager_policy import ManagerPolicy


def _docx_bytes() -> bytes:
    doc = Document()
    doc.add_heading("论文标题", level=1)
    doc.add_paragraph("这是  一个待检查段落。")
    doc.add_paragraph("参考文献")
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


@pytest.mark.asyncio
async def test_manager_policy_routes_paper_queries_to_paper_format_check():
    policy = ManagerPolicy()
    request = NormalizedRequest(
        request_id="req-1",
        workflow_run_id="wf-1",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        query="请帮我检查这篇论文的格式和错别字",
        attachments=[NormalizedAttachment(name="paper.docx", kind="file")],
        ext={"surface": "chat"},
    )

    state = policy.initialize_state(request)
    understanding = await policy.understand(state)

    assert understanding.intent == "paper_format_check"
    assert understanding.needs == ["file.paper_format_check", "chat.response.compose"]


@pytest.mark.asyncio
async def test_manager_loop_returns_paper_format_report(monkeypatch):
    async def fake_call_model(self, state, request, prompt, **kwargs):
        return "已完成论文查非，发现摘要缺失和连续空格问题。"

    monkeypatch.setattr(
        "agent.router.executors.chat_executor.ChatExecutor._call_model",
        fake_call_model,
    )
    monkeypatch.setattr(
        "app.services.object_storage.resolver.read_attachment_bytes",
        lambda attachment: (_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    )

    output = await ManagerLoop().run(
        NormalizedRequest(
            request_id="req-2",
            workflow_run_id="wf-2",
            org_id="org-1",
            user_id="user-1",
            session_id="session-1",
            query="帮我做论文查非",
            attachments=[
                NormalizedAttachment(
                    name="paper.docx",
                    kind="file",
                    bucket="test",
                    object_key="paper.docx",
                )
            ],
            ext={"surface": "chat"},
        )
    )

    artifacts = output.agent_output["artifacts"]
    paper_reports = [item for item in artifacts if item["type"] == "paper_format_report"]

    assert output.route_decision.sub_route == "paper_format_check"
    assert output.agent_output["message_type"] == "file_answer"
    assert paper_reports
    assert paper_reports[0]["content"]["issues"]
