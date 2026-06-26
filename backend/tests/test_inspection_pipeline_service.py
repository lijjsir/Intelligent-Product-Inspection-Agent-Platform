from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.contracts.quality_contracts import (
    AgentOutput,
    PersistableOutput,
    QualityTraceEvent,
    ResultAggregate,
    StabilityAggregate,
    TaskAggregate,
    TokenUsageEvent,
)
from agent.router.contracts import AgentRouteDecision, AgentRouterOutput
from app.services.inspection_pipeline_service import (
    _build_manager_task_request,
    _normalize_image_urls_for_runtime,
)


def test_normalize_image_urls_for_runtime_keeps_remote_and_data_urls(monkeypatch):
    calls: list[str] = []

    class FakeStorageService:
        def to_data_url(self, url: str) -> str | None:
            calls.append(url)
            return None

    monkeypatch.setattr(
        "app.services.inspection_pipeline_service.FileStorageService",
        lambda: FakeStorageService(),
    )

    normalized = _normalize_image_urls_for_runtime(
        [
            "https://example.com/demo.png",
            "http://example.com/demo.png",
            "data:image/png;base64,abc123",
        ]
    )

    assert normalized == [
        "https://example.com/demo.png",
        "http://example.com/demo.png",
        "data:image/png;base64,abc123",
    ]
    assert calls == []


def test_normalize_image_urls_for_runtime_converts_local_upload_urls(monkeypatch):
    class FakeStorageService:
        def to_data_url(self, url: str) -> str | None:
            if url == "/uploads/chat_attachments/demo.png":
                return "data:image/png;base64,ZmFrZQ=="
            return None

    monkeypatch.setattr(
        "app.services.inspection_pipeline_service.FileStorageService",
        lambda: FakeStorageService(),
    )

    assert _normalize_image_urls_for_runtime(
        [
            "/uploads/chat_attachments/demo.png",
            "/uploads/chat_attachments/missing.png",
        ]
    ) == [
        "data:image/png;base64,ZmFrZQ==",
        "/uploads/chat_attachments/missing.png",
    ]


class PipelineTask:
    id = "task-1"
    org_id = "org-1"
    created_by = "user-1"
    product_id = "screw"
    spec_code = "SCREW-A-2026-V1"
    status = "pending"
    priority = 5
    image_urls = ["https://example.com/screw.png"]
    image_items = [
        {
            "id": "image-1",
            "name": "screw.png",
            "url": "https://example.com/screw.png",
        }
    ]
    meta_data = {
        "product_family": "screw",
        "selected_rag_space_id": "user-rag-1",
        "selected_rag_scope_node_ids": ["folder-1"],
        "structured_record": {"product_id": "screw"},
    }


def test_build_manager_request_uses_quality_task_contract_without_compat_flag():
    request = _build_manager_task_request(PipelineTask())

    assert request.workspace == "quality_task"
    assert request.ext["surface"] == "quality_task"
    assert request.ext["evidence_packet_required"] is True
    assert request.ext["rag_scope"]["rag_space_id"] == "user-rag-1"
    assert "use_inspection_task_graph_compat" not in request.ext


def test_build_manager_request_allows_explicit_rag_skip():
    task = PipelineTask()
    task.meta_data = {
        **PipelineTask.meta_data,
        "manager_skip_rag_evidence": True,
    }

    request = _build_manager_task_request(task)

    assert request.ext["manager_skip_rag_evidence"] is True
    assert request.ext["evidence_packet_required"] is False


class FakeSession:
    async def commit(self):
        return None


class FakeTaskRepo:
    def __init__(self, _session):
        self.task = PipelineTask()
        self.status_updates: list[str] = []

    async def get(self, org_id, task_id):
        assert (org_id, task_id) == ("org-1", "task-1")
        return self.task

    async def update_status(self, org_id, task_id, status):
        assert (org_id, task_id) == ("org-1", "task-1")
        self.status_updates.append(status)
        self.task.status = status
        return True

    async def patch_metadata(self, org_id, task_id, patch):
        assert (org_id, task_id) == ("org-1", "task-1")
        self.task.meta_data = {**self.task.meta_data, **patch}
        return True


class FakeUpsertRepo:
    def __init__(self, _session):
        self.saved_payload = None

    async def upsert_by_task(self, payload):
        self.saved_payload = dict(payload)
        return SimpleNamespace(**payload)


class FakeAlertRepo:
    def __init__(self, _session):
        self.created: list[dict] = []

    async def create(self, payload):
        self.created.append(dict(payload))
        return SimpleNamespace(**payload)


class FakeTokenRepo:
    def __init__(self, _session):
        self.created: list[dict] = []

    async def create(self, payload):
        self.created.append(dict(payload))
        return SimpleNamespace(**payload)


class FakeUsageRepo:
    def __init__(self, _session):
        self.calls: list[dict] = []

    async def increment(self, **kwargs):
        self.calls.append(dict(kwargs))


class FakeEventRepo:
    def __init__(self, _session):
        pass

    async def create(self, payload):
        return SimpleNamespace(**payload)


