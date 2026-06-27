from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_APP_DEVELOPER,
    ROLE_EXPERT,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
)


RESPONSE_VISIBILITY_ROOM = "room"
RESPONSE_VISIBILITY_PRIVATE = "private"

WORKSPACE_APP = "app"
WORKSPACE_OPS = "ops"
WORKSPACE_GOVERNANCE = "governance"

BLOCKED_SECRET_FIELDS = [
    "api_key",
    "secret_key",
    "token",
    "password",
    "connection_string",
]

DATA_DOMAIN_CATALOG: dict[str, list[str]] = {
    "quality": ["quality.task", "quality.result", "quality.review", "quality.analytics"],
    "standard": ["standard.library", "standard.rule", "standard.version", "standard.approval"],
    "meeting": ["meeting.message", "meeting.summary", "meeting.action_item", "meeting.private_message"],
    "memory": ["memory.user", "memory.meeting", "memory.agent", "memory.org_space", "memory.business"],
    "platform_ops": ["ops.agent", "ops.prompt", "ops.route", "ops.tool", "ops.release", "ops.trace"],
    "model_billing": [
        "model.catalog",
        "model.config",
        "model.experiment",
        "model.deployment",
        "model.experiment_cost",
        "model.org_usage",
        "billing.invoice",
    ],
    "org_admin": ["org.member", "org.role", "org.department", "org.policy"],
    "data_access": ["data.dataset", "data.sample", "data.rag_space", "data.connector", "data.import_job"],
    "security_audit": ["audit.auth", "audit.tool_execution", "audit.agent_query", "audit.approval"],
    "ai_conversation": [
        "conversation.own",
        "conversation.meeting",
        "conversation.private",
        "conversation.trace_redacted",
    ],
}

LEGACY_DOMAIN_ALIASES = DATA_DOMAIN_CATALOG

_ALL_FINE_DOMAINS = [domain for domains in DATA_DOMAIN_CATALOG.values() for domain in domains]
ALL_DATA_DOMAINS = [*DATA_DOMAIN_CATALOG.keys(), *_ALL_FINE_DOMAINS]

SENSITIVE_DOMAINS = {
    "model.catalog",
    "model.config",
    "model.experiment",
    "model.deployment",
    "model.experiment_cost",
    "model.org_usage",
    "billing.invoice",
    "org.member",
    "org.role",
    "org.department",
    "org.policy",
    "audit.auth",
    "audit.tool_execution",
    "audit.agent_query",
    "audit.approval",
    "conversation.private",
    "meeting.private_message",
    "memory.user",
}

SENSITIVE_LEGACY_DOMAINS = {
    "model_billing",
    "org_admin",
    "security_audit",
}

ROLE_DOMAIN_GRANTS: dict[str, set[str]] = {
    ROLE_USER: {
        "quality.task",
        "quality.result",
        "standard.library",
        "meeting.message",
        "meeting.summary",
        "meeting.action_item",
        "memory.user",
        "memory.meeting",
        "conversation.own",
        "conversation.meeting",
    },
    ROLE_EXPERT: {
        "quality.task",
        "quality.result",
        "quality.review",
        "standard.library",
        "standard.rule",
        "standard.version",
        "meeting.message",
        "meeting.summary",
        "meeting.action_item",
        "memory.user",
        "memory.meeting",
        "memory.business",
        "conversation.own",
        "conversation.meeting",
    },
    ROLE_ALGORITHM_ENGINEER: {
        "quality.analytics",
        "standard.library",
        "meeting.message",
        "meeting.summary",
        "meeting.action_item",
        "memory.meeting",
        "memory.agent",
        "memory.business",
        "data.dataset",
        "data.sample",
        "data.rag_space",
        "data.import_job",
        "model.catalog",
        "model.config",
        "model.experiment",
        "model.deployment",
        "model.experiment_cost",
        "conversation.trace_redacted",
    },
    ROLE_APP_DEVELOPER: {
        "meeting.message",
        "meeting.summary",
        "meeting.action_item",
        "memory.meeting",
        "memory.agent",
        "ops.agent",
        "ops.prompt",
        "ops.route",
        "ops.tool",
        "ops.release",
        "ops.trace",
        "data.rag_space",
        "data.connector",
        "audit.tool_execution",
        "conversation.trace_redacted",
    },
    ROLE_PLATFORM_OPERATOR: {
        "quality.task",
        "quality.result",
        "quality.analytics",
        "standard.library",
        "meeting.message",
        "meeting.summary",
        "meeting.action_item",
        "memory.meeting",
        "memory.business",
        "ops.agent",
        "ops.release",
        "ops.trace",
        "model.catalog",
        "model.org_usage",
        "audit.auth",
        "audit.tool_execution",
        "audit.agent_query",
        "audit.approval",
        "conversation.trace_redacted",
    },
    ROLE_ADMIN: set(_ALL_FINE_DOMAINS),
}

