from __future__ import annotations


class ModelPricing:
    # Unit: CNY per 1M tokens. Keep this table explicit and easy to update.
    PRICE_TABLE = {
        "ep-20260310154131-fp54f": {"input_per_million": 2.0, "output_per_million": 8.0},
        "ep-20260311135919-gktlx": {"input_per_million": 0.7, "output_per_million": 0.0},
        "doubao-embedding-vision-251215": {"input_per_million": 0.7, "output_per_million": 0.0},
        # USD pricing from DeepSeek official API pricing. Keep CNY-denominated
        # custom provider prices in model_configs when available.
        "deepseek-v4-flash": {"input_per_million": 0.14, "output_per_million": 0.28},
    }

    @classmethod
    def estimate_cost(
        cls,
        model_key: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
    ) -> float:
        pricing = cls.PRICE_TABLE.get(str(model_key or ""), {"input_per_million": 0.0, "output_per_million": 0.0})
        input_price = input_price_per_million if input_price_per_million is not None else pricing.get("input_per_million")
        output_price = output_price_per_million if output_price_per_million is not None else pricing.get("output_per_million")

        input_cost = (max(prompt_tokens, 0) / 1_000_000) * float(input_price or 0.0)
        output_cost = (max(completion_tokens, 0) / 1_000_000) * float(output_price or 0.0)
        return round(input_cost + output_cost, 6)
