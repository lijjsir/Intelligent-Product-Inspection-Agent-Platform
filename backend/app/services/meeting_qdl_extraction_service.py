from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ConfigDict, Field, ValidationError

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from app.schemas.qdl import QDLClaim, QDLEntity, QDLKnowledgeProperties, QDLStrictModel, KnowledgeLevel
from app.services.model_config_service import ModelConfigService


logger = logging.getLogger(__name__)
_MODEL_TYPES = {"chat", "llm", "multimodal"}


class QDLSemanticCandidate(QDLStrictModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_level: KnowledgeLevel
    claim: QDLClaim
    properties: QDLKnowledgeProperties = Field(default_factory=QDLKnowledgeProperties)
    entities: list[QDLEntity] = Field(default_factory=list, max_length=50)
    applicability_conditions: list[str] = Field(default_factory=list, max_length=20)
    evidence_message_ids: list[str] = Field(min_length=1, max_length=20)


@dataclass(frozen=True)
class QDLSemanticExtractionResult:
    status: str
    entries: tuple[dict[str, Any], ...] = ()
    model_id: str | None = None
    elapsed_ms: int = 0
    usage: dict[str, int] | None = None
    error_code: str | None = None
    invalid_candidate_count: int = 0


class MeetingQDLExtractionService:
    """LLM semantic extraction without persistence or publication authority."""

    def __init__(self, session: Any, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def extract(
        self,
        messages: list[Any],
        *,
        max_items: int,
        topic: str = "",
        trace_id: str | None = None,
    ) -> QDLSemanticExtractionResult:
        transcript, message_map = self._public_transcript(messages)
        if not transcript:
            return QDLSemanticExtractionResult(status="empty")

        started = time.perf_counter()
        try:
            models = await ModelConfigService(self._session, self._org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(models=models, model_types=_MODEL_TYPES)
            if runtime is None:
                return self._failure("runtime_unavailable", started)

            model_id = str(runtime.get("model_id") or "") or None
            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=model_id,
                provider=str(runtime.get("provider") or "custom"),
                trace_id=trace_id,
                org_id=self._org_id,
                input_price_per_million=runtime.get("input_price_per_million"),
                output_price_per_million=runtime.get("output_price_per_million"),
            )
            response = await asyncio.wait_for(
                client.chat(
                    self._prompt_messages(transcript, topic=topic, max_items=max_items),
                    temperature=0.1,
                    observation_name="meeting.qdl.extract",
                    observation_metadata={"message_count": len(transcript), "max_items": max_items},
                ),
                timeout=40,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            meta = response.get("__meta__") if isinstance(response.get("__meta__"), dict) else {}
            usage = self._normalize_usage(meta.get("usage"))
            raw_candidates = response.get("candidates")
            if not isinstance(raw_candidates, list):
                return QDLSemanticExtractionResult(
                    status="failed",
                    model_id=model_id,
                    elapsed_ms=elapsed_ms,
                    usage=usage,
                    error_code="invalid_response_shape",
                )

            entries: list[dict[str, Any]] = []
            invalid_count = 0
            for raw in raw_candidates[:max_items]:
                try:
                    candidate = QDLSemanticCandidate.model_validate(raw)
                except ValidationError:
                    invalid_count += 1
                    continue
                entry = self._candidate_entry(candidate, message_map, model_id, elapsed_ms, usage)
                if entry is None:
                    invalid_count += 1
                    continue
                entries.append(entry)

            status = "success" if raw_candidates == [] or entries else "failed"
            return QDLSemanticExtractionResult(
                status=status,
                entries=tuple(entries),
                model_id=model_id,
                elapsed_ms=elapsed_ms,
                usage=usage,
                error_code="candidate_validation_failed" if status == "failed" else None,
                invalid_candidate_count=invalid_count,
            )
        except asyncio.TimeoutError:
            return self._failure("timeout", started)
        except Exception as exc:
            logger.warning(
                "meeting QDL semantic extraction failed org_id=%s error_type=%s",
                self._org_id,
                type(exc).__name__,
            )
            return self._failure("llm_error", started)

    @staticmethod
    def _public_transcript(messages: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        transcript: list[dict[str, Any]] = []
        message_map: dict[str, Any] = {}
        total_chars = 0
        for message in messages:
            message_id = str(getattr(message, "id", "") or "")
            content = str(getattr(message, "content", "") or "").strip()
            if not message_id or not content:
                continue
            metadata = getattr(message, "metadata_json", None) or {}
            if metadata.get("visibility") == "private" or getattr(message, "private_recipient_user_id", None):
                continue
            message_type = str(getattr(message, "message_type", "user") or "user")
            if message_type not in {"user", "agent", "summary", "action_item"}:
                continue
            if total_chars >= 24000:
                break
            content = content[:4000]
            total_chars += len(content)
            message_map[message_id] = message
            transcript.append(
                {
                    "message_id": message_id,
                    "seq_no": int(getattr(message, "seq_no", 0) or 0),
                    "speaker": str(getattr(message, "username", "") or "participant")[:80],
                    "message_type": message_type,
                    "content": content,
                }
            )
        return transcript, message_map

    @staticmethod
    def _prompt_messages(transcript: list[dict[str, Any]], *, topic: str, max_items: int) -> list[dict[str, str]]:
        system_prompt = (
            "You extract reusable meeting knowledge into QDL semantic candidates. Return valid JSON only. "
            "Do not treat greetings, questions without answers, acknowledgements, brainstorming fragments, or private chat as knowledge. "
            "Extract facts, decisions, reusable rules, recurring patterns, concepts, or hypotheses only when supported by the supplied messages. "
            "Every candidate must cite one or more exact message_id values. Never invent identifiers, permissions, publication scopes, or confirmation status. "
            "For each knowledge property use an object with level low|medium|high|unknown, confidence 0..1 or null, and optional rationale. "
            "Use entity_type product|batch|task|standard|role|other and resolution_status resolved|ambiguous|unresolved. "
            "The response shape is {\"candidates\":[{\"knowledge_level\":\"fact|decision|rule|pattern|concept|hypothesis\","
            "\"claim\":{\"title\":\"...\",\"text\":\"...\",\"type\":\"...\"},"
            "\"properties\":{\"abstraction\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"environment\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"boundary\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"dynamic\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"social\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"tacit\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"hierarchy\":{\"level\":\"unknown\",\"confidence\":null},"
            "\"stability\":{\"level\":\"unknown\",\"confidence\":null},\"extensions\":{}},"
            "\"entities\":[],\"applicability_conditions\":[],\"evidence_message_ids\":[\"...\"]}]}."
        )
        user_payload = {
            "topic_hint": str(topic or "")[:200],
            "max_candidates": max_items,
            "messages": transcript,
        }
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    @staticmethod
    def _candidate_entry(
        candidate: QDLSemanticCandidate,
        message_map: dict[str, Any],
        model_id: str | None,
        elapsed_ms: int,
        usage: dict[str, int] | None,
    ) -> dict[str, Any] | None:
        source_ids = [item for item in candidate.evidence_message_ids if item in message_map]
        if not source_ids:
            return None
        spans: list[dict[str, Any]] = []
        for index, message_id in enumerate(source_ids, 1):
            content = str(getattr(message_map[message_id], "content", "") or "").strip()
            spans.append(
                {
                    "type": "meeting_message_span",
                    "message_id": message_id,
                    "span_index": index,
                    "start": 0,
                    "end": len(content),
                    "text": content,
                }
            )
        return {
            "summary": candidate.claim.title,
            "content": candidate.claim.text,
            "source_message_id": source_ids[0],
            "source_spans": spans,
            "qdl_semantics": candidate.model_dump(mode="json"),
            "extraction_method": "mixed",
            "extraction_model_id": model_id,
            "extraction_elapsed_ms": elapsed_ms,
            "extraction_usage": usage,
        }

    @staticmethod
    def _normalize_usage(value: Any) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        result = {
            key: int(value.get(key) or 0)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(value.get(key), (int, float))
        }
        return result or None

    @staticmethod
    def _failure(code: str, started: float) -> QDLSemanticExtractionResult:
        return QDLSemanticExtractionResult(
            status="failed",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            error_code=code,
        )
