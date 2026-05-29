from __future__ import annotations

import time

import pytest

from app.services.paper_review_runtime_service import PaperReviewRuntimeService


@pytest.mark.asyncio
async def test_runtime_marks_pycorrector_unhealthy_when_probe_fails(monkeypatch):
    async def _ok_docx():
        return {"name": "docx", "ok": True, "detail": "installed"}

    async def _ok_lxml():
        return {"name": "lxml", "ok": True, "detail": "installed"}

    async def _ok_macro():
        return {"name": "macro_correct", "ok": True, "detail": "installed"}

    async def _ok_languagetool():
        return {"name": "languagetool", "ok": True, "detail": "http://127.0.0.1:8010"}

    async def _ok_vale():
        return {"name": "vale", "ok": True, "detail": "vale 3"}

    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_python_docx",
        staticmethod(_ok_docx),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_lxml",
        staticmethod(_ok_lxml),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct",
        staticmethod(_ok_macro),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_languagetool",
        staticmethod(_ok_languagetool),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_vale",
        staticmethod(_ok_vale),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.diagnose_pycorrector",
        lambda: {"ok": False, "detail": "Corrector init failed: missing kenlm"},
    )

    status = await PaperReviewRuntimeService.diagnose()

    assert status["ok"] is False
    pycorrector_status = next(item for item in status["engine_status"] if item["name"] == "pycorrector")
    assert pycorrector_status["ok"] is False
    assert "kenlm" in pycorrector_status["detail"]


@pytest.mark.asyncio
async def test_runtime_marks_macro_correct_unhealthy_when_probe_fails(monkeypatch):
    async def _ok_docx():
        return {"name": "docx", "ok": True, "detail": "installed"}

    async def _ok_lxml():
        return {"name": "lxml", "ok": True, "detail": "installed"}

    async def _ok_languagetool():
        return {"name": "languagetool", "ok": True, "detail": "http://127.0.0.1:8010"}

    async def _ok_vale():
        return {"name": "vale", "ok": True, "detail": "vale 3"}

    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_python_docx",
        staticmethod(_ok_docx),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_lxml",
        staticmethod(_ok_lxml),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_languagetool",
        staticmethod(_ok_languagetool),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_vale",
        staticmethod(_ok_vale),
    )
    monkeypatch.setattr(
        "agent.tools.paper_review_pycorrector.diagnose_pycorrector",
        lambda: {"ok": True, "detail": "pycorrector.correct"},
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.diagnose_macro_correct",
        lambda: {"ok": False, "detail": "token detector init failed: missing AdamW"},
    )

    status = await PaperReviewRuntimeService.diagnose()

    assert status["ok"] is False
    macro_status = next(item for item in status["engine_status"] if item["name"] == "macro_correct")
    assert macro_status["ok"] is False
    assert "AdamW" in macro_status["detail"]


@pytest.mark.asyncio
async def test_runtime_marks_optional_engine_unhealthy_when_probe_times_out(monkeypatch):
    async def _ok_docx():
        return {"name": "docx", "ok": True, "detail": "installed"}

    async def _ok_lxml():
        return {"name": "lxml", "ok": True, "detail": "installed"}

    async def _ok_macro():
        return {"name": "macro_correct", "ok": True, "detail": "installed"}

    async def _ok_languagetool():
        return {"name": "languagetool", "ok": True, "detail": "http://127.0.0.1:8010"}

    async def _ok_vale():
        return {"name": "vale", "ok": True, "detail": "vale 3"}

    monkeypatch.setattr("app.core.config.settings.paper_check_engine_timeout_sec", 1)
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_python_docx",
        staticmethod(_ok_docx),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_lxml",
        staticmethod(_ok_lxml),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct",
        staticmethod(_ok_macro),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_languagetool",
        staticmethod(_ok_languagetool),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_vale",
        staticmethod(_ok_vale),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.diagnose_pycorrector",
        lambda: time.sleep(5),
    )

    started = time.monotonic()
    status = await PaperReviewRuntimeService.diagnose()

    assert time.monotonic() - started < 3
    assert status["ok"] is False
    pycorrector_status = next(item for item in status["engine_status"] if item["name"] == "pycorrector")
    assert pycorrector_status["ok"] is False
    assert "timed out" in pycorrector_status["detail"]


def test_pycorrector_defaults_to_local_corrector(monkeypatch):
    from agent.tools import paper_review_pycorrector

    paper_review_pycorrector._build_corrector.cache_clear()

    class FakeCorrector:
        def correct(self, text: str):
            return {"source": text, "target": text, "errors": []}

    class FailingMacBert:
        def __init__(self, *args, **kwargs):
            raise AssertionError("MacBert should not be initialized by default")

    fake_module = type(
        "FakePycorrector",
        (),
        {
            "Corrector": FakeCorrector,
            "MacBertCorrector": FailingMacBert,
        },
    )

    monkeypatch.setattr("app.core.config.settings.paper_check_pycorrector_entrypoint", "corrector")
    monkeypatch.setitem(__import__("sys").modules, "pycorrector", fake_module)

    correct, entrypoint = paper_review_pycorrector._build_corrector()

    assert entrypoint == "pycorrector.Corrector.correct"
    assert correct("abc")["errors"] == []
    paper_review_pycorrector._build_corrector.cache_clear()


def test_pycorrector_macbert_entrypoint_requires_local_model_dir(monkeypatch):
    from agent.tools import paper_review_pycorrector

    paper_review_pycorrector._build_corrector.cache_clear()

    class FakeMacBertCorrector:
        def __init__(self, model_name_or_path: str):
            self.model_name_or_path = model_name_or_path

        def correct(self, text: str):
            return {"source": text, "target": text, "errors": []}

    fake_module = type(
        "FakePycorrector",
        (),
        {
            "Corrector": object,
            "MacBertCorrector": FakeMacBertCorrector,
        },
    )

    monkeypatch.setattr("app.core.config.settings.paper_check_pycorrector_entrypoint", "macbert_local")
    monkeypatch.setattr("app.core.config.settings.paper_check_pycorrector_model_dir", "/opt/piap-paper-assets/macro_correct/token")
    monkeypatch.setitem(__import__("sys").modules, "pycorrector", fake_module)

    correct, entrypoint = paper_review_pycorrector._build_corrector()

    assert entrypoint == "pycorrector.MacBertCorrector.macbert_correct"
    assert correct("abc")["errors"] == []
    paper_review_pycorrector._build_corrector.cache_clear()


def test_macro_correct_requires_local_model_files(monkeypatch, tmp_path):
    from agent.tools import paper_review_macro_correct

    package_root = tmp_path / "macro_correct"
    package_root.mkdir()
    config_path = package_root / "output" / "text_correction" / "macbert4mdcspell_v3" / "csc.config"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_token_config", "")

    with pytest.raises(paper_review_macro_correct.MacroCorrectUnavailableError):
        paper_review_macro_correct._ensure_local_model_files(config_path)

    (config_path.parent / "pytorch_model.bin").write_bytes(b"model")

    assert paper_review_macro_correct._ensure_local_model_files(config_path) == config_path
