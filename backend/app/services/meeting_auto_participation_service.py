from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from app.core.permissions import ROLE_USER
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import MeetingAgentRunRequest, MeetingMemoryScopeRequest
from app.services.model_config_service import ModelConfigService
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

logger = logging.getLogger(__name__)

_GENERAL_AGENT_ID = "general_agent"
_DECISION_REF_TYPE = "auto_participation_decision"
_DECISIONS = {"silent", "observe", "participate"}
_TRIGGER_TYPES = {
    "none",
    "evidence_gap",
    "unresolved_conflict",
    "history_conflict",
    "discussion_stall",
    "decision_ready",
}
_ACTION_TYPES = {
    "none",
    "evidence_query",
    "clarify",
    "standard_remind",
    "brainstorm",
    "decision_support",
}
_TARGET_ROLES = {"user", "expert", "algorithm_engineer", "platform_operator"}
_CONFIDENCE_THRESHOLD = 0.75
_SUPPRESSION_WINDOW = 3


class AutoParticipationError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class MeetingAutoParticipationService:
    """Diagnose proactive participation without adding a second Agent runtime."""

    def __init__(self, session: Any, *, org_id: str, user_id: str, user_role: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._user_role = user_role or ROLE_USER
        self._repo = MeetingRepository(session)
        self._users = UserRepository(session)

    @classmethod
    async def evaluate_trigger(
        cls,
        *,
        room_id: str,
        message_id: str,
        org_id: str,
        user_id: str,
        user_role: str,
        expected_mode: str,
    ) -> None:
        try:
            async with get_session() as session:
                service = cls(
                    session,
                    org_id=org_id,
                    user_id=user_id,
                    user_role=user_role,
                )
                await service._evaluate(
                    room_id=room_id,
                    message_id=message_id,
                    expected_mode=expected_mode,
                )
        except Exception as exc:
            logger.exception(
                "meeting auto participation failed room_id=%s message_id=%s",
                room_id,
                message_id,
            )
            reason = exc.reason if isinstance(exc, AutoParticipationError) else "evaluation_failed"
            await cls._record_failure_safely(
                room_id=room_id,
                message_id=message_id,
                org_id=org_id,
                user_id=user_id,
                user_role=user_role,
                expected_mode=expected_mode,
                reason=reason,
            )

    async def _evaluate(self, *, room_id: str, message_id: str, expected_mode: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if room is None:
            return
        mode = self.mode_from_room(room)
        if mode == "off" or mode != expected_mode:
            return
        message = await self._repo.get_message(self._org_id, room_id, message_id)
        if not self._eligible_message(message):
            return

        context = await self._build_context(room=room, room_id=room_id)
        model_decision = await self._diagnose(context)
        final_decision = await self._apply_hard_suppression(
            context=context,
            decision=model_decision,
            room_id=room_id,
            trigger_message=message,
        )
        audit = await self._record_audit(
            room=room,
            message=message,
            mode=mode,
            decision=final_decision,
        )

        if mode != "live" or final_decision["decision"] != "participate":
            await self._session.commit()
            await self._publish_audit_event(room_id, str(audit.id))
            return

        from app.services.meeting_service import MeetingService

        action_mode = self._agent_mode(final_decision)
        query = self._agent_query(final_decision)
        metadata = {
            "version": "meeting-auto-participation-v1",
            "audit_id": str(audit.id),
            "trigger_message_id": str(message.id),
            "trigger_type": final_decision["trigger_type"],
            "action_type": final_decision["action_type"],
            "target_role": final_decision["target_role"],
            "confidence": final_decision["confidence"],
            "resource_key": final_decision["resource_key"],
            "reason": final_decision["reason"],
            "evidence_refs": final_decision["evidence_refs"],
        }
        meeting_service = MeetingService(
            self._session,
            org_id=self._org_id,
            user_id=self._user_id,
            role=self._user_role,
        )
        await meeting_service.run_general_agent(
            room_id,
            MeetingAgentRunRequest(
                query=query,
                mode=action_mode,
                memory_scope=MeetingMemoryScopeRequest(
                    include_meeting=True,
                    include_confirmed=True,
                    include_personal_authorized=False,
                    include_user=False,
                    include_agent=True,
                    include_org_space=True,
                ),
                auto_participation=metadata,
                interaction_mode="auto_participation",
                trigger_message_id=str(message.id),
                question_message_id=str(message.id),
                question_revision=str(getattr(message, "updated_at", None) or message.id),
                question_sources=[
                    {"message_id": str(message.id), "kind": "public_trigger"},
                    *[
                        {"id": ref.get("id"), "kind": ref.get("type")}
                        for ref in final_decision["evidence_refs"]
                    ],
                ],
            ),
        )
        await self._publish_audit_event(room_id, str(audit.id))

    async def _build_context(self, *, room: Any, room_id: str) -> dict[str, Any]:
        from app.services.meeting_service import MeetingService

        list_public = getattr(self._repo, "list_recent_public_messages", None)
        if callable(list_public):
            recent_rows = await list_public(
                org_id=self._org_id,
                room_id=room_id,
                limit=40,
            )
        else:
            recent_rows = await self._repo.list_recent_messages(
                org_id=self._org_id,
                room_id=room_id,
                limit=40,
                visible_user_id=None,
            )
        public_agent_rows = [
            row
            for row in recent_rows
            if str(getattr(row, "message_type", "") or "") in {"agent", "agent_streaming"}
            and str(getattr(row, "content", "") or "").strip()
            and not self._private_recipient(row)
        ][-8:]
        human_rows = [
            row
            for row in recent_rows
            if str(getattr(row, "message_type", "") or "") == "user"
            and str(getattr(row, "content", "") or "").strip()
            and not self._private_recipient(row)
        ][-12:]

        member_rows = await self._repo.list_members(self._org_id, room_id)
        member_roles: list[dict[str, str]] = []
        present_roles: set[str] = set()
        role_by_user: dict[str, str] = {}
        for member in member_rows:
            member_user_id = str(member.user_id)
            user = await self._users.get_by_id(self._org_id, member_user_id)
            system_role = self._normalize_target_role(getattr(user, "role", None))
            present_roles.add(system_role)
            role_by_user[member_user_id] = system_role
            member_roles.append(
                {
                    "user_id": member_user_id,
                    "username": str(getattr(user, "username", "") or member_user_id[-8:]),
                    "system_role": system_role,
                    "room_role": str(getattr(member, "role", "member") or "member"),
                }
            )

        messages = [
            {
                "id": str(row.id),
                "seq_no": int(getattr(row, "seq_no", 0) or 0),
                "user_id": str(getattr(row, "user_id", "") or ""),
                "username": str(getattr(row, "username", "") or ""),
                "system_role": role_by_user.get(str(getattr(row, "user_id", "") or ""), "user"),
                "content": str(getattr(row, "content", "") or "")[:1200],
            }
            for row in human_rows
        ]

        meeting_service = MeetingService(
            self._session,
            org_id=self._org_id,
            user_id=self._user_id,
            role=self._user_role,
        )
        business_context = meeting_service._business_context_from_room(room).model_dump(mode="json")
        raw_quality_context = await meeting_service._build_meeting_inspection_context(room)
        quality_tasks = self._strict_quality_tasks(raw_quality_context)

        memories = await self._repo.list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            business_context=business_context,
            include_confirmed=True,
            statuses=["confirmed", "active", "disputed"],
            limit=40,
        )
        active_memories = [
            self._memory_payload(item)
            for item in memories
            if self._memory_is_active(item)
        ]
        disputed_memories = [
            self._memory_payload(item)
            for item in memories
            if str(getattr(item, "status", "") or "") == "disputed"
        ]
        conflicts = await self._repo.list_conflict_events(
            org_id=self._org_id,
            room_id=room_id,
            statuses=["pending"],
            limit=20,
        )
        conflict_payloads = [self._conflict_payload(item) for item in conflicts]

        return {
            "messages": messages,
            "public_agent_suggestions": [
                {
                    "id": str(row.id),
                    "seq_no": int(getattr(row, "seq_no", 0) or 0),
                    "content": str(getattr(row, "content", "") or "")[:1200],
                    "confirmation_status": str(
                        (getattr(row, "metadata_json", None) or {}).get("confirmation_status")
                        or "unconfirmed_ai_suggestion"
                    ),
                }
                for row in public_agent_rows
            ],
            "members": member_roles,
            "present_roles": sorted(present_roles),
            "business_context": business_context,
            "quality_context": {"tasks": quality_tasks},
            "active_memories": active_memories,
            "unresolved_conflicts": [*conflict_payloads, *disputed_memories],
        }

    async def _diagnose(self, context: dict[str, Any]) -> dict[str, Any]:
        runtime_models = await ModelConfigService(self._session, self._org_id).list_runtime_models()
        runtime = await LLMGateway().select_runtime(
            models=runtime_models,
            model_types={"chat", "llm", "multimodal", "text_generation"},
        )
        if not runtime:
            raise AutoParticipationError("model_unavailable")
        client = LLMClient(
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            model_id=str(runtime.get("model_id") or ""),
            org_id=self._org_id,
            provider=str(runtime.get("provider") or ""),
            input_price_per_million=runtime.get("input_price_per_million"),
            output_price_per_million=runtime.get("output_price_per_million"),
        )
        try:
            response = await client.chat(
                [
                    {"role": "system", "content": self._system_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(context, ensure_ascii=False, default=str),
                    },
                ],
                temperature=0.0,
                observation_name="meeting.auto_participation_v1",
                observation_metadata={"room_id": context.get("business_context", {}).get("room_id")},
            )
        except Exception as exc:
            raise AutoParticipationError("model_unavailable") from exc
        if "text" in response:
            response = self._extract_json(str(response.get("text") or ""))
        if not isinstance(response, dict):
            raise AutoParticipationError("invalid_model_json")
        return self._normalize_decision(response)

    async def _apply_hard_suppression(
        self,
        *,
        context: dict[str, Any],
        decision: dict[str, Any],
        room_id: str,
        trigger_message: Any,
    ) -> dict[str, Any]:
        result = dict(decision)
        suppressions = list(result.get("suppression_reasons") or [])
        valid_refs = self._valid_evidence_refs(context, result.get("evidence_refs") or [])
        result["evidence_refs"] = valid_refs
        if not result["resource_key"]:
            result["resource_key"] = self._derive_resource_key(valid_refs)

        if result["decision"] not in _DECISIONS:
            suppressions.append("invalid_decision")
        required_confidence = (
            0.85
            if result["trigger_type"] in {"discussion_stall", "decision_ready"}
            else _CONFIDENCE_THRESHOLD
        )
        if result["confidence"] < required_confidence:
            suppressions.append("confidence_below_threshold")
        if (
            result["trigger_type"] in {"discussion_stall", "decision_ready"}
            and len(context.get("messages") or []) < 4
        ):
            suppressions.append("insufficient_human_turns")
        if result["decision"] != "silent" and not valid_refs:
            suppressions.append("no_valid_evidence")
        if result["decision"] != "silent" and not result["resource_key"]:
            suppressions.append("missing_resource_key")
        if result["decision"] != "silent" and result["trigger_type"] == "none":
            suppressions.append("missing_trigger")
        if result["decision"] != "silent" and result["action_type"] == "none":
            suppressions.append("missing_action")
        if result["decision"] != "silent" and result["target_role"] not in set(context["present_roles"]):
            suppressions.append("target_role_not_present")
        if result["human_is_handling"]:
            suppressions.append("human_is_handling")
        if (
            result["decision"] != "silent"
            and result["trigger_type"] == "history_conflict"
            and not self._has_active_history_basis(context, valid_refs)
        ):
            suppressions.append("no_active_history_basis")

        previous = await self._previous_decisions(
            room_id,
            result["resource_key"],
            evidence_refs=valid_refs,
        )
        trigger_seq = int(getattr(trigger_message, "seq_no", 0) or 0)
        evidence_keys = self._evidence_keys(valid_refs)
        immediate = self._is_immediate(context, result)

        if not suppressions and result["decision"] != "silent" and previous:
            last = previous[0]
            human_turns = self._human_turns_since(context["messages"], int(last.get("trigger_seq_no") or 0))
            prior_evidence = set(str(item) for item in list(last.get("evidence_keys") or []))
            has_new_evidence = bool(evidence_keys - prior_evidence)
            if (
                last.get("decision") == "participate"
                and 0 < human_turns <= _SUPPRESSION_WINDOW
                and not has_new_evidence
            ):
                suppressions.append("duplicate_without_new_evidence")

        if suppressions:
            result["decision"] = "silent"
        elif result["decision"] != "silent" and not immediate:
            last_observe = next(
                (item for item in previous if item.get("decision") == "observe"),
                None,
            )
            turns = (
                self._human_turns_since(context["messages"], int(last_observe.get("trigger_seq_no") or 0))
                if last_observe
                else 0
            )
            result["decision"] = (
                "participate"
                if last_observe and 0 < turns <= _SUPPRESSION_WINDOW
                else "observe"
            )

        result["suppression_reasons"] = self._dedupe(suppressions)
        result["trigger_seq_no"] = trigger_seq
        result["evidence_keys"] = sorted(evidence_keys)
        result["immediate"] = immediate
        return result

    async def _previous_decisions(
        self,
        room_id: str,
        resource_key: str,
        *,
        evidence_refs: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        current_ref_keys = self._reference_keys(evidence_refs or [])
        if not resource_key and not current_ref_keys:
            return []
        rows = await self._repo.list_agent_query_audits(
            org_id=self._org_id,
            room_id=room_id,
            limit=50,
        )
        matches: list[dict[str, Any]] = []
        for row in rows:
            for ref in list(getattr(row, "source_refs", None) or []):
                if not isinstance(ref, dict) or ref.get("type") != _DECISION_REF_TYPE:
                    continue
                prior_resource_key = str(ref.get("resource_key") or "")
                same_resource = bool(resource_key and prior_resource_key == resource_key)
                legacy_missing_key = bool(
                    not prior_resource_key
                    and "missing_resource_key" in list(ref.get("suppression_reasons") or [])
                    and current_ref_keys & self._reference_keys(list(ref.get("evidence_refs") or []))
                )
                if same_resource or legacy_missing_key:
                    prior = dict(ref)
                    if legacy_missing_key and prior.get("decision") == "silent":
                        prior["decision"] = "observe"
                        prior["resource_key"] = resource_key
                    matches.append(prior)
                    break
        return matches

    async def _record_audit(
        self,
        *,
        room: Any,
        message: Any,
        mode: str,
        decision: dict[str, Any],
    ) -> Any:
        decision_ref = {
            "type": _DECISION_REF_TYPE,
            "version": "meeting-auto-participation-v1",
            "mode": mode,
            **decision,
        }
        return await self._repo.create_agent_query_audit(
            org_id=self._org_id,
            room_id=str(room.id),
            user_id=self._user_id,
            agent_id=_GENERAL_AGENT_ID,
            question=str(getattr(message, "content", "") or "")[:4000],
            intent=f"auto_{decision['trigger_type']}",
            requested_domains=[],
            allowed_domains=list(getattr(room, "allowed_data_domains", None) or []),
            denied_domains=[],
            tool_calls=[],
            source_refs=[decision_ref, *decision["evidence_refs"]],
            redacted_fields=[],
            decision=decision["decision"],
            response_visibility="room",
            redaction_level="none",
            denied_reasons={},
        )

    @classmethod
    async def _record_failure_safely(
        cls,
        *,
        room_id: str,
        message_id: str,
        org_id: str,
        user_id: str,
        user_role: str,
        expected_mode: str,
        reason: str,
    ) -> None:
        try:
            async with get_session() as session:
                service = cls(session, org_id=org_id, user_id=user_id, user_role=user_role)
                room = await service._repo.get_room(org_id, room_id)
                message = await service._repo.get_message(org_id, room_id, message_id)
                if room is None or message is None or service.mode_from_room(room) == "off":
                    return
                audit = await service._record_audit(
                    room=room,
                    message=message,
                    mode=expected_mode,
                    decision={
                        "decision": "silent",
                        "trigger_type": "none",
                        "action_type": "none",
                        "target_role": None,
                        "confidence": 0.0,
                        "resource_key": "",
                        "reason": "主动参与判断失败，保持沉默。",
                        "human_is_handling": False,
                        "evidence_refs": [],
                        "suppression_reasons": [reason],
                        "trigger_seq_no": int(getattr(message, "seq_no", 0) or 0),
                        "evidence_keys": [],
                        "immediate": False,
                    },
                )
                await session.commit()
                await service._publish_audit_event(room_id, str(audit.id))
        except Exception:
            logger.exception("failed to persist auto participation failure audit")

    @staticmethod
    def mode_from_room(room: Any | None) -> str:
        policy = getattr(room, "audit_policy", None) if room is not None else None
        value = policy.get("auto_participation_mode") if isinstance(policy, dict) else "off"
        mode = str(value or "off").strip().lower()
        return mode if mode in {"off", "live"} else "off"

    @staticmethod
    async def _publish_audit_event(room_id: str, audit_id: str) -> None:
        await meeting_stream_broker.publish(
            room_id,
            {
                "event": "agent_query_audit_created",
                "room_id": room_id,
                "audit_id": audit_id,
            },
        )

    @staticmethod
    def _eligible_message(message: Any | None) -> bool:
        if message is None or str(getattr(message, "message_type", "") or "") != "user":
            return False
        if not str(getattr(message, "content", "") or "").strip():
            return False
        metadata = getattr(message, "metadata_json", None) or {}
        if not isinstance(metadata, dict):
            return True
        return not (
            metadata.get("private_recipient_user_id")
            or metadata.get("visibility") == "private"
            or metadata.get("recalled_at")
        )

    @staticmethod
    def _private_recipient(message: Any) -> str:
        metadata = getattr(message, "metadata_json", None) or {}
        return str(metadata.get("private_recipient_user_id") or "") if isinstance(metadata, dict) else ""

    @staticmethod
    def _normalize_target_role(value: Any) -> str:
        role = str(value or ROLE_USER).strip().lower()
        return role if role in _TARGET_ROLES else "user"

    @staticmethod
    def _strict_quality_tasks(context: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(context, dict):
            return []
        candidates: list[dict[str, Any]] = []
        if isinstance(context.get("latest_task"), dict):
            candidates.append(context["latest_task"])
        for key in ("selected_tasks", "recent_failures", "recent_tasks"):
            candidates.extend(item for item in list(context.get(key) or []) if isinstance(item, dict))
        allowed = (
            "task_id",
            "id",
            "status",
            "verdict",
            "overall_score",
            "risk_level",
            "failed_rules",
            "root_cause",
            "defects",
            "manual_review",
            "model_key",
            "prompt_version",
        )
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in candidates:
            task_id = str(item.get("task_id") or item.get("id") or "").strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            snapshot = {key: item.get(key) for key in allowed if item.get(key) not in (None, "", [], {})}
            snapshot["task_id"] = task_id
            snapshot.pop("id", None)
            if isinstance(snapshot.get("defects"), list):
                snapshot["defects"] = snapshot["defects"][:5]
            result.append(snapshot)
        return result[:12]

    @staticmethod
    def _memory_is_active(item: Any) -> bool:
        content = getattr(item, "content_json", None) or {}
        return (
            str(getattr(item, "status", "") or "") in {"active", "confirmed"}
            and not (content.get("superseded_by") if isinstance(content, dict) else None)
        )

    @staticmethod
    def _memory_payload(item: Any) -> dict[str, Any]:
        content = getattr(item, "content_json", None) or {}
        content = content if isinstance(content, dict) else {}
        return {
            "type": "memory",
            "id": str(getattr(item, "memory_id", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "memory_type": str(getattr(item, "memory_type", "") or ""),
            "title": str(content.get("title") or "")[:240],
            "content": str(content.get("content") or getattr(item, "content_summary", "") or "")[:1200],
            "standard_code": str(getattr(item, "standard_code", "") or ""),
            "standard_version": str(getattr(item, "standard_version", "") or ""),
        }

    @staticmethod
    def _conflict_payload(item: Any) -> dict[str, Any]:
        return {
            "type": "conflict",
            "id": str(getattr(item, "id", "") or ""),
            "conflict_type": str(getattr(item, "conflict_type", "") or ""),
            "resource_key": str(getattr(item, "resource_key", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "related_message_ids": list(getattr(item, "related_message_ids", None) or []),
            "metadata": dict(getattr(item, "metadata_json", None) or {}),
        }

    @staticmethod
    def _normalize_decision(value: dict[str, Any]) -> dict[str, Any]:
        try:
            confidence = max(0.0, min(1.0, float(value.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        decision = str(value.get("decision") or "silent").strip().lower()
        trigger_type = str(value.get("trigger_type") or "none").strip().lower()
        action_type = str(value.get("action_type") or "none").strip().lower()
        target_raw = value.get("target_role")
        target_role = str(target_raw).strip().lower() if target_raw is not None else None
        return {
            "decision": decision if decision in _DECISIONS else "silent",
            "trigger_type": trigger_type if trigger_type in _TRIGGER_TYPES else "none",
            "action_type": action_type if action_type in _ACTION_TYPES else "none",
            "target_role": target_role if target_role in _TARGET_ROLES else None,
            "confidence": confidence,
            "resource_key": re.sub(r"\s+", " ", str(value.get("resource_key") or "").strip())[:200],
            "reason": str(value.get("reason") or "").strip()[:1000],
            "human_is_handling": bool(value.get("human_is_handling", False)),
            "evidence_refs": list(value.get("evidence_refs") or []),
            "suppression_reasons": [
                str(item)[:200]
                for item in list(value.get("suppression_reasons") or [])
                if str(item).strip()
            ],
        }

    @staticmethod
    def _valid_evidence_refs(context: dict[str, Any], refs: list[Any]) -> list[dict[str, str]]:
        valid: dict[str, set[str]] = {
            "meeting_message": {str(item["id"]) for item in context["messages"]},
            "inspection_task": {
                str(item["task_id"]) for item in context["quality_context"]["tasks"]
            },
            "memory": {
                str(item["id"])
                for item in [*context["active_memories"], *context["unresolved_conflicts"]]
                if item.get("type") == "memory"
            },
            "conflict": {
                str(item["id"])
                for item in context["unresolved_conflicts"]
                if item.get("type") == "conflict"
            },
            "standard": set(str(item) for item in context["business_context"].get("standard_ids") or []),
        }
        aliases = {
            "message": "meeting_message",
            "task": "inspection_task",
            "quality_task": "inspection_task",
            "disputed_memory": "memory",
            "conflict_event": "conflict",
        }
        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for ref in refs:
            if isinstance(ref, str) and ":" in ref:
                raw_type, raw_id = ref.split(":", 1)
            elif isinstance(ref, dict):
                raw_type = str(ref.get("type") or ref.get("kind") or "")
                raw_id = str(ref.get("id") or ref.get("ref_id") or "")
            else:
                continue
            ref_type = aliases.get(raw_type.strip().lower(), raw_type.strip().lower())
            ref_id = raw_id.strip()
            key = (ref_type, ref_id)
            if not ref_id or ref_type not in valid or ref_id not in valid[ref_type] or key in seen:
                continue
            seen.add(key)
            normalized.append({"type": ref_type, "id": ref_id})
        return normalized

    @staticmethod
    def _evidence_keys(refs: list[dict[str, str]]) -> set[str]:
        # A new discussion turn is not new evidence by itself. Only a newly
        # referenced project resource can release the three-turn cooldown.
        return {
            f"{item['type']}:{item['id']}"
            for item in refs
            if item["type"] != "meeting_message"
        }

    @staticmethod
    def _reference_keys(refs: list[dict[str, str]]) -> set[str]:
        return {
            f"{item.get('type')}:{item.get('id')}"
            for item in refs
            if item.get("type") and item.get("id")
        }

    @staticmethod
    def _derive_resource_key(refs: list[dict[str, str]]) -> str:
        # Resource identity must remain stable when the model changes trigger
        # labels between related turns. Prefer project resources, then anchor
        # a message-only discussion to its earliest cited message.
        for ref_type in ("inspection_task", "conflict", "memory", "standard", "meeting_message"):
            ref_ids = sorted(
                str(item.get("id") or "")
                for item in refs
                if item.get("type") == ref_type and item.get("id")
            )
            if ref_ids:
                return f"{ref_type}:{ref_ids[0]}"
        return ""

    @staticmethod
    def _has_active_history_basis(
        context: dict[str, Any],
        refs: list[dict[str, str]],
    ) -> bool:
        active_memory_ids = {
            str(item.get("id") or "")
            for item in context.get("active_memories") or []
        }
        return any(
            ref["type"] == "standard"
            or (ref["type"] == "memory" and ref["id"] in active_memory_ids)
            for ref in refs
        )

    @staticmethod
    def _human_turns_since(messages: list[dict[str, Any]], seq_no: int) -> int:
        return sum(1 for item in messages if int(item.get("seq_no") or 0) > seq_no)

    @staticmethod
    def _is_immediate(context: dict[str, Any], decision: dict[str, Any]) -> bool:
        if decision["trigger_type"] == "history_conflict":
            return MeetingAutoParticipationService._has_active_history_basis(
                context,
                list(decision.get("evidence_refs") or []),
            )
        recent_text = " ".join(str(item.get("content") or "") for item in context["messages"][-3:]).lower()
        approval_terms = ("放行", "通过", "确认", "定版", "上线", "approve", "release")
        if not any(term in recent_text for term in approval_terms):
            return False
        for task in context["quality_context"]["tasks"]:
            status = str(task.get("status") or "").lower()
            verdict = str(task.get("verdict") or "").lower()
            risk = str(task.get("risk_level") or "").lower()
            manual = task.get("manual_review")
            manual_text = json.dumps(manual, ensure_ascii=False, default=str).lower() if manual is not None else ""
            pending_review = bool(manual is not None and not any(
                token in manual_text for token in ("completed", "approved", "通过", "已完成")
            ))
            if (
                status in {"pending", "queued", "running", "no_result", "manual_required"}
                or verdict in {"fail", "failed", "manual_required", "reject", "rejected"}
                or risk in {"high", "critical", "高", "严重"}
                or pending_review
            ):
                return True
        return False

    @staticmethod
    def _agent_mode(decision: dict[str, Any]) -> str:
        if decision["trigger_type"] == "evidence_gap":
            return "evidence_query"
        if decision["trigger_type"] == "history_conflict":
            has_standard = any(
                ref.get("type") == "standard" for ref in decision.get("evidence_refs") or []
            )
            return "standard_explain" if has_standard else "auto"
        if decision["trigger_type"] == "decision_ready":
            return "auto"
        return "auto"

    @staticmethod
    def _agent_query(decision: dict[str, Any]) -> str:
        role_labels = {
            "user": "参会成员",
            "expert": "领域专家",
            "algorithm_engineer": "算法工程师",
            "platform_operator": "平台运营人员",
        }
        target = role_labels.get(decision.get("target_role"), "相关成员")
        reason = str(decision.get("reason") or "当前讨论仍有未解决问题").strip()
        action = decision.get("action_type")
        if action == "evidence_query":
            instruction = f"请向{target}提出一个简短、具体的证据补充问题"
        elif action == "standard_remind":
            instruction = f"请依据当前有效记忆或标准，向{target}做一次简短提醒"
        elif action == "brainstorm":
            instruction = "请给出一个反例、一个替代方案和一个最小可验证假设，帮助讨论突破停滞"
        elif action == "decision_support":
            instruction = "请简要比较当前方案的依据、风险和下一步验证动作，帮助会议形成已确认结论"
        else:
            instruction = f"请针对争议双方，向{target}提出一个中立的澄清问题"
        return f"{instruction}。触发原因：{reason}。只使用会议现有依据，不补造事实。"

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是会议Agent主动参与诊断器，只判断是否需要介入，不回答会议问题。"
            "只能使用输入中的最近公共人类消息、公开但未确认的Agent建议、成员系统角色、业务上下文、质检任务、有效记忆和未决冲突。"
            "confirmed/active记忆可作为历史事实；disputed记忆只能作为未决冲突。"
            "闲聊、会议安排、首次出现且无紧迫风险的普通问题应silent或observe。"
            "当人类已经追问、补证、协调或明确接手时，human_is_handling必须为true。"
            "高风险或失败质检结果与放行主张冲突、人工复核未完成却准备确认、当前方案违反有效历史标准时可participate。"
            "四个以上相关人类轮次没有新进展时，可用discussion_stall提供反例、替代方案和待验证假设。"
            "多个方案已经具备比较和收敛条件时，可用decision_ready给出方案比较与下一步建议。"
            "discussion_stall和decision_ready只有在confidence不低于0.85时才可participate。"
            "evidence_refs必须只引用输入中真实存在的ID，格式为[{\"type\":\"meeting_message|inspection_task|memory|conflict|standard\",\"id\":\"...\"}]；"
            "重复发言本身不是新证据，不要把它引用为证据。"
            "非silent判断的resource_key不能为空；优先使用所引用任务、冲突、记忆、标准或最早相关消息的ID作为稳定资源键，不要随trigger_type变化。"
            "target_role必须是在场的user、expert、algorithm_engineer或platform_operator。"
            "只返回一个JSON对象，字段严格为：decision、trigger_type、action_type、target_role、confidence、resource_key、reason、human_is_handling、evidence_refs、suppression_reasons。"
            "decision取silent|observe|participate；trigger_type取none|evidence_gap|unresolved_conflict|history_conflict|discussion_stall|decision_ready；"
            "action_type取none|evidence_query|clarify|standard_remind|brainstorm|decision_support；confidence为0到1。"
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        candidates = [str(text or "").strip()]
        fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", str(text or ""), flags=re.I)
        candidates = [*fenced, *candidates]
        raw = re.search(r"\{[\s\S]*\}", str(text or ""))
        if raw:
            candidates.append(raw.group(0))
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                return value
        raise AutoParticipationError("invalid_model_json")

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(item) for item in values if str(item).strip()))
