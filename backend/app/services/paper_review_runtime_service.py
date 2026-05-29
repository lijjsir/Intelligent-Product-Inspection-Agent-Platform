from __future__ import annotations

import asyncio
import importlib
import shutil
from pathlib import Path
from typing import Any

import httpx

from agent.tools.paper_review_macro_correct import diagnose_macro_correct
from agent.tools.paper_review_pycorrector import diagnose_pycorrector
from app.core.config import settings


class PaperReviewDependencyError(RuntimeError):
    pass


class PaperReviewRuntimeService:
    ENGINE_NAMES = ("rule", "pycorrector", "macro_correct", "languagetool", "vale")

    @classmethod
    async def diagnose(cls) -> dict[str, Any]:
        checks = await asyncio.gather(
            cls._check_python_docx(),
            cls._check_lxml(),
            cls._check_pycorrector(),
            cls._check_macro_correct(),
            cls._check_languagetool(),
            cls._check_vale(),
        )
        engines = [cls._engine_from_check(item) for item in checks]
        ok = all(item["ok"] for item in checks)
        return {
            "ok": ok,
            "status": "healthy" if ok else "unhealthy",
            "engines_used": list(cls.ENGINE_NAMES),
            "engine_status": engines,
            "message": "paper review runtime ready" if ok else "paper review runtime not ready",
        }

    @classmethod
    def diagnose_sync(cls) -> dict[str, Any]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return _run_coro_in_new_loop(cls.diagnose())
        return asyncio.run(cls.diagnose())

    @classmethod
    async def assert_ready(cls) -> dict[str, Any]:
        status = await cls.diagnose()
        if not status["ok"]:
            detail = "; ".join(
                f"{item['name']}: {item.get('detail') or 'unavailable'}"
                for item in status["engine_status"]
                if not item["ok"]
            )
            raise PaperReviewDependencyError(f"论文检测环境未就绪：{detail}")
        return status

    @staticmethod
    async def _check_python_docx() -> dict[str, Any]:
        return await _check_import("docx", "python-docx")

    @staticmethod
    async def _check_lxml() -> dict[str, Any]:
        return await _check_import("lxml", "lxml")

    @staticmethod
    async def _check_pycorrector() -> dict[str, Any]:
        if not settings.paper_check_pycorrector_enabled:
            return {"name": "pycorrector", "ok": True, "detail": "disabled by config"}
        result = await asyncio.to_thread(diagnose_pycorrector)
        return {
            "name": "pycorrector",
            "ok": bool(result.get("ok")),
            "detail": str(result.get("detail") or ""),
        }

    @staticmethod
    async def _check_macro_correct() -> dict[str, Any]:
        if not settings.paper_check_macro_correct_enabled:
            return {"name": "macro_correct", "ok": True, "detail": "disabled by config"}
        result = await asyncio.to_thread(diagnose_macro_correct)
        if result.get("ok"):
            return {
                "name": "macro_correct",
                "ok": True,
                "detail": str(result.get("detail") or ""),
            }
        return {
            "name": "macro_correct",
            "ok": False,
            "detail": str(result.get("detail") or "missing python package macro-correct"),
        }

    @staticmethod
    async def _check_languagetool() -> dict[str, Any]:
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
        vale_bin = str(settings.paper_check_vale_bin or "vale").strip() or "vale"
        config_dir = Path(str(settings.paper_check_vale_config_dir or "").strip() or "agent/tools/assets/vale")
        resolved_bin = shutil.which(vale_bin) or vale_bin
        if not shutil.which(vale_bin) and not Path(vale_bin).exists():
            return {"name": "vale", "ok": False, "detail": f"vale executable not found: {vale_bin}"}
        if not config_dir.is_absolute():
            config_dir = Path(__file__).resolve().parents[2] / config_dir
        if not config_dir.exists():
            return {"name": "vale", "ok": False, "detail": f"vale config dir not found: {config_dir}"}
        try:
            proc = await asyncio.create_subprocess_exec(
                resolved_bin,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(settings.paper_check_vale_timeout_sec or 20),
            )
            if proc.returncode != 0:
                return {"name": "vale", "ok": False, "detail": (stderr or stdout).decode("utf-8", errors="ignore").strip()}
            return {"name": "vale", "ok": True, "detail": stdout.decode("utf-8", errors="ignore").strip() or str(config_dir)}
        except Exception as exc:
            return {"name": "vale", "ok": False, "detail": str(exc)}

    @staticmethod
    def _engine_from_check(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(item.get("name") or ""),
            "ok": bool(item.get("ok")),
            "detail": str(item.get("detail") or ""),
        }


async def _check_import(module_name: str, display_name: str, *, quiet: bool = False) -> dict[str, Any]:
    try:
        importlib.import_module(module_name)
        return {"name": display_name if quiet else module_name, "ok": True, "detail": "installed"}
    except Exception as exc:
        return {"name": display_name if quiet else module_name, "ok": False, "detail": str(exc)}


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
