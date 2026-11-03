"""Run standalone defect detection from any working directory."""
from __future__ import annotations

import sys
import time
from pathlib import Path

QDL_DIR = Path(__file__).resolve().parents[1] / "tools" / "qdl"


def prepare_arguments(argv: list[str]) -> list[str]:
    args = list(argv)

    def provided(flag: str) -> bool:
        return any(value == flag or value.startswith(flag + "=") for value in args)

    if not provided("--output"):
        if "--resume" in args:
            raise ValueError("--resume requires --output pointing to an existing checkpoint")
        args.extend(["--output", str(QDL_DIR / "results" / f"defects-{time.time_ns()}.jsonl")])
    if not provided("--prompt-mode"):
        args.extend(["--prompt-mode", "open-vocab"])
    return args


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(QDL_DIR))
    from predict import main as predict_main

    previous = sys.argv
    try:
        sys.argv = [str(Path(__file__).resolve()), *prepare_arguments(list(argv) if argv is not None else previous[1:])]
        return predict_main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Defect detection failed: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.argv = previous


if __name__ == "__main__":
    raise SystemExit(main())
