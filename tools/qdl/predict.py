"""Standalone image defect inference and labeled evaluation.

From the project root, use scripts/detect_defects.py for JSON output and
automatic result filenames. This lower-level entry also supports the original
evidence protocol, dataset evaluation and explicit optional inference backends.
Ground truth is never included in the inference prompt.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping
from qdl_http import OpenAIClient, DEFAULT_URL, DEFAULT_MODEL, runtime_defaults

from rebuildcode_bootstrap import ensure_rebuildcode

ensure_rebuildcode()
from rebuildcode.evidence_protocol import evidence_prompt, parse_evidence_output


FIELDS = (
    "has_defect", "risk_type", "severity", "defect_category",
    "location_hint", "evidence_summary", "confidence", "bbox",
)

OPEN_VOCAB_PROMPT = """Inspect the image for a visible product defect. Return one JSON object only with these keys:
has_defect (Yes or No), risk_type, severity, defect_category, location_hint,
evidence_summary, confidence (0 to 1), bbox ([x1,y1,x2,y2] normalized to 0-1000).
The defect_category is OPEN-VOCABULARY: describe the visible defect in a short phrase;
do not choose from a fixed class list or infer a dataset label. Use \"none\" when no defect
is visible and \"unknown\" when a defect may exist but its type cannot be determined.
If has_defect is No, use none for risk_type, severity, and defect_category, an empty
location_hint, and [0,0,0,0] for bbox. Do not output internal audit fields such as
mapping_source, alignment_score, or source dataset. Do not claim details that are not
visually supported."""


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _load_json(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError(f"第 {line_number} 行不是 JSON object")
            rows.append(row)
    return rows


def _direct_image_rows(images: list[str], image_dir: str | None, prompt: str,
                       dataset_name: str, category: str | None = None) -> list[dict[str, Any]]:
    """Build inference-only rows without ground truth or an input JSONL."""
    paths = [Path(item) for item in images]
    if image_dir:
        root = Path(image_dir)
        if not root.is_dir():
            raise FileNotFoundError(f"图片目录不存在: {root}")
        paths.extend(sorted(p for p in root.rglob("*")
                            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS))
    # Preserve order while removing duplicates.
    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique_paths.append(path)
    return [
        {
            "id": f"{dataset_name}/{path.as_posix()}",
            "dataset": dataset_name,
            "category": category or "industrial product",
            "image": str(path),
            "conversations": [{"from": "human", "value": f"<image>\n{prompt}"}],
        }
        for path in unique_paths
    ]


def _image_path(row: Mapping[str, Any], image_root: Path | None = None) -> str:
    image = row.get("image")
    if isinstance(image, str) and image:
        return image
    images = row.get("images")
    if isinstance(images, list) and images and isinstance(images[0], str):
        return images[0]
    raise ValueError("样本缺少 image/images")


def _resolve_image_path(row: Mapping[str, Any], image_root: Path | None = None) -> str:
    """Resolve paths from a locally generated JSONL on Kaggle.

    VisA annotations are often created on a different machine, so the JSONL may
    contain a Windows path or a path rooted at another ``/kaggle/input`` slug.
    Prefer the recorded path, then search under ``--image-root`` by suffix and
    finally by unique basename.
    """
    recorded = _image_path(row)
    candidate = Path(recorded)
    if candidate.is_file():
        return str(candidate)
    if image_root is not None and image_root.is_dir():
        normalized = recorded.replace("\\", "/")
        marker_candidates = ("/Images/", "/images/", "/Data/")
        suffixes = [normalized.lstrip("/")]
        for marker in marker_candidates:
            if marker in normalized:
                suffixes.append(normalized.split(marker, 1)[1])
        for suffix in suffixes:
            matches = list(image_root.rglob(Path(suffix).name)) if "/" not in suffix else list(image_root.rglob(suffix))
            if len(matches) == 1 and matches[0].is_file():
                return str(matches[0])
        basename_matches = list(image_root.rglob(candidate.name))
        if len(basename_matches) == 1:
            return str(basename_matches[0])
    raise FileNotFoundError(
        f"测试图片不存在: {recorded}. 请挂载 VisA 数据集，或通过 --image-root 指定 VisA 根目录。"
    )


def _prompt(row: Mapping[str, Any], prompt_mode: str = "dataset") -> str:
    if prompt_mode == "evidence-first":
        return evidence_prompt(str(row.get("category", "industrial product")))
    if prompt_mode == "open-vocab":
        category = row.get("category")
        prefix = f"Product category: {category}.\n" if category else ""
        return prefix + OPEN_VOCAB_PROMPT
    conversations = row.get("conversations")
    if isinstance(conversations, list) and conversations:
        first = conversations[0]
        if isinstance(first, Mapping):
            value = first.get("value", first.get("content", ""))
            if isinstance(value, str):
                return value.replace("<image>", "").strip()
    category = row.get("category", "industrial product")
    return (
        f"Analyze this {category} image and return the requested structured defect "
        "fields as JSON. Output JSON only."
    )


def _truth(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("ground_truth")
    if isinstance(value, Mapping):
        return dict(value)
    conversations = row.get("conversations")
    if isinstance(conversations, list) and len(conversations) > 1:
        answer = conversations[1]
        text = answer.get("value", "") if isinstance(answer, Mapping) else ""
        if isinstance(text, str):
            try:
                decoded = json.loads(text)
                if isinstance(decoded, dict):
                    return decoded
            except json.JSONDecodeError:
                pass
    return {}


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    candidates = [text]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(fenced)
    starts = [m.start() for m in re.finditer(r"\{", text)]
    candidates.extend(text[start:] for start in starts)
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None


def _norm(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _bbox_iou(a: Any, b: Any) -> float | None:
    if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)):
        return None
    if len(a) != 4 or len(b) != 4:
        return None
    try:
        ax1, ay1, ax2, ay2 = (float(x) for x in a)
        bx1, by1, bx2, by2 = (float(x) for x in b)
    except (TypeError, ValueError):
        return None
    if [ax1, ay1, ax2, ay2] == [0.0, 0.0, 0.0, 0.0] and [bx1, by1, bx2, by2] == [0.0, 0.0, 0.0, 0.0]:
        return 1.0
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _binary_metrics(counts: Mapping[str, int], total_samples: int | None = None) -> dict[str, Any]:
    tp, fp, fn, tn = (counts.get(key, 0) for key in ("tp", "fp", "fn", "tn"))
    valid = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / valid if valid else 0.0
    result = {
        "valid_samples": valid,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy_valid": accuracy,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "balanced_accuracy": (recall + specificity) / 2,
        "f1": f1,
    }
    if total_samples is not None:
        result["samples_including_parse_failures"] = total_samples
        result["accuracy_all_samples"] = (tp + tn) / total_samples if total_samples else 0.0
    return result


class OllamaAPIClient:
    """Small Ollama vision client using the local HTTP chat API."""

    def __init__(self, base_url: str, model_name: str, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def generate(self, image_path: str, prompt: str, max_new_tokens: int) -> str:
        if self.base_url.endswith("/api/chat"):
            endpoint = self.base_url
        elif self.base_url.endswith("/api"):
            endpoint = f"{self.base_url}/chat"
        else:
            endpoint = f"{self.base_url}/api/chat"
        image_data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        payload = {
            "model": self.model_name,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [image_data],
            }],
            "stream": False,
            "options": {"temperature": 0, "num_predict": max_new_tokens},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"无法连接 Ollama API {endpoint}: {exc.reason}. "
                "请检查服务是否启动，以及远程服务器能否访问该地址。"
            ) from exc
        content = (result.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"Ollama 返回中没有 message.content: {result}")
        return content.strip()


def _load_model(model_path: str | None, adapter_path: str | None, dtype: str,
                backend: str = "transformers", ollama_url: str = "http://localhost:11434",
                ollama_model: str | None = None, request_timeout: float = 300.0):
    if backend == "openai":
        if adapter_path:
            raise ValueError("API inference does not load a LoRA adapter; use an already deployed model")
        return OpenAIClient(ollama_url, ollama_model or DEFAULT_MODEL, request_timeout), None
    if backend == "ollama":
        if adapter_path:
            raise ValueError("Ollama 后端不使用 --adapter-path；请先将 LoRA 合并或使用已微调的 Ollama 模型名")
        if not ollama_model:
            raise ValueError("Ollama 后端必须通过 --ollama-model 指定已安装的视觉模型名")
        return OllamaAPIClient(ollama_url, ollama_model, request_timeout), None
    if backend != "transformers":
        raise ValueError(f"unsupported inference backend: {backend}")
    if not model_path:
        raise ValueError("Transformers 后端必须提供 --model-path")
    import torch
    from transformers import AutoProcessor
    try:
        from transformers import Qwen3VLForConditionalGeneration as ModelClass
    except ImportError:
        try:
            from transformers import Qwen2VLForConditionalGeneration as ModelClass
        except ImportError:
            from transformers import AutoModelForImageTextToText as ModelClass

    torch_dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[dtype]
    model = ModelClass.from_pretrained(model_path, torch_dtype=torch_dtype, device_map="auto")
    if adapter_path:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter_path)
    processor = AutoProcessor.from_pretrained(model_path)
    model.eval()
    return model, processor


def _generate(model, processor, image_path: str, prompt: str, max_new_tokens: int) -> str:
    if isinstance(model, (OllamaAPIClient, OpenAIClient)):
        return model.generate(image_path, prompt, max_new_tokens)
    import torch
    messages = [{"role": "user", "content": [
        {"type": "image", "image": image_path},
        {"type": "text", "text": prompt},
    ]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    try:
        from qwen_vl_utils import process_vision_info
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt")
    except ImportError:
        from PIL import Image
        image = Image.open(image_path).convert("RGB")
        inputs = processor(text=[text], images=[image], padding=True, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    prompt_length = inputs["input_ids"].shape[1]
    return processor.batch_decode(generated[:, prompt_length:], skip_special_tokens=True)[0].strip()


def evaluate(rows: list[dict[str, Any]], model, processor, max_new_tokens: int,
             output: Path, image_root: Path | None = None, dataset_name: str = "unknown",
             prompt_mode: str = "dataset", resume: bool = False) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    completed: dict[int, dict[str, Any]] = {}
    if resume and output.exists():
        with output.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    completed[int(record["index"])] = record
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"Cannot resume: invalid checkpoint at line {line_number}") from exc
    totals = {field: 0 for field in FIELDS}
    correct = {field: 0 for field in FIELDS}
    defect_counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    category_defect_counts: dict[str, dict[str, int]] = {}
    positive_bbox_ious: list[float] = []
    parseable = 0
    evidence_mode = prompt_mode == "evidence-first"
    category_total = 0
    category_correct = 0
    predictions: list[dict[str, Any]] = []
    output_mode = "a" if resume else "w"
    checkpoint_handle = output.open(output_mode, encoding="utf-8")
    for index, row in enumerate(rows):
        if index in completed:
            saved = completed[index]
            if saved.get("id") != row.get("id"):
                raise ValueError(
                    f"Cannot resume at index {index}: checkpoint id {saved.get('id')!r} "
                    f"does not match input id {row.get('id')!r}"
                )
            image = saved["image"]
            raw = saved.get("raw_output", "")
            predicted = saved.get("prediction")
            truth = saved.get("ground_truth", _truth(row))
        else:
            image = _resolve_image_path(row, image_root)
            raw = _generate(model, processor, image, _prompt(row, prompt_mode), max_new_tokens)
            if evidence_mode:
                predicted = parse_evidence_output(raw)
            else:
                predicted = _extract_json(raw)
            truth = _truth(row)
        if not evidence_mode and _norm(truth.get("has_defect")) in {"yes", "true", "1", "y"}:
            bbox_iou = _bbox_iou(truth.get("bbox"), predicted.get("bbox") if predicted else None)
            if bbox_iou is not None:
                positive_bbox_ious.append(bbox_iou)
        if predicted is not None:
            parseable += 1
        if evidence_mode:
            if "has_defect" in truth:
                totals["has_defect"] += 1
                if predicted is not None and _norm(predicted.get("has_defect")) == _norm(truth.get("has_defect")):
                    correct["has_defect"] += 1
            truth_category = _norm(truth.get("defect_category"))
            generic_categories = {"", "anomaly", "abnormal", "defect", "unknown", "none"}
            if truth_category not in generic_categories and predicted is not None:
                category_total += 1
                if _norm(predicted.get("defect_category")) == truth_category:
                    category_correct += 1
        else:
            for field in FIELDS:
                if field in truth:
                    totals[field] += 1
                    if predicted is not None and _norm(predicted.get(field)) == _norm(truth.get(field)):
                        correct[field] += 1
        if predicted is not None and "has_defect" in truth:
            category_counts = category_defect_counts.setdefault(
                str(row.get("category", "unknown")), {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
            )
            actual_yes = _norm(truth.get("has_defect")) in {"yes", "true", "1", "y"}
            predicted_yes = _norm(predicted.get("has_defect")) in {"yes", "true", "1", "y"}
            if predicted_yes and actual_yes:
                defect_counts["tp"] += 1
                category_counts["tp"] += 1
            elif predicted_yes and not actual_yes:
                defect_counts["fp"] += 1
                category_counts["fp"] += 1
            elif not predicted_yes and actual_yes:
                defect_counts["fn"] += 1
                category_counts["fn"] += 1
            else:
                defect_counts["tn"] += 1
                category_counts["tn"] += 1
        prediction_record = {"index": index, "id": row.get("id"), "dataset": row.get("dataset", dataset_name),
                             "category": row.get("category"), "image": image,
                             "split": row.get("split"), "ground_truth": truth,
                             "prediction": predicted,
                             "raw_output": raw}
        predictions.append(prediction_record)
        if index not in completed:
            checkpoint_handle.write(json.dumps(prediction_record, ensure_ascii=False) + "\n")
            checkpoint_handle.flush()
        print(f"[{index + 1}/{len(rows)}] parseable={predicted is not None} image={image}")
    checkpoint_handle.close()
    labeled_samples = sum("has_defect" in _truth(row) for row in rows)
    binary_summary = _binary_metrics(defect_counts, labeled_samples)
    per_category = {
        category: _binary_metrics(counts)
        for category, counts in sorted(category_defect_counts.items())
    }
    has_ground_truth = any(bool(_truth(row)) for row in rows)
    summary = {
        "dataset": dataset_name,
        "prompt_mode": prompt_mode,
        "evaluation_mode": "with_ground_truth" if has_ground_truth else "inference_only",
        "samples": len(rows),
        "parse_rate": parseable / len(rows) if rows else 0.0,
        "has_defect_confusion": defect_counts,
        "has_defect_metrics": binary_summary,
        "has_defect_accuracy": binary_summary["accuracy_all_samples"],
        "has_defect_accuracy_valid": binary_summary["accuracy_valid"],
        "has_defect_precision": binary_summary["precision"],
        "has_defect_recall": binary_summary["recall"],
        "has_defect_specificity": binary_summary["specificity"],
        "has_defect_balanced_accuracy": binary_summary["balanced_accuracy"],
        "has_defect_f1": binary_summary["f1"],
        "per_category_has_defect_metrics": per_category,
        "predictions": str(output),
    }
    if evidence_mode:
        summary.update({
            "evidence_parse_rate": summary["parse_rate"],
            "field_accuracy": {
                "has_defect": correct["has_defect"] / totals["has_defect"]
                if totals["has_defect"] else None,
            },
            "field_counts": {"has_defect": totals["has_defect"]},
            "correct": {"has_defect": correct["has_defect"]},
            "category_evaluable_samples": category_total,
            "category_exact_accuracy": category_correct / category_total if category_total else None,
            "open_vocabulary_note": (
                "Generic VisA anomaly/unknown labels are excluded from category accuracy; "
                "use an independent ontology or human-labeled subset for semantic category quality."
            ),
        })
    else:
        summary.update({
            "json_parse_rate": summary["parse_rate"],
            "field_accuracy": {field: (correct[field] / totals[field] if totals[field] else None) for field in FIELDS},
            "field_counts": totals,
            "correct": correct,
            "open_vocabulary_note": (
                "defect_category exact match is lexical only; it is not a semantic score. "
                "Use independent human/ontology review for open-vocabulary category quality."
            ),
            "positive_bbox_iou": {
                "positive_samples": len(positive_bbox_ious),
                "mean_iou": (sum(positive_bbox_ious) / len(positive_bbox_ious)) if positive_bbox_ious else None,
                "iou_at_0_25": (sum(value >= 0.25 for value in positive_bbox_ious) / len(positive_bbox_ious)) if positive_bbox_ious else None,
                "iou_at_0_50": (sum(value >= 0.50 for value in positive_bbox_ious) / len(positive_bbox_ious)) if positive_bbox_ious else None,
            },
        })
    # Unlabeled images have no accuracy/precision/recall; zero would be misleading.
    summary["labeled_samples"] = labeled_samples
    if not labeled_samples:
        summary["has_defect_metrics"] = None
        for key in ("has_defect_accuracy", "has_defect_accuracy_valid", "has_defect_precision",
                    "has_defect_recall", "has_defect_specificity", "has_defect_balanced_accuracy", "has_defect_f1"):
            summary[key] = None
    summary_path = output.with_name(output.stem + "_metrics.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    default_url, default_model = runtime_defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("transformers", "ollama", "openai"), default="openai",
                        help="Inference backend (default: OpenAI-compatible HTTP)")
    parser.add_argument("--model-path", default=None,
                        help="Transformers 模型目录；Ollama 后端不需要")
    parser.add_argument("--adapter-path", default=None, help="LoRA 输出目录；省略则评估基座模型")
    parser.add_argument("--ollama-url", "--base-url", default=default_url,
                        help="API base URL; --base-url is an alias")
    parser.add_argument("--ollama-model", "--model", default=default_model,
                        help="Ollama 中已安装且支持图像输入的模型名")
    parser.add_argument("--request-timeout", type=float, default=300.0,
                        help="单张图片 API 请求超时秒数")
    parser.add_argument("--data", default=None,
                        help="带 ground_truth 的 JSONL；直接图片推理时可省略")
    parser.add_argument("--image", action="append", default=[],
                        help="直接推理单张图片；可重复传入多个 --image")
    parser.add_argument("--image-dir", default=None,
                        help="直接递归推理一个图片目录；不计算准确率")
    parser.add_argument("--prompt", default=evidence_prompt("industrial product"),
                        help="直接图片推理时使用的提示词")
    parser.add_argument("--prompt-mode", choices=("evidence-first", "dataset", "open-vocab"),
                        default="evidence-first",
                        help="evidence-first is the default; dataset/open-vocab are legacy JSON modes")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset-name", default="unknown", help="数据集名，例如 VisA 或 MVTec")
    parser.add_argument("--category", help="Explicit product category; never inferred from directory labels")
    parser.add_argument("--image-root", default=None,
                        help="图片根目录；用于修复 JSONL 中来自其他机器的图片路径")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--limit", type=int, default=0,
                        help="最多推理多少条样本；0 表示不限制")
    parser.add_argument("--start-index", type=int, default=0,
                        help="对按稳定排序得到的样本跳过前 N 条；用于分批推理")
    parser.add_argument("--resume", action="store_true",
                        help="从 --output 中逐条 JSONL checkpoint 恢复，跳过已完成样本")
    parser.add_argument("--dtype", choices=("float16", "bfloat16", "float32"), default="float16")
    args = parser.parse_args()
    if args.data:
        rows = _load_json(Path(args.data))
    elif args.image or args.image_dir:
        rows = _direct_image_rows(args.image, args.image_dir, args.prompt, args.dataset_name, args.category)
    else:
        parser.error("必须提供 --data，或提供 --image / --image-dir")
    if not rows:
        parser.error("没有找到可推理的样本或图片")
    if args.start_index < 0:
        parser.error("--start-index 不能小于 0")
    if args.resume and args.start_index:
        parser.error("--resume 需要完整数据集索引，请不要同时使用 --start-index")
    if args.start_index:
        rows = rows[args.start_index:]
    if args.limit > 0:
        rows = rows[:args.limit]
    image_root = Path(args.image_root) if args.image_root else None
    # 在加载数十 GB 模型前先检查全部图片路径，避免跑到第一张才发现 VisA 未挂载。
    for row in rows:
        _resolve_image_path(row, image_root)
    if args.backend == "transformers" and not args.model_path:
        parser.error("Transformers 后端必须提供 --model-path")
    if args.backend == "ollama" and not args.ollama_model:
        parser.error("Ollama 后端必须提供 --ollama-model")
    if args.backend in {"ollama", "openai"} and args.adapter_path:
        parser.error("Ollama 后端不接受 --adapter-path；请使用已合并/已导入 Ollama 的模型")
    model, processor = _load_model(
        args.model_path, args.adapter_path, args.dtype,
        backend=args.backend, ollama_url=args.ollama_url,
        ollama_model=args.ollama_model, request_timeout=args.request_timeout,
    )
    evaluate(rows, model, processor, args.max_new_tokens, Path(args.output), image_root,
             args.dataset_name, args.prompt_mode, resume=args.resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
