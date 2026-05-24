from app.services.inspection_pipeline_service import _normalize_image_urls_for_runtime
from pathlib import Path
from types import SimpleNamespace

import pytest


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
    calls: list[str] = []

    class FakeStorageService:
        def to_data_url(self, url: str) -> str | None:
            calls.append(url)
            if url == "/uploads/chat_attachments/demo.png":
                return "data:image/png;base64,ZmFrZQ=="
            return None

    monkeypatch.setattr(
        "app.services.inspection_pipeline_service.FileStorageService",
        lambda: FakeStorageService(),
    )

    normalized = _normalize_image_urls_for_runtime(
        [
            "/uploads/chat_attachments/demo.png",
            "/uploads/chat_attachments/missing.png",
        ]
    )

    assert normalized == [
        "data:image/png;base64,ZmFrZQ==",
        "/uploads/chat_attachments/missing.png",
    ]
    assert calls == [
        "/uploads/chat_attachments/demo.png",
        "/uploads/chat_attachments/missing.png",
    ]


def test_normalize_image_urls_for_runtime_converts_api_file_urls(monkeypatch):
    calls: list[str] = []

    class FakeStorageService:
        def to_data_url(self, url: str) -> str | None:
            calls.append(url)
            if url == "/api/v1/files/chat-attachments/chat_attachments/demo.png":
                return "data:image/png;base64,ZmFrZQ=="
            return None

    monkeypatch.setattr(
        "app.services.inspection_pipeline_service.FileStorageService",
        lambda: FakeStorageService(),
    )

    normalized = _normalize_image_urls_for_runtime(
        [
            "/api/v1/files/chat-attachments/chat_attachments/demo.png",
        ]
    )

    assert normalized == [
        "data:image/png;base64,ZmFrZQ==",
    ]
    assert calls == [
        "/api/v1/files/chat-attachments/chat_attachments/demo.png",
    ]


class _PipelineTask:
    def __init__(self):
        image_path = Path(__file__).parents[2] / "test_data" / "test_image.png"
        self.id = "task-1"
        self.org_id = "org-1"
        self.created_by = "user-1"
        self.product_id = "screw"
        self.spec_code = "SCREW-A-2026-V1"
        self.status = "pending"
        self.priority = 5
        self.image_urls = [str(image_path)]
        self.image_items = [{"index": 0, "url": self.image_urls[0], "hash": "img-hash-1"}]
        self.meta_data = {
            "product_family": "screw",
            "selected_rag_space_id": "user-rag-1",
            "selected_rag_space_name": "用户知识库",
            "selected_rag_scope_node_ids": ["folder-1"],
            "selected_rag_space": {"id": "user-rag-1", "name": "用户知识库"},
            "structured_record": {
                "product_id": "screw",
                "spec_code": "SCREW-A-2026-V1",
                "inspection_type": "appearance",
                "surface_condition": "clean",
                "crack_count": 0,
                "surface_scratch_count": 0,
                "coating_defect_count": 0,
                "thread_damage_count": 0,
                "oil_stain_count": 0,
                "expected_decision": "PASS",
            },
        }


class _FakeSession:
    async def commit(self):
        return None

    async def flush(self):
        return None

    async def refresh(self, _obj, attribute_names=None):
        return None


class _FakeTaskRepo:
    def __init__(self, _session):
        self.task = _PipelineTask()
        self.metadata_patches: list[dict] = []
        self.status_updates: list[str] = []

    async def get(self, org_id, task_id):
        assert org_id == "org-1"
        assert task_id == "task-1"
        return self.task

    async def update_status(self, org_id, task_id, status):
        assert org_id == "org-1"
        assert task_id == "task-1"
        self.status_updates.append(status)
        self.task.status = status
        return True

    async def patch_metadata(self, org_id, task_id, patch):
        assert org_id == "org-1"
        assert task_id == "task-1"
        self.metadata_patches.append(dict(patch))
        self.task.meta_data = {**dict(self.task.meta_data or {}), **patch}
        return True


class _FakeResultRepo:
    def __init__(self, _session):
        self.saved_payload = None

    async def upsert_by_task(self, payload):
        self.saved_payload = dict(payload)
        return SimpleNamespace(**payload)


class _FakeStabilityRepo:
    def __init__(self, _session):
        self.saved_payload = None

    async def upsert_by_task(self, payload):
        self.saved_payload = dict(payload)
        return SimpleNamespace(**payload)


class _FakeAlertRepo:
    def __init__(self, _session):
        self.created = []

    async def create(self, payload):
        self.created.append(dict(payload))
        return SimpleNamespace(**payload)


class _FakeTokenLedgerRepo:
    def __init__(self, _session):
        self.created = []

    async def create(self, payload):
        self.created.append(dict(payload))
        return SimpleNamespace(**payload)


class _FakeUserTokenUsageRepo:
    def __init__(self, _session):
        self.calls = []

    async def increment(self, **kwargs):
        self.calls.append(dict(kwargs))
        return None


