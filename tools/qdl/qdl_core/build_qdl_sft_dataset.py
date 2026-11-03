"""Build QDL-audited and QDL-filtered SFT JSONL datasets.

Input is one JSON object per line with ``image``, ``text_structured`` and
``image_structured``.  The latter two objects are intentionally supplied by
an upstream generation pipeline; this script does not invent visual labels.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from qdl_module import QDLConfig, QDLMatcher
from evidence_protocol import evidence_prompt, format_evidence_answer


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_callable(spec: str | None) -> Callable[[str], Any] | None:
    if not spec:
        return None
    if ":" not in spec:
        raise ValueError("reviewer must use MODULE:FUNCTION syntax")
    module_name, function_name = spec.rsplit(":", 1)
    function = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(function):
        raise ValueError(f"reviewer is not callable: {spec}")
    return function


def _load_default_models(*, model_path: str | None, pipeline_dir: Path | None,
                         embed_model: str) -> tuple[Any, Callable[[str], Any]]:
    """Load the default BGE embedder and the repository's Qwen text reviewer."""
    runtime_dir = pipeline_dir or Path(__file__).resolve().parent
    if not runtime_dir.is_dir():
        raise RuntimeError(f"找不到 Qwen reviewer 运行目录：{runtime_dir}；请通过 --pipeline-dir 指定模型运行目录。")
    runtime_value = str(runtime_dir.resolve())
    if runtime_value not in sys.path:
        sys.path.insert(0, runtime_value)
    try:
        model_module = importlib.import_module("models")
        model_module.EMBED_MODEL_NAME = embed_model
        if model_path:
            model_module.MODEL_PATH = model_path
        elif os.environ.get("QDL_REVIEW_MODEL_PATH"):
            model_module.MODEL_PATH = os.environ["QDL_REVIEW_MODEL_PATH"]
        model = model_module.StructuredPipelineModels()
        model.load()
    except Exception as exc:
        raise RuntimeError(
            "无法加载默认 QDL 关系审查模型。请检查 --model-path/QDL_REVIEW_MODEL_PATH 和 --pipeline-dir。"
        ) from exc

    embedder = model.embedder
    if embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            embedder = SentenceTransformer(embed_model)
        except Exception as exc:
            raise RuntimeError(f"无法加载 QDL embedding 模型 {embed_model!r}: {exc}") from exc

    def reviewer(prompt: str) -> Any:
        return model_module._llm_text_inference(model, prompt, max_new_tokens=128)

    return embedder, reviewer


def _record_error(line_number: int, reason: str, raw: str | None = None) -> dict[str, Any]:
    result = {"line": line_number, "error": reason}
    if raw is not None:
        result["raw"] = raw[:2000]
    return result


def _bucket(score: float, high: float, medium: float) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "conflict"


def _sample_weight(score: float, bucket: str) -> float:
    # This is a monotonic engineering weight, not a calibrated probability.
    if bucket == "high":
        return max(0.0, min(1.0, score))
    if bucket == "medium":
        return max(0.0, min(0.75, score * 0.75))
    return max(0.0, min(0.50, score * 0.50))


