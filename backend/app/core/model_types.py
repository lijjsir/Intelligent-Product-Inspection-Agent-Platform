from __future__ import annotations


def normalize_model_type(value: str) -> str:
    name = str(value or "").strip().lower()
    return {
        "vision": "multimodal",
        "vlm": "multimodal",
        "llm": "chat",
        "text_generation": "chat",
        "embed": "embedding",
        "text_embedding": "embedding",
    }.get(name, name)
