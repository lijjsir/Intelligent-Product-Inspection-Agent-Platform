from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


TOKEN_REPO = "Macropodus/macbert4mdcspell_v2"
PUNCT_REPO = "Macropodus/bert4sl_punct_zh_public"

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
    parser = argparse.ArgumentParser(description="Download paper review model assets into a local immutable directory.")
    parser.add_argument("--base-dir", default="/opt/piap-paper-assets")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    _download_repo(TOKEN_REPO, base_dir / "macro_correct" / "token", TOKEN_FILES)
    _download_repo(PUNCT_REPO, base_dir / "macro_correct" / "punct", PUNCT_FILES)
    return 0


def _download_repo(repo_id: str, target_dir: Path, files: list[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        allow_patterns=files,
        local_dir_use_symlinks=False,
    )
    missing = [name for name in files if not (target_dir / name).exists()]
    if missing:
        raise RuntimeError(f"{repo_id} missing files after download: {missing}")
    print(f"{repo_id} ready at {target_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