class _FakeModelConfigService:
    def __init__(self, _session, org_id):
        self.org_id = org_id

    async def list_runtime_models(self):
        return [
            {
                "model_key": "test-model",
                "id": "cfg-1",
                "provider": "openai",
                "endpoint": "https://example.com",
                "api_key": "sk-test",
            }
        ]


class _FakeGateway:
    async def select_runtime(self, _models, excluded_runtime_ids=None):
        return {
            "model_id": "test-model",
            "model_config_id": "cfg-1",
            "provider": "openai",
            "base_url": "https://example.com",
            "api_key": "sk-test",
            "input_price_per_million": None,
            "output_price_per_million": None,
        }

    async def has_available_runtime(self, _models, excluded_runtime_ids=None):
        return False


class _FakeTrace:
    def start_trace(self, **kwargs):
        return {"trace_id": "trace-1", "trace_url": "https://trace.local/1"}


class _FakeEventRepo:
    def __init__(self, _session):
        self.items = []

    async def create(self, payload):
        self.items.append(dict(payload))
        return SimpleNamespace(**payload)


class _FakeRagAnalysisRepo:
    logs: list[dict] = []

    def __init__(self, _session, org_id):
        self.org_id = org_id

    async def create_log_once(self, payload):
        self.logs.append(dict(payload))
        return SimpleNamespace(**payload)


class _FakeInspectionSpecRepo:
    def __init__(self, _session):
        self.spec = SimpleNamespace(
            id="spec-1",
            spec_code="SCREW-A-2026-V1",
            name="螺丝测试标准",
            version="v-test",
            product_id="screw",
            product_family="screw",
            applicable_skus=[],
            required_views=[],
            effective_from=None,
            effective_to=None,
            required_image_count=1,
            aggregation_rules={},
            ai_gate_rules={},
            manual_review_policies={},
            auto_pass_enabled=True,
            ai_gate_confidence_threshold=0.72,
            ai_gate_evidence_threshold=0.5,
            ai_gate_traceability_threshold=0.5,
        )

    async def get_active_spec(self, org_id: str, spec_code: str):
        assert org_id == "org-1"
        return self.spec if spec_code == "SCREW-A-2026-V1" else None

    async def list_items(self, spec_id: str):
        assert spec_id == "spec-1"
        return []


