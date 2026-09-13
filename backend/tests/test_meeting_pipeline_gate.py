from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from agent.adapters.factory import AgentAdapterFactory
from app.core.exceptions import AgentAdapterUnavailableError
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.meeting import AgentDefinitionCreateRequest


def test_pipeline_adapter_is_explicitly_disabled_until_deployment_gate():
    with pytest.raises(AgentAdapterUnavailableError) as exc_info:
        AgentAdapterFactory.get_for_agent(SimpleNamespace(adapter_type="pipeline"))

    error = exc_info.value
    assert error.code == "AGENT_ADAPTER_UNAVAILABLE"
    assert error.detail == {
        "adapter_type": "pipeline",
        "supported_adapter_types": ["llm"],
        "implementation_status": "implemented_but_disabled",
    }
    assert "已实现但尚未启用" in error.message
    assert "PIAP_PIPELINE_AGENT_ENABLED=true" in error.suggestion


def test_meeting_agent_definition_request_rejects_pipeline_type_when_disabled():
    with pytest.raises(PydanticValidationError):
        AgentDefinitionCreateRequest(
            name="待启用流程 Agent",
            system_prompt="测试",
            adapter_type="pipeline",
        )


@pytest.mark.asyncio
async def test_meeting_repository_rejects_pipeline_definition_before_write():
    repository = MeetingRepository(None)

    with pytest.raises(AgentAdapterUnavailableError):
        await repository.create_agent_definition(
            org_id="org-1",
            name="待启用流程 Agent",
            system_prompt="测试",
            adapter_type="pipeline",
            created_by="user-1",
        )


def test_pipeline_adapter_factory_and_schema_accept_pipeline_when_enabled(monkeypatch):
    from app.core.config import settings
    from agent.adapters.pipeline_adapter import PipelineAgentAdapter

    monkeypatch.setattr(settings, "pipeline_agent_enabled", True)
    AgentAdapterFactory._adapters.pop("pipeline", None)

    definition = AgentDefinitionCreateRequest(
        name="流程知识 Agent",
        system_prompt="只基于知识空间回答",
        adapter_type="pipeline",
    )
    adapter = AgentAdapterFactory.get_for_agent(definition)

    assert definition.adapter_type == "pipeline"
    assert isinstance(adapter, PipelineAgentAdapter)

    # Keep later tests isolated from this process-wide adapter cache and gate.
    AgentAdapterFactory._adapters.pop("pipeline", None)
    monkeypatch.setattr(settings, "pipeline_agent_enabled", False)
