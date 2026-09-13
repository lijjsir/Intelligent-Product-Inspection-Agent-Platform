from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meeting_auto_participation_corpus import (
    build_corpus,
    evaluate_methods,
    seed_text_dataset,
    select_confidence_threshold,
    validate_corpus,
)
from infra.database.session import get_session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build, validate, seed, or evaluate meeting-auto-participation-v1.")
    parser.add_argument("--bindings", type=Path, help="JSON file containing existing task/product/batch/standard/memory IDs.")
    parser.add_argument("--output", type=Path, help="Write the generated 80 samples as JSONL.")
    parser.add_argument("--seed", action="store_true", help="Seed the existing text Dataset module.")
    parser.add_argument("--org-id", help="Organization ID used with --seed.")
    parser.add_argument("--user-id", help="Dataset owner user ID used with --seed.")
    parser.add_argument("--predictions", type=Path, help="JSON predictions for the three evaluation methods.")
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


async def seed(args: argparse.Namespace, samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not args.org_id or not args.user_id:
        raise ValueError("--seed requires --org-id and --user-id")
    if not args.bindings:
        raise ValueError("--seed requires --bindings so related entities use existing project IDs")
    async with get_session() as session:
        return await seed_text_dataset(
            session,
            org_id=args.org_id,
            user_id=args.user_id,
            samples=samples,
        )


def main() -> None:
    args = parse_args()
    bindings = read_json(args.bindings) if args.bindings else None
    samples = build_corpus(bindings)
    result: dict[str, Any] = {"validation": validate_corpus(samples)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in samples) + "\n",
            encoding="utf-8",
        )
        result["output"] = str(args.output.resolve())
    if args.predictions:
        predictions = read_json(args.predictions)
        result["dev_thresholds"] = {
            method: select_confidence_threshold(samples, values, split="dev")
            for method, values in predictions.items()
        }
        result["evaluation"] = evaluate_methods(
            samples,
            predictions,
            split=args.split,
        )
    if args.seed:
        result["seed"] = asyncio.run(seed(args, samples))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