DEFAULT_ROOM_DOMAINS = [
    "quality.task",
    "quality.result",
    "quality.review",
    "quality.analytics",
    "standard.library",
    "standard.rule",
    "standard.version",
    "meeting.message",
    "meeting.summary",
    "meeting.action_item",
    "memory.meeting",
    "memory.business",
]

CORE_CONTEXT_DOMAIN_ALIASES = ["meeting", "memory"]

_ORDER_INDEX = {domain: index for index, domain in enumerate(_ALL_FINE_DOMAINS)}


@dataclass(frozen=True)
class DomainAuthorization:
    requested_domains: list[str]
    allowed_domains: list[str]
    denied_domains: list[str]
    redacted_fields: list[str] = field(default_factory=list)
    response_visibility: str = RESPONSE_VISIBILITY_ROOM
    decision: str = "allowed"
    denied_reasons: dict[str, str] = field(default_factory=dict)
    redaction_level: str = "none"


def ordered_domains(domains: Iterable[str]) -> list[str]:
    return sorted({str(item) for item in domains if item}, key=lambda value: (_ORDER_INDEX.get(value, 10_000), value))


def normalize_domains(values: Any, *, expand_legacy: bool = True) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [item.strip() for item in values.replace(";", ",").split(",")]
    elif isinstance(values, (list, tuple, set)):
        raw_values = [str(item or "").strip() for item in values]
    else:
        return []

    result: list[str] = []
    seen: set[str] = set()
    fine_domains = set(_ALL_FINE_DOMAINS)
    for value in raw_values:
        if not value:
            continue
        expanded = LEGACY_DOMAIN_ALIASES.get(value, [value] if value in fine_domains else [])
        for domain in expanded if expand_legacy else [value]:
            if domain in fine_domains and domain not in seen:
                seen.add(domain)
                result.append(domain)
    return ordered_domains(result)


