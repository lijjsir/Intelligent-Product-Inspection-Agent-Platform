from pathlib import Path
from uuid import UUID
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.services.standard_pdf_importer import (
    build_index_docs,
    build_point_id,
    StandardPdfImporter,
    is_unreadable_pdf_text,
    normalize_standard_no,
    repair_unreadable_pdf_pages_with_ocr,
    resolve_standard_meta,
    split_text_to_chunks,
)


def test_resolve_standard_meta_uses_registry_for_downloaded_pdf_names():
    meta = resolve_standard_meta(Path("standard/current/ceramic/GB-T-3301-2023.pdf"))

    assert meta["standard_no"] == "GB/T 3301-2023"
    assert meta["standard_name"] == "日用陶瓷器规格误差和缺陷尺寸的测定方法"
    assert meta["domain"] == "日用陶瓷"
    assert meta["product_category"] == "日用陶瓷器"
    assert "裂纹" in meta["image_defect_keywords"]


def test_normalize_standard_no_handles_gbt_download_file_names():
    assert normalize_standard_no("6544-2008-gbt-e-300.pdf") == "GB/T 6544-2008"
    assert normalize_standard_no("GB-18401-2010.pdf") == "GB 18401-2010"
    assert normalize_standard_no("GB-17761-2024.pdf") == "GB 17761-2024"
    assert normalize_standard_no("GB-43854-2024.pdf") == "GB 43854-2024"
    assert normalize_standard_no("GB-4351-2023.pdf") == "GB 4351-2023"
    assert normalize_standard_no("report-1234-2026.pdf") == "report-1234-2026"


def test_uploaded_standard_metadata_uses_original_filename_instead_of_tempfile():
    meta = resolve_standard_meta(Path("/tmp/tmp-random-upload.pdf"), source_file_name="GB-T-3532-2022.pdf")
    assert meta["standard_no"] == "GB/T 3532-2022"
    assert meta["standard_name"] == "日用瓷器"
    unverified = resolve_standard_meta(Path("/tmp/tmp-random-upload.pdf"), source_file_name="GB-17761-2024.pdf")
    assert unverified["standard_no"] == "GB 17761-2024"
    assert unverified["standard_level"] == "GB"
    assert unverified["standard_status"] == "待核实"


def test_arbitrary_pdf_is_not_declared_current_or_assigned_a_standard_level():
    meta = resolve_standard_meta(Path("ordinary_report-2026.pdf"))
    assert meta["standard_level"] == "待核实"
    assert meta["standard_status"] == "待核实"


def test_split_text_to_chunks_uses_overlap_without_empty_chunks():
    text = "0123456789" * 8

    chunks = split_text_to_chunks(text, chunk_size=25, overlap=5)

    assert chunks == [
        "0123456789012345678901234",
        "0123456789012345678901234",
        "0123456789012345678901234",
        "01234567890123456789",
    ]


def test_build_point_id_is_deterministic_and_qdrant_safe():
    scope = {"org_id": "org-1", "library_id": "lib-1", "document_id": "doc-1", "content_revision": "revision-1"}
    first = build_point_id("GB/T 3301-2023", page_number=4, chunk_index=2, **scope)
    assert UUID(first).version == 5
    assert first == build_point_id("GB/T 3301-2023", page_number=4, chunk_index=2, **scope)


@pytest.mark.parametrize("field,value", [
    ("org_id", "org-2"), ("org_id", None), ("library_id", "lib-2"),
    ("document_id", "doc-2"), ("content_revision", "revision-2"),
])
def test_same_standard_cannot_overwrite_another_resource_scope_or_revision(field, value):
    scope = {"org_id": "org-1", "library_id": "lib-1", "document_id": "doc-1", "content_revision": "revision-1"}
    first = build_point_id("GB/T 3301-2023", page_number=4, chunk_index=2, **scope)
    other = build_point_id("GB/T 3301-2023", page_number=4, chunk_index=2, **{**scope, field: value})
    assert first != other


def test_point_identity_requires_resource_identity():
    with pytest.raises(ValidationError, match="index identity"):
        build_point_id("GB/T 3301-2023", org_id="org-1", library_id="lib-1", document_id="",
                       content_revision="revision-1", page_number=1, chunk_index=1)


def test_build_index_docs_adds_required_standard_payload_fields():
    meta = resolve_standard_meta(Path("standard/current/ceramic/GB-T-3532-2022.pdf"))
    docs = build_index_docs(
        library_id="lib-1",
        document_id="doc-1",
        file_path=Path("standard/current/ceramic/GB-T-3532-2022.pdf"),
        meta=meta,
        pages=[{"page_number": 3, "text": "裂纹和缺釉需要按外观质量要求判定。" * 20}],
        chunk_size=80,
        overlap=10,
    )

    assert docs
    first = docs[0]
    assert UUID(first["id"]).version == 5
    assert first["payload"]["point_id_version"] == "standard-point-v2"
    assert len(first["payload"]["content_revision"]) == 64
    assert first["source"] == "GB/T 3532-2022"
    assert first["payload"]["library_id"] == "lib-1"
    assert first["payload"]["document_id"] == "doc-1"
    assert first["payload"]["standard_no"] == "GB/T 3532-2022"
    assert first["payload"]["standard_status"] == "现行"
    assert first["payload"]["file_name"] == "GB-T-3532-2022.pdf"
    assert first["payload"]["page_number"] == 3
    assert first["payload"]["chunk_index"] == 1


