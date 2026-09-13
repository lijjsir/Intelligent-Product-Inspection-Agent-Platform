"""Deterministic, review-first knowledge transformation between scopes.

The tunnel operates on QDL rather than free-form text.  It produces a target
projection (K') together with every mapping decision so a caller can attach
the plan to an approval/transfer audit record.  No missing mapping is filled
from model guesses.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from app.schemas.qdl import QDL_VERSION, parse_qdl


_ALLOWED_SCOPE_TYPES = {"meeting_room", "user", "agent", "org_space", "collab_thread"}
_ALLOWED_ENTITY_TYPES = {"product", "batch", "task", "standard", "role", "other"}
_ALIASES = {
    "meeting": "meeting_room",
    "workspace": "org_space",
    "organization": "org_space",
}


@dataclass(frozen=True)
class KnowledgeTunnelResult:
    status: str
    source_scope: dict[str, str]
    target_scope: dict[str, str]
    mapping_version: str
    interpolation_strategy: str
    transform_reason: str
    transformed_qdl: dict[str, Any] | None
    mapping_decisions: tuple[dict[str, Any], ...]
    unmapped_fields: tuple[str, ...]
    constraints: tuple[str, ...]
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_scope": dict(self.source_scope),
            "target_scope": dict(self.target_scope),
            "mapping_version": self.mapping_version,
            "interpolation_strategy": self.interpolation_strategy,
            "transform_reason": self.transform_reason,
            "transformed_qdl": deepcopy(self.transformed_qdl),
            "mapping_decisions": [dict(item) for item in self.mapping_decisions],
            "unmapped_fields": list(self.unmapped_fields),
            "constraints": list(self.constraints),
            "errors": list(self.errors),
        }


class KnowledgeTunnelService:
    """Build an auditable QDL projection from source scope Cs to target Ct."""

    @classmethod
    def transform_qdl(
        cls,
        qdl_payload: dict[str, Any],
        *,
        source_scope_type: str,
        source_scope_id: str,
        target_scope_type: str,
        target_scope_id: str,
        mapping_rules: dict[str, Any] | None = None,
        mapping_version: str = "manual-v1",
        interpolation_strategy: str = "explicit",
        transform_reason: str = "",
        source_memory_id: str | None = None,
    ) -> KnowledgeTunnelResult:
        source_scope = cls._scope(source_scope_type, source_scope_id)
        target_scope = cls._scope(target_scope_type, target_scope_id)
        normalized_strategy = str(interpolation_strategy or "explicit").strip().lower()
        normalized_version = str(mapping_version or "manual-v1").strip() or "manual-v1"
        reason = str(transform_reason or "").strip()
        decisions: list[dict[str, Any]] = []
        unmapped: list[str] = []
        errors: list[str] = []

        if source_scope is None:
            errors.append("invalid source scope; expected a supported scope type and non-empty scope id")
            source_scope = {"scope_type": str(source_scope_type or ""), "scope_id": str(source_scope_id or "")}
        if target_scope is None:
            errors.append("invalid target scope; expected a supported scope type and non-empty scope id")
            target_scope = {"scope_type": str(target_scope_type or ""), "scope_id": str(target_scope_id or "")}
        if normalized_strategy not in {"explicit", "identity", "drop_unmapped"}:
            errors.append("unsupported interpolation_strategy")
        if not reason:
            errors.append("transform_reason is required")

        parsed = parse_qdl(qdl_payload)
        if parsed.document is None:
            errors.extend(parsed.errors or ("invalid or missing QDL document",))
            return cls._result(
                status="rejected",
                source_scope=source_scope,
                target_scope=target_scope,
                mapping_version=normalized_version,
                interpolation_strategy=normalized_strategy,
                transform_reason=reason,
                transformed_qdl=None,
                decisions=decisions,
                unmapped=unmapped,
                errors=errors,
            )

        if errors:
            return cls._result(
                status="rejected",
                source_scope=source_scope,
                target_scope=target_scope,
                mapping_version=normalized_version,
                interpolation_strategy=normalized_strategy,
                transform_reason=reason,
                transformed_qdl=None,
                decisions=decisions,
                unmapped=unmapped,
                errors=errors,
            )

        rules = dict(mapping_rules or {})
        entity_type_rules = cls._dict_rules(rules.get("entity_types"))
        entity_value_rules = cls._nested_dict_rules(rules.get("entity_values"))
        relation_rules = cls._dict_rules(rules.get("relation_targets"))
        scope_changed = source_scope != target_scope
        transformed = parsed.document.model_dump(mode="json")

        transformed_entities: list[dict[str, Any]] = []
        for index, entity in enumerate(transformed.get("entities") or []):
            path = f"entities[{index}]"
            source_type = str(entity.get("entity_type") or "other")
            source_value = str(entity.get("value") or "")
            drop_entity = False
            target_type = entity_type_rules.get(source_type)
            if target_type is None:
                if normalized_strategy == "identity" or not scope_changed:
                    target_type = source_type
                    decisions.append(cls._decision(path + ".entity_type", source_type, target_type, "preserve", "identity"))
                elif normalized_strategy == "drop_unmapped":
                    decisions.append(cls._decision(path + ".entity_type", source_type, None, "drop", "unmapped entity type"))
                    drop_entity = True
                else:
                    unmapped.append(path + ".entity_type")
                    decisions.append(cls._decision(path + ".entity_type", source_type, None, "unmapped", "explicit mapping required"))
                    target_type = source_type
            elif target_type not in _ALLOWED_ENTITY_TYPES:
                if normalized_strategy == "drop_unmapped":
                    decisions.append(cls._decision(path + ".entity_type", source_type, target_type, "drop", "target entity type is not supported"))
                    drop_entity = True
                else:
                    unmapped.append(path + ".entity_type")
                    decisions.append(cls._decision(path + ".entity_type", source_type, target_type, "invalid", "target entity type is not supported"))
                    target_type = source_type
            else:
                decisions.append(cls._decision(path + ".entity_type", source_type, target_type, "map", "rule"))
            entity["entity_type"] = target_type

            value_map = entity_value_rules.get(source_type, {})
            target_value = value_map.get(source_value)
            if target_value is None:
                if normalized_strategy == "identity" or not scope_changed:
                    target_value = source_value
                    decisions.append(cls._decision(path + ".value", source_value, target_value, "preserve", "identity"))
                elif normalized_strategy == "drop_unmapped":
                    decisions.append(cls._decision(path + ".value", source_value, None, "drop", "unmapped entity value"))
                    drop_entity = True
                else:
                    unmapped.append(path + ".value")
                    decisions.append(cls._decision(path + ".value", source_value, None, "unmapped", "explicit value mapping required"))
                    target_value = source_value
            elif target_value is not None:
                target_value = str(target_value)
                decisions.append(cls._decision(path + ".value", source_value, target_value, "map", "rule"))
            if drop_entity:
                continue
            entity["value"] = target_value
            transformed_entities.append(entity)
        transformed["entities"] = transformed_entities

        transformed_relations: list[dict[str, Any]] = []
        for index, relation in enumerate(transformed.get("relations") or []):
            source_target = str(relation.get("target_id") or "")
            target_id = relation_rules.get(source_target)
            path = f"relations[{index}].target_id"
            if target_id is None:
                if normalized_strategy == "identity" or not scope_changed:
                    target_id = source_target
                    decisions.append(cls._decision(path, source_target, target_id, "preserve", "identity"))
                elif normalized_strategy == "drop_unmapped":
                    decisions.append(cls._decision(path, source_target, None, "drop", "unmapped relation target"))
                    continue
                else:
                    unmapped.append(path)
                    decisions.append(cls._decision(path, source_target, None, "unmapped", "explicit relation mapping required"))
                    target_id = source_target
            else:
                target_id = str(target_id)
                decisions.append(cls._decision(path, source_target, target_id, "map", "rule"))
            relation["target_id"] = target_id
            transformed_relations.append(relation)
        transformed["relations"] = transformed_relations

        applicability = transformed.get("applicability")
        if isinstance(applicability, dict):
            applicability["scope_type"] = target_scope["scope_type"]
            applicability["scope_id"] = target_scope["scope_id"]
            decisions.append(
                cls._decision(
                    "applicability.scope",
                    f"{source_scope['scope_type']}:{source_scope['scope_id']}",
                    f"{target_scope['scope_type']}:{target_scope['scope_id']}",
                    "map",
                    "target scope",
                )
            )

        provenance = transformed.get("provenance")
        if isinstance(provenance, dict):
            provenance["source_hash"] = cls._source_hash(
                qdl_payload,
                mapping_version=normalized_version,
                mapping_rules=rules,
            )
            provenance["generated_at"] = datetime.now(timezone.utc).isoformat()

        lifecycle = transformed.get("lifecycle")
        if isinstance(lifecycle, dict):
            lifecycle["revision"] = max(1, int(lifecycle.get("revision") or 1)) + (1 if scope_changed else 0)
            if source_memory_id:
                lifecycle["parent_memory_id"] = str(source_memory_id)

        # A cross-scope projection is always a candidate until the target
        # scope's approval workflow accepts it.
        if scope_changed:
            governance = transformed.get("governance") or {}
            consensus = transformed.get("consensus") or {}
            governance.update({"status": "candidate", "requires_human_confirmation": True})
            governance["confirmed_by"] = None
            governance["confirmed_at"] = None
            consensus.update({"status": "candidate", "confirmed_by": []})
            transformed["governance"] = governance
            transformed["consensus"] = consensus

        status = "needs_review" if unmapped else "ready"
        return cls._result(
            status=status,
            source_scope=source_scope,
            target_scope=target_scope,
            mapping_version=normalized_version,
            interpolation_strategy=normalized_strategy,
            transform_reason=reason,
            transformed_qdl=transformed,
            decisions=decisions,
            unmapped=unmapped,
            errors=errors,
        )

    @staticmethod
    def _scope(scope_type: str, scope_id: str) -> dict[str, str] | None:
        normalized_type = _ALIASES.get(str(scope_type or "").strip().lower(), str(scope_type or "").strip().lower())
        normalized_id = str(scope_id or "").strip()
        if normalized_type not in _ALLOWED_SCOPE_TYPES or not normalized_id:
            return None
        return {"scope_type": normalized_type, "scope_id": normalized_id}

    @staticmethod
    def _dict_rules(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {str(key): str(item) for key, item in value.items() if str(key) and item is not None}

    @staticmethod
    def _nested_dict_rules(value: Any) -> dict[str, dict[str, str]]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key): {str(inner_key): str(inner_value) for inner_key, inner_value in inner.items() if inner_value is not None}
            for key, inner in value.items()
            if isinstance(inner, dict)
        }

    @staticmethod
    def _decision(path: str, source: Any, target: Any, action: str, reason: str) -> dict[str, Any]:
        return {"path": path, "source": source, "target": target, "action": action, "reason": reason}

    @staticmethod
    def _source_hash(payload: dict[str, Any], *, mapping_version: str, mapping_rules: dict[str, Any]) -> str:
        canonical = json.dumps(
            {"qdl": payload, "mapping_version": mapping_version, "mapping_rules": mapping_rules},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _result(
        *,
        status: str,
        source_scope: dict[str, str],
        target_scope: dict[str, str],
        mapping_version: str,
        interpolation_strategy: str,
        transform_reason: str,
        transformed_qdl: dict[str, Any] | None,
        decisions: list[dict[str, Any]],
        unmapped: list[str],
        errors: list[str],
    ) -> KnowledgeTunnelResult:
        constraints = [
            "target scope visibility must not exceed the approved target scope",
            "unmapped fields must be reviewed before publication",
            "source QDL and mapping version remain part of the transfer audit",
        ]
        if source_scope != target_scope:
            constraints.append("cross-scope projection requires target-scope approval")
        return KnowledgeTunnelResult(
            status=status,
            source_scope=source_scope,
            target_scope=target_scope,
            mapping_version=mapping_version,
            interpolation_strategy=interpolation_strategy,
            transform_reason=transform_reason,
            transformed_qdl=transformed_qdl,
            mapping_decisions=tuple(decisions),
            unmapped_fields=tuple(dict.fromkeys(unmapped)),
            constraints=tuple(constraints),
            errors=tuple(dict.fromkeys(errors)),
        )


__all__ = ["KnowledgeTunnelResult", "KnowledgeTunnelService", "QDL_VERSION"]
