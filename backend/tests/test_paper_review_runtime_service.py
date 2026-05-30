from __future__ import annotations

import subprocess
import time

import pytest

from app.services.paper_review_runtime_service import PaperReviewRuntimeService


@pytest.mark.asyncio
async def test_runtime_marks_pycorrector_unhealthy_when_probe_fails(monkeypatch):
    async def _ok_enhanced_parser():
        return {"name": "enhanced_parser", "ok": True, "detail": "python-docx: installed; lxml: installed; PyMuPDF: installed"}

    async def _ok_macro_token():
        return {"name": "macro_correct_token", "ok": True, "detail": "macro_correct.MacroCSC4Token.func_csc_token_batch"}

    async def _ok_macro_punct():
        return {"name": "macro_correct_punct", "ok": True, "detail": "macro_correct.MacroCSC4Punct.func_csc_punct_batch"}

    async def _ok_languagetool():
        return {"name": "languagetool", "ok": True, "detail": "http://127.0.0.1:8010"}

    async def _ok_vale():
        return {"name": "vale", "ok": True, "detail": "vale 3"}

    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_enhanced_parser",
        staticmethod(_ok_enhanced_parser),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct_token",
        staticmethod(_ok_macro_token),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct_punct",
        staticmethod(_ok_macro_punct),
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
        lambda: {"ok": False, "detail": "Corrector init failed: missing kenlm"},
    )

    status = await PaperReviewRuntimeService.diagnose()

    assert status["ok"] is False
    assert status["strict"] is True
    pycorrector_status = next(item for item in status["engine_status"] if item["name"] == "pycorrector")
    assert pycorrector_status["ok"] is False
    assert "kenlm" in pycorrector_status["detail"]


@pytest.mark.asyncio
async def test_runtime_marks_macro_correct_token_unhealthy_when_probe_fails(monkeypatch):
    async def _ok_enhanced_parser():
        return {"name": "enhanced_parser", "ok": True, "detail": "python-docx: installed; lxml: installed; PyMuPDF: installed"}

    async def _ok_macro_punct():
        return {"name": "macro_correct_punct", "ok": True, "detail": "macro_correct.MacroCSC4Punct.func_csc_punct_batch"}

    async def _ok_languagetool():
        return {"name": "languagetool", "ok": True, "detail": "http://127.0.0.1:8010"}

    async def _ok_vale():
        return {"name": "vale", "ok": True, "detail": "vale 3"}

    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_enhanced_parser",
        staticmethod(_ok_enhanced_parser),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct_punct",
        staticmethod(_ok_macro_punct),
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
        "app.services.paper_review_runtime_service._diagnose_macro_correct_token",
        lambda: {"ok": False, "detail": "token detector init failed: missing AdamW"},
    )

    status = await PaperReviewRuntimeService.diagnose()

    assert status["ok"] is False
    macro_status = next(item for item in status["engine_status"] if item["name"] == "macro_correct_token")
    assert macro_status["ok"] is False
    assert "AdamW" in macro_status["detail"]


@pytest.mark.asyncio
async def test_runtime_marks_optional_engine_unhealthy_when_probe_times_out(monkeypatch):
    async def _ok_enhanced_parser():
        return {"name": "enhanced_parser", "ok": True, "detail": "python-docx: installed; lxml: installed; PyMuPDF: installed"}

    async def _ok_macro_token():
        return {"name": "macro_correct_token", "ok": True, "detail": "macro_correct.MacroCSC4Token.func_csc_token_batch"}

    async def _ok_macro_punct():
        return {"name": "macro_correct_punct", "ok": True, "detail": "macro_correct.MacroCSC4Punct.func_csc_punct_batch"}

    async def _ok_languagetool():
        return {"name": "languagetool", "ok": True, "detail": "http://127.0.0.1:8010"}

    async def _ok_vale():
        return {"name": "vale", "ok": True, "detail": "vale 3"}

    monkeypatch.setattr("app.core.config.settings.paper_check_engine_timeout_sec", 1)
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_enhanced_parser",
        staticmethod(_ok_enhanced_parser),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct_token",
        staticmethod(_ok_macro_token),
    )
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService._check_macro_correct_punct",
        staticmethod(_ok_macro_punct),
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


