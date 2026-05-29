from __future__ import annotations

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
        "agent.tools.paper_review_pycorrector.diagnose_pycorrector",
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