class FakeArtifactRepo:
    def __init__(self, _session):
        pass

    async def create_once(self, payload):
        return SimpleNamespace(**payload)


class FakeManager:
    def __init__(self):
        self.requests = []

    async def run(self, request, db_session=None):
        self.requests.append((request, db_session))
        output = AgentOutput(
            answer="正式质检完成",
            summary="真实证据链已完成分析",
            citations=[{"id": "rag-1", "quote": "不得存在裂纹"}],
            persistable_output=PersistableOutput(
                task=TaskAggregate(
                    id="task-1",
                    product_id="screw",
                    spec_code="SCREW-A-2026-V1",
                    status="done",
                    priority=5,
                    image_count=1,
                ),
                result=ResultAggregate(
                    id="result-1",
                    task_id="task-1",
                    verdict="pass",
                    overall_score=0.96,
                    llm_model="quality-model",
                    citations={"items": [{"id": "rag-1"}]},
                    reasoning_chain={
                        "standard_evaluation": {"verdict": "pass"},
                        "consumed_artifact_ids": ["evidence-1", "vision-1"],
                    },
                ),
                stability=StabilityAggregate(
                    risk_score=0.04,
                    risk_level="low",
                    evidence_score=0.95,
                    confidence_score=0.96,
                    traceability_score=0.95,
                    faithfulness_score=0.97,
                    physical_hallucination_score=0.01,
                ),
                token_usage=[
                    TokenUsageEvent(
                        model_key="quality-model",
                        prompt_tokens=10,
                        completion_tokens=5,
                        total_tokens=15,
                        trace_id="trace-1",
                    )
                ],
                quality_trace=QualityTraceEvent(
                    trace_id="trace-1",
                    workflow_version="quality_analysis_v1",
                    prompt_version="quality_analysis_v1",
                    route_subgraph="quality_analysis",
                ),
            ),
            raw_state={
                "request_id": request.request_id,
                "response_payload": {
                    "route_trace": {
                        "observations": [
                            {
                                "capability_key": "evidence.arbitrate",
                                "owner_agent": "orchestrator",
                                "status": "success",
                                "summary": "证据检索完成",
                                "artifact_ids": ["evidence-1"],
                            },
                            {
                                "capability_key": "quality.inspection.execute",
                                "owner_agent": "quality_analysis",
                                "status": "success",
                                "summary": "质量分析完成",
                                "artifact_ids": ["result-1"],
                            },
                        ]
                    },
                    "artifacts": [],
                },
            },
        )
        return AgentRouterOutput(
            route_decision=AgentRouteDecision(
                selected_agent="quality_analysis",
                sub_route="inspection_execute",
                intent="inspection_execute",
                reason="formal quality task",
                route_source="manager",
            ),
            agent_output=output.model_dump(mode="json"),
            status="completed",
        )


@pytest.mark.asyncio
async def test_run_inspection_pipeline_uses_manager_quality_analysis_contract(monkeypatch):
    from app.services import inspection_pipeline_service as pipeline

    session = FakeSession()
    task_repo = FakeTaskRepo(session)
    result_repo = FakeUpsertRepo(session)
    stability_repo = FakeUpsertRepo(session)
    manager = FakeManager()

    @asynccontextmanager
    async def fake_get_session():
        yield session

    monkeypatch.setattr(pipeline, "get_session", fake_get_session)
    monkeypatch.setattr(pipeline, "TaskRepository", lambda _session: task_repo)
    monkeypatch.setattr(pipeline, "ResultRepository", lambda _session: result_repo)
    monkeypatch.setattr(pipeline, "StabilityRepository", lambda _session: stability_repo)
    monkeypatch.setattr(pipeline, "AlertRepository", FakeAlertRepo)
    monkeypatch.setattr(pipeline, "TokenLedgerRepository", FakeTokenRepo)
    monkeypatch.setattr(pipeline, "UserTokenUsageSummaryRepository", FakeUsageRepo)
    monkeypatch.setattr(pipeline, "TaskExecutionEventRepository", FakeEventRepo)
    monkeypatch.setattr(pipeline, "get_agent_manager", lambda: manager)
    monkeypatch.setattr(
        "app.repositories.agent_artifact_repo.AgentArtifactRepository",
        FakeArtifactRepo,
    )

    result = await pipeline.run_inspection_pipeline("task-1", "org-1")

    assert result == {"task_id": "task-1", "status": "done"}
    assert task_repo.status_updates == ["running", "done"]
    assert len(manager.requests) == 1
    manager_request, manager_session = manager.requests[0]
    assert manager_session is session
    assert manager_request.ext["surface"] == "quality_task"
    assert result_repo.saved_payload["verdict"] == "pass"
    assert result_repo.saved_payload["latency_ms"] >= 1
    assert result_repo.saved_payload["reasoning_chain"]["consumed_artifact_ids"] == [
        "evidence-1",
        "vision-1",
    ]
    assert stability_repo.saved_payload["risk_level"] == "low"
