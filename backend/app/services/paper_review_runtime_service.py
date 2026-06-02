from __future__ import annotations

import asyncio
import importlib
import importlib.util
import shutil
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


class PaperReviewDependencyError(RuntimeError):
    def __init__(self, message: str, *, runtime_status: dict[str, Any] | None = None):
        super().__init__(message)
        self.runtime_status = runtime_status or {}

    def to_payload(self) -> dict[str, Any]:
        engine_status = list(self.runtime_status.get("engine_status") or [])
        return {
            "error_code": "paper_review_runtime_not_ready",
            "error_message": str(self),
            "runtime_ready": False,
            "runtime_status": self.runtime_status,
            "engine_status": engine_status,
            "missing_engines": [
                {
                    "name": str(item.get("name") or ""),
                    "detail": str(item.get("detail") or ""),
                }
                for item in engine_status
                if not bool(item.get("ok"))
            ],
        }


class PaperReviewRuntimeService:
    ENGINE_NAMES = (
        "enhanced_parser",
        "macro_correct_token",
        "macro_correct_punct",
        "languagetool",
        "vale",
    )

    @classmethod
    async def diagnose(cls, *, load_models: bool = True) -> dict[str, Any]:
        cheap_checks = await asyncio.gather(
            cls._check_enhanced_parser(),
            cls._check_languagetool(),
            cls._check_vale(),
        )
        if load_models:
            model_checks = [
                await cls._check_macro_correct_token(),
                await cls._check_macro_correct_punct(),
            ]
        else:
            model_checks = [
                await cls._check_macro_correct_token_ready(),
                await cls._check_macro_correct_punct_ready(),
            ]
        checks = [cheap_checks[0], *model_checks, *cheap_checks[1:]]
        engines = [cls._engine_from_check(item) for item in checks]
        ok = all(item["ok"] for item in checks)
        return {
            "ok": ok,
            "status": "healthy" if ok else "unhealthy",
            "strict": True,
            "engines_used": list(cls.ENGINE_NAMES),
            "engine_status": engines,
            "message": "paper review runtime ready" if ok else "paper review runtime not ready",
        }

    @classmethod
    def diagnose_sync(cls, *, load_models: bool = True) -> dict[str, Any]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return _run_coro_in_new_loop(cls.diagnose(load_models=load_models))
        return asyncio.run(cls.diagnose(load_models=load_models))

    @classmethod
    async def assert_ready(cls) -> dict[str, Any]:
        status = await cls.diagnose(load_models=True)
        if not status["ok"]:
            detail = "; ".join(
                f"{item['name']}: {item.get('detail') or 'unavailable'}"
                for item in status["engine_status"]
                if not item["ok"]
            )
            raise PaperReviewDependencyError(f"论文检测环境未就绪：{detail}")
        return status

    @staticmethod
    async def _check_enhanced_parser() -> dict[str, Any]:
        checks = await asyncio.gather(
            _check_import("docx", "python-docx"),
            _check_import("lxml", "lxml"),
            _check_import("fitz", "PyMuPDF"),
        )
        ok = all(item["ok"] for item in checks)
        detail = "; ".join(
            f"{item['name']}: {item['detail']}" for item in checks
        )
        return {"name": "enhanced_parser", "ok": ok, "detail": detail}

    @staticmethod
    async def _check_macro_correct_token() -> dict[str, Any]:
        if not settings.paper_check_macro_correct_enabled:
            return {"name": "macro_correct_token", "ok": False, "detail": "disabled but required in strict mode"}
        result = await _run_diagnostic_probe("macro_correct_token", _diagnose_macro_correct_token)
        return {
            "name": "macro_correct_token",
            "ok": bool(result.get("ok")),
            "detail": str(result.get("detail") or ""),
        }

    @staticmethod
    async def _check_macro_correct_token_ready() -> dict[str, Any]:
        return _check_macro_correct_files(
            name="macro_correct_token",
            config_path=str(settings.paper_check_macro_correct_token_config or ""),
        )

    @staticmethod
    async def _check_macro_correct_punct() -> dict[str, Any]:
        if not settings.paper_check_macro_correct_enabled:
            return {"name": "macro_correct_punct", "ok": False, "detail": "disabled but required in strict mode"}
        result = await _run_diagnostic_probe("macro_correct_punct", _diagnose_macro_correct_punct)
        return {
            "name": "macro_correct_punct",
            "ok": bool(result.get("ok")),
            "detail": str(result.get("detail") or ""),
        }

    @staticmethod
    async def _check_macro_correct_punct_ready() -> dict[str, Any]:
        return _check_macro_correct_files(
            name="macro_correct_punct",
            config_path=str(settings.paper_check_macro_correct_punct_config or ""),
        )

    @staticmethod
    async def _check_languagetool() -> dict[str, Any]:
        if not settings.paper_check_languagetool_enabled:
            return {"name": "languagetool", "ok": False, "detail": "disabled but required in strict mode"}
        base_url = str(settings.paper_check_languagetool_url or "").strip().rstrip("/")
        if not base_url:
            return {"name": "languagetool", "ok": False, "detail": "paper_check_languagetool_url is empty"}
        try:
            timeout = httpx.Timeout(float(settings.paper_check_languagetool_timeout_sec or 20))
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                response = await client.post(
                    f"{base_url}/v2/check",
                    data={"text": "测试。", "language": settings.paper_check_languagetool_language},
                )
                response.raise_for_status()
            return {"name": "languagetool", "ok": True, "detail": base_url}
        except Exception as exc:
            return {"name": "languagetool", "ok": False, "detail": str(exc)}

    @staticmethod
    async def _check_vale() -> dict[str, Any]:
        import subprocess

        vale_bin = str(settings.paper_check_vale_bin or "vale").strip() or "vale"
        config_dir = Path(str(settings.paper_check_vale_config_dir or "").strip() or "agent/tools/assets/vale")
        resolved_bin = shutil.which(vale_bin) or vale_bin
        if not shutil.which(vale_bin) and not Path(vale_bin).exists():
            return {"name": "vale", "ok": False, "detail": f"vale executable not found: {vale_bin}"}
        if not config_dir.is_absolute():
            config_dir = Path(__file__).resolve().parents[2] / config_dir
        if not config_dir.exists():
            return {"name": "vale", "ok": False, "detail": f"vale config dir not found: {config_dir}"}
        config_path = config_dir / ".vale.ini"
        if not config_path.exists():
            return {"name": "vale", "ok": False, "detail": f"vale config file not found: {config_path}"}
        styles_dir = config_dir / "styles"
        if not styles_dir.exists():
            return {"name": "vale", "ok": False, "detail": f"vale styles dir not found: {styles_dir}"}
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [resolved_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=float(settings.paper_check_vale_timeout_sec or 20),
                check=False,
            )
            if completed.returncode != 0:
                return {"name": "vale", "ok": False, "detail": (completed.stderr or completed.stdout).strip()}
            return {"name": "vale", "ok": True, "detail": completed.stdout.strip() or str(config_dir)}
        except Exception as exc:
            return {"name": "vale", "ok": False, "detail": str(exc)}

    @staticmethod
    def _engine_from_check(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(item.get("name") or ""),
            "ok": bool(item.get("ok")),
            "detail": str(item.get("detail") or ""),
        }


