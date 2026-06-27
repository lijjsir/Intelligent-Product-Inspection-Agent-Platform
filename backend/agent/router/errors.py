from __future__ import annotations

from enum import Enum
from typing import Any


def _enum_value(value: Any) -> str:
    """Extract the string value from an Enum member, or coerce to str.

    Using ``str(SomeEnum.field)`` on a ``str, Enum`` subclass can produce
    ``"SomeEnum.field"`` in certain Python versions / contexts, which would
    break frontend checks like ``category === "routing"``.  ``.value`` is the
    canonical path to the underlying string.
    """
    if isinstance(value, Enum):
        return value.value
    return str(value)


class AgentErrorCategory(str, Enum):
    VALIDATION = "validation"
    ROUTING = "routing"
    DISPATCH = "dispatch"
    CAPABILITY = "capability"
    TOOL = "tool"
    MODEL = "model"
    DATA = "data"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    EXTERNAL = "external"
    INTERNAL = "internal"


class AgentErrorStatus(str, Enum):
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentRuntimeError(Exception):
    """Base exception for agent runtime errors exposed through AgentErrorPayload."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        title: str | None = None,
        category: AgentErrorCategory | str = AgentErrorCategory.INTERNAL,
        severity: str = "error",
        status: AgentErrorStatus | str = AgentErrorStatus.FAILED,
        frontend_visible: bool = True,
        retryable: bool = False,
        user_action: str | None = None,
        detail: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
        source: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.code = code
        self.title = title or code
        self.message = message or "Agent 执行失败。"
        self.category = _enum_value(category)
        self.severity = severity
        self.status = _enum_value(status)
        self.frontend_visible = frontend_visible
        self.retryable = retryable
        self.user_action = user_action
        self.detail = detail or {}
        self.debug = debug or {}
        self.source = source
        self.cause = cause
        super().__init__(self.message)

    def to_dict(
        self,
        *,
        state: Any | None = None,
        include_debug: bool = False,
        stage: str | None = None,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "title": self.title,
            "message": self.message,
            "category": self.category,
            "severity": self.severity,
            "status": self.status,
            "frontend_visible": self.frontend_visible,
            "retryable": self.retryable,
            "user_action": self.user_action,
            "source": self.source,
            "detail": dict(self.detail or {}),
        }
        if state is not None:
            selected_agent = agent_name or getattr(state, "selected_agent", None) or None
            payload.update(
                {
                    "request_id": getattr(state, "request_id", None),
                    "workflow_run_id": getattr(state, "workflow_run_id", None),
                    "trace_id": getattr(state, "trace_id", None) or getattr(state, "workflow_run_id", None) or getattr(state, "request_id", None),
                    "session_id": getattr(state, "session_id", None),
                    "owner_agent": selected_agent,
                    "agent_name": selected_agent,
                }
            )
            current_capability = getattr(state, "current_capability", None)
            current_step_id = getattr(state, "current_step_id", None)
            current_owner_agent = getattr(state, "current_owner_agent", None)
            if current_capability or current_step_id or current_owner_agent:
                payload["owner_agent"] = current_owner_agent or payload.get("owner_agent")
                payload["agent_name"] = current_owner_agent or payload.get("agent_name")
                payload["capability"] = current_capability
                payload["step_id"] = current_step_id
            else:
                route_plan = getattr(state, "route_plan", None)
                steps = list(getattr(route_plan, "steps", []) or [])
                if steps:
                    step = steps[-1]
                    payload.setdefault("owner_agent", getattr(step, "owner_agent", None))
                    payload["capability"] = getattr(step, "capability", None)
                    payload["step_id"] = getattr(step, "step_id", None)
        if stage:
            payload["stage"] = stage
        elif self.source:
            payload["stage"] = str(self.source).split(".", 1)[0]
        if agent_name:
            payload["agent_name"] = agent_name
            payload["owner_agent"] = agent_name
        if include_debug and self.debug:
            payload["debug"] = dict(self.debug)
        return {key: value for key, value in payload.items() if value is not None}


class AgentValidationError(AgentRuntimeError):
    pass


class AgentBlockedError(AgentRuntimeError):
    pass


class AgentRoutingError(AgentRuntimeError):
    pass


class AgentDispatchError(AgentRuntimeError):
    pass


class AgentCapabilityError(AgentRuntimeError):
    pass


class AgentToolError(AgentRuntimeError):
    pass


class AgentExecutionError(AgentCapabilityError):
    pass


class AgentModelError(AgentRuntimeError):
    pass


class AgentDataError(AgentRuntimeError):
    pass


class AgentTimeoutError(AgentRuntimeError):
    pass


class AgentPermissionError(AgentRuntimeError):
    pass


class AgentExternalServiceError(AgentRuntimeError):
    pass


class AgentInternalError(AgentRuntimeError):
    pass


ERROR_CATALOG: dict[str, dict[str, Any]] = {
    "UNKNOWN_CAPABILITY": {
        "title": "未知能力",
        "message": "请求的 Agent 能力不存在。",
        "category": AgentErrorCategory.ROUTING,
        "user_action": "请刷新页面后重试；如果持续失败，请联系管理员。",
        "retryable": False,
    },
    "UNKNOWN_OWNER_AGENT": {
        "title": "未知业务 Agent",
        "message": "请求被路由到了不存在的业务 Agent。",
        "category": AgentErrorCategory.DISPATCH,
        "user_action": "请刷新页面后重试；如果持续失败，请联系管理员。",
        "retryable": False,
    },
    "MISSING_OWNER_AGENT": {
        "title": "缺少业务 Agent",
        "message": "计划步骤缺少 owner_agent。",
        "category": AgentErrorCategory.ROUTING,
        "user_action": "请刷新页面后重试；如果持续失败，请联系管理员。",
        "retryable": False,
    },
    "UNSUPPORTED_CAPABILITY": {
        "title": "能力不支持",
        "message": "当前业务 Agent 不支持该能力。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请换用正确页面或稍后重试。",
        "retryable": False,
    },
    "PLAN_OWNER_CAPABILITY_MISMATCH": {
        "title": "路由计划不匹配",
        "message": "计划中的业务 Agent 与能力归属不匹配。",
        "category": AgentErrorCategory.ROUTING,
        "user_action": "请刷新页面后重试；如果持续失败，请联系管理员。",
        "retryable": False,
    },
    "CAPABILITY_HAS_NO_OWNER": {
        "title": "能力配置缺少归属",
        "message": "能力没有配置可执行的业务 Agent。",
        "category": AgentErrorCategory.ROUTING,
        "user_action": "请联系管理员检查能力注册表。",
        "retryable": False,
    },
    "CAPABILITY_EXECUTION_FAILED": {
        "title": "能力执行失败",
        "message": "能力执行过程中发生异常。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请稍后重试；如果持续失败，请联系管理员。",
        "retryable": True,
    },
    "AGENT_FAILED": {
        "title": "Agent 执行失败",
        "message": "Agent 执行失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请稍后重试；如果持续失败，请联系管理员。",
        "retryable": True,
    },
    "AGENT_STEP_FAILED": {
        "title": "步骤执行失败",
        "message": "Agent 执行步骤失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请稍后重试；如果持续失败，请联系管理员。",
        "retryable": True,
    },
    "STEP_EXECUTION_FAILED": {
        "title": "步骤执行失败",
        "message": "Agent 执行步骤失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请稍后重试；如果持续失败，请联系管理员。",
        "retryable": True,
    },
    "RAG_RETRIEVE_FAILED": {
        "title": "知识库检索失败",
        "message": "知识库检索失败，无法完成当前 RAG 问答。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请稍后重试，或检查知识库服务与向量库连接是否正常。",
        "retryable": True,
    },
    "FILE_PARSE_FAILED": {
        "title": "文件解析失败",
        "message": "文件解析失败，无法继续执行文件总结、问答或论文检查。",
        "category": AgentErrorCategory.DATA,
        "user_action": "请检查文件是否损坏，并上传 docx、pdf、txt、csv、xlsx 等支持格式。",
        "retryable": False,
    },
    "IMAGE_MODEL_UNAVAILABLE": {
        "title": "视觉模型不可用",
        "message": "当前组织没有可用的视觉模型，无法完成图片理解。",
        "category": AgentErrorCategory.MODEL,
        "user_action": "请在后台模型配置中启用 multimodal、vision 或 vlm 模型。",
        "retryable": False,
    },
    "IMAGE_UNDERSTANDING_FAILED": {
        "title": "图片理解失败",
        "message": "图片理解失败，无法完成当前图片分析。",
        "category": AgentErrorCategory.MODEL,
        "user_action": "请稍后重试，或检查视觉模型配置。",
        "retryable": True,
    },
    "EVIDENCE_ARBITRATION_FAILED": {
        "title": "证据仲裁失败",
        "message": "证据仲裁执行失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请检查知识库、记忆或质量知识图谱服务配置后重试。",
        "retryable": True,
    },
    "VISION_INSPECTION_FAILED": {
        "title": "视觉检验失败",
        "message": "视觉检验执行失败。",
        "category": AgentErrorCategory.MODEL,
        "user_action": "请检查图片输入与视觉模型配置后重试。",
        "retryable": True,
    },
    "LAB_DETECTION_FAILED": {
        "title": "实验室检测研判失败",
        "message": "实验室检测早期风险研判失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请检查实验室输入数据格式和模型配置后重试。",
        "retryable": True,
    },
    "MEMORY_GOVERNANCE_FAILED": {
        "title": "记忆治理失败",
        "message": "记忆治理图执行失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请检查记忆服务和治理配置后重试。",
        "retryable": True,
    },
    "CHAT_COMPOSE_MODEL_UNAVAILABLE": {
        "title": "回复生成模型不可用",
        "message": "模型不可用，无法组织最终回复。",
        "category": AgentErrorCategory.MODEL,
        "user_action": "请检查后台聊天模型配置。",
        "retryable": True,
    },
    "MODEL_CALL_FAILED": {
        "title": "模型调用失败",
        "message": "图节点模型调用失败。",
        "category": AgentErrorCategory.MODEL,
        "user_action": "请检查模型服务、API Key、Base URL 和模型配置后重试。",
        "retryable": True,
    },
    "INSPECTION_TASK_FAILED": {
        "title": "正式质检执行失败",
        "message": "正式质检任务执行失败。",
        "category": AgentErrorCategory.CAPABILITY,
        "user_action": "请检查任务输入、模型配置和质检规则配置后重试。",
        "retryable": True,
    },
    "ACTION_INTENT_REQUIRED": {
        "title": "缺少正式操作确认",
        "message": "正式质量检测需要由质量检测任务页面显式提交。",
        "category": AgentErrorCategory.VALIDATION,
        "status": AgentErrorStatus.BLOCKED,
        "user_action": "请前往质量检测任务页面提交，并携带 action_intent=quality_inspection_execute。",
        "retryable": False,
    },
    "ACTION_BLOCKED_BY_SURFACE": {
        "title": "当前页面不允许执行正式动作",
        "message": "当前页面只能进行只读咨询，不能执行正式业务动作。",
        "category": AgentErrorCategory.VALIDATION,
        "status": AgentErrorStatus.BLOCKED,
        "user_action": "请前往对应业务页面显式确认后再提交正式操作。",
        "retryable": False,
    },
    "ACTION_MODE_FORBIDDEN": {
        "title": "当前页面已禁用正式动作",
        "message": "当前页面配置禁止执行 action 模式。",
        "category": AgentErrorCategory.VALIDATION,
        "status": AgentErrorStatus.BLOCKED,
        "user_action": "请检查页面权限或切换到允许正式操作的入口。",
        "retryable": False,
    },
    "MANAGER_TIMEOUT": {
        "title": "Agent 执行超时",
        "message": "当前请求执行超时。",
        "category": AgentErrorCategory.TIMEOUT,
        "user_action": "请稍后重试，或减少单次上传文件数量。",
        "retryable": True,
    },
    "PLAN_DEPENDENCY_DEADLOCK": {
        "title": "计划依赖无法满足",
        "message": "Agent 路由计划中的步骤依赖无法满足。",
        "category": AgentErrorCategory.ROUTING,
        "user_action": "请联系管理员检查 Agent 计划生成逻辑。",
        "retryable": False,
    },
    "INTERNAL_AGENT_ERROR": {
        "title": "系统内部错误",
        "message": "系统执行失败，请查看错误信息或联系管理员。",
        "category": AgentErrorCategory.INTERNAL,
        "user_action": "请联系管理员并提供 trace_id。",
        "retryable": True,
    },
}


def make_agent_error(
    code: str,
    *,
    message: str | None = None,
    title: str | None = None,
    detail: dict[str, Any] | None = None,
    debug: dict[str, Any] | None = None,
    source: str | None = None,
    cause: Exception | None = None,
    status: AgentErrorStatus | str | None = None,
    retryable: bool | None = None,
    frontend_visible: bool | None = None,
    user_action: str | None = None,
    severity: str | None = None,
) -> AgentRuntimeError:
    config = ERROR_CATALOG.get(code, {})
    category = config.get("category", AgentErrorCategory.INTERNAL)

    error_cls: type[AgentRuntimeError]
    if category == AgentErrorCategory.VALIDATION:
        error_cls = AgentValidationError
    elif category == AgentErrorCategory.DISPATCH:
        error_cls = AgentDispatchError
    elif category == AgentErrorCategory.ROUTING:
        error_cls = AgentRoutingError
    elif category == AgentErrorCategory.CAPABILITY:
        error_cls = AgentCapabilityError
    elif category == AgentErrorCategory.TOOL:
        error_cls = AgentToolError
    elif category == AgentErrorCategory.MODEL:
        error_cls = AgentModelError
    elif category == AgentErrorCategory.DATA:
        error_cls = AgentDataError
    elif category == AgentErrorCategory.TIMEOUT:
        error_cls = AgentTimeoutError
    elif category == AgentErrorCategory.PERMISSION:
        error_cls = AgentPermissionError
    elif category == AgentErrorCategory.EXTERNAL:
        error_cls = AgentExternalServiceError
    else:
        error_cls = AgentInternalError

    return error_cls(
        code=code,
        title=title or config.get("title"),
        message=message or config.get("message") or "Agent 执行失败。",
        category=category,
        status=status or config.get("status", AgentErrorStatus.FAILED),
        severity=severity or "error",
        frontend_visible=True if frontend_visible is None else frontend_visible,
        retryable=bool(config.get("retryable", False) if retryable is None else retryable),
        user_action=user_action or config.get("user_action"),
        detail=detail,
        debug=debug,
        source=source,
        cause=cause,
    )
