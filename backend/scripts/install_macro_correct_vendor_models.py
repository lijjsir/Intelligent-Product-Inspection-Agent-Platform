from __future__ import annotations

import shutil
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
VENDOR_OUTPUT_ROOT = BACKEND_ROOT / "vendor_models" / "macro_correct" / "output"

MODEL_SPECS = (
    (
        Path("text_correction/macbert4mdcspell_v3"),
        {
            "config.json": None,
            "csc.config": None,
            "generation_config.json": None,
            "pytorch_model.bin": 409234681,
            "special_tokens_map.json": None,
            "tokenizer.json": None,
            "tokenizer_config.json": None,
            "vocab.txt": None,
        },
    ),
    (
        Path("sequence_labeling/bert4sl_punct_zh_public"),
        {
            "config.json": None,
            "idx2pun.json": None,
            "pytorch_model.bin": 416223240,
            "sl.config": None,
            "special_tokens_map.json": None,
            "tokenizer_config.json": None,
            "vocab.txt": None,
        },
    ),
)


def _get_macro_correct_output_root() -> Path:
    try:
        import macro_correct
    except Exception as exc:  # pragma: no cover - depends on container image
        raise RuntimeError(f"macro_correct import failed: {exc}") from exc

    return Path(macro_correct.__file__).resolve().parent / "output"


def _validate_vendor_models() -> None:
    missing: list[str] = []
    mismatched: list[str] = []

    for rel_dir, files in MODEL_SPECS:
        for filename, expected_size in files.items():
            path = VENDOR_OUTPUT_ROOT / rel_dir / filename
            if not path.exists() or path.stat().st_size <= 0:
                missing.append(str(path))
                continue
            if expected_size is not None and path.stat().st_size != expected_size:
                mismatched.append(f"{path} ({path.stat().st_size} != {expected_size})")

    if missing or mismatched:
        details = []
        if missing:
            details.append("missing: " + "; ".join(missing))
        if mismatched:
            details.append("size mismatch: " + "; ".join(mismatched))
        raise RuntimeError("vendor macro_correct models are incomplete; " + " | ".join(details))


def _copy_if_needed(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return False
    shutil.copy2(src, dest)
    return True


def main() -> int:
    _validate_vendor_models()
    package_output_root = _get_macro_correct_output_root()

    copied = 0
    skipped = 0
    for rel_dir, files in MODEL_SPECS:
        for filename in files:
            src = VENDOR_OUTPUT_ROOT / rel_dir / filename
            dest = package_output_root / rel_dir / filename
            if _copy_if_needed(src, dest):
                copied += 1
            else:
                skipped += 1

    print(
        "[ok] macro_correct vendor models installed "
        f"to {package_output_root} (copied={copied}, skipped={skipped})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
