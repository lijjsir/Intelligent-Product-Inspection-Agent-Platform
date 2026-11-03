"""Audit paired structured image/text JSONL independently of the PIAP platform."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path

from qdl_http import OpenAIClient, runtime_defaults

core = importlib.import_module("qdl_core.qdl_module")
REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "relation": {"type": "string", "enum": sorted(core.QDLMatcher.RELATIONS)},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 300},
    },
    "required": ["relation", "score", "confidence", "reason"],
}


def main(argv=None):
    default_url, default_model = runtime_defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", action="store_true", help="Ask the deployed model to review candidate edges")
    parser.add_argument("--embed-model", help="Optional local sentence-transformers directory (no automatic download)")
    parser.add_argument("--base-url", default=default_url)
    parser.add_argument("--model", default=default_model)
    parser.add_argument("--max-candidates", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if args.max_candidates < 1 or args.max_candidates > 128:
        parser.error("--max-candidates must be in 1..128")
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must be different files")
    embedder = None
    if args.embed_model:
        if not Path(args.embed_model).is_dir():
            parser.error("--embed-model must be an existing local directory")
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer(args.embed_model, device="cpu", local_files_only=True)
    client = OpenAIClient(args.base_url, args.model, args.timeout) if args.review else None
    matcher = core.QDLMatcher(
        embedder=embedder,
        llm_reviewer=(lambda prompt: client.chat(
            "Return only the JSON review object requested below; use an allowed relation exactly.\n" + prompt,
            512, response_schema=REVIEW_SCHEMA,
        )) if client else None,
        config=core.QDLConfig(llm_review=args.review, max_candidates=args.max_candidates),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    processed = errors = 0
    with args.input.open(encoding="utf-8-sig") as source, args.output.open("w", encoding="utf-8") as target:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            row = None
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("each row must be a JSON object")
                for side in ("text_structured", "image_structured"):
                    if not isinstance(row.get(side), dict) or not row[side]:
                        raise ValueError(f"{side} must be a non-empty object")
                result = matcher.match(row["text_structured"], row["image_structured"], category=row.get("category"))
                record = {"id": row.get("id"), "image": row.get("image"), "split": row.get("split"),
                          "status": "ok", "qdl_result": result,
                          "configuration": {"review_model": args.model if args.review else None,
                                            "max_candidates": args.max_candidates,
                                            "embed_model": args.embed_model,
                                            "score_is_calibrated_probability": False}}
                processed += 1
            except (ValueError, TypeError, KeyError) as exc:
                record = {"line": line_number, "status": "error", "error": str(exc)}
                errors += 1
            target.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            target.flush()
    print(json.dumps({"processed": processed, "errors": errors, "output": str(args.output)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
