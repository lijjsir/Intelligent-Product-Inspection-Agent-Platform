from app.core.data_domain_policy import authorize_meeting_query, authorize_room_domains
from app.core.permissions import ROLE_USER


def test_default_meeting_room_allows_user_quality_task_context():
    room_domains = authorize_room_domains(ROLE_USER, None)
    auth = authorize_meeting_query(
        role=ROLE_USER,
        requested_domains=["quality"],
        room_domains=room_domains,
        question="@会议Agent 有几条质检任务被创建？",
    )

    assert "quality.task" in room_domains
    assert "quality.result" in room_domains
    assert "standard.library" in room_domains
    assert auth.decision == "partial"
    assert {"quality.task", "quality.result"}.issubset(set(auth.allowed_domains))
