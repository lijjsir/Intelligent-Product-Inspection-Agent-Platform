from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from agent.subgraphs.lab_detection import nodes as lab_nodes
from agent.subgraphs.lab_detection import LabDetectionGraph


def _install_offline_runtime() -> None:
    @asynccontextmanager
    async def fake_get_session():
        yield object()

    class FakeModelConfigService:
        def __init__(self, session: object, org_id: str) -> None:
            self.org_id = org_id

        async def list_runtime_models(self, model_type: str | None = None) -> list[dict[str, Any]]:
            return [{"model_key": "offline-lab-detection-demo", "provider": "offline"}]

    class FakeGateway:
        async def select_runtime(self, models: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any] | None:
            return {
                "model_id": "offline-lab-detection-demo",
                "base_url": "offline://lab-detection",
                "api_key": "offline",
                "provider": "offline",
            }

    class FakeLLMClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
            return {
                "assessment_state": "early_abnormal",
                "abnormal_probability": 0.76,
                "risk_level": "high",
                "early_warning": True,
                "can_make_final_verdict": False,
                "suggested_action": "priority_followup_test",
                "next_test_priority": [
                    {
                        "item": "microbiology",
                        "priority": "high",
                        "reason": "Moisture is already above limit; microbiology should be prioritized before any final conclusion.",
                    }
                ],
                "explanation": "Partial laboratory data already shows early abnormal signals, but this is not a final quality verdict.",
                "requires_manual_review": True,
                "confidence": 0.74,
            }

    lab_nodes.get_session = fake_get_session
    lab_nodes.ModelConfigService = FakeModelConfigService
    lab_nodes.LLMGateway = lambda: FakeGateway()
    lab_nodes.LLMClient = FakeLLMClient


async def main(*, real_runtime: bool) -> None:
    if not real_runtime:
        _install_offline_runtime()

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "dev-lab-001",
            "workflow_run_id": "dev-lab-001",
            "session_id": "dev-session",
            "org_id": "00000000-0000-0000-0000-000000000001",
            "user_id": "dev-user",
            "input_context": {
                "sample_id": "SAMPLE-001",
                "product_id": "FOOD-001",
                "product_family": "food",
                "spec_code": "GB-XXX",
                "test_plan": {
                    "total_items": 6,
                    "completed_items": 2,
                    "pending_items": [
                        "microbiology",
                        "heavy_metal",
                        "stability_observation",
                    ],
                    "critical_items": ["microbiology"],
                },
                "partial_measurements": [
                    {
                        "item": "moisture",
                        "value": 18.6,
                        "unit": "%",
                        "normal_range": "10-15",
                        "standard_limit": "<=15",
                    },
                    {
                        "item": "pH",
                        "value": 4.1,
                        "unit": "",
                        "normal_range": "5.5-7.0",
                        "standard_limit": "5.0-8.0",
                    },
                ],
                "historical_baseline": {
                    "similar_samples_count": 230,
                    "normal_response_pattern": "Similar samples usually keep moisture at 11%-14%.",
                    "abnormal_patterns": [
                        "Early high moisture may correlate with storage or package-sealing issues."
                    ],
                },
            },
        }
    )
    print(json.dumps(result.get("assessment"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the standalone LabDetectionGraph.")
    parser.add_argument(
        "--real-runtime",
        action="store_true",
        help="Use configured database/model runtime instead of the offline demo runtime.",
    )
    args = parser.parse_args()
    asyncio.run(main(real_runtime=args.real_runtime))