def test_macro_correct_punct_uses_config_without_constructor_download(monkeypatch, tmp_path):
    from agent.tools import paper_review_macro_correct

    paper_review_macro_correct._build_punct_detector.cache_clear()
    package_root = tmp_path / "macro_correct"
    package_root.mkdir()
    config_path = tmp_path / "assets" / "punct" / "sl.config"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    (config_path.parent / "pytorch_model.bin").write_bytes(b"model")
    loaded_paths: list[str] = []

    class FakePunct:
        def __init__(self):
            raise AssertionError("constructor would trigger package default download")

        def load_trained_model(self, path_config=None):
            loaded_paths.append(str(path_config))
            self.model_csc = object()

        def func_csc_punct_batch(self, texts):
            return [{"errors": []} for _ in texts]

    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_punct_config", str(config_path))
    monkeypatch.setattr(paper_review_macro_correct, "_get_package_root", lambda: package_root)
    monkeypatch.setitem(
        __import__("sys").modules,
        "macro_correct.predict_csc_punct_zh",
        type("FakePunctModule", (), {"MacroCSC4Punct": FakePunct}),
    )

    batch, entrypoint = paper_review_macro_correct._build_punct_detector()

    assert entrypoint == "macro_correct.MacroCSC4Punct.func_csc_punct_batch"
    assert loaded_paths == [str(config_path)]
    assert batch(["文本"]) == [{"errors": []}]
    paper_review_macro_correct._build_punct_detector.cache_clear()


def test_macro_correct_diagnose_requires_token_and_punct(monkeypatch):
    from agent.tools import paper_review_macro_correct

    monkeypatch.setattr(
        paper_review_macro_correct,
        "_build_token_detector",
        lambda: (lambda texts: [], "macro_correct.MacroCSC4Token.func_csc_token_batch"),
    )

    def missing_punct():
        raise paper_review_macro_correct.MacroCorrectUnavailableError("punct config missing")

    monkeypatch.setattr(paper_review_macro_correct, "_build_punct_detector", missing_punct)

    status = paper_review_macro_correct.diagnose_macro_correct()

    assert status["ok"] is False
    assert status["entrypoints"] == ["macro_correct.MacroCSC4Token.func_csc_token_batch"]
    assert "punct config missing" in status["detail"]


@pytest.mark.asyncio
async def test_runtime_vale_check_requires_config_file(monkeypatch, tmp_path):
    vale_bin = tmp_path / "vale"
    vale_bin.write_text("", encoding="utf-8")
    config_dir = tmp_path / "vale-config"
    config_dir.mkdir()

    monkeypatch.setattr("app.core.config.settings.paper_check_vale_bin", str(vale_bin))
    monkeypatch.setattr("app.core.config.settings.paper_check_vale_config_dir", str(config_dir))
    monkeypatch.setattr("shutil.which", lambda value: None)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="vale version 3", stderr=""),
    )

    status = await PaperReviewRuntimeService._check_vale()

    assert status["ok"] is False
    assert ".vale.ini" in status["detail"]


@pytest.mark.asyncio
async def test_runtime_vale_check_requires_styles_dir(monkeypatch, tmp_path):
    vale_bin = tmp_path / "vale"
    vale_bin.write_text("", encoding="utf-8")
    config_dir = tmp_path / "vale-config"
    config_dir.mkdir()
    (config_dir / ".vale.ini").write_text("StylesPath = styles\n", encoding="utf-8")

    monkeypatch.setattr("app.core.config.settings.paper_check_vale_bin", str(vale_bin))
    monkeypatch.setattr("app.core.config.settings.paper_check_vale_config_dir", str(config_dir))
    monkeypatch.setattr("shutil.which", lambda value: None)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="vale version 3", stderr=""),
    )

    status = await PaperReviewRuntimeService._check_vale()

    assert status["ok"] is False
    assert "styles" in status["detail"]
