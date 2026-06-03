from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import hf_hub_download


os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

BACKEND_ROOT = Path(__file__).resolve().parents[1]

MODEL_SPECS = (
    (
        "Macropodus/macbert4mdcspell_v3",
        BACKEND_ROOT / "vendor_models/macro_correct/output/text_correction/macbert4mdcspell_v3",
        (
            "config.json",
            "csc.config",
            "generation_config.json",
            "pytorch_model.bin",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
        ),
    ),
    (
        "Macropodus/bert4sl_punct_zh_public",
        BACKEND_ROOT / "vendor_models/macro_correct/output/sequence_labeling/bert4sl_punct_zh_public",
        (
            "config.json",
            "idx2pun.json",
            "pytorch_model.bin",
            "sl.config",
            "special_tokens_map.json",
            "tokenizer_config.json",
            "vocab.txt",
        ),
    ),
)


def log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    for repo_id, target_dir, filenames in MODEL_SPECS:
        target_dir.mkdir(parents=True, exist_ok=True)
        log(f"[model] {repo_id} -> {target_dir}")
        for filename in filenames:
            target_path = target_dir / filename
            if target_path.exists() and target_path.stat().st_size > 0:
                log(f"[skip] {filename} ({target_path.stat().st_size} bytes)")
                continue

            log(f"[download] {repo_id}/{filename}")
            downloaded = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
                force_download=False,
                resume_download=True,
            )
            path = Path(downloaded)
            log(f"[ok] {filename}: {path.stat().st_size} bytes")

    missing: list[str] = []
    for _repo_id, target_dir, filenames in MODEL_SPECS:
        for filename in filenames:
            path = target_dir / filename
            if not path.exists() or path.stat().st_size <= 0:
                missing.append(str(path))
    if missing:
        log("[error] missing files:")
        for item in missing:
            log(f"  - {item}")
        return 1

    for part_file in (BACKEND_ROOT / "vendor_models/macro_correct").rglob("*.part"):
        part_file.unlink(missing_ok=True)
        log(f"[cleanup] removed stale partial {part_file}")

    log("[done] all macro_correct model files are ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
