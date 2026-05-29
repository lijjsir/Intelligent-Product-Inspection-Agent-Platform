from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


class MacroCorrectUnavailableError(RuntimeError):
    pass


_TOKEN_CONFIG_REL = Path("output/text_correction/macbert4mdcspell_v3/csc.config")
_PUNCT_CONFIG_REL = Path("output/sequence_labeling/bert4sl_punct_zh_public/sl.config")


def _get_package_root() -> Path:
    try:
        import macro_correct
    except Exception as exc:  # pragma: no cover - import path depends on env
        raise MacroCorrectUnavailableError(f"import failed: {exc}") from exc
    return Path(macro_correct.__file__).resolve().parent


def _ensure_local_model_files(package_root: Path, rel_config: Path) -> Path:
    config_path = package_root / rel_config
    model_path = config_path.parent / "pytorch_model.bin"
    if not config_path.exists() or not model_path.exists():
        raise MacroCorrectUnavailableError(f"local model files missing: {config_path.parent}")
    return config_path


def _patch_transformers_compat() -> None:
    try:
        import transformers
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"transformers import failed: {exc}") from exc

    if hasattr(transformers, "AdamW"):
        return

    try:
        import torch.optim
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"torch.optim import failed: {exc}") from exc

    transformers.AdamW = torch.optim.AdamW


@lru_cache(maxsize=1)
def _build_token_detector() -> tuple[Callable[[list[str]], Any], str]:
    package_root = _get_package_root()
    config_path = _ensure_local_model_files(package_root, _TOKEN_CONFIG_REL)
    _patch_transformers_compat()
    try:
        from macro_correct.predict_csc_token_zh import MacroCSC4Token
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"token detector import failed: {exc}") from exc
    try:
        detector = MacroCSC4Token(path_config=str(config_path))
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"token detector init failed: {exc}") from exc
    batch = getattr(detector, "func_csc_token_batch", None)
    if not callable(batch):
        raise MacroCorrectUnavailableError("token detector missing func_csc_token_batch()")
    return batch, "macro_correct.MacroCSC4Token.func_csc_token_batch"


@lru_cache(maxsize=1)
def _build_punct_detector() -> tuple[Callable[[list[str]], Any], str]:
    package_root = _get_package_root()
    _ensure_local_model_files(package_root, _PUNCT_CONFIG_REL)
    _patch_transformers_compat()
    try:
        from macro_correct.predict_csc_punct_zh import MacroCSC4Punct
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"punct detector import failed: {exc}") from exc
    try:
        detector = MacroCSC4Punct()
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"punct detector init failed: {exc}") from exc
    batch = getattr(detector, "func_csc_punct_batch", None)
    if not callable(batch):
        raise MacroCorrectUnavailableError("punct detector missing func_csc_punct_batch()")
    return batch, "macro_correct.MacroCSC4Punct.func_csc_punct_batch"


def diagnose_macro_correct() -> dict[str, Any]:
    details: list[str] = []
    entrypoints: list[str] = []
    try:
        _, entrypoint = _build_token_detector()
        entrypoints.append(entrypoint)
    except MacroCorrectUnavailableError as exc:
        details.append(str(exc))
    try:
        _, entrypoint = _build_punct_detector()
        entrypoints.append(entrypoint)
    except MacroCorrectUnavailableError as exc:
        details.append(str(exc))

    if not entrypoints:
        return {"ok": False, "detail": "; ".join(details) or "no callable macro-correct detector"}
    return {
        "ok": True,
        "detail": ", ".join(entrypoints),
        "entrypoints": entrypoints,
    }


def run_macro_correct_token(texts: list[str]) -> tuple[Any, str]:
    detector, entrypoint = _build_token_detector()
    return detector(texts), entrypoint


def run_macro_correct_punct(texts: list[str]) -> tuple[Any, str]:
    detector, entrypoint = _build_punct_detector()
    return detector(texts), entrypoint
