from __future__ import annotations

from typing import Iterable

from app.core.exceptions import ValidationError


DATASET_MODALITY_ORDER = ("image", "video", "text")
DATASET_MODALITY_SET = set(DATASET_MODALITY_ORDER)
LEGACY_DATASET_MODALITY_ALIASES = {
    "image_text": ("image", "text"),
}


def parse_dataset_modalities(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ()
        if raw in LEGACY_DATASET_MODALITY_ALIASES:
            tokens = LEGACY_DATASET_MODALITY_ALIASES[raw]
        else:
            normalized = raw.replace(",", "+").replace("|", "+").replace("/", "+").replace(" ", "+")
            tokens = tuple(part.strip().lower() for part in normalized.split("+") if part.strip())
    else:
        tokens = tuple(str(part).strip().lower() for part in value if str(part).strip())
    unique_tokens = {token for token in tokens if token}
    invalid = sorted(unique_tokens - DATASET_MODALITY_SET)
    if invalid:
        raise ValidationError(f"unsupported dataset modality: {', '.join(invalid)}")
    return tuple(token for token in DATASET_MODALITY_ORDER if token in unique_tokens)


def normalize_dataset_modality(value: str | Iterable[str] | None) -> str:
    tokens = parse_dataset_modalities(value)
    if not tokens:
        raise ValidationError("dataset modality cannot be empty")
    return "+".join(tokens)


def dataset_supports_sample_type(modality: str | Iterable[str] | None, sample_type: str) -> bool:
    sample = str(sample_type or "").strip().lower()
    if sample not in DATASET_MODALITY_SET:
        return False
    return sample in parse_dataset_modalities(modality)
