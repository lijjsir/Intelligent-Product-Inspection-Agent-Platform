from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import inspect
import logging
from typing import Any, Callable

from app.core.config import settings

# Patch transformers for macro_correct compatibility (AdamW removed in transformers 5.x).
# Must happen at module level before any macro_correct sub-imports.
try:
    import torch.optim
    import transformers

    _adamw = getattr(torch.optim, "AdamW", None)
    if _adamw is not None:
        if not hasattr(transformers, "AdamW"):
            transformers.AdamW = _adamw
        # _LazyModule (transformers >=5.x) stores exportable objects in _objects
        _objects = getattr(transformers, "_objects", None)
        if isinstance(_objects, dict) and "AdamW" not in _objects:
            _objects["AdamW"] = _adamw
except Exception:
    pass


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


def _resolve_config_path(package_root: Path, configured_path: str, fallback_rel_config: Path) -> Path:
    if configured_path.strip():
        config_path = Path(configured_path.strip())
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path
        return config_path
    return package_root / fallback_rel_config


def _ensure_local_model_files(config_path: Path) -> Path:
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

    _adamw = getattr(torch.optim, "AdamW", None)
    if _adamw is None:
        raise MacroCorrectUnavailableError("torch.optim.AdamW not available")
    transformers.AdamW = _adamw
    _objects = getattr(transformers, "_objects", None)
    if isinstance(_objects, dict) and "AdamW" not in _objects:
        _objects["AdamW"] = _adamw


@lru_cache(maxsize=1)
def _build_token_detector() -> tuple[Callable[[list[str]], Any], str]:
    package_root = _get_package_root()
    config_path = _ensure_local_model_files(
        _resolve_config_path(package_root, settings.paper_check_macro_correct_token_config, _TOKEN_CONFIG_REL)
    )
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
    punct_config_path = _ensure_local_model_files(
        _resolve_config_path(package_root, settings.paper_check_macro_correct_punct_config, _PUNCT_CONFIG_REL)
    )
    _patch_transformers_compat()
    try:
        from macro_correct.predict_csc_punct_zh import MacroCSC4Punct
    except Exception as exc:
        raise MacroCorrectUnavailableError(f"punct detector import failed: {exc}") from exc
    try:
        if "path_config" in inspect.signature(MacroCSC4Punct).parameters:
            detector = MacroCSC4Punct(path_config=str(punct_config_path))
        else:
            detector = MacroCSC4Punct.__new__(MacroCSC4Punct)
            detector.logger = logging.getLogger(__name__)
            detector.path_config = str(punct_config_path)
            load_model = getattr(detector, "load_trained_model", None)
            if not callable(load_model):
                raise MacroCorrectUnavailableError("punct detector cannot load local path_config")
            load_model(path_config=str(punct_config_path))
            if getattr(detector, "model_csc", None) is None:
                raise MacroCorrectUnavailableError("punct detector local model load produced no model")
    except Exception as exc:
        if isinstance(exc, MacroCorrectUnavailableError):
            raise
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

    if len(entrypoints) != 2:
        return {
            "ok": False,
            "detail": "; ".join(details) or "macro-correct token and punct detectors are both required",
            "entrypoints": entrypoints,
        }
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
