import pytest
from app.api.v1 import knowledge
from app.schemas.user import CurrentUser
from app.schemas.knowledge_admission import KnowledgeReview,KnowledgeAction
from app.core.exceptions import ForbiddenError
from app.core.permissions import PermissionRole


@pytest.mark.asyncio
async def test_admin_cannot_sign_professional_knowledge_review():
    with pytest.raises(ForbiddenError):
        await knowledge.review("id",KnowledgeReview(expected_version=1,request_key="fixture-1",reason="fixture review",decision="approve"),
            current=CurrentUser(user_id="admin",org_id="org",role="admin"),db=object())


@pytest.mark.asyncio
async def test_revoked_expert_review_permission_is_checked_before_service():
    current=CurrentUser(user_id="expert",org_id="org",role="expert");current.role=PermissionRole("expert",["knowledge_read"])
    with pytest.raises(ForbiddenError):
        await knowledge.review("id",KnowledgeReview(expected_version=1,request_key="fixture-1",reason="fixture review",decision="approve"),current=current,db=object())


def test_client_cannot_forge_namespace_or_publish_state():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):KnowledgeAction(expected_version=1,request_key="fixture-1",reason="fixture action",org_id="other",publication_status="published")
