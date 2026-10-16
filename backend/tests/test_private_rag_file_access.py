from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.api.v1 import files
from app.core.config import settings
from app.core.exceptions import ForbiddenError,NotFoundError
from app.schemas.user import CurrentUser


@pytest.mark.asyncio
async def test_private_rag_file_requires_identity_before_reading_storage(monkeypatch):
    doc=SimpleNamespace(rag_space_id="space",org_id="org",deleted_at=None)
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda:doc)))
    called=[]
    monkeypatch.setattr(files,"build_object_storage",lambda:called.append("storage"))
    with pytest.raises(ForbiddenError):await files.serve_file(settings.rag_storage_bucket,"private.pdf",authorization="",db=db)
    assert called==[]


@pytest.mark.asyncio
async def test_admin_cannot_fetch_unguarded_private_file_by_url(monkeypatch):
    doc=SimpleNamespace(rag_space_id="space",org_id="org",deleted_at=None)
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda:doc)))
    monkeypatch.setattr(files,"get_permission_identity",AsyncMock(return_value={}))
    monkeypatch.setattr(files,"get_current_user",lambda **kw:CurrentUser(user_id="admin",org_id="org",role="admin"))
    monkeypatch.setattr(files,"RagSpaceRepository",lambda _:SimpleNamespace(get=AsyncMock(return_value=None)))
    called=[];monkeypatch.setattr(files,"build_object_storage",lambda:called.append("storage"))
    with pytest.raises(NotFoundError):await files.serve_file(settings.rag_storage_bucket,"private.pdf",authorization="Bearer fixture",db=db)
    assert called==[]
