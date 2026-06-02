from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.executors.file_executor import FileExecutor
from agent.router.manager_state import ManagerState


logger = logging.getLogger(__name__)


class PaperReviewEnrichmentService:
    async def enrich(
        self,
        *,
        paper_report: dict[str, Any],
        request: NormalizedRequest,
        emit_patch: Callable[..., Awaitable[None]] | None = None,
        emit_progress: Callable[..., Awaitable[None]] | None = None,
        db_session: Any = None,
    ) -> dict[str, Any]:
        merged = dict(paper_report or {})
        payload = dict(merged.get("enrichment_payload") or {})
        if not payload:
            return merged

        try:
            from agent.tools.paper_template_evidence import load_writing_guide_evidence
            from agent.tools.paper_review_ai import generate_ai_review_output

            guide_evidence = await load_writing_guide_evidence(
                str(payload.get("template_id") or ""),
                issues=list(payload.get("issues") or paper_report.get("issues") or []),
                trace_id=str(payload.get("trace_id") or request.workflow_run_id or request.request_id or ""),
                task_id=str(payload.get("task_id") or request.session_id or ""),
                org_id=str(payload.get("org_id") or request.org_id or ""),
            )
            if guide_evidence:
                merged["writing_guide_evidence"] = guide_evidence
                if guide_evidence.get("error"):
                    merged.setdefault("template_errors", []).append(
                        guide_evidence.get("error_message", "模板文件加载失败")
                    )

            if callable(emit_progress):
                await emit_progress("ai_reviewing", "正在生成 Ai-Review 审阅结论...", "running")
            ai_started = time.perf_counter()
            ai_review_output = await generate_ai_review_output(
                evidence_pack=dict(payload.get("review_evidence_pack") or {}),
                guide_evidence=guide_evidence if guide_evidence and not guide_evidence.get("error") else None,
                query=str(payload.get("query") or request.query or ""),
                db_session=db_session,
                org_id=str(payload.get("org_id") or request.org_id),
                trace_id=str(payload.get("trace_id") or request.workflow_run_id or request.request_id or ""),
                task_id=str(payload.get("task_id") or request.session_id or ""),
            )
            ai_duration_ms = int((time.perf_counter() - ai_started) * 1000)
            merged.setdefault("paper_review_timings_ms", {})["ai_reviewing"] = ai_duration_ms
            logger.info("paper review stage completed phase=ai_reviewing duration_ms=%s", ai_duration_ms)
            if callable(emit_progress):
                await emit_progress(
                    "ai_reviewing",
                    "Ai-Review 论文审阅完成",
                    "running",
                    ai_duration_ms,
                    {"paper_review_timings_ms": dict(merged.get("paper_review_timings_ms") or {})},
                )
            merged["ai_review_output"] = ai_review_output
            merged["model_used"] = ai_review_output.get("model_used")

            ai_limitations = [
                str(item)
                for item in list(ai_review_output.get("limitations") or [])
                if str(item).strip()
            ]
            if ai_limitations:
                merged["limitations"] = list(
                    dict.fromkeys([*list(merged.get("limitations") or []), *ai_limitations])
                )
            if ai_review_output.get("summary"):
                merged["summary"] = str(ai_review_output.get("summary"))
                merged["model_summary"] = str(ai_review_output.get("summary"))

            state = self._build_state(request)
            if callable(emit_progress):
                await emit_progress("report_generating", "正在生成查非报告文件...", "running")
            report_started = time.perf_counter()
            report_files = await FileExecutor._save_report_files(
                merged=merged,
                state=state,
                request=request,
            )
            report_duration_ms = int((time.perf_counter() - report_started) * 1000)
            merged.setdefault("paper_review_timings_ms", {})["report_generating"] = report_duration_ms
            logger.info("paper review stage completed phase=report_generating duration_ms=%s", report_duration_ms)
            if callable(emit_progress):
                await emit_progress(
                    "report_generating",
                    "查非报告文件生成完成",
                    "running",
                    report_duration_ms,
                    {"paper_review_timings_ms": dict(merged.get("paper_review_timings_ms") or {})},
                )
            merged["report_files"] = report_files
        except Exception as exc:
            logger.exception(
                "paper review enrichment failed session_id=%s assistant_message_id=%s",
                request.session_id,
                request.assistant_message_id,
            )
            raise

        merged.pop("enrichment_payload", None)
        FileExecutor._finalize_paper_report_counts(merged)

        if callable(emit_patch):
            await emit_patch(
                content=str(merged.get("chat_advice") or ""),
                message_type="file_answer",
                payload={"paper_format_report": merged},
            )
        return merged

    @staticmethod
    def _build_state(request: NormalizedRequest) -> ManagerState:
        return ManagerState(
            request_id=str(request.request_id),
            workflow_run_id=str(request.workflow_run_id or request.request_id),
            org_id=str(request.org_id),
            user_id=str(request.user_id or ""),
            session_id=str(request.session_id or ""),
            assistant_message_id=str(request.assistant_message_id or ""),
            original_query=str(request.query or ""),
            attachments=[item.model_dump() for item in list(request.attachments or [])],
        )