def _ground_truth(record: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(record.get("ground_truth"), Mapping):
        return dict(record["ground_truth"])
    known = {
        key: record[key]
        for key in (
            "has_defect", "risk_type", "severity", "defect_category",
            "location_hint", "evidence_summary", "confidence", "bbox",
        )
        if key in record
    }
    return known


def _conversation(record: Mapping[str, Any], qdl_result: Mapping[str, Any],
                  target_format: str = "evidence") -> list[dict[str, str]]:
    image = record.get("image", "")
    category = record.get("category", "industrial product")
    truth = _ground_truth(record)
    image_data = qdl_result.get("image_structured", {})
    if target_format == "evidence":
        prompt = evidence_prompt(str(category))
        answer = format_evidence_answer(
            truth.get("evidence_summary") or image_data.get("evidence_summary", ""),
            truth.get("has_defect", image_data.get("has_defect", "Unknown")),
        )
    elif target_format == "json":
        prompt = (
            f"<image>\nYou are an industrial inspection assistant. Analyze this {category} image "
            "and return JSON with has_defect, risk_type, severity, defect_category, location_hint, "
            "evidence_summary, confidence, and bbox. Output JSON only."
        )
        answer_obj = {key: value for key, value in truth.items()
                      if key not in {"mapping_source", "alignment_score", "qdl_bucket", "sample_weight"}}
        if not answer_obj:
            answer_obj = {key: image_data.get(key) for key in (
                "has_defect", "risk_type", "severity", "defect_category",
                "location_hint", "evidence_summary", "confidence", "bbox",
            )}
        answer = _json(answer_obj)
    else:
        raise ValueError(f"unsupported target format: {target_format}")
    return [
        {"from": "human", "value": prompt},
        {"from": "gpt", "value": answer},
    ]


def _text_candidates(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the text-side candidate set while keeping old inputs valid."""
    supplied = record.get("text_structured_candidates")
    if supplied is None:
        supplied = [record.get("text_structured")]
    elif isinstance(supplied, Mapping):
        supplied = [supplied]
    if not isinstance(supplied, list):
        raise ValueError("text_structured_candidates must be a list of objects")
    candidates = [dict(item) for item in supplied if isinstance(item, Mapping)]
    if not candidates:
        raise ValueError("missing or empty text_structured_candidates")
    return candidates


def build_record(record: Mapping[str, Any], matcher: QDLMatcher,
                 high_threshold: float, medium_threshold: float,
                 target_format: str = "evidence",
                 max_candidates_per_image: int | None = 128,
                 progress: Callable[[str], None] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    image_structured = record.get("image_structured")
    if not isinstance(image_structured, Mapping) or not image_structured:
        raise ValueError("missing or empty image_structured")
    text_candidates = _text_candidates(record)
    candidate_results: list[dict[str, Any]] = []
    remaining_budget = max_candidates_per_image
    for index, candidate in enumerate(text_candidates):
        if progress:
            progress(f"candidate_start index={index + 1}/{len(text_candidates)}")
        def edge_trace(event: Mapping[str, Any], candidate_index: int = index + 1) -> None:
            if not progress:
                return
            event_name = event.get("event")
            if event_name == "candidate_pool_ready":
                progress(
                    f"candidate_pool index={candidate_index}/{len(text_candidates)} "
                    f"pool={event.get('candidate_pool_count', 0)} "
                    f"screened={event.get('candidate_count', 0)}"
                )
            elif event_name == "edge_start":
                edge_index = int(event.get("edge_index", 0) or 0)
                edge_total = int(event.get("edge_total", 0) or 0)
                if edge_index == 1 or edge_index == edge_total or edge_index % 10 == 0:
                    progress(
                        f"edge_start candidate={candidate_index} edge={edge_index}/{edge_total} "
                        f"pair={event.get('text_field')}->{event.get('image_field')}"
                    )
            elif event_name == "edge_done":
                edge_index = int(event.get("edge_index", 0) or 0)
                edge_total = int(event.get("edge_total", 0) or 0)
                if edge_index == 1 or edge_index == edge_total or edge_index % 10 == 0:
                    progress(
                        f"edge_done candidate={candidate_index} edge={edge_index}/{edge_total} "
                        f"relation={event.get('relation')} score={float(event.get('score', 0.0) or 0.0):.4f} "
                        f"accepted={event.get('accepted')}"
                    )
        candidate_matcher = matcher
        if isinstance(matcher, QDLMatcher) and remaining_budget is not None:
            configured_limit = matcher.config.max_candidates
            available = max(0, int(remaining_budget))
            limit = available if configured_limit is None else min(available, max(0, int(configured_limit)))
            candidate_matcher = QDLMatcher(
                embedder=matcher.embedder,
                llm_reviewer=matcher.llm_reviewer,
                config=replace(matcher.config, max_candidates=limit),
                trace_callback=edge_trace,
            )
        elif isinstance(matcher, QDLMatcher):
            candidate_matcher = QDLMatcher(
                embedder=matcher.embedder,
                llm_reviewer=matcher.llm_reviewer,
                config=matcher.config,
                trace_callback=edge_trace,
            )
        candidate_result = candidate_matcher.match(
            text_structured=candidate,
            image_structured=image_structured,
            category=record.get("category"),
            retrieved_docs=record.get("retrieved_docs"),
        )
        candidate_results.append({
            "candidate_index": index,
            "candidate_id": candidate.get("candidate_id", f"candidate_{index}"),
            "text_structured": candidate,
            "alignment_score": float(candidate_result.get("alignment_score", 0.0) or 0.0),
            "qdl_result": candidate_result,
        })
        if progress:
            progress(
                f"candidate_done index={index + 1}/{len(text_candidates)} "
                f"edges={len(candidate_result.get('candidate_edges', []))} "
                f"accepted={len(candidate_result.get('accepted_edges', []))} "
                f"alignment={float(candidate_result.get('alignment_score', 0.0) or 0.0):.4f}"
            )
        if remaining_budget is not None:
            remaining_budget = max(
                0, int(remaining_budget) - len(candidate_result.get("candidate_edges", []))
            )
    best = max(candidate_results, key=lambda item: item["alignment_score"])
    text_structured = best["text_structured"]
    result = dict(best["qdl_result"])
    # The best candidate remains available at the top level for compatibility;
    # all candidate-to-image graphs are retained for many-to-many auditing.
    result["text_candidate_results"] = candidate_results
    result["text_candidate_count"] = len(candidate_results)
    result["best_text_candidate_index"] = best["candidate_index"]
    result["candidate_alignment_scores"] = [item["alignment_score"] for item in candidate_results]
    result["candidate_edges_by_text_candidate"] = [
        {
            "candidate_index": item["candidate_index"],
            "candidate_id": item["candidate_id"],
            "candidate_edges": item["qdl_result"].get("candidate_edges", []),
            "accepted_edges": item["qdl_result"].get("accepted_edges", []),
        }
        for item in candidate_results
    ]
    result["candidate_aggregation"] = "max_alignment_score"
    result["total_candidate_edge_count"] = sum(
        len(item["qdl_result"].get("candidate_edges", [])) for item in candidate_results
    )
    result["max_candidate_edges_per_image"] = max_candidates_per_image
    score = best["alignment_score"]
    bucket = _bucket(score, high_threshold, medium_threshold)
    audit = {
        "image": record.get("image"),
        "id": record.get("id"),
        "category": record.get("category"),
        "split": record.get("split", "train"),
        "ground_truth": _ground_truth(record),
        "text_structured": dict(text_structured),
        "text_structured_candidates": text_candidates,
        "image_structured": dict(image_structured),
        "qdl_result": result,
        "alignment_score": score,
        "consistency_label": result.get("consistency_label"),
        "field_scores": result.get("field_scores", {}),
        "sample_weight": _sample_weight(score, bucket),
        "qdl_bucket": bucket,
        "thresholds_used": {"high": high_threshold, "medium": medium_threshold},
        "candidate_edge_count": result["total_candidate_edge_count"],
        "max_candidate_edges_per_image": max_candidates_per_image,
    }
    sft = {
        "image": record.get("image"),
        "images": [record.get("image")] if record.get("image") else [],
        "conversations": _conversation(
            record, {**record, "image_structured": dict(image_structured)}, target_format
        ),
        "ground_truth": _ground_truth(record),
        "text_structured": dict(text_structured),
        "text_structured_candidates": text_candidates,
        "image_structured": dict(image_structured),
        "qdl_result": result,
        "sample_weight": audit["sample_weight"],
        "qdl_bucket": bucket,
        "split": audit["split"],
    }
    return audit, sft


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(_json(row) + "\n")


def generate(input_path: Path, output_dir: Path, *, high_threshold: float = 0.80,
             medium_threshold: float = 0.55, edge_threshold: float = 0.60,
             candidate_threshold: float = 0.55, max_candidates: int | None = 128,
             llm_review: bool = True, reviewer: Callable[[str], Any] | None = None,
             target_format: str = "evidence", embedder: Any = None,
             model_path: str | None = None, pipeline_dir: Path | None = None,
             embed_model: str = "BAAI/bge-small-zh",
             progress_every: int = 1) -> dict[str, int]:
    if not 0 <= medium_threshold <= high_threshold <= 1:
        raise ValueError("thresholds must satisfy 0 <= medium <= high <= 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    config = QDLConfig(
        candidate_threshold=candidate_threshold,
        edge_threshold=edge_threshold,
        max_candidates=max_candidates,
        llm_review=llm_review,
    )
    if llm_review and (embedder is None or reviewer is None):
        loaded_embedder, loaded_reviewer = _load_default_models(
            model_path=model_path, pipeline_dir=pipeline_dir, embed_model=embed_model,
        )
        embedder = embedder or loaded_embedder
        reviewer = reviewer or loaded_reviewer
    matcher = QDLMatcher(embedder=embedder, llm_reviewer=reviewer, config=config)
    all_rows: list[dict[str, Any]] = []
    sft_rows: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "conflict": []}
    eval_rows: dict[str, list[dict[str, Any]]] = {"validation": [], "test": []}
    errors: list[dict[str, Any]] = []
    log_path = output_dir / "qdl_progress.log"
    output_paths = {
        "all": output_dir / "qdl_train_all.jsonl",
        "high": output_dir / "qdl_train_high.jsonl",
        "medium": output_dir / "qdl_train_medium.jsonl",
        "conflict": output_dir / "qdl_train_conflict.jsonl",
        "validation": output_dir / "qdl_train_sft_val.jsonl",
        "test": output_dir / "qdl_train_sft_test.jsonl",
        "errors": output_dir / "qdl_generation_errors.jsonl",
    }
    output_handles = {key: path.open("w", encoding="utf-8", newline="\n")
                      for key, path in output_paths.items()}
    started = time.time()
    def progress(message: str) -> None:
        line = f"[QDL] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as log_handle:
            log_handle.write(line + "\n")
    progress(f"start input={input_path} max_candidates_per_image={max_candidates} llm_review={llm_review}")
    try:
        with input_path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    record = json.loads(raw)
                    if not isinstance(record, Mapping):
                        raise ValueError("record must be a JSON object")
                    record_id = record.get("id", record.get("image", f"line-{line_number}"))
                    if progress_every > 0 and (len(all_rows) + len(errors)) % progress_every == 0:
                        progress(f"sample_start number={len(all_rows) + len(errors) + 1} id={record_id}")
                    audit, sft = build_record(
                        record, matcher, high_threshold, medium_threshold, target_format,
                        max_candidates_per_image=max_candidates, progress=progress,
                    )
                    all_rows.append(audit)
                    output_handles["all"].write(_json(audit) + "\n")
                    output_handles["all"].flush()
                    if audit["split"] == "train":
                        bucket = audit["qdl_bucket"]
                        sft_rows[bucket].append(sft)
                        output_handles[bucket].write(_json(sft) + "\n")
                        output_handles[bucket].flush()
                    elif audit["split"] in eval_rows:
                        split = audit["split"]
                        eval_rows[split].append(sft)
                        output_handles[split].write(_json(sft) + "\n")
                        output_handles[split].flush()
                    progress(
                        f"sample_done number={len(all_rows)} id={record_id} split={audit['split']} "
                        f"candidate_edges={audit['candidate_edge_count']} "
                        f"accepted_edges={len(audit['qdl_result'].get('accepted_edges', []))} "
                        f"alignment={audit['alignment_score']:.4f} bucket={audit['qdl_bucket']} "
                        f"elapsed_sec={time.time() - started:.1f}"
                    )
                except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                    error = _record_error(line_number, str(exc), raw)
                    errors.append(error)
                    output_handles["errors"].write(_json(error) + "\n")
                    output_handles["errors"].flush()
                    progress(f"sample_error line={line_number} error={str(exc)[:300]}")
                except Exception as exc:  # keep one bad model/reviewer call from aborting a dataset
                    error = _record_error(line_number, f"unexpected: {type(exc).__name__}: {exc}", raw)
                    errors.append(error)
                    output_handles["errors"].write(_json(error) + "\n")
                    output_handles["errors"].flush()
                    progress(f"sample_error line={line_number} error={type(exc).__name__}: {str(exc)[:250]}")
    finally:
        for file_handle in output_handles.values():
            file_handle.close()
        progress(f"finished processed={len(all_rows)} errors={len(errors)} elapsed_sec={time.time() - started:.1f}")
    return {
        "processed": len(all_rows), "errors": len(errors),
        **{k: len(v) for k, v in sft_rows.items()},
        "validation": len(eval_rows["validation"]),
        "test": len(eval_rows["test"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input JSONL")
    parser.add_argument("--output-dir", type=Path, default=Path("qdl_dataset"))
    parser.add_argument("--high-threshold", type=float, default=0.80)
    parser.add_argument("--medium-threshold", type=float, default=0.55)
    parser.add_argument("--edge-threshold", type=float, default=0.60)
    parser.add_argument("--candidate-threshold", type=float, default=0.55)
    parser.add_argument("--max-candidates", type=int, default=128,
                        help="negative value keeps all candidates")
    parser.add_argument("--no-llm-review", action="store_true")
    parser.add_argument("--reviewer-module", help="override Qwen reviewer with MODULE:FUNCTION callback")
    parser.add_argument("--model-path", help="Qwen reviewer model path; defaults to models.py or QDL_REVIEW_MODEL_PATH")
    parser.add_argument("--pipeline-dir", type=Path, help="目录路径，需包含 models.py、utils.py 和结构化生成模块")
    parser.add_argument("--embed-model", default="BAAI/bge-small-zh", help="sentence-transformers model for candidate semantics")
    parser.add_argument("--target-format", choices=("evidence", "json"), default="evidence",
                        help="SFT target protocol; evidence is the new default")
    parser.add_argument("--progress-every", type=int, default=1,
                        help="log sample starts at this interval; candidate and completion logs are always written")
    args = parser.parse_args(argv)
    try:
        reviewer = _load_callable(args.reviewer_module)
        stats = generate(
            args.input, args.output_dir,
            high_threshold=args.high_threshold,
            medium_threshold=args.medium_threshold,
            edge_threshold=args.edge_threshold,
            candidate_threshold=args.candidate_threshold,
            max_candidates=None if args.max_candidates < 0 else args.max_candidates,
            llm_review=not args.no_llm_review,
            reviewer=reviewer,
            target_format=args.target_format,
            model_path=args.model_path,
            pipeline_dir=args.pipeline_dir,
            embed_model=args.embed_model,
            progress_every=args.progress_every,
        )
    except (OSError, ValueError, ImportError) as exc:
        parser.error(str(exc))
        return 2
    print(_json(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
