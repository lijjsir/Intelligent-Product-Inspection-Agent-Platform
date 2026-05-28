from __future__ import annotations

import pytest

from agent.tools.paper_template_evidence import load_writing_guide_evidence


@pytest.mark.asyncio
async def test_load_writing_guide_evidence_without_issues_does_not_load_full_guide():
    evidence = await load_writing_guide_evidence("cqupt_graduate_thesis_2022")

    assert evidence is not None
    assert evidence["template_id"] == "cqupt_graduate_thesis_2022"
    assert evidence["source"] == "none"
    assert evidence["clauses"] == []


@pytest.mark.asyncio
async def test_load_writing_guide_evidence_uses_retrieved_clauses(monkeypatch):
    class FakeRetriever:
        def __init__(self, **kwargs):
            pass

        async def retrieve_for_issues(self, *, template_id, issues, top_k):
            return [
                {
                    "clause_id": "c001",
                    "text": "摘要应说明研究目的、方法、结果和结论。",
                    "source_file_name": "writing-guide.docx",
                    "score": 0.91,
                }
            ]

    monkeypatch.setattr(
        "agent.rag.paper_template_clause_retriever.PaperTemplateClauseRetriever",
        FakeRetriever,
    )

    evidence = await load_writing_guide_evidence(
        "cqupt_graduate_thesis_2022",
        issues=[{"code": "structure.abstract_missing", "title": "缺少摘要"}],
    )

    assert evidence is not None
    assert evidence["source"] == "qdrant_rag"
    assert evidence["file_name"] == "writing-guide.docx"
    assert evidence["clauses"][0]["clause_id"] == "c001"


@pytest.mark.asyncio
async def test_load_writing_guide_evidence_returns_error_when_retrieval_empty(monkeypatch):
    class FakeRetriever:
        def __init__(self, **kwargs):
            pass

        async def retrieve_for_issues(self, *, template_id, issues, top_k):
            return []

    monkeypatch.setattr(
        "agent.rag.paper_template_clause_retriever.PaperTemplateClauseRetriever",
        FakeRetriever,
    )

    evidence = await load_writing_guide_evidence(
        "cqupt_graduate_thesis_2022",
        issues=[{"code": "structure.abstract_missing", "title": "缺少摘要"}],
    )

    assert evidence is not None
    assert evidence["error"] is True
    assert "写作指南条款未索引" in evidence["error_message"]


@pytest.mark.asyncio
async def test_load_writing_guide_evidence_reindexes_with_org_id_when_empty(monkeypatch):
    calls = {"retrieve": 0, "ready_org_id": None, "force_index": None}

    class FakeRetriever:
        def __init__(self, **kwargs):
            pass

        async def retrieve_for_issues(self, *, template_id, issues, top_k):
            calls["retrieve"] += 1
            if calls["retrieve"] == 1:
                return []
            return [
                {
                    "clause_id": "c001",
                    "text": "摘要应说明研究目的、方法、结果和结论。",
                    "source_file_name": "writing-guide.docx",
                    "score": 0.42,
                }
            ]

    async def fake_ensure_paper_templates_ready(*, org_id=None, force_index=False):
        calls["ready_org_id"] = org_id
        calls["force_index"] = force_index
        return {"index_status": "indexed", "clause_count": 1}

    monkeypatch.setattr(
        "agent.rag.paper_template_clause_retriever.PaperTemplateClauseRetriever",
        FakeRetriever,
    )
    monkeypatch.setattr(
        "agent.tools.paper_template_storage.ensure_paper_templates_ready",
        fake_ensure_paper_templates_ready,
    )

    evidence = await load_writing_guide_evidence(
        "cqupt_graduate_thesis_2022",
        issues=[{"code": "structure.abstract_missing", "title": "缺少摘要"}],
        org_id="org-1",
    )

    assert evidence is not None
    assert evidence["source"] == "qdrant_rag"
    assert evidence["clauses"][0]["score"] == 0.42
    assert calls == {"retrieve": 2, "ready_org_id": "org-1", "force_index": True}
