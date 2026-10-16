from pathlib import Path

import pytest

from agent.tools.file_parsers import parse_pdf_bytes


def pdf_reader(monkeypatch, texts, images=True):
    class Page:
        def __init__(self, text):
            self.text = text
            self.images = ["scan"] if images else []
        def extract_text(self):
            return self.text
    class Reader:
        pages = [Page(text) for text in texts]
    monkeypatch.setattr("pypdf.PdfReader", lambda _: Reader())


def test_image_only_report_uses_ocr_and_retains_original_page_numbers(monkeypatch):
    pdf_reader(monkeypatch, ["", ""])
    paths = []
    def ocr(path, *, page_number):
        assert Path(path).exists()
        paths.append(Path(path))
        return f"第{page_number}页 实际检验结果"
    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", ocr)
    parsed = parse_pdf_bytes(b"fixture bytes")
    assert [page["page_no"] for page in parsed["pages"]] == [1, 2]
    assert parsed["pages"][0]["extraction_method"] == "ocr"
    assert "实际检验结果" in parsed["text"]
    assert not paths[0].exists()


def test_text_pdf_does_not_call_ocr(monkeypatch):
    pdf_reader(monkeypatch, ["可读取的标准正文"])
    def unexpected(*args, **kwargs):
        raise AssertionError("text PDF should not call OCR")
    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", unexpected)
    assert parse_pdf_bytes(b"fixture bytes")["layout"]["parser"] == "pypdf"


def test_mixed_pdf_preserves_text_pages_and_recovers_only_missing_scan_pages(monkeypatch):
    pdf_reader(monkeypatch, ["原始数字正文", ""])
    called = []
    def ocr(path, *, page_number):
        called.append(page_number)
        return "扫描的检测数据"
    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", ocr)
    parsed = parse_pdf_bytes(b"fixture bytes")
    assert called == [2]
    assert parsed["pages"][0]["text"] == "原始数字正文"
    assert parsed["pages"][0]["extraction_method"] == "text_layer"
    assert parsed["pages"][1]["extraction_method"] == "ocr"


def test_ocr_failure_is_explicit_and_does_not_return_empty_success(monkeypatch):
    pdf_reader(monkeypatch, [""])
    def missing(*args, **kwargs):
        raise RuntimeError("missing OCR dependency")
    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", missing)
    with pytest.raises(ValueError, match="OCR"):
        parse_pdf_bytes(b"fixture bytes")


def test_native_text_does_not_hide_failed_scan_recovery(monkeypatch):
    pdf_reader(monkeypatch, ["封面有文字", ""])
    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", lambda *args, **kwargs: "")
    with pytest.raises(ValueError, match="未识别"):
        parse_pdf_bytes(b"fixture bytes")


def test_oversized_scan_is_not_processed_synchronously(monkeypatch):
    pdf_reader(monkeypatch, [""] * 21)
    with pytest.raises(ValueError, match="20页"):
        parse_pdf_bytes(b"fixture bytes")