def test_document_retries_are_stable_but_changed_content_and_chunking_have_new_ids():
    kwargs = dict(
        org_id="org-1", library_id="lib-1", document_id="doc-1",
        file_path=Path("example.pdf"),
        meta={"standard_no": "GB/T EXAMPLE-2026", "standard_name": "示例标准"},
        pages=[{"page_number": 1, "text": "温度不得超过规定限值。" * 20}],
    )
    first = build_index_docs(**kwargs)
    assert [x["id"] for x in first] == [x["id"] for x in build_index_docs(**kwargs)]
    changed = build_index_docs(**{**kwargs, "pages": [{"page_number": 1, "text": "温度条件已修订。" * 20}]})
    assert first[0]["id"] != changed[0]["id"]
    assert first[0]["id"] != build_index_docs(**kwargs, chunk_size=80)[0]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("org_id", ["org-1", None])
@pytest.mark.parametrize("complete", [True, False])
async def test_reindex_cleanup_is_scoped_and_waits_for_a_complete_new_projection(monkeypatch, complete, org_id):
    monkeypatch.setattr("app.services.standard_pdf_importer.extract_pdf_pages", lambda _path: (
        [{"page_number": 1, "text": "检测项目应满足适用要求。" * 10}], 1,
    ))
    indexer = type("Indexer", (), {})()
    indexer.index = AsyncMock(return_value={"accepted": 1 if complete else 0, "failed_embeddings": 0 if complete else 1})
    indexer.delete_by_filter = AsyncMock()
    importer = StandardPdfImporter(org_id=org_id, indexer=indexer, retriever=object())
    result = await importer.index_document(
        library_id="lib-1", document_id="doc-1", file_path="example.pdf",
        meta={"standard_no": "GB/T EXAMPLE-2026", "standard_name": "示例标准"},
    )
    if complete and org_id:
        indexer.delete_by_filter.assert_awaited_once_with(
            {"org_id": "org-1", "library_id": "lib-1", "document_id": "doc-1"},
            exclude_filter={"content_revision": result["docs"][0]["payload"]["content_revision"]},
        )
    else:
        indexer.delete_by_filter.assert_not_awaited()


def test_build_index_docs_requires_ocr_for_unreadable_pdf_glyph_codes(monkeypatch):
    meta = resolve_standard_meta(Path("standard/current/ceramic/GB-T-3532-2022.pdf"))
    glyph_code_text = " /G21/G22/G23/G24/G25/G26/G27/G28/G29/G2A 2009 /G57/G58/G30 " * 8

    monkeypatch.setattr("app.services.standard_pdf_importer.shutil.which", lambda name: None)

    with pytest.raises(ValidationError, match="OCR fallback requires tesseract"):
        build_index_docs(
            library_id="lib-1",
            document_id="doc-1",
            file_path=Path("standard/current/ceramic/GB-T-3532-2022.pdf"),
            meta=meta,
            pages=[{"page_number": 1, "text": glyph_code_text}],
        )


def test_unreadable_pdf_detection_flags_symbolic_font_text():
    symbolic = "".join(chr(codepoint) for codepoint in (0x7290, 0x7286, 0x729B, 0x728C, 0x7285, 0x729C))
    text = f"{symbolic} 81.060.20 {symbolic} 3298 " * 8

    assert is_unreadable_pdf_text(text) is True


def test_unreadable_pdf_detection_allows_formula_symbols_in_readable_chinese_text():
    text = "每件试样同色密度偏差按式计算。犇ｓ表示同色密度偏差，犉表示网点面积覆盖率。" * 8

    assert is_unreadable_pdf_text(text) is False


def test_unreadable_pdf_detection_flags_control_character_garbled_text():
    text = "\x9f\x99 ８．２．３ \x9b\x9c ú \x9e \x8f -./ 12@jk 0f 4{| -èàfg 。" * 8

    assert is_unreadable_pdf_text(text) is True


def test_repair_unreadable_pdf_pages_with_ocr_replaces_bad_pages(monkeypatch):
    glyph_code_text = " /G21/G22/G23/G24/G25/G26/G27/G28/G29/G2A 2009 /G57/G58/G30 " * 8

    def fake_ocr_page(file_path, *, page_number):
        assert str(file_path).endswith("GB-T-7705-2008.pdf")
        assert page_number == 2
        return "目次\n前言\n1 范围\n2 规范性引用文件"

    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", fake_ocr_page)

    pages = repair_unreadable_pdf_pages_with_ocr(
        [
            {"page_number": 1, "text": "平版装潢印刷品\n1 范围\n本标准规定了印刷品外观质量要求。"},
            {"page_number": 2, "text": glyph_code_text},
        ],
        file_path=Path("standard/current/printing/GB-T-7705-2008.pdf"),
    )

    assert pages[0]["text"].startswith("平版装潢印刷品")
    assert pages[1]["text"] == "目次\n前言\n1 范围\n2 规范性引用文件"


def test_build_index_docs_rejects_when_ocr_text_is_still_unreadable(monkeypatch):
    meta = resolve_standard_meta(Path("standard/current/printing/GB-T-7705-2008.pdf"))
    glyph_code_text = " /G21/G22/G23/G24/G25/G26/G27/G28/G29/G2A 2009 /G57/G58/G30 " * 8

    def fake_ocr_page(file_path, *, page_number):
        return glyph_code_text

    monkeypatch.setattr("app.services.standard_pdf_importer.ocr_pdf_page_text", fake_ocr_page)

    with pytest.raises(ValidationError, match="OCR fallback did not produce readable text"):
        build_index_docs(
            library_id="lib-1",
            document_id="doc-1",
            file_path=Path("standard/current/printing/GB-T-7705-2008.pdf"),
            meta=meta,
            pages=[{"page_number": 2, "text": glyph_code_text}],
        )
