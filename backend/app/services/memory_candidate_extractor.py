"""Extract shared-memory candidates from task blackboards and agent-local memory."""
from __future__ import annotations

import logging
from typing import Any

from agent.rag.embedder import Embedder
from app.schemas.memory import (
    MemoryContent,
    MemoryScope,
    MemorySource,
    MemoryType,
    MemoryWriteRequest,
    MemoryWriteResponse,
)
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import (
    CANDIDATE_MEMORY_COLLECTION,
    MEMORY_COLLECTION,
    MemoryVectorService,
)
from app.services.task_blackboard_service import TaskBlackboardService

logger = logging.getLogger(__name__)

_BLOCKED_ARTIFACT_TYPES = {
    "raw_image",
    "image",
    "file",
    "raw_file",
    "pdf",
    "csv",
    "visual_bbox_draft",
}
_SENSITIVE_KEYS = {
    "password",
    "secret",
    "api_key",
    "token",
    "private_key",
    "authorization",
    "身份证",
    "手机号",
}


class MemoryCandidateExtractor:
    def __init__(
        self,
        db_session,
        *,
        blackboard: TaskBlackboardService | None = None,
        local_memory_service: Any = None,
        user_id: str | None = None,
        min_share_value_score: float = 0.70,
    ) -> None:
        self._db_session = db_session
        self._blackboard = blackboard or TaskBlackboardService()
        self._local_memory = local_memory_service
        self._user_id = user_id
        self._min_score = min_share_value_score

    async def extract_from_blackboard(
        self,
        org_id: str,
        workflow_run_id: str,
        task_id: str | None,
    ) -> list[MemoryWriteRequest]:
        snapshot = await self._blackboard.snapshot(org_id, workflow_run_id)
        artifacts = {
            str(item.get("artifact_id")): item
            for item in snapshot.get("artifacts") or []
            if isinstance(item, dict) and item.get("artifact_id")
        }
        global_state = dict(snapshot.get("global_state") or {})
        requests: list[MemoryWriteRequest] = []

        for source in snapshot.get("candidate_sources") or []:
            if not isinstance(source, dict):
                continue
            score = self._score(source)
            if score < self._min_score:
                continue
            artifact_id = str(source.get("source_artifact_id") or "")
            artifact = artifacts.get(artifact_id)
            if not artifact or not self._shareable_artifact(artifact):
                continue

            content = dict(artifact.get("content") or {})
            summary = self._summary(artifact, content)
            if (
                not summary
                or self._contains_sensitive_data(content, summary)
                or self._has_unresolved_conflict(content)
            ):
                continue

            memory_type = self._memory_type(source.get("candidate_type"))
            product_line = str(
                content.get("product_line")
                or global_state.get("product_line")
                or ""
            ).strip()
            rag_space_id = str(
                content.get("rag_space_id")
                or global_state.get("rag_space_id")
                or ""
            ).strip()
            effective_task_id = str(task_id or snapshot.get("task_id") or "").strip() or None
            scope = self._scope_for(
                memory_type,
                task_id=effective_task_id,
                product_line=product_line or None,
                rag_space_id=rag_space_id or None,
                role=str(source.get("source_agent") or artifact.get("source_agent") or "") or None,
            )
            if scope is None:
                continue

            evidence_ids = list(source.get("evidence_artifact_ids") or [])
            if artifact_id and artifact_id not in evidence_ids:
                evidence_ids.append(artifact_id)
            requests.append(
                MemoryWriteRequest(
                    org_id=org_id,
                    user_id=self._user_id,
                    source=MemorySource(
                        kind="agent_message",
                        task_id=effective_task_id,
                        trace_id=workflow_run_id,
                        agent_id=str(source.get("source_agent") or artifact.get("source_agent") or "") or None,
                    ),
                    memory_type=memory_type,
                    scope=scope,
                    content=MemoryContent(
                        summary=summary[:500],
                        facts=self._facts(content),
                        warnings=self._warnings(content),
                        risk_notes=[str(item)[:300] for item in list(content.get("risk_notes") or [])[:10]],
                    ),
                    evidence_pointers={
                        "workflow_run_id": workflow_run_id,
                        "artifact_ids": evidence_ids,
                        "source": "task_blackboard",
                        "share_value_score": score,
                        "target_agents": list(source.get("target_agents") or []),
                        "candidate_reason": source.get("reason"),
                    },
                    confidence=max(0.4, min(1.0, score)),
                    trace_id=workflow_run_id,
                )
            )
        return requests

    async def extract_from_local_memory(
        self,
        org_id: str,
        workflow_run_id: str,
        agent_ids: list[str],
    ) -> list[MemoryWriteRequest]:
        if self._local_memory is None:
            return []
        requests: list[MemoryWriteRequest] = []
        for agent_id in agent_ids:
            try:
                items = await self._local_memory.list_shareable(
                    org_id=org_id,
                    agent_id=agent_id,
                    workflow_run_id=workflow_run_id,
                )
            except Exception:
                logger.exception(
                    "Failed to read local memory org_id=%s agent_id=%s "
                    "workflow_run_id=%s",
                    org_id,
                    agent_id,
                    workflow_run_id,
                )
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("artifact_type") or "").lower() in _BLOCKED_ARTIFACT_TYPES:
                    continue
                score = float(item.get("share_value_score") or 0.0)
                if not item.get("shareable") or score < self._min_score:
                    continue
                summary = str(item.get("summary") or "").strip()
                product_line = str(item.get("product_line") or "").strip()
                if (
                    not summary
                    or not product_line
                    or self._contains_sensitive_data(item, summary)
                    or self._has_unresolved_conflict(item)
                ):
                    continue
                requests.append(
                    MemoryWriteRequest(
                        org_id=org_id,
                        user_id=item.get("user_id") or self._user_id,
                        source=MemorySource(
                            kind="agent_message",
                            trace_id=workflow_run_id,
                            agent_id=agent_id,
                        ),
                        memory_type=MemoryType.INSPECTION_PATTERN,
                        scope=MemoryScope(product_line=product_line, role=agent_id),
                        content=MemoryContent(
                            summary=summary[:500],
                            facts=[str(value)[:300] for value in list(item.get("facts") or [])[:20]],
                            warnings=[str(value)[:300] for value in list(item.get("warnings") or [])[:10]],
                        ),
                        evidence_pointers={
                            "source": "agent_local_memory",
                            "local_memory_id": item.get("memory_id"),
                            "share_reason": item.get("share_reason"),
                            "target_agents": list(item.get("target_agents") or []),
                            "share_value_score": score,
                        },
                        confidence=max(0.4, min(1.0, score)),
                        trace_id=workflow_run_id,
                    )
                )
        return requests

    async def submit_candidates(
        self,
        requests: list[MemoryWriteRequest],
    ) -> list[MemoryWriteResponse]:
        if self._db_session is None:
            return []
        responses: list[MemoryWriteResponse] = []
        for request in requests:
            try:
                service = self._build_memory_service(request)
                responses.append(await service.write_candidate(request))
            except Exception:
                logger.exception(
                    "Failed to submit blackboard memory candidate org_id=%s trace_id=%s",
                    request.org_id,
                    request.trace_id,
                )
        return responses

    def _build_memory_service(self, request: MemoryWriteRequest) -> MemoryService:
        async def embedder_factory(text: str) -> list[float]:
            embedder = Embedder(
                org_id=request.org_id,
                user_id=request.user_id,
                trace_id=request.trace_id,
                allow_pseudo_fallback=False,
            )
            return await embedder.embed(text)

        common = {
            "embedder_factory": embedder_factory,
            "org_id": request.org_id,
            "user_id": request.user_id,
            "trace_id": request.trace_id,
        }
        return MemoryService(
            self._db_session,
            request.org_id,
            vector_service=MemoryVectorService(
                collection=MEMORY_COLLECTION,
                **common,
            ),
            candidate_vector_service=MemoryVectorService(
                collection=CANDIDATE_MEMORY_COLLECTION,
                **common,
            ),
        )

    @staticmethod
    def _score(source: dict[str, Any]) -> float:
        explicit = source.get("share_value_score")
        if explicit is not None:
            return max(0.0, min(1.0, float(explicit)))
        evidence_count = len(source.get("evidence_artifact_ids") or [])
        return min(1.0, 0.45 + min(evidence_count, 4) * 0.1)

    @staticmethod
    def _shareable_artifact(artifact: dict[str, Any]) -> bool:
        if str(artifact.get("type") or "").lower() in _BLOCKED_ARTIFACT_TYPES:
            return False
        if artifact.get("status") not in {"success", "completed"}:
            return False
        return bool(
            artifact.get("candidate_extractable")
            or (artifact.get("content") or {}).get("candidate_extractable")
        )

    @staticmethod
    def _summary(artifact: dict[str, Any], content: dict[str, Any]) -> str:
        return str(
            content.get("candidate_summary")
            or content.get("summary")
            or artifact.get("summary")
            or content.get("answer")
            or ""
        ).strip()

    @staticmethod
    def _memory_type(value: Any) -> MemoryType:
        raw = str(value or "inspection_pattern")
        try:
            return MemoryType(raw)
        except ValueError:
            return MemoryType.INSPECTION_PATTERN

    @staticmethod
    def _scope_for(
        memory_type: MemoryType,
        *,
        task_id: str | None,
        product_line: str | None,
        rag_space_id: str | None,
        role: str | None,
    ) -> MemoryScope | None:
        if memory_type == MemoryType.INSPECTION_PATTERN:
            return MemoryScope(product_line=product_line, task_id=task_id, role=role) if product_line else None
        if memory_type == MemoryType.RAG_USAGE_MEMORY:
            return MemoryScope(rag_space_id=rag_space_id, task_id=task_id, role=role) if rag_space_id else None
        if memory_type == MemoryType.TASK_EPISODE:
            return MemoryScope(task_id=task_id, role=role) if task_id else None
        return MemoryScope(task_id=task_id, product_line=product_line, rag_space_id=rag_space_id, role=role)

    @staticmethod
    def _facts(content: dict[str, Any]) -> list[str]:
        facts = [str(item)[:300] for item in list(content.get("facts") or [])[:20]]
        for key in ("final_verdict", "risk_level", "recommended_action"):
            value = content.get(key)
            if value not in (None, "", []):
                facts.append(f"{key}: {value}"[:300])
        return facts

    @staticmethod
    def _warnings(content: dict[str, Any]) -> list[str]:
        warnings = [str(item)[:300] for item in list(content.get("warnings") or [])[:10]]
        for conflict in list(content.get("conflicts") or [])[:10]:
            warnings.append(f"conflict: {str(conflict)[:280]}")
        return warnings

    @staticmethod
    def _contains_sensitive_data(payload: dict[str, Any], summary: str) -> bool:
        flattened = f"{summary} {payload}".lower()
        return any(key.lower() in flattened for key in _SENSITIVE_KEYS)

    @staticmethod
    def _has_unresolved_conflict(payload: dict[str, Any]) -> bool:
        if payload.get("conflict_resolved") is True:
            return False
        risk = str(
            payload.get("conflict_risk")
            or payload.get("conflict_severity")
            or ""
        ).strip().lower()
        if risk == "high":
            return True
        return bool(payload.get("conflicts"))
