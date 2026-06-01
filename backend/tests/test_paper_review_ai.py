from __future__ import annotations

import json

import httpx
import pytest

from agent.tools import paper_review_ai
from agent.tools.paper_review_ai import PaperReviewModelError


@pytest.mark.asyncio
async def test_generate_ai_review_output_uses_configured_chat_model(monkeypatch):
    calls: dict[str, object] = {}

    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            calls["service_org_id"] = org_id

        async def list_runtime_models(self):
            return [{"id": "model-1", "model_key": "paper-review-model", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve):
            calls["models"] = models
            calls["model_types"] = model_types
            calls["reserve"] = reserve
            return {
                "api_key": "test-key",
                "base_url": "https://llm.example/v1",
                "model_id": "paper-review-model",
                "provider": "local_openai",
                "input_price_per_million": 1.0,
                "output_price_per_million": 2.0,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs

        async def chat(self, messages, **kwargs):
            calls["messages"] = messages
            calls["chat_kwargs"] = kwargs
            return {
                "answer": "已完成模型审阅。",
                "summary": "模型发现 1 个高优先级问题。",
                "markdown_report": "# 模型生成的论文查非报告\n\n唯一模型报告文本",
                "issues": [
                    {
                        "title": "缺少摘要",
                        "severity": "high",
                        "category": "structure",
                        "location": "abstract",
                        "evidence": "未找到摘要标题",
                        "impact": "结构不完整",
                        "suggestion": "补充摘要",
                        "need_human_review": False,
                    }
                ],
                "download_title": "模型报告",
            }

    monkeypatch.setattr(paper_review_ai, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(paper_review_ai, "LLMGateway", FakeGateway)
    monkeypatch.setattr(paper_review_ai, "LLMClient", FakeLLMClient)

    evidence_pack = {
        "document": {"file_name": "paper.docx", "document_type": "docx"},
        "score": 88,
        "issues": [{"code": "structure.abstract_missing", "severity": "high"}],
        "limitations": ["模板规则有限"],
    }

    result = await paper_review_ai.generate_ai_review_output(
        evidence_pack=evidence_pack,
        query="请进行论文查非",
        db_session=object(),
        org_id="org-1",
        trace_id="trace-1",
        task_id="session-1",
    )

    assert result["answer"] == "已完成模型审阅。"
    assert result["summary"] == "模型发现 1 个高优先级问题。"
    assert "唯一模型报告文本" in result["markdown_report"]
    assert result["model_used"] is True
    assert result["issues"][0]["title"] == "缺少摘要"
    assert calls["service_org_id"] == "org-1"
    assert calls["model_types"] == {"chat"}
    assert calls["reserve"] is False
    assert calls["client_kwargs"] == {
        "api_key": "test-key",
        "base_url": "https://llm.example/v1",
        "model_id": "paper-review-model",
        "provider": "local_openai",
        "trace_id": "trace-1",
        "task_id": "session-1",
        "org_id": "org-1",
        "input_price_per_million": 1.0,
        "output_price_per_million": 2.0,
    }
    messages = calls["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "论文格式与规范审阅助手" in messages[0]["content"]
    payload = messages[1]["content"]
    assert "请进行论文查非" in payload
    assert "structure.abstract_missing" in payload


@pytest.mark.asyncio
async def test_generate_ai_review_output_includes_guide_clauses(monkeypatch):
    calls: list[list[dict[str, str]]] = []

    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-1", "model_key": "paper-review-model", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve):
            return {
                "api_key": "test-key",
                "base_url": "https://llm.example/v1",
                "model_id": "paper-review-model",
                "provider": "local_openai",
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat(self, messages, **kwargs):
            calls.append(messages)
            return {
                "answer": "规则结果已生成，并参考了写作指南。",
                "summary": "规则发现 1 个问题，并补充了模板建议。",
                "markdown_report": "# 审阅报告\n\n缺少摘要。应按指南完善摘要。",
                "issues": [{"title": "缺少摘要", "severity": "high"}],
                "download_title": "论文查非与格式审阅报告",
            }

    monkeypatch.setattr(paper_review_ai, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(paper_review_ai, "LLMGateway", FakeGateway)
    monkeypatch.setattr(paper_review_ai, "LLMClient", FakeLLMClient)

    result = await paper_review_ai.generate_ai_review_output(
        evidence_pack={
            "document": {"file_name": "paper.docx", "template_id": "cqupt_graduate_thesis_2022"},
            "issues": [{"code": "structure.abstract_missing"}],
        },
        guide_evidence={
            "template_id": "cqupt_graduate_thesis_2022",
            "template_name": "重庆邮电大学模板",
            "source": "qdrant_rag",
            "file_name": "附件4-写作指南.docx",
            "clauses": [
                {"clause_id": "c001", "text": "摘要应说明研究目的、方法、结果和结论。", "score": 0.9}
            ],
        },
        query="请按重邮模板查非",
        db_session=object(),
        org_id="org-1",
    )

    assert len(calls) == 1
    assert result["model_used"] is True
    assert "审阅报告" in result["markdown_report"]
    assert result["review_sources"] == {
        "rule_template": "cqupt_graduate_thesis_2022",
        "writing_guide": "附件4-写作指南.docx",
    }
    # Verify clauses are included in model input
    user_content = calls[0][1]["content"]
    assert "检索到的模板条款" in user_content
    assert "摘要应说明研究目的" in user_content


@pytest.mark.asyncio
async def test_generate_ai_review_output_raises_when_runtime_unavailable(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return []

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve):
            return None

    monkeypatch.setattr(paper_review_ai, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(paper_review_ai, "LLMGateway", FakeGateway)

    with pytest.raises(PaperReviewModelError) as exc_info:
        await paper_review_ai.generate_ai_review_output(
            evidence_pack={"score": 70, "issues": []},
            query="查非",
            db_session=object(),
            org_id="org-1",
        )

    assert "未找到可用" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_ai_review_output_surfaces_actionable_connect_error(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-1", "model_key": "paper-review-model", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve):
            return {
                "api_key": None,
                "base_url": "http://127.0.0.1:11434/v1",
                "model_id": "paper-review-model",
                "provider": "local_openai",
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat(self, messages, **kwargs):
            raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(paper_review_ai, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(paper_review_ai, "LLMGateway", FakeGateway)
    monkeypatch.setattr(paper_review_ai, "LLMClient", FakeLLMClient)

    with pytest.raises(PaperReviewModelError) as exc_info:
        await paper_review_ai.generate_ai_review_output(
            evidence_pack={"document": {"file_name": "paper.docx"}, "issues": []},
            query="查非",
            db_session=object(),
            org_id="org-1",
        )

    message = str(exc_info.value)
    assert "无法连接到 local_openai 模型端点 http://127.0.0.1:11434/v1" in message
    assert "host.docker.internal" in message


def test_normalize_ai_review_output_accepts_text_json_payload():
    result = paper_review_ai.normalize_ai_review_output(
        {
            "text": json.dumps(
                {
                    "answer": "ok",
                    "summary": "done",
                    "markdown_report": "# report",
                    "issues": [],
                    "download_title": "title",
                },
                ensure_ascii=False,
            )
        }
    )

    assert result["answer"] == "ok"
    assert result["summary"] == "done"
    assert result["markdown_report"] == "# report"
    assert result["download_title"] == "title"


@pytest.mark.asyncio
async def test_generate_ai_review_output_filters_model_invented_limitations(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-1", "model_key": "paper-review-model", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve):
            return {
                "api_key": "test-key",
                "base_url": "https://llm.example/v1",
                "model_id": "paper-review-model",
                "provider": "local_openai",
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat(self, messages, **kwargs):
            return {
                "answer": "已完成。",
                "summary": "发现 1 个问题。",
                "markdown_report": (
                    "# 报告\n\n"
                    "已按证据生成。\n\n"
                    "## 局限性说明\n\n"
                    "- 当前检查仅基于规则引擎自动识别，图表格式、页眉页脚、参考文献著录格式等未覆盖，需人工复核。\n"
                    "- 字体字号检查仅依据第1段证据，其他段落可能也存在类似问题，建议全面核查。\n\n"
                    "## 修改建议\n\n"
                    "请按模板修改。"
                ),
                "issues": [],
                "limitations": [
                    "当前检查仅基于规则引擎自动识别，图表格式、页眉页脚、参考文献著录格式等未覆盖，需人工复核。",
                    "字体字号检查仅依据第1段证据，其他段落可能也存在类似问题，建议全面核查。",
                    "已使用重庆邮电大学研究生学位论文模板（2022版）规则进行辅助校验，仍需以学校最新正式文件为准。",
                ],
                "download_title": "论文查非与格式审阅报告",
            }

    monkeypatch.setattr(paper_review_ai, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(paper_review_ai, "LLMGateway", FakeGateway)
    monkeypatch.setattr(paper_review_ai, "LLMClient", FakeLLMClient)

    allowed_limit = "已使用重庆邮电大学研究生学位论文模板（2022版）规则进行辅助校验，仍需以学校最新正式文件为准。"
    result = await paper_review_ai.generate_ai_review_output(
        evidence_pack={
            "document": {"file_name": "paper.docx", "document_type": "docx"},
            "issues": [{"code": "template.body_font_mismatch"}],
            "limitations": [allowed_limit],
        },
        query="查非",
        db_session=object(),
        org_id="org-1",
    )

    assert result["limitations"] == [allowed_limit]
    assert "当前检查仅基于规则引擎" not in result["markdown_report"]
    assert "字体字号检查仅依据第1段证据" not in result["markdown_report"]
    assert "局限性说明" not in result["markdown_report"]
    assert "请按模板修改" in result["markdown_report"]


def test_trim_issues_for_model_trims_low_severity():
    issues = [
        {"severity": "high", "code": "h1"},
        {"severity": "high", "code": "h2"},
        {"severity": "medium", "code": "m1"},
        {"severity": "medium", "code": "m2"},
        {"severity": "low", "code": "l1"},
        {"severity": "low", "code": "l2"},
        {"severity": "low", "code": "l3"},
        {"severity": "low", "code": "l4"},
        {"severity": "low", "code": "l5"},
        {"severity": "low", "code": "l6"},
        {"severity": "low", "code": "l7"},
    ]
    result = paper_review_ai._trim_issues_for_model(issues, max_high=20, max_medium=10, max_low_abstract=5)
    codes = [i["code"] for i in result]
    assert "h1" in codes
    assert "h2" in codes
    assert "m1" in codes
    assert "l1" in codes
    assert "l5" in codes
    assert "l6" not in codes


def test_trim_issues_for_model_adds_omitted_summary():
    issues = [
        {"severity": "low", "code": f"l{i}"} for i in range(20)
    ]
    result = paper_review_ai._trim_issues_for_model(issues, max_low_abstract=3)
    assert len(result) == 4
    assert result[-1]["code"] == "summary.low_severity_omitted"
