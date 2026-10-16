from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.schemas.task import TaskCreate
from app.schemas.user import CurrentUser
from app.services.material_task_service import MaterialTaskService


@pytest.mark.asyncio
async def test_material_task_reuses_file_hash_and_does_not_upload_or_execute(monkeypatch):
    record=SimpleNamespace(id="record",attachment_ids=["file"],content={"text":"fixture"})
    attachment=SimpleNamespace(id="file",mime_type="image/png",sha256="a"*64)
    responses=[SimpleNamespace(scalar_one=lambda:record),SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[attachment]))]
    db=SimpleNamespace(execute=AsyncMock(side_effect=responses))
    monkeypatch.setattr("app.services.material_task_service.KnowledgeSourceService",lambda *args:SimpleNamespace(resolve=AsyncMock(return_value={})))
    create=AsyncMock(return_value=SimpleNamespace(id="task",status="pending"))
    monkeypatch.setattr("app.services.material_task_service.TaskService",lambda *args:SimpleNamespace(create_task=create))
    result=await MaterialTaskService(db,CurrentUser(user_id="author",org_id="org",role="expert")).draft("record",TaskCreate(inspection_standard_id="standard"))
    values=create.call_args.kwargs
    assert values["image_items"][0].hash=="a"*64
    assert values["metadata"]["material_reference"]["attachment_ids"]==["file"]
    assert values["metadata"]["execution_requested"] is False
    assert result["reused_attachment_ids"]==["file"] and result["status"]=="pending"
