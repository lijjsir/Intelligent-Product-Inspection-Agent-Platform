"""Dependency-light loading and validation for QDL training image manifests."""

from __future__ import annotations

import json
from pathlib import Path


MANIFEST_SCHEMA = "anomalygpt_qdl_train_image_manifest_v1"


def image_key(path: str | Path) -> str:
    return Path(path).expanduser().resolve().as_posix().casefold()


def load_qdl_image_manifest(path: str | None) -> set[str] | None:
    if not path:
        return None
    manifest_path = Path(path).expanduser()
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported QDL image manifest schema: {manifest_path}")
    values = manifest.get("selected_images")
    if not isinstance(values, list) or not values:
        raise ValueError(f"QDL image manifest has no selected_images: {manifest_path}")
    selected = {
        image_key(value)
        for value in values
        if isinstance(value, str) and value.strip()
    }
    if len(selected) != len(values):
        raise ValueError(f"QDL image manifest has invalid or duplicate paths: {manifest_path}")
    return selected


def validate_manifest_coverage(selected: set[str] | None, matched: set[str],
                               dataset_name: str) -> None:
    if selected is None:
        return
    missing = selected - matched
    if missing:
        examples = ", ".join(sorted(missing)[:3])
        raise ValueError(
            f"{len(missing)} QDL manifest images are not eligible {dataset_name} training "
            f"images; examples: {examples}"
        )