def _diagnose_macro_correct_token() -> dict[str, Any]:
    from agent.tools.paper_review_macro_correct import MacroCorrectUnavailableError, _build_token_detector

    try:
        detector, entrypoint = _build_token_detector()
        return {
            "ok": True,
            "detail": entrypoint,
            "entrypoint": entrypoint,
        }
    except MacroCorrectUnavailableError as exc:
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "detail": f"macro_correct_token probe failed: {exc}"}


def _diagnose_macro_correct_punct() -> dict[str, Any]:
    from agent.tools.paper_review_macro_correct import MacroCorrectUnavailableError, _build_punct_detector

    try:
        detector, entrypoint = _build_punct_detector()
        return {
            "ok": True,
            "detail": entrypoint,
            "entrypoint": entrypoint,
        }
    except MacroCorrectUnavailableError as exc:
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "detail": f"macro_correct_punct probe failed: {exc}"}


async def _check_import(module_name: str, display_name: str) -> dict[str, Any]:
    try:
        importlib.import_module(module_name)
        return {"name": display_name, "ok": True, "detail": "installed"}
    except Exception as exc:
        return {"name": display_name, "ok": False, "detail": str(exc)}


def _check_macro_correct_files(*, name: str, config_path: str) -> dict[str, Any]:
    if not settings.paper_check_macro_correct_enabled:
        return {"name": name, "ok": False, "detail": "disabled but required in strict mode"}
    if importlib.util.find_spec("macro_correct") is None:
        return {"name": name, "ok": False, "detail": "macro_correct package not installed"}
    configured_path = config_path.strip()
    if not configured_path:
        return {"name": name, "ok": False, "detail": f"{name} config path is empty"}
    path = Path(configured_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    model_path = path.parent / "pytorch_model.bin"
    if not path.exists():
        return {"name": name, "ok": False, "detail": f"config file not found: {path}"}
    if not model_path.exists():
        return {"name": name, "ok": False, "detail": f"model file not found: {model_path}"}
    return {"name": name, "ok": True, "detail": f"package and local model files ready: {path.parent}"}


async def _run_diagnostic_probe(name: str, probe) -> dict[str, Any]:
    timeout_sec = max(1.0, float(settings.paper_check_engine_timeout_sec or 20))
    try:
        return await asyncio.wait_for(asyncio.to_thread(probe), timeout=timeout_sec)
    except asyncio.TimeoutError:
        return {"ok": False, "detail": f"{name} diagnose timed out after {timeout_sec:g}s"}


def _run_coro_in_new_loop(coro) -> dict[str, Any]:
    import threading

    result: dict[str, Any] = {}
    error: list[Exception] = []

    def runner() -> None:
        nonlocal result
        try:
            result = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - defensive
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result
