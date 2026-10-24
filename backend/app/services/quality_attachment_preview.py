"""Render the authenticated stored PDF without OCR or rewriting its contents."""
from __future__ import annotations

import hashlib

from app.core.exceptions import ConflictError, ValidationError


def render_attachment_page(content: bytes, expected_sha256: str, page_number: int) -> tuple[bytes, int]:
    if not expected_sha256 or hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ConflictError("附件原件校验不一致，请重新核对原始文件")
    import pymupdf
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise ValidationError("此附件无法作为 PDF 预览，请下载核对原件") from exc
    with document:
        if document.needs_pass:
            raise ValidationError("此 PDF 需要密码，请下载后核对")
        count = len(document)
        if page_number < 1 or page_number > count:
            raise ValidationError("原 PDF 页码超出范围")
        page = document[page_number - 1]
        scale = min(2.0, 1800 / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png"), count
