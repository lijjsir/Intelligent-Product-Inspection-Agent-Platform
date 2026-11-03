"""Build a leakage-safe image manifest for QDL-selected AnomalyGPT training."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


NORMAL_VALUES = {"no", "false", "0", "n", "否", "无", "normal", "good"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def _is_normal(row: Mapping[str, Any]) -> bool:
    truth = row.get("ground_truth") or row.get("image_structured") or {}
    if isinstance(truth, Mapping):
        value = truth.get("has_defect")
        if value is not None and str(value).strip().casefold() in NORMAL_VALUES:
            return True
        if value is not None:
            return False
    defect_type = str(row.get("defect_type", "")).strip().casefold()
    if defect_type in NORMAL_VALUES:
        return True
    raise ValueError(
        f"sample {row.get('id', '<unknown>')} has no explicit normal label; "
        "AnomalyGPT's unsupervised source stream must contain normal images only"
    )


def _image_path(row: Mapping[str, Any], image_root: Path) -> Path:
    value = row.get("image")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"sample {row.get('id', '<unknown>')} has no image path")

    source_split = str(row.get("source_split", "")).strip().casefold()
    if "test" in source_split:
        raise ValueError(
            f"sample {row.get('id', '<unknown>')} came from source_split={source_split!r}"
        )

    root = image_root.expanduser().resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        image = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"training image does not exist: {candidate}") from exc
    try:
        image.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"training image is outside --image-root: {image}") from exc
    if "test" in {part.casefold() for part in image.parts}:
        raise ValueError(f"training manifest cannot include a test image: {image}")
    if not image.is_file():
        raise ValueError(f"training image is not a file: {image}")
    return image


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    truth = row.get("ground_truth") or row.get("image_structured") or {}
    label = str(truth.get("has_defect", "unknown")).strip().casefold() if isinstance(truth, Mapping) else "unknown"
    return str(row.get("category", "unknown")), label


def _random_matched(train_rows: list[dict[str, Any]],
                    high_rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    quotas = Counter(_key(row) for row in high_rows)
    high_images = {str(row["_resolved_image"]) for row in high_rows}
    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in train_rows:
        if str(row["_resolved_image"]) not in high_images and row.get("qdl_bucket") != "high":
            pools[_key(row)].append(row)

    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for key, count in sorted(quotas.items()):
        candidates = pools.get(key, [])
        if len(candidates) < count:
            raise ValueError(
                f"not enough non-high random controls for category/label {key}: "
                f"{len(candidates)} < {count}"
            )
        selected.extend(rng.sample(candidates, count))
    rng.shuffle(selected)
    return selected


def build_manifest(audit_jsonl: Path, image_root: Path, output: Path,
                   mode: str, seed: int = 42) -> dict[str, Any]:
    rows = _read_jsonl(audit_jsonl)
    train_rows: list[dict[str, Any]] = []
    seen_images: set[str] = set()
    for row in rows:
        if str(row.get("split", "")).strip().casefold() != "train":
            continue
        if not _is_normal(row):
            raise ValueError(
                f"sample {row.get('id', '<unknown>')} is anomalous; "
                "use only normal official training images for this AnomalyGPT stream"
            )
        image = _image_path(row, image_root)
        key = image.as_posix().casefold()
        if key in seen_images:
            raise ValueError(f"duplicate training image in QDL audit: {image}")
        seen_images.add(key)
        train_rows.append({**row, "_resolved_image": image.as_posix()})

    if not train_rows:
        raise ValueError("QDL audit contains no eligible split=train normal images")

    if mode == "all_train":
        selected = train_rows
    elif mode == "qdl_high":
        selected = [row for row in train_rows if row.get("qdl_bucket") == "high"]
        if not selected:
            raise ValueError("QDL audit contains no qdl_bucket=high normal training images")
    else:
        high_rows = [row for row in train_rows if row.get("qdl_bucket") == "high"]
        if not high_rows:
            raise ValueError("QDL audit contains no qdl_bucket=high normal training images")
        selected = _random_matched(train_rows, high_rows, seed)

    selected_images = [str(row["_resolved_image"]) for row in selected]
    categories = Counter(str(row.get("category", "unknown")) for row in selected)
    manifest = {
        "schema": "anomalygpt_qdl_train_image_manifest_v1",
        "mode": mode,
        "seed": seed,
        "source_qdl_audit": str(audit_jsonl.resolve()),
        "image_root": str(image_root.resolve()),
        "source_policy": "split=train and explicitly normal; test paths rejected",
        "selected_count": len(selected_images),
        "category_counts": dict(sorted(categories.items())),
        "selected_images": selected_images,
        "qdl_edge_counts": {
            "candidate": sum(int(row.get("candidate_edge_count", 0) or 0) for row in selected),
            "accepted": sum(
                len((row.get("qdl_result") or {}).get("accepted_edges", []))
                for row in selected
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdl-audit-jsonl", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("all_train", "qdl_high", "random_matched"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(
        build_manifest(args.qdl_audit_jsonl, args.image_root, args.output, args.mode, args.seed),
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
