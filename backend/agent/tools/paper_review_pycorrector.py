from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable

from app.core.config import settings


class PycorrectorUnavailableError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _build_corrector() -> tuple[Callable[[str], Any], str]:
    try:
        import pycorrector
    except Exception as exc:  # pragma: no cover - import path depends on env
        raise PycorrectorUnavailableError(f"import failed: {exc}") from exc

    entrypoint = str(settings.paper_check_pycorrector_entrypoint or "corrector").strip().lower()
    if entrypoint in {"corrector", "local", "classic"}:
        return _build_local_corrector(pycorrector)
    if entrypoint in {"module", "function"}:
        module_correct = getattr(pycorrector, "correct", None)
        if callable(module_correct):
            return module_correct, "pycorrector.correct"
        return _build_local_corrector(pycorrector)
    if entrypoint in {"macbert", "macbert_local"}:
        return _build_macbert_corrector(pycorrector)

    raise PycorrectorUnavailableError(f"unsupported pycorrector entrypoint: {entrypoint}")


def _build_macbert_corrector(pycorrector: Any) -> tuple[Callable[[str], Any], str]:
    model_dir = str(settings.paper_check_pycorrector_model_dir or "").strip()
    if not model_dir:
        raise PycorrectorUnavailableError("MacBert entrypoint requires local paper_check_pycorrector_model_dir")
    macbert_cls = getattr(pycorrector, "MacBertCorrector", None)
    if macbert_cls is None:
        raise PycorrectorUnavailableError("missing pycorrector.MacBertCorrector")
    try:
        instance = macbert_cls(model_name_or_path=model_dir)
    except Exception as exc:
        raise PycorrectorUnavailableError(f"MacBertCorrector init failed: {exc}") from exc
    correct = getattr(instance, "macbert_correct", None) or getattr(instance, "correct", None)
    if callable(correct):
        return correct, "pycorrector.MacBertCorrector.macbert_correct"
    raise PycorrectorUnavailableError("MacBertCorrector has no callable macbert_correct/correct")


def _build_local_corrector(pycorrector: Any) -> tuple[Callable[[str], Any], str]:
    corrector_cls = getattr(pycorrector, "Corrector", None)
    if corrector_cls is None:
        raise PycorrectorUnavailableError("missing pycorrector.Corrector")

    try:
        instance = corrector_cls()
    except Exception as exc:
        raise PycorrectorUnavailableError(f"Corrector init failed: {exc}") from exc

    correct = getattr(instance, "correct", None)
    if not callable(correct):
        raise PycorrectorUnavailableError("pycorrector Corrector has no callable correct()")
    return correct, "pycorrector.Corrector.correct"


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
