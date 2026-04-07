from types import SimpleNamespace

import pytest

from app.services.inspection_pipeline_service import _record_token_usage


class FakeTokenLedgerRepo:
    def __init__(self):
        self.payloads = []

    async def create(self, payload):
        self.payloads.append(payload)
        return payload


class FakeUserTokenSummaryRepo:
    def __init__(self):
        self.calls = []

    async def increment(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_record_token_usage_persists_ledger_and_user_summary():
    token_repo = FakeTokenLedgerRepo()
    user_summary_repo = FakeUserTokenSummaryRepo()
    task = SimpleNamespace(
        id="task-1",
        org_id="org-1",
        created_by="user-1",
        product_id="P-1001",
    )
    state = {
        "model_id": "model-a",
        "model_config_id": "config-1",
        "trace_id": "trace-1",
        "model_input_price_per_million": 1.0,
        "model_output_price_per_million": 2.0,
    }

    total_tokens = await _record_token_usage(
        token_ledger_repo=token_repo,
        user_token_usage_repo=user_summary_repo,
        task=task,
        result_id="result-1",
        state=state,
        usage_events=[
            {"prompt_tokens": 100, "completion_tokens": 50, "model_key": "model-a"},
            {"prompt_tokens": 0, "completion_tokens": 0, "model_key": "model-a"},
        ],
    )

    assert total_tokens == 150
    assert token_repo.payloads[0]["user_id"] == "user-1"
    assert token_repo.payloads[0]["total_tokens"] == 150
    assert user_summary_repo.calls[0]["user_id"] == "user-1"
    assert user_summary_repo.calls[0]["total_tokens"] == 150
