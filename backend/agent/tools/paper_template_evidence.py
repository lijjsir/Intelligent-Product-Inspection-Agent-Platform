"""Load template-side evidence used by the paper review model.

The paper review path must use retrieved clauses, not full writing-guide text.
"""

from __future__ import annotations

from typing import Any

from agent.tools.paper_format_templates import get_paper_template


async def load_writing_guide_evidence(
    template_id: str | None,
    *,
    issues: list[dict[str, Any]] | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    org_id: str | None = None,
) -> dict[str, Any] | None:
    """Load template writing guide evidence via RAG retrieval.

    Returns error dict when retrieval fails — no silent fallback to full-text.
    Caller must raise or propagate the error to the frontend.
    """
    template = get_paper_template(template_id)
    if template is None:
        return None

    effective_template_id = str(template.get("template_id") or template_id)

    if issues:
        retrieved = []
        retrieval_error: Exception | None = None
        try:
            from agent.rag.paper_template_clause_retriever import PaperTemplateClauseRetriever
            retriever = PaperTemplateClauseRetriever(
                trace_id=trace_id, task_id=task_id, org_id=org_id
            )
            retrieved = await retriever.retrieve_for_issues(
                template_id=effective_template_id,
                issues=issues,
                top_k=10,
            )
            if retrieved:
                return {
                    "template_id": effective_template_id,
                    "template_name": str(template.get("name") or ""),
                    "source": "qdrant_rag",
                    "file_name": str(retrieved[0].get("source_file_name") or ""),
                    "clauses": retrieved,
                    "clause_count": len(retrieved),
                }
        except Exception as exc:
            retrieval_error = exc

        if org_id:
            try:
                from agent.tools.paper_template_storage import ensure_paper_templates_ready

                ready_result = await ensure_paper_templates_ready(org_id=org_id, force_index=True)
                if str(ready_result.get("index_status") or "") in {"failed", "skipped"}:
                    raise RuntimeError(str(ready_result.get("error") or ready_result.get("reason") or ready_result))
                from agent.rag.paper_template_clause_retriever import PaperTemplateClauseRetriever
                retriever = PaperTemplateClauseRetriever(
                    trace_id=trace_id, task_id=task_id, org_id=org_id
                )
                retrieved = await retriever.retrieve_for_issues(
                    template_id=effective_template_id,
                    issues=issues,
                    top_k=10,
                )
                if retrieved:
                    return {
                        "template_id": effective_template_id,
                        "template_name": str(template.get("name") or ""),
                        "source": "qdrant_rag",
                        "file_name": str(retrieved[0].get("source_file_name") or ""),
                        "clauses": retrieved,
                        "clause_count": len(retrieved),
                    }
            except Exception as exc:
                retrieval_error = exc

        if retrieval_error is not None:
            return _error_result(
                template, template_id,
                f"模板条款检索失败：{retrieval_error}"
                " — 请检查 Qdrant 服务是否正常，以及嵌入模型是否已配置。"
                " 错误码: PAPER_TEMPLATE_RETRIEVAL_ERROR"
            )
        return _error_result(
            template, template_id,
            "写作指南条款未索引 — 请联系管理员配置嵌入模型后重启服务，或通过 POST /paper-templates/import 导入写作指南。"
            " 错误码: PAPER_TEMPLATE_CLAUSES_NOT_INDEXED"
        )

    return {
        "template_id": effective_template_id,
        "template_name": str(template.get("name") or ""),
        "source": "none",
        "clauses": [],
        "clause_count": 0,
    }


def _error_result(template: dict[str, Any], template_id: str | None, message: str) -> dict[str, Any]:
    return {
        "template_id": str(template.get("template_id") or template_id or ""),
        "template_name": str(template.get("name") or ""),
        "source": "error",
        "role": "writing_guide",
        "error": True,
        "error_message": message,
    }
