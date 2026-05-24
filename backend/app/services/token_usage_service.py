from __future__ import annotations

from typing import Any

from app.core.ids import uuid7
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from agent.llm.pricing import ModelPricing


async def record_embedding_usage(
    *,
    token_ledger_repo: TokenLedgerRepository,
    user_token_usage_repo: UserTokenUsageSummaryRepository | None = None,
    org_id: str,
    user_id: str | None = None,
    usage_events: list[dict[str, Any]],
    trace_id: str | None = None,
    task_id: str | None = None,
    result_id: str | None = None,
    model_config_id: str | None = None,
    product_line: str | None = None,
    input_price_per_million: float | None = None,
    output_price_per_million: float | None = None,
) -> int:
    total_tokens = 0
    for event in usage_events:
        prompt_tokens = int(event.get("prompt_tokens") or 0)
        completion_tokens = int(event.get("completion_tokens") or 0)
        event_total = int(event.get("total_tokens") or (prompt_tokens + completion_tokens))
        if event_total <= 0:
            continue

        total_tokens += event_total
        model_key = str(event.get("model_key") or "unknown")

        cost_amount = ModelPricing.estimate_cost(
            model_key,
            prompt_tokens,
            completion_tokens,
            input_price_per_million=input_price_per_million,
            output_price_per_million=output_price_per_million,
        )

        response_id = event.get("response_id")
        idempotency_key = f"embed:{response_id}" if response_id else None

        payload = {
            "id": str(uuid7()),
            "org_id": org_id,
            "user_id": user_id,
            "task_id": task_id,
            "result_id": result_id,
            "model_config_id": model_config_id,
            "model_key": model_key,
            "product_line": product_line,
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": event_total,
            "cost_amount": cost_amount,
        }

        if idempotency_key:
            await token_ledger_repo.create_once(payload)
        else:
            await token_ledger_repo.create(payload)

        if user_token_usage_repo and user_id:
            await user_token_usage_repo.increment(
                org_id=org_id,
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=event_total,
                cost_amount=cost_amount,
            )

    return total_tokens
