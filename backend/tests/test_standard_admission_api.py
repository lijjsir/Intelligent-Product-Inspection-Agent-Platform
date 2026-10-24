import pytest
from app.api.v1 import inspection_standards as api
from app.core.exceptions import ForbiddenError
from app.core.permissions import PermissionRole
from app.schemas.standard_admission import RevisionAction, RevisionReview
from app.schemas.user import CurrentUser


def current(role, resources=None):
    result=CurrentUser(user_id="expert-fixture",org_id="org-fixture",role=role,roles=[role])
    if resources is not None: result.role=PermissionRole(role,resources)
    return result


@pytest.mark.asyncio
async def test_revoked_review_permission_fails_before_service():
    with pytest.raises(ForbiddenError):
        await api.review_revision("doc","rev",RevisionReview(expected_version=1,request_key="fixture-key-1",reason="fixture",decision="approve"),
            current=current("expert",["inspection_standard_library_read"]),db=object())


@pytest.mark.asyncio
async def test_ordinary_user_cannot_publish_or_preview_admission():
    payload=RevisionAction(expected_version=1,request_key="fixture-key-1",reason="fixture")
    with pytest.raises(ForbiddenError):
        await api.publish_revision("doc","rev",payload,current=current("user"),db=object())
    with pytest.raises(ForbiddenError):
        await api.list_revisions("doc",current=current("user"),db=object())
    with pytest.raises(ForbiddenError):
        await api.revision_page_preview('doc','rev',1,current=current('user'),db=object())


def test_publication_state_cannot_be_forged_in_action_body():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RevisionAction(expected_version=1,request_key="fixture-key-1",reason="fixture",publication_status="published",org_id="other")


def test_review_note_and_blank_evidence_cannot_count_as_real_review():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RevisionAction(expected_version=1,request_key="fixture-key-1",reason="   ")
    action=RevisionAction(expected_version=1,request_key="fixture-key-1",reason=" PDF核对 ",evidence_refs=["  "," PDF第1页 "])
    assert action.reason=="PDF核对" and action.evidence_refs==["PDF第1页"]