@pytest.mark.asyncio
async def test_run_inspection_pipeline_merges_user_and_system_rag_and_passes_gate(monkeypatch):
    from contextlib import asynccontextmanager
    from app.services import inspection_pipeline_service as pipeline_mod

    image_path = Path(__file__).parents[2] / "test_data" / "test_image.png"
    assert image_path.exists()

    task_repo = _FakeTaskRepo(None)
    result_repo = _FakeResultRepo(None)
    stability_repo = _FakeStabilityRepo(None)
    alert_repo = _FakeAlertRepo(None)
    token_repo = _FakeTokenLedgerRepo(None)
    user_token_repo = _FakeUserTokenUsageRepo(None)
    _FakeRagAnalysisRepo.logs = []

    @asynccontextmanager
    async def fake_get_session():
        yield _FakeSession()

    async def fake_resolve_and_search_system_rag(**kwargs):
        assert kwargs["product_family"] == "screw"
        assert kwargs["product_id"] == "screw"
        assert kwargs["spec_code"] == "SCREW-A-2026-V1"
        assert kwargs["user_rag_space_id"] == "user-rag-1"
        assert kwargs["scope_node_ids"] == ["folder-1"]
        return {
            "rag_space_id": "system-rag-1",
            "rag_space_name": "系统标准库",
            "rag_space_ids": ["user-rag-1", "system-rag-1"],
            "rag_space_names": ["用户知识库", "系统标准库"],
            "hits": [
                {
                    "id": "hit-1",
                    "title": "批次外观说明",
                    "source": "用户知识库/批次说明",
                    "full_path": "用户知识库/批次说明",
                    "quote": "该批次螺丝外观清洁，无裂纹、无划伤、无涂层缺陷。",
                    "score": 0.95,
                    "document_id": "doc-user-1",
                    "chunk_index": 1,
                    "rag_space_id": "user-rag-1",
                    "rag_space_name": "用户知识库",
                },
                {
                    "id": "hit-2",
                    "title": "螺丝国标",
                    "source": "系统标准库/螺丝国标",
                    "full_path": "系统标准库/螺丝国标",
                    "quote": "螺丝外观检验要求：不得存在裂纹、划伤、涂层脱落、牙纹损伤、油污。",
                    "score": 0.93,
                    "document_id": "doc-system-1",
                    "chunk_index": 1,
                    "rag_space_id": "system-rag-1",
                    "rag_space_name": "系统标准库",
                },
            ],
            "hit_count": 2,
            "latency_ms": 8.5,
            "source_count": 2,
            "candidate_count": 3,
            "rejected_count": 1,
            "score_threshold": 0.55,
            "system_rag_space_ids": ["system-rag-1"],
            "system_rag_space_names": ["系统标准库"],
            "standard_binding_name": "螺丝国家标准",
            "merged_rag_source_count": 2,
        }

    async def fake_analyze(payload):
        assert len(payload["citations"]) >= 2
        return {
            "evidence_score": 0.95,
            "consistency_score": 0.94,
            "confidence_score": 0.97,
            "traceability_score": 0.96,
            "anomaly_score": 0.05,
            "risk_score": 0.08,
            "risk_score_100": 8.0,
            "risk_level": "low",
            "dimension_detail": {},
        }

    monkeypatch.setattr(pipeline_mod, "get_session", fake_get_session)
    monkeypatch.setattr(pipeline_mod, "TaskRepository", lambda session: task_repo)
    monkeypatch.setattr(pipeline_mod, "ResultRepository", lambda session: result_repo)
    monkeypatch.setattr(pipeline_mod, "StabilityRepository", lambda session: stability_repo)
    monkeypatch.setattr(pipeline_mod, "AlertRepository", lambda session: alert_repo)
    monkeypatch.setattr(pipeline_mod, "TokenLedgerRepository", lambda session: token_repo)
    monkeypatch.setattr(pipeline_mod, "UserTokenUsageSummaryRepository", lambda session: user_token_repo)
    monkeypatch.setattr(pipeline_mod, "ModelConfigService", _FakeModelConfigService)
    monkeypatch.setattr(pipeline_mod, "LLMGateway", lambda: _FakeGateway())
    monkeypatch.setattr(pipeline_mod, "LangfuseTracer", lambda: _FakeTrace())
    monkeypatch.setattr(pipeline_mod, "TaskExecutionEventRepository", _FakeEventRepo)
    monkeypatch.setattr(pipeline_mod, "RagAnalysisRepository", _FakeRagAnalysisRepo)
    monkeypatch.setattr(pipeline_mod, "analyze", fake_analyze)
    monkeypatch.setattr(pipeline_mod, "should_trigger", lambda _stability: False)
    monkeypatch.setattr("app.services.inspection_standard_service.InspectionSpecRepository", _FakeInspectionSpecRepo)

    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.nodes.knowledge.resolve_and_search_system_rag",
        fake_resolve_and_search_system_rag,
    )
    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.nodes.vision.VisionDetectorClient",
        lambda: SimpleNamespace(enabled=False),
    )

    async def fake_chat(self, messages, temperature=0.1, observation_name=None, observation_metadata=None):
        if observation_name == "inspection.vision":
            return {"defects": [], "image_summary": "螺丝外观完整，无可见异常。"}
        if observation_name == "inspection.reasoning":
            return {
                "verdict": "pass",
                "overall_score": 0.98,
                "reasoning_chain": {"llm_reason": "视觉与标准证据均支持通过。"},
                "__meta__": {
                    "model": "test-model",
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 30,
                        "total_tokens": 150,
                    },
                },
            }
        raise AssertionError(f"unexpected llm observation {observation_name}")

    monkeypatch.setattr("agent.subgraphs.inspection_task.nodes.vision.LLMClient.chat", fake_chat)

    result = await pipeline_mod.run_inspection_pipeline("task-1", "org-1")

    assert result == {"task_id": "task-1", "status": "done"}
    assert task_repo.status_updates == ["running", "done"]
    assert result_repo.saved_payload is not None
    assert result_repo.saved_payload["verdict"] == "pass"
    assert result_repo.saved_payload["latency_ms"] > 0
    reasoning_chain = result_repo.saved_payload["reasoning_chain"]
    assert reasoning_chain["trace"]["trust_score"] is not None
    assert reasoning_chain["trace"]["hallucination_risk"] is not None
    assert reasoning_chain["trace"]["overconfidence"] is not None
    assert reasoning_chain["trace"]["has_citation"] is True
    assert reasoning_chain["standard_evaluation"]["verdict"] == "pass"
    assert reasoning_chain["rag_summary"]["system_rag_space_ids"] == ["system-rag-1"]
    assert reasoning_chain["rag_summary"]["standard_binding_name"] == "螺丝国家标准"
    assert reasoning_chain["rag_summary"]["merged_rag_source_count"] == 2
    assert set(reasoning_chain["rag_summary"]["rag_space_ids"]) == {"user-rag-1", "system-rag-1"}
    assert reasoning_chain["structured_record"]["expected_decision"] == "PASS"
    citations = result_repo.saved_payload["citations"]["items"]
    assert len(citations) >= 2
    assert stability_repo.saved_payload is not None
    assert stability_repo.saved_payload["risk_level"] == "low"
    assert len(_FakeRagAnalysisRepo.logs) == 1
    rag_log = _FakeRagAnalysisRepo.logs[0]
    assert rag_log["task_id"] == "task-1"
    assert rag_log["source_graph"] == "inspection_task"
    assert rag_log["sub_route"] == "task_execution"
    assert rag_log["hit_count"] == 2
    assert rag_log["top_score"] == 0.95
    assert rag_log["metadata_json"]["candidate_count"] == 3
    assert rag_log["metadata_json"]["rejected_count"] == 1
    assert rag_log["metadata_json"]["evidence_used"] is True
