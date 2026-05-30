from __future__ import annotations

import argparse
import json
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
    changed = prepare_assets(base_dir)
    print(f"[paper-assets] {'download complete' if changed else 'already ready'}: {base_dir}")
    return 0


def prepare_assets(base_dir: Path) -> bool:
    changed = False
    token_dir = base_dir / "macro_correct" / "token"
    punct_dir = base_dir / "macro_correct" / "punct"

    if _asset_set_ready(token_dir, TOKEN_FILES):
        print(f"{TOKEN_REPO} already ready at {token_dir}")
    else:
        _download_repo(TOKEN_REPO, token_dir, TOKEN_FILES)
        changed = True

    if _asset_set_ready(punct_dir, PUNCT_FILES):
        print(f"{PUNCT_REPO} already ready at {punct_dir}")
    else:
        _download_repo(PUNCT_REPO, punct_dir, PUNCT_FILES)
        changed = True

    if changed or not _manifest_ready(base_dir):
        _write_manifest(base_dir)
        changed = True

    return changed


def _download_repo(repo_id: str, target_dir: Path, files: list[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        allow_patterns=files,
        local_dir_use_symlinks=False,
    )
    missing = _missing_asset_files(target_dir, files)
    if missing:
        raise RuntimeError(f"{repo_id} missing files after download: {missing}")
    print(f"{repo_id} ready at {target_dir}")


def _asset_set_ready(target_dir: Path, files: list[str]) -> bool:
    return not _missing_asset_files(target_dir, files)


def _missing_asset_files(target_dir: Path, files: list[str]) -> list[str]:
    missing: list[str] = []
    for name in files:
        path = target_dir / name
        if not path.exists():
            missing.append(name)
            continue
        if name in {"pytorch_model.bin", "vocab.txt"} and path.stat().st_size <= 0:
            missing.append(name)
    return missing


def _manifest_ready(base_dir: Path) -> bool:
    manifest_path = base_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        manifest.get("asset_version") == "paper-check-assets-v1"
        and manifest.get("created_by") == "download_paper_review_assets.py"
    )


def _write_manifest(base_dir: Path) -> None:
    manifest = {
        "asset_version": "paper-check-assets-v1",
        "created_by": "download_paper_review_assets.py",
        "base_dir": str(base_dir),
        "repos": {
            "token": {
                "repo_id": TOKEN_REPO,
                "target": "macro_correct/token",
                "required_files": TOKEN_FILES,
            },
            "punct": {
                "repo_id": PUNCT_REPO,
                "target": "macro_correct/punct",
                "required_files": PUNCT_FILES,
            },
        },
    }
    (base_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[paper-assets] manifest written to {base_dir / 'manifest.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
