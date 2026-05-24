from __future__ import annotations

from typing import Protocol

from app.services.report_renderers.pdf_renderer import PdfRenderer


class ReportRenderer(Protocol):
    def render(self, data: dict) -> bytes:
        ...


def build_renderer(format: str) -> ReportRenderer:
    fmt = str(format or "").strip().lower()
    if fmt == "pdf":
        return PdfRenderer()
    raise ValueError(f"unsupported export format: {format}")
