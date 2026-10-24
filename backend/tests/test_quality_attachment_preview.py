from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import hashlib

import pymupdf
import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.services.quality_attachment_preview import render_attachment_page
from app.api.v1.quality_risk import preview_quality_attachment


def original():
    with pymupdf.open() as document:
        document.new_page().insert_text((50, 50), 'Original report 30.8 km/h')
        document.new_page().insert_text((50, 50), 'Original second page 73 dB(A)')
        content = document.tobytes()
    return content, hashlib.sha256(content).hexdigest()


def test_render_retains_original_and_bounds_image_dimensions():
    content, digest = original()
    image, count = render_attachment_page(content, digest, 2)
    assert count == 2 and image.startswith(b'\x89PNG\r\n\x1a\n')
    assert max(pymupdf.Pixmap(image).width, pymupdf.Pixmap(image).height) <= 1800
    assert hashlib.sha256(content).hexdigest() == digest


def test_rejects_changed_original_missing_digest_invalid_page_or_invalid_pdf():
    content, digest = original()
    for expected in ['', 'wrong-digest']:
        with pytest.raises(ConflictError): render_attachment_page(content, expected, 1)
    for page in [0, 3]:
        with pytest.raises(ValidationError): render_attachment_page(content, digest, page)
    invalid = b'not a PDF'
    with pytest.raises(ValidationError): render_attachment_page(invalid, hashlib.sha256(invalid).hexdigest(), 1)


@pytest.mark.asyncio
async def test_endpoint_checks_access_before_storage_and_returns_private_original_image():
    content, digest = original()
    svc = SimpleNamespace(require_intake=Mock(), accessible_attachment=AsyncMock(return_value=SimpleNamespace(bucket='private', object_key='original', sha256=digest)), storage=SimpleNamespace(get_bytes=Mock(return_value=(content, 'application/pdf'))))
    result = await preview_quality_attachment('attachment', 1, svc)
    svc.require_intake.assert_called_once()
    svc.accessible_attachment.assert_awaited_once_with('attachment')
    assert result.media_type == 'image/png'
    assert result.headers['x-pdf-page-count'] == '2'
    assert result.headers['cache-control'] == 'private, no-store'
    assert result.headers['x-original-sha256'] == digest
    svc.storage.get_bytes.reset_mock()
    svc.accessible_attachment.side_effect = ForbiddenError('another organization or withdrawn attachment')
    with pytest.raises(ForbiddenError): await preview_quality_attachment('attachment', 1, svc)
    svc.storage.get_bytes.assert_not_called()


@pytest.mark.asyncio
async def test_missing_stored_file_is_explicit():
    svc = SimpleNamespace(require_intake=Mock(), accessible_attachment=AsyncMock(return_value=SimpleNamespace(bucket='private', object_key='missing', sha256='hash')), storage=SimpleNamespace(get_bytes=Mock(return_value=None)))
    with pytest.raises(NotFoundError): await preview_quality_attachment('attachment', 1, svc)