def raw_domain_tokens(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [item.strip() for item in values.replace(";", ",").split(",")]
    elif isinstance(values, (list, tuple, set)):
        raw_values = [str(item or "").strip() for item in values]
    else:
        return []
    return [value for value in raw_values if value]


def role_allowed_domains(role: str | None) -> set[str]:
    return set(ROLE_DOMAIN_GRANTS.get(str(role or ROLE_USER), ROLE_DOMAIN_GRANTS[ROLE_USER]))


def derive_workspaces_for_roles(roles: Iterable[str], plan_tier: str = "basic") -> list[str]:
    role_set = {str(role) for role in roles if role}
    workspaces: list[str] = [WORKSPACE_APP]
    if role_set & {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER}:
        workspaces.append(WORKSPACE_OPS)
    if ROLE_ADMIN in role_set or ROLE_ALGORITHM_ENGINEER in role_set:
        workspaces.append(WORKSPACE_GOVERNANCE)
    return list(dict.fromkeys(workspaces))


def authorize_room_domains(role: str | None, requested_domains: Any) -> list[str]:
    requested = normalize_domains(requested_domains) or list(DEFAULT_ROOM_DOMAINS)
    allowed = role_allowed_domains(role)
    effective = set(requested) & allowed
    effective.update(domain for domain in DEFAULT_ROOM_DOMAINS if domain in allowed)
    return ordered_domains(effective)


def authorize_agent_domains(*, role: str | None, room_domains: Any, requested_domains: Any = None) -> list[str]:
    effective_room_domains = set(normalize_domains(room_domains) or authorize_room_domains(role, None))
    requested = normalize_domains(requested_domains) if requested_domains is not None else list(effective_room_domains)
    return ordered_domains(set(requested) & effective_room_domains & role_allowed_domains(role))


def authorize_meeting_query(
    *,
    role: str | None,
    requested_domains: Any,
    room_domains: Any,
    agent_domains: Any = None,
    question: str = "",
) -> DomainAuthorization:
    raw_requested = raw_domain_tokens(requested_domains)
    requested = normalize_domains(requested_domains) or list(DEFAULT_ROOM_DOMAINS)
    role_domains = role_allowed_domains(role)
    room_set = set(normalize_domains(room_domains) or DEFAULT_ROOM_DOMAINS)
    agent_set = set(normalize_domains(agent_domains)) if agent_domains is not None else room_set
    allowed_set = set(requested) & role_domains & room_set & agent_set
    denied_set = set(requested) - allowed_set
    denied_reasons = {
        domain: _denied_reason(domain, role_domains=role_domains, room_domains=room_set, agent_domains=agent_set)
        for domain in denied_set
    }
    redacted_fields = redacted_fields_for_question(question)
    sensitive_requested = bool(set(raw_requested) & (SENSITIVE_DOMAINS | SENSITIVE_LEGACY_DOMAINS)) or bool(allowed_set & SENSITIVE_DOMAINS)
    response_visibility = RESPONSE_VISIBILITY_PRIVATE if sensitive_requested or redacted_fields else RESPONSE_VISIBILITY_ROOM
    decision = "allowed" if not denied_set else ("partial" if allowed_set else "denied")
    return DomainAuthorization(
        requested_domains=ordered_domains(requested),
        allowed_domains=ordered_domains(allowed_set),
        denied_domains=ordered_domains(denied_set),
        redacted_fields=redacted_fields,
        response_visibility=response_visibility,
        decision=decision,
        denied_reasons=denied_reasons,
        redaction_level="secret" if redacted_fields else ("sensitive" if sensitive_requested else "none"),
    )


def is_sensitive_authorization(auth: DomainAuthorization) -> bool:
    return auth.response_visibility == RESPONSE_VISIBILITY_PRIVATE or auth.redaction_level != "none"


def redacted_fields_for_question(question: str) -> list[str]:
    normalized = str(question or "").lower()
    sensitive_terms = (
        "api key",
        "apikey",
        "secret",
        "token",
        "password",
        "passwd",
        "pwd",
        "connection string",
        "连接串",
        "密钥",
        "密码",
        "令牌",
        "私钥",
    )
    return list(BLOCKED_SECRET_FIELDS) if any(term in normalized for term in sensitive_terms) else []


def strip_meeting_agent_mentions(question: str) -> str:
    normalized = str(question or "")
    replacements = (
        "@会议Agent",
        "@会议 Agent",
        "@会议室Agent",
        "@会议室 Agent",
        "@AI助手",
        "@AI 助手",
        "@智能助手",
        "@总Agent",
        "@总 Agent",
        "@总智能体",
        "@agent",
        "@general agent",
    )
    for marker in replacements:
        normalized = normalized.replace(marker, "")
    return normalized.strip()


def infer_requested_domains_for_query(intent: str | None, question: str) -> list[str]:
    intent_key = str(intent or "").strip()
    if intent_key in {"capability_intro", "meeting_summary", "action_items", "memory_transfer"}:
        return list(CORE_CONTEXT_DOMAIN_ALIASES)
    if intent_key in {"risk_forecast", "evidence_query", "standard_explain"}:
        return ["quality", "standard", "meeting", "memory"]

    cleaned_question = strip_meeting_agent_mentions(question)
    normalized = str(cleaned_question or "").lower()
    compact = "".join(normalized.split())
    domains: set[str] = set()
    keyword_groups = [
        (("质检", "检测", "任务", "缺陷", "复核", "批次", "产品", "quality", "inspection"), {"quality", "standard"}),
        (("标准", "条款", "判定", "standard"), {"standard"}),
        (("模型", "价格", "成本", "供应商", "billing", "model", "price", "cost"), {"platform_ops", "model_billing"}),
        (("agent", "智能体", "路由", "trace", "prompt", "运行", "队列"), {"platform_ops"}),
        (("组织", "成员", "角色", "权限", "部门", "admin", "审计记录"), {"org_admin", "security_audit"}),
        (("数据源", "数据集", "样本", "连接器", "rag", "同步", "索引", "dataset", "sample", "connector"), {"data_access", "platform_ops"}),
        (("会话", "聊天记录", "私聊", "conversation", "chat history"), {"ai_conversation", "security_audit"}),
        (("记忆", "候选记忆", "共享记忆", "memory"), {"memory"}),
    ]
    for keywords, mapped_domains in keyword_groups:
        if any(keyword in normalized or keyword in compact for keyword in keywords):
            domains.update(mapped_domains)
    if not domains:
        domains.update(CORE_CONTEXT_DOMAIN_ALIASES)
    return ordered_domains(domains)


def _denied_reason(domain: str, *, role_domains: set[str], room_domains: set[str], agent_domains: set[str]) -> str:
    if domain not in role_domains:
        return "role_not_allowed"
    if domain not in room_domains:
        return "room_not_allowed"
    if domain not in agent_domains:
        return "agent_not_allowed"
    return "not_allowed"
