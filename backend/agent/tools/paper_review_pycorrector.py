from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings


class PycorrectorUnavailableError(RuntimeError):
    pass


def _resolve_pycorrector_data_dir() -> Path:
    data_dir = str(settings.paper_check_pycorrector_data_dir or "").strip()
    if data_dir:
        resolved = Path(data_dir)
        if not resolved.is_absolute():
            resolved = Path(__file__).resolve().parents[2] / resolved
        return resolved
    return Path.home() / ".pycorrector" / "datasets"


def _configure_pycorrector_env() -> dict[str, Any]:
    resolved_data_dir = _resolve_pycorrector_data_dir()
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PYCORRECTOR_DATA_DIR"] = str(resolved_data_dir)

    kwargs: dict[str, Any] = {}
    language_model = str(settings.paper_check_pycorrector_language_model or "").strip()
    if language_model:
        model_path = Path(language_model)
        if not model_path.is_absolute():
            model_path = resolved_data_dir / language_model
        kwargs["language_model_path"] = str(model_path)
    return kwargs


@lru_cache(maxsize=1)
def _build_corrector() -> tuple[Callable[[str], Any], str]:
    corrector_kwargs = _configure_pycorrector_env()
    try:
        import pycorrector
    except Exception as exc:  # pragma: no cover - import path depends on env
        raise PycorrectorUnavailableError(f"import failed: {exc}") from exc

    corrector_cls = getattr(pycorrector, "Corrector", None)
    if corrector_cls is not None:
        try:
            instance = corrector_cls(**corrector_kwargs)
        except Exception as exc:
            raise PycorrectorUnavailableError(f"Corrector init failed: {exc}") from exc

        correct = getattr(instance, "correct", None)
        if not callable(correct):
            raise PycorrectorUnavailableError("pycorrector Corrector has no callable correct()")
        return correct, "pycorrector.Corrector.correct"

    module_correct = getattr(pycorrector, "correct", None)
    if callable(module_correct):
        return module_correct, "pycorrector.correct"

    raise PycorrectorUnavailableError("missing pycorrector.Corrector")


def diagnose_pycorrector() -> dict[str, Any]:
    try:
        correct, entrypoint = _build_corrector()
        sample = correct("这是一个测试。")
        errors = normalize_pycorrector_errors(sample)
        return {
            "ok": True,
            "detail": entrypoint,
            "entrypoint": entrypoint,
            "sample_error_count": len(errors),
        }
    except PycorrectorUnavailableError as exc:
        return {
            "ok": False,
            "detail": str(exc),
        }
    except Exception as exc:  # pragma: no cover - runtime dependency behavior
        return {
            "ok": False,
            "detail": f"correct() probe failed: {exc}",
        }


def run_pycorrector(text: str) -> tuple[Any, str]:
    correct, entrypoint = _build_corrector()
    return correct(text), entrypoint


def normalize_pycorrector_errors(result: Any) -> list[tuple[str, str, int, int]]:
    if isinstance(result, dict):
        items = result.get("errors") or []
        normalized: list[tuple[str, str, int, int]] = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            wrong = str(item[0])
            right = str(item[1])
            begin = int(item[2])
            end = begin + len(wrong)
            normalized.append((wrong, right, begin, end))
        return normalized

    if isinstance(result, tuple) and len(result) >= 2:
        items = result[1] or []
        normalized = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) < 4:
                continue
            wrong = str(item[0])
            right = str(item[1])
            begin = int(item[2])
            end = int(item[3])
            normalized.append((wrong, right, begin, end))
        return normalized

    return []
