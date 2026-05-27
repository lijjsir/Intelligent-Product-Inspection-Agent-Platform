from __future__ import annotations

import json

import pytest

from agent.tools import paper_review_ai


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
    assert "Review Evidence Pack" in messages[0]["content"]
    payload = messages[1]["content"]
    assert "请进行论文查非" in payload
    assert "structure.abstract_missing" in payload


@pytest.mark.asyncio
async def test_generate_ai_review_output_merges_writing_guide_review(monkeypatch):
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
            if "Writing Guide Evidence" in messages[1]["content"]:
                return {
                    "answer": "写作指南建议补充摘要写法。",
                    "summary": "指南补充 1 条建议。",
                    "markdown_report": "# 写作指南补充\n\n应按指南完善摘要。",
                    "issues": [
                        {
                            "title": "摘要写法需人工复核",
                            "severity": "low",
                            "category": "guide",
                            "location": "摘要",
                            "evidence": "写作指南摘要要求",
                            "impact": "表达不完整",
                            "suggestion": "对照指南完善摘要",
                            "need_human_review": True,
                        }
                    ],
                    "download_title": "指南补充报告",
                }
            return {
                "answer": "规则结果已生成。",
                "summary": "规则发现 1 个问题。",
                "markdown_report": "# 规则审阅\n\n缺少摘要。",
                "issues": [{"title": "缺少摘要", "severity": "high"}],
                "download_title": "规则报告",
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
            "role": "writing_guide",
            "file_name": "附件4-写作指南.docx",
            "text": "摘要应说明研究目的、方法、结果和结论。",
        },
        query="请按重邮模板查非",
        db_session=object(),
        org_id="org-1",
    )

    assert len(calls) == 2
    assert result["model_used"] is True
    assert result["guide_review_output"]["summary"] == "指南补充 1 条建议。"
    assert "规则审阅" in result["markdown_report"]
    assert "写作指南补充评判" in result["markdown_report"]
    assert "应按指南完善摘要" in result["markdown_report"]
    assert result["review_sources"] == {
        "rule_template": "cqupt_graduate_thesis_2022",
        "writing_guide": "附件4-写作指南.docx",
    }


@pytest.mark.asyncio
async def test_generate_ai_review_output_returns_fallback_when_runtime_unavailable(monkeypatch):
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

    result = await paper_review_ai.generate_ai_review_output(
        evidence_pack={"score": 70, "issues": []},
        query="查非",
        db_session=object(),
        org_id="org-1",
    )

    assert result["model_used"] is False
    assert result["markdown_report"] == ""
    assert any("未找到可用" in item for item in result["limitations"])


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
