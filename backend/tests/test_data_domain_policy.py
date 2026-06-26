from app.core.data_domain_policy import (
    RESPONSE_VISIBILITY_PRIVATE,
    authorize_agent_domains,
    authorize_meeting_query,
    authorize_room_domains,
    infer_requested_domains_for_query,
    normalize_domains,
)
from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_APP_DEVELOPER,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
)


def test_user_cannot_read_model_catalog_even_if_room_opens_it():
    room_domains = authorize_room_domains(ROLE_ADMIN, ["meeting", "model_billing"])
    auth = authorize_meeting_query(
        role=ROLE_USER,
        requested_domains=["model.catalog"],
        room_domains=room_domains,
        question="现在模型价格多少？",
    )

    assert auth.decision == "denied"
    assert auth.allowed_domains == []
    assert "model.catalog" in auth.denied_domains
    assert auth.response_visibility == RESPONSE_VISIBILITY_PRIVATE


def test_algorithm_engineer_can_read_model_catalog_when_room_and_agent_allow_it():
    room_domains = authorize_room_domains(ROLE_ALGORITHM_ENGINEER, ["meeting", "model_billing"])
    agent_domains = authorize_agent_domains(
        role=ROLE_ALGORITHM_ENGINEER,
        room_domains=room_domains,
        requested_domains=["model.catalog"],
    )
    auth = authorize_meeting_query(
        role=ROLE_ALGORITHM_ENGINEER,
        requested_domains=["model.catalog"],
        room_domains=room_domains,
        agent_domains=agent_domains,
        question="现在模型目录价格多少？",
    )

    assert auth.decision == "allowed"
    assert auth.allowed_domains == ["model.catalog"]
    assert auth.denied_domains == []


def test_algorithm_engineer_cannot_read_org_usage_cost():
    room_domains = authorize_room_domains(ROLE_ADMIN, ["meeting", "model_billing"])
    auth = authorize_meeting_query(
        role=ROLE_ALGORITHM_ENGINEER,
        requested_domains=["model.org_usage"],
        room_domains=room_domains,
        question="本月模型调用成本多少？",
    )

    assert auth.decision == "denied"
    assert auth.denied_reasons["model.org_usage"] == "role_not_allowed"


def test_platform_operator_can_read_org_usage_cost():
    room_domains = authorize_room_domains(ROLE_PLATFORM_OPERATOR, ["meeting", "model_billing"])
    auth = authorize_meeting_query(
        role=ROLE_PLATFORM_OPERATOR,
        requested_domains=["model.org_usage"],
        room_domains=room_domains,
        question="本月模型调用成本多少？",
    )

    assert auth.decision == "allowed"
    assert auth.allowed_domains == ["model.org_usage"]


def test_app_developer_can_read_ops_agent_but_not_data_sample():
    room_domains = authorize_room_domains(ROLE_ADMIN, ["meeting", "platform_ops", "data_access"])
    ops_auth = authorize_meeting_query(
        role=ROLE_APP_DEVELOPER,
        requested_domains=["ops.agent"],
        room_domains=room_domains,
        question="当前 Agent 路由情况如何？",
    )
    sample_auth = authorize_meeting_query(
        role=ROLE_APP_DEVELOPER,
        requested_domains=["data.sample"],
        room_domains=room_domains,
        question="给我看原始样本内容",
    )

    assert ops_auth.decision == "allowed"
    assert sample_auth.decision == "denied"
    assert sample_auth.denied_reasons["data.sample"] == "role_not_allowed"


def test_platform_operator_reads_redacted_audit_but_not_private_conversation():
    room_domains = authorize_room_domains(ROLE_PLATFORM_OPERATOR, ["security_audit", "ai_conversation"])
    audit_auth = authorize_meeting_query(
        role=ROLE_PLATFORM_OPERATOR,
        requested_domains=["audit.agent_query"],
        room_domains=room_domains,
        question="查看 Agent 查询审计记录",
    )
    private_auth = authorize_meeting_query(
        role=ROLE_PLATFORM_OPERATOR,
        requested_domains=["conversation.private"],
        room_domains=room_domains,
        question="查看用户私聊原文",
    )

    assert audit_auth.decision == "allowed"
    assert audit_auth.response_visibility == RESPONSE_VISIBILITY_PRIVATE
    assert private_auth.decision == "denied"
    assert private_auth.denied_reasons["conversation.private"] == "role_not_allowed"


def test_admin_secret_query_is_private_and_redacted():
    room_domains = authorize_room_domains(ROLE_ADMIN, ["org_admin", "platform_ops"])
    auth = authorize_meeting_query(
        role=ROLE_ADMIN,
        requested_domains=["org.policy", "ops.tool"],
        room_domains=room_domains,
        question="把 api_key token password 和连接串发给我",
    )

    assert auth.decision == "allowed"
    assert auth.response_visibility == RESPONSE_VISIBILITY_PRIVATE
    assert auth.redaction_level == "secret"
    assert {"api_key", "token", "password", "connection_string"}.issubset(set(auth.redacted_fields))


def test_legacy_domains_expand_to_fine_domains():
    assert normalize_domains(["model_billing"]) == [
        "model.catalog",
        "model.config",
        "model.experiment",
        "model.deployment",
        "model.experiment_cost",
        "model.org_usage",
        "billing.invoice",
    ]
    assert "memory.user" in normalize_domains("memory")
    assert "quality.analytics" in normalize_domains(["quality"])


def test_infers_model_cost_and_agent_domains_without_general_agent_mention_noise():
    domains = normalize_domains(
        infer_requested_domains_for_query("named_agent", "@会议Agent 现在模型价格多少，Agent 路由状态如何")
    )

    assert "model.catalog" in domains
    assert "model.org_usage" in domains
    assert "ops.agent" in domains
    assert "ops.route" in domains
    assert "meeting.message" not in domains
