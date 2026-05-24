from __future__ import annotations

from typing import Protocol


class ReportRenderer(Protocol):
    def render(self, data: dict) -> bytes:
        ...


def build_renderer(format: str) -> ReportRenderer:
    fmt = str(format or "").strip().lower()
    if fmt == "pdf":
        try:
            from app.services.report_renderers.pdf_renderer import PdfRenderer
        except ModuleNotFoundError as exc:
            if exc.name == "reportlab":
                raise RuntimeError("PDF 导出依赖未安装：缺少 reportlab，请先安装后端新增依赖") from exc
            raise
        return PdfRenderer()
    raise ValueError(f"unsupported export format: {format}")
