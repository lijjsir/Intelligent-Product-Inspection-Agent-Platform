"""Build input JSONL for the QDL audit and data-selection pipeline.

The builder reads only MVTec ``train/good`` images and splits that source into
QDL train/validation/test. Qwen image structuring is optional at the CLI;
deterministic normal fields are used when it is disabled.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

from PIL import Image


CATEGORIES = [
    "bottle", "cable", "capsule", "carpet", "grid", "hazelnut", "leather",
    "metal_nut", "pill", "screw", "tile", "toothbrush", "transistor", "wood", "zipper",
]

def _resolve_pipeline_dir(explicit_dir: Path | None = None) -> Path:
    """Find the directory containing the existing VLM runtime modules."""
    script_dir = Path(__file__).resolve().parent
    candidates = [
        explicit_dir,
        Path(os.environ["QDL_PIPELINE_DIR"]) if os.environ.get("QDL_PIPELINE_DIR") else None,
        script_dir,
        Path("/kaggle/working/test-code"),
        Path("/kaggle/working"),
    ]
    required = ("models.py", "utils.py", "structured_generation_module.py")
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        candidate = candidate.expanduser().resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if all((candidate / filename).is_file() for filename in required):
            return candidate
    searched = "\n".join(f"  - {path}" for path in seen)
    raise FileNotFoundError(
        "找不到现有 VLM 运行模块。请将模型运行模块（至少包含 "
        "models.py、utils.py、structured_generation_module.py 及其依赖）放到可访问位置，"
        "并通过 --pipeline-dir 指向该目录；或设置环境变量 QDL_PIPELINE_DIR。\n"
        f"已检查：\n{searched}"
    )


def _normal_structured() -> dict[str, Any]:
    return {
        "has_defect": "No",
        "risk_type": "none",
        "severity": "none",
        "defect_category": "none",
        "location_hint": "",
        "evidence_summary": "表面完好无明显异常",
        "confidence": 0.90,
        "bbox": [0, 0, 0, 0],
        "mapping_source": "mvtec_label",
    }


def _template_text(category: str, image_structured: dict[str, Any]) -> dict[str, Any]:
    return {"has_defect": image_structured["has_defect"], "risk_type": image_structured["risk_type"], "severity": image_structured["severity"], "defect_category": image_structured["defect_category"], "location_hint": image_structured.get("location_hint", f"{category}区域"), "evidence_summary": image_structured.get("evidence_summary", ""), "confidence": image_structured.get("confidence", 0.8), "bbox": image_structured.get("bbox", [0, 0, 0, 0]), "mapping_source": "mvtec_template"}


def _template_text_candidates(category: str, image_structured: dict[str, Any],
                              count: int = 4) -> list[dict[str, Any]]:
    """Create deterministic, semantically equivalent text-side candidates.

    The candidates intentionally vary the natural-language evidence and
    location wording while keeping the structured label, severity and bbox
    stable.  They are separate text nodes for the downstream matcher, not
    multiple copies of one field inside a single node.
    """
    count = max(1, int(count))
    base = _template_text(category, image_structured)
    summaries = [
        "图像整体正常，未见明显缺陷",
        "产品表面完好，没有发现异常",
        "未观察到可见的质量问题",
        "该样本外观正常，无明显缺陷",
    ]
    locations = ["", f"{category}整体", f"{category}表面", f"{category}区域"]
    candidates: list[dict[str, Any]] = []
    for index in range(min(count, len(summaries))):
        candidate = dict(base)
        candidate["evidence_summary"] = summaries[index]
        candidate["location_hint"] = locations[index]
        candidate["mapping_source"] = "mvtec_template" if index == 0 else "mvtec_template_variant"
        candidate["candidate_id"] = f"template_{index}"
        candidates.append(candidate)
    return candidates


def _text_candidates(category: str, image_structured: dict[str, Any],
                     external: dict[str, Any] | None,
                     count: int) -> list[dict[str, Any]]:
    """Resolve external normal descriptions first, with safe templates as fallback."""
    if isinstance(external, dict):
        supplied = external.get("text_structured_candidates")
        if isinstance(supplied, list):
            candidates = [dict(item) for item in supplied if isinstance(item, dict)]
            if candidates:
                return candidates
        single = external.get("text_structured")
        if isinstance(single, dict):
            base = dict(single)
            summary = str(base.get("evidence_summary") or base.get("description") or "").strip()
            variants = [summary]
            if summary:
                variants.extend([
                    f"检测描述：{summary}",
                    f"检查结果显示，{summary}",
                    f"{category}检查记录：{summary}",
                ])
            candidates = []
            for index, paraphrase in enumerate(variants[:max(1, int(count))]):
                candidate = dict(base)
                if "evidence_summary" in candidate or paraphrase:
                    candidate["evidence_summary"] = paraphrase
                candidate["mapping_source"] = "external_text_variant"
                candidate["candidate_id"] = f"external_{index}"
                candidates.append(candidate)
            return candidates
    return _template_text_candidates(category, image_structured, count)


def _load_external_text(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    rows = []
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("samples", data.get("rows", []))
    result = {}
    for row in rows:
        if isinstance(row, dict):
            key = str(row.get("id") or row.get("image") or row.get("image_path") or "")
            if key:
                result[key] = row
    return result


def _split_names(names: list[str], train_ratio: float, val_ratio: float, rng: random.Random) -> dict[str, list[str]]:
    shuffled = list(names)
    rng.shuffle(shuffled)
    n = len(shuffled)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)
    if n >= 3:
        train_end = min(max(train_end, 1), n - 2)
        val_end = min(max(val_end, train_end + 1), n - 1)
    return {"train": shuffled[:train_end], "validation": shuffled[train_end:val_end], "test": shuffled[val_end:]}


def build_input(base_path: Path, output_path: Path, categories: list[str], seed: int,
                train_ratio: float, val_ratio: float, external_text: Path | None,
                use_vlm: bool = False, model_path: str | None = None,
                pipeline_dir: Path | None = None,
                text_candidate_count: int = 4) -> dict[str, int]:
    if not 0 < train_ratio < 1 or not 0 < val_ratio < 1 or train_ratio + val_ratio >= 1:
        raise ValueError("train/validation ratios must be positive and sum to less than 1")
    text_rows = _load_external_text(external_text)
    models = None
    generate_image = None
    if use_vlm:
        if not model_path:
            raise ValueError("--use-vlm requires --model-path")
        test_code = str(_resolve_pipeline_dir(pipeline_dir))
        if test_code not in sys.path:
            sys.path.insert(0, test_code)
        import models as model_module
        import structured_generation_module as generation_module
        model_module.MODEL_PATH = model_path
        models = model_module.StructuredPipelineModels()
        models.load()
        generate_image = generation_module.generate_image_side_json
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    counts = {"train": 0, "validation": 0, "test": 0}
    for category in categories:
        train_good_dir = base_path / category / "train" / "good"
        names = sorted(path.name for path in train_good_dir.glob("*.png"))
        splits = _split_names(names, train_ratio, val_ratio, rng)
        for split, split_names in splits.items():
            for name in split_names:
                image_path = train_good_dir / name
                fallback = _normal_structured()
                image_structured = dict(fallback)
                if generate_image is not None:
                    try:
                        with Image.open(image_path) as image:
                            image_structured = generate_image(
                                models, str(image_path), category, image.width, image.height,
                                inject_text_context=False, inject_rag_context=False,
                            )
                        image_structured["fallback_label_structured"] = fallback
                    except Exception as exc:
                        image_structured["vlm_error"] = f"{type(exc).__name__}: {exc}"
                external = (
                    text_rows.get(str(image_path))
                    or text_rows.get(name)
                    or text_rows.get(str(image_path.resolve()))
                )
                text_candidates = _text_candidates(
                    category, image_structured, external, text_candidate_count,
                )
                rows.append({
                    "id": f"{category}/train/good/{Path(name).stem}",
                    "image": str(image_path.resolve()),
                    "category": category,
                    "defect_type": "good",
                    "split": split,
                    "source_split": "official_train_good",
                    "ground_truth": fallback,
                    "text_structured": text_candidates[0],
                    "text_structured_candidates": text_candidates,
                    "image_structured": image_structured,
                })
                counts[split] += 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"total": len(rows), **counts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("mvtec_qdl_input.jsonl"))
    parser.add_argument("--categories", nargs="+", default=CATEGORIES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--external-text", type=Path)
    parser.add_argument("--text-candidates", type=int, default=4,
                        help="每张图生成的文本候选数（默认 4）")
    parser.add_argument("--use-vlm", action="store_true")
    parser.add_argument("--model-path")
    parser.add_argument(
        "--pipeline-dir", type=Path,
        help="目录路径，需包含 models.py、utils.py 和结构化生成模块；"
             "也可通过 QDL_PIPELINE_DIR 环境变量指定",
    )
    args = parser.parse_args(argv)
    print(json.dumps(build_input(
        args.base_path, args.output, args.categories, args.seed,
        args.train_ratio, args.val_ratio, args.external_text, args.use_vlm,
        args.model_path, args.pipeline_dir, args.text_candidates,
    ), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
