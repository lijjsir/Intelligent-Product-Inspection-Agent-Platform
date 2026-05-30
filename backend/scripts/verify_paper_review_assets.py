from __future__ import annotations

import argparse
import json
from pathlib import Path

TOKEN_FILES = [
    "config.json",
    "csc.config",
    "pytorch_model.bin",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
]

PUNCT_FILES = [
    "config.json",
    "idx2pun.json",
    "pytorch_model.bin",
    "sl.config",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "vocab.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="/opt/piap-paper-assets")
    args = parser.parse_args()

    base = Path(args.base_dir)
    errors: list[str] = []

    _check_dir(base / "macro_correct" / "token", TOKEN_FILES, errors)
    _check_dir(base / "macro_correct" / "punct", PUNCT_FILES, errors)

    manifest = base / "manifest.json"
    if not manifest.exists():
        errors.append(f"missing manifest: {manifest}")
    else:
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid manifest.json: {exc}")

    if errors:
        for item in errors:
            print(f"[paper-assets] {item}")
        return 1

    print(f"[paper-assets] ready: {base}")
    return 0


def _check_dir(path: Path, files: list[str], errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"missing dir: {path}")
        return

    for name in files:
        file_path = path / name
        if not file_path.exists():
            errors.append(f"missing file: {file_path}")
            continue

        if name in {"pytorch_model.bin", "vocab.txt"} and file_path.stat().st_size <= 0:
            errors.append(f"empty file: {file_path}")


if __name__ == "__main__":
    raise SystemExit(main())
