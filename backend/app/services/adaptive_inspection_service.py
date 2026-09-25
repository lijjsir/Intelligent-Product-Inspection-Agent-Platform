"""Persistent adaptive inspection goals and auditable decision proposals."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.supervision import (
    InspectionDecision,
    InspectionEvidenceState,
    InspectionGoal,
    MeasurementRecord,
    SupervisionEvent,
)
from app.schemas.supervision import (
    InspectionGoalCreate,
    NextTestDecisionCreate,
    StopDecisionCreate,
)
from app.services.supervision_service import SupervisionService


def serialize_goal(goal: InspectionGoal) -> dict:
    return {
        "id": goal.id,
        "org_id": goal.org_id,
        "session_id": goal.session_id,
        "plan_id": goal.plan_id,
        "version": goal.version,
        "request_key": goal.request_key,
        "status": goal.status,
        "risk_hypotheses": list(goal.risk_hypotheses or []),
        "required_items": list(goal.required_items or []),
        "candidate_items": list(goal.candidate_items or []),
        "success_criteria": dict(goal.success_criteria or {}),
        "stop_policy": dict(goal.stop_policy or {}),
        "max_cost": float(goal.max_cost) if goal.max_cost is not None else None,
        "max_duration_seconds": goal.max_duration_seconds,
        "created_by": goal.created_by,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }


def serialize_evidence_state(state: InspectionEvidenceState) -> dict:
    return {
        "id": state.id,
        "org_id": state.org_id,
        "session_id": state.session_id,
        "round": state.round,
        "device_trust_state": dict(state.device_trust_state or {}),
        "product_quality_state": dict(state.product_quality_state or {}),
        "supported_hypotheses": list(state.supported_hypotheses or []),
        "rejected_hypotheses": list(state.rejected_hypotheses or []),
        "unresolved_conflicts": list(state.unresolved_conflicts or []),
        "evidence_sufficiency": float(state.evidence_sufficiency),
        "remaining_uncertainty": float(state.remaining_uncertainty),
        "evidence_ids": list(state.evidence_ids or []),
        "created_at": state.created_at.isoformat(),
    }


def serialize_decision(decision: InspectionDecision) -> dict:
    return {
        "id": decision.id,
        "org_id": decision.org_id,
        "session_id": decision.session_id,
        "round": decision.round,
        "kind": decision.kind,
        "input_state_id": decision.input_state_id,
        "request_key": decision.request_key,
        "payload": dict(decision.payload or {}),
        "rule_version": decision.rule_version,
        "status": decision.status,
        "proposed_by": decision.proposed_by,
        "approved_by": decision.approved_by,
        "created_at": decision.created_at.isoformat(),
        "reviewed_at": decision.reviewed_at.isoformat() if decision.reviewed_at else None,
    }


class AdaptiveInspectionService:
    def __init__(self, db, current):
        self.db = db
        self.current = current
        self.org_id = str(current.org_id)
        self.actor = str(current.user_id)
        self.supervision = SupervisionService(db, current)

    async def create_goal(self, session_id: str, payload: InspectionGoalCreate) -> dict:
        await self.supervision.require_enabled()
        self.supervision.require_role({"user", "expert"})
        session = await self.supervision.get("inspection-sessions", session_id, lock=True)
        self.supervision.edit_access(session)
        existing = await self.db.scalar(
            select(InspectionGoal).where(
                InspectionGoal.org_id == self.org_id,
                InspectionGoal.request_key == payload.request_key,
            )
        )
        if existing:
            if existing.session_id != session_id:
                raise ConflictError("检测目标幂等编号已用于其他会话")
            return serialize_goal(existing)
        if session.version != payload.session_version:
            raise ConflictError("检测会话已更新，请刷新后重新创建检测目标")
        if session.data.get("input_mode") == "image":
            raise ValidationError("纯图片任务不创建设备自适应检测目标")

        plan_id = str(payload.plan_id) if payload.plan_id else session.data.get("plan_id")
        if payload.plan_id and session.data.get("plan_id") not in {None, plan_id}:
            raise ValidationError("检测目标关联计划与会话不一致")
        if plan_id:
            plan = await self.supervision.get("sampling-plans", plan_id)
            if plan.status != "approved":
                raise ValidationError("检测目标必须关联已批准抽查计划")

        allowed_items = {
            (str(item.get("item")), str(item.get("unit")), str(item.get("method")))
            for item in session.data.get("test_items", [])
        }
        goal_items = [*payload.required_items, *payload.candidate_items]
        if allowed_items and any(
            (item.item, item.unit, item.method) not in allowed_items for item in goal_items
        ):
            raise ValidationError("检测目标包含会话计划之外的检测项目")

        latest_version = await self.db.scalar(
            select(func.max(InspectionGoal.version)).where(
                InspectionGoal.org_id == self.org_id,
                InspectionGoal.session_id == session_id,
            )
        )
        goal = InspectionGoal(
            org_id=self.org_id,
            session_id=session_id,
            plan_id=plan_id,
            version=int(latest_version or 0) + 1,
            request_key=payload.request_key,
            status="active",
            risk_hypotheses=list(payload.risk_hypotheses),
            required_items=[item.model_dump(mode="json") for item in payload.required_items],
            candidate_items=[item.model_dump(mode="json") for item in payload.candidate_items],
            success_criteria=dict(payload.success_criteria),
            stop_policy=payload.stop_policy.model_dump(mode="json"),
            max_cost=payload.max_cost,
            max_duration_seconds=payload.max_duration_seconds,
            created_by=self.actor,
        )
        self.db.add(goal)
        await self.db.flush()

        evidence_state = InspectionEvidenceState(
            org_id=self.org_id,
            session_id=session_id,
            round=0,
            device_trust_state={
                "status": "unknown",
                "device_ids": list(session.data.get("device_ids") or []),
                "calibration_valid": False,
                "quality_issues": [],
            },
            product_quality_state={
                "status": "uncertain",
                "supported_hypotheses": [],
                "rejected_hypotheses": [],
                "findings": [],
            },
            supported_hypotheses=[],
            rejected_hypotheses=[],
            unresolved_conflicts=[],
            evidence_sufficiency=0,
            remaining_uncertainty=1,
            evidence_ids=[],
        )
        self.db.add(evidence_state)
        await self.db.flush()

        session.data = {
            **session.data,
            "goal_id": goal.id,
            "adaptive_enabled": True,
            "required_items": goal.required_items,
            "candidate_items": goal.candidate_items,
        }
        await self.supervision.journal(session, "inspection_goal_created")
        await self._event(
            aggregate_type="inspection_session",
            aggregate_id=session_id,
            aggregate_version=session.version,
            event_type="inspection.goal.created",
            event_key=f"inspection.goal.created:{goal.id}",
            payload={"goal_id": goal.id, "goal_version": goal.version},
        )
        return serialize_goal(goal)

    async def get_goal(self, session_id: str) -> dict:
        await self.supervision.require_enabled()
        await self.supervision.get("inspection-sessions", session_id)
        goal = await self.db.scalar(
            select(InspectionGoal)
            .where(
                InspectionGoal.org_id == self.org_id,
                InspectionGoal.session_id == session_id,
            )
            .order_by(InspectionGoal.version.desc())
        )
        if not goal:
            raise NotFoundError("检测目标不存在")
        return serialize_goal(goal)

    async def get_latest_evidence_state(self, session_id: str) -> dict:
        await self.supervision.require_enabled()
        await self.supervision.get("inspection-sessions", session_id)
        state = await self._latest_state(session_id)
        return serialize_evidence_state(state)

    async def refresh_evidence_state(
        self, session_id: str, *, actor_type: str = "user"
    ) -> dict | None:
        """Materialize a new immutable evidence round from accepted device observations."""
        goal = await self.db.scalar(
            select(InspectionGoal)
            .where(
                InspectionGoal.org_id == self.org_id,
                InspectionGoal.session_id == session_id,
                InspectionGoal.status == "active",
            )
            .order_by(InspectionGoal.version.desc())
        )
        if not goal:
            return None
        previous = await self._latest_state(session_id)
        rows = list(
            await self.db.scalars(
                select(MeasurementRecord).where(
                    MeasurementRecord.org_id == self.org_id,
                    MeasurementRecord.session_id == session_id,
                )
            )
        )
        accepted = [row for row in rows if row.validation_status in {None, "accepted"}]
        suspect = [row for row in rows if row.validation_status not in {None, "accepted"}]
        required = {
            self._item_identity(item): item for item in list(goal.required_items or [])
        }
        candidate = {
            self._item_identity(item): item for item in list(goal.candidate_items or [])
        }
        planned = {**candidate, **required}
        completed = {self._item_identity(row.data) for row in accepted}
        required_ratio = (
            len(set(required) & completed) / len(required) if required else 1.0
        )
        candidate_ratio = (
            len(set(candidate) & completed) / len(candidate) if candidate else 1.0
        )
        if required and candidate:
            evidence_sufficiency = (0.8 * required_ratio) + (0.2 * candidate_ratio)
        elif required:
            evidence_sufficiency = required_ratio
        else:
            evidence_sufficiency = candidate_ratio
        findings: list[dict] = []
        for row in accepted:
            item = planned.get(self._item_identity(row.data))
            if not item:
                continue
            value = row.data.get("value")
            if value is None:
                continue
            below = item.get("lower_limit") is not None and value < item["lower_limit"]
            above = item.get("upper_limit") is not None and value > item["upper_limit"]
            if below or above:
                findings.append(
                    {
                        "type": "product_abnormal",
                        "event_id": row.event_id,
                        "item": row.data.get("item"),
                        "value": value,
                        "standard_ref": item.get("standard_ref"),
                    }
                )
        required_complete = set(required).issubset(completed)
        if findings:
            product_status = "abnormal"
            supported = list(goal.risk_hypotheses or [])
            rejected: list[str] = []
        elif required_complete and accepted:
            product_status = "normal"
            supported = []
            rejected = list(goal.risk_hypotheses or [])
        else:
            product_status = "uncertain"
            supported = []
            rejected = []
        device_status = "invalid" if suspect else "trusted" if accepted else "unknown"
        state = InspectionEvidenceState(
            org_id=self.org_id,
            session_id=session_id,
            round=previous.round + 1,
            device_trust_state={
                "status": device_status,
                "device_ids": sorted({row.device_id for row in rows}),
                "calibration_valid": bool(accepted) and not suspect,
                "quality_issues": [
                    f"{row.event_id}:{row.validation_status}" for row in suspect
                ],
            },
            product_quality_state={
                "status": product_status,
                "supported_hypotheses": supported,
                "rejected_hypotheses": rejected,
                "findings": findings,
            },
            supported_hypotheses=supported,
            rejected_hypotheses=rejected,
            unresolved_conflicts=[],
            evidence_sufficiency=round(min(1.0, evidence_sufficiency), 4),
            remaining_uncertainty=round(max(0.0, 1 - evidence_sufficiency), 4),
            evidence_ids=[row.event_id for row in accepted],
        )
        self.db.add(state)
        await self.db.flush()
        await self._event(
            aggregate_type="inspection_session",
            aggregate_id=session_id,
            event_type="inspection.evidence.updated",
            event_key=f"inspection.evidence.updated:{state.id}",
            payload={
                "evidence_state_id": state.id,
                "round": state.round,
                "device_status": device_status,
                "product_status": product_status,
            },
            actor_type=actor_type,
        )
        return serialize_evidence_state(state)

    async def propose_next_test(
        self, session_id: str, payload: NextTestDecisionCreate
    ) -> dict:
        await self.supervision.require_enabled()
        self.supervision.require_role({"user", "expert"})
        await self.supervision.get("inspection-sessions", session_id)
        existing = await self._existing_decision(payload.request_key, session_id)
        if existing:
            return serialize_decision(existing)
        state = await self._require_latest_state(session_id, str(payload.evidence_state_id))
        goal = await self._active_goal(session_id)
        completed = await self._completed_items(session_id)
        ranked: list[dict] = []
        for item_class, items, base_score in (
            ("required", goal.required_items or [], 100),
            ("candidate", goal.candidate_items or [], 50),
        ):
            for position, item in enumerate(items):
                identity = self._item_identity(item)
                if identity in completed:
                    continue
                score = base_score - position
                if item.get("standard_ref"):
                    score += 20
                ranked.append(
                    {
                        "item": item,
                        "item_class": item_class,
                        "score": score,
                        "reason": (
                            "尚未完成的必检项"
                            if item_class == "required"
                            else "用于补足当前证据的候选项"
                        ),
                    }
                )
        ranked.sort(key=lambda item: (-item["score"], self._item_identity(item["item"])))
        kind = "next_test" if ranked else "goal_reached"
        decision = InspectionDecision(
            org_id=self.org_id,
            session_id=session_id,
            round=state.round,
            kind=kind,
            input_state_id=state.id,
            request_key=payload.request_key,
            payload={
                "selected": ranked[0] if ranked else None,
                "candidate_ranking": ranked,
                "completed_items": sorted(completed),
            },
            rule_version=payload.rule_version,
            status="proposed",
            proposed_by=self.actor,
        )
        self.db.add(decision)
        await self.db.flush()
        await self._event(
            aggregate_type="inspection_session",
            aggregate_id=session_id,
            event_type="inspection.next_test.proposed",
            event_key=f"inspection.next_test.proposed:{decision.id}",
            payload={"decision_id": decision.id, "kind": decision.kind},
        )
        return serialize_decision(decision)

    async def propose_stop(self, session_id: str, payload: StopDecisionCreate) -> dict:
        await self.supervision.require_enabled()
        self.supervision.require_role({"user", "expert"})
        await self.supervision.get("inspection-sessions", session_id)
        existing = await self._existing_decision(payload.request_key, session_id)
        if existing:
            return serialize_decision(existing)
        state = await self._require_latest_state(session_id, str(payload.evidence_state_id))
        goal = await self._active_goal(session_id)
        completed = await self._completed_items(session_id)
        required = {self._item_identity(item) for item in goal.required_items or []}
        mandatory_complete = required.issubset(completed)
        threshold = float((goal.stop_policy or {}).get("evidence_sufficiency_threshold", 1))
        device_trusted = (state.device_trust_state or {}).get("status") == "trusted"
        product_status = (state.product_quality_state or {}).get("status")
        hypotheses_resolved = product_status in {"normal", "abnormal"}
        no_conflicts = not state.unresolved_conflicts
        allow_early_stop = bool((goal.stop_policy or {}).get("allow_early_stop"))
        can_stop = all(
            (
                mandatory_complete,
                device_trusted,
                hypotheses_resolved,
                no_conflicts,
                float(state.evidence_sufficiency) >= threshold,
                allow_early_stop,
            )
        )
        if can_stop:
            decision_kind = "goal_reached"
        elif not device_trusted:
            decision_kind = "device_change_required"
        elif not mandatory_complete:
            decision_kind = "full_plan_required"
        elif state.unresolved_conflicts:
            decision_kind = "manual_review_required"
        else:
            decision_kind = "full_plan_required"
        skipped = [
            {"item": item, "item_class": "candidate", "reason": "检测目标已满足"}
            for item in goal.candidate_items or []
            if self._item_identity(item) not in completed
        ] if decision_kind == "goal_reached" else []
        decision = InspectionDecision(
            org_id=self.org_id,
            session_id=session_id,
            round=state.round,
            kind=decision_kind,
            input_state_id=state.id,
            request_key=payload.request_key,
            payload={
                "mandatory_items_complete": mandatory_complete,
                "device_trusted": device_trusted,
                "hypotheses_resolved": hypotheses_resolved,
                "no_unresolved_conflict": no_conflicts,
                "evidence_sufficiency": float(state.evidence_sufficiency),
                "evidence_threshold": threshold,
                "skipped_items": skipped,
            },
            rule_version=payload.rule_version,
            status="awaiting_approval" if decision_kind == "goal_reached" else "proposed",
            proposed_by=self.actor,
        )
        self.db.add(decision)
        await self.db.flush()
        await self._event(
            aggregate_type="inspection_session",
            aggregate_id=session_id,
            event_type="inspection.stop.proposed",
            event_key=f"inspection.stop.proposed:{decision.id}",
            payload={"decision_id": decision.id, "decision": decision.kind},
        )
        return serialize_decision(decision)

    async def review_stop_decision(
        self,
        session_id: str,
        decision_id: str,
        *,
        approve: bool,
        comment: str,
    ) -> dict:
        await self.supervision.require_enabled()
        self.supervision.require_role({"expert"})
        session = await self.supervision.get("inspection-sessions", session_id, lock=True)
        decision = await self.db.scalar(
            select(InspectionDecision)
            .where(
                InspectionDecision.id == decision_id,
                InspectionDecision.org_id == self.org_id,
                InspectionDecision.session_id == session_id,
            )
            .with_for_update()
        )
        if not decision:
            raise NotFoundError("停止决定不存在")
        if decision.kind != "goal_reached":
            raise ValidationError("只有达到检测目标的停止建议可以审批")
        if decision.status != "awaiting_approval":
            raise ConflictError("停止建议已经处理")
        if decision.proposed_by == self.actor:
            raise ForbiddenError("不能审批本人提出的停止建议")
        latest = await self._latest_state(session_id)
        if latest.id != decision.input_state_id:
            raise ConflictError("证据状态已更新，请重新评估停止条件")
        if approve:
            gate = dict(decision.payload or {})
            if not all(
                (
                    gate.get("mandatory_items_complete"),
                    gate.get("device_trusted"),
                    gate.get("hypotheses_resolved"),
                    gate.get("no_unresolved_conflict"),
                    float(gate.get("evidence_sufficiency") or 0)
                    >= float(gate.get("evidence_threshold") or 1),
                )
            ):
                raise ConflictError("停止门禁不再满足，请重新评估")
            decision.status = "approved"
            session.status = "goal_reached"
            await self.supervision.journal(session, "adaptive_stop_approved")
            event_type = "inspection.stop.approved"
        else:
            decision.status = "rejected"
            event_type = "inspection.stop.rejected"
        decision.approved_by = self.actor
        decision.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._event(
            aggregate_type="inspection_session",
            aggregate_id=session_id,
            aggregate_version=session.version,
            event_type=event_type,
            event_key=f"{event_type}:{decision.id}",
            payload={
                "decision_id": decision.id,
                "reviewer_id": self.actor,
                "comment": comment,
            },
        )
        return serialize_decision(decision)

    async def _active_goal(self, session_id: str) -> InspectionGoal:
        goal = await self.db.scalar(
            select(InspectionGoal)
            .where(
                InspectionGoal.org_id == self.org_id,
                InspectionGoal.session_id == session_id,
                InspectionGoal.status == "active",
            )
            .order_by(InspectionGoal.version.desc())
        )
        if not goal:
            raise ValidationError("请先创建并启用检测目标")
        return goal

    async def _latest_state(self, session_id: str) -> InspectionEvidenceState:
        state = await self.db.scalar(
            select(InspectionEvidenceState)
            .where(
                InspectionEvidenceState.org_id == self.org_id,
                InspectionEvidenceState.session_id == session_id,
            )
            .order_by(InspectionEvidenceState.round.desc())
        )
        if not state:
            raise NotFoundError("检测证据状态不存在")
        return state

    async def _require_latest_state(
        self, session_id: str, evidence_state_id: str
    ) -> InspectionEvidenceState:
        state = await self._latest_state(session_id)
        if state.id != evidence_state_id:
            raise ConflictError("证据状态已更新，请基于最新轮次重新决策")
        return state

    async def _existing_decision(
        self, request_key: str, session_id: str
    ) -> InspectionDecision | None:
        decision = await self.db.scalar(
            select(InspectionDecision).where(
                InspectionDecision.org_id == self.org_id,
                InspectionDecision.request_key == request_key,
            )
        )
        if decision and decision.session_id != session_id:
            raise ConflictError("决策幂等编号已用于其他检测会话")
        return decision

    async def _completed_items(self, session_id: str) -> set[str]:
        rows = list(
            await self.db.scalars(
                select(MeasurementRecord).where(
                    MeasurementRecord.org_id == self.org_id,
                    MeasurementRecord.session_id == session_id,
                )
            )
        )
        return {
            self._item_identity(row.data)
            for row in rows
            if (row.validation_status in {None, "accepted", "valid"})
            and (row.data or {}).get("quality_flag") == "valid"
        }

    @staticmethod
    def _item_identity(item: dict) -> str:
        return "|".join(
            (
                str(item.get("item") or ""),
                str(item.get("unit") or ""),
                str(item.get("method") or ""),
            )
        )

    async def _event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_key: str,
        payload: dict,
        aggregate_version: int | None = None,
        actor_type: str = "user",
    ) -> None:
        self.db.add(
            SupervisionEvent(
                org_id=self.org_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                aggregate_version=aggregate_version,
                event_type=event_type,
                event_key=event_key,
                actor_type=actor_type,
                actor_id=self.actor,
                payload=payload,
            )
        )
        await self.db.flush()
