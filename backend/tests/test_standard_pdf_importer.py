from pathlib import Path

from app.services.standard_pdf_importer import (
    build_index_docs,
    build_point_id,
    normalize_standard_no,
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
    assert build_point_id("GB/T 3301-2023", page_number=4, chunk_index=2) == "GB-T-3301-2023-p4-c2"
    assert build_point_id("GB 18401-2010", page_number=1, chunk_index=1) == "GB-18401-2010-p1-c1"


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
    assert first["id"] == "GB-T-3532-2022-p3-c1"
    assert first["source"] == "GB/T 3532-2022"
    assert first["payload"]["library_id"] == "lib-1"
    assert first["payload"]["document_id"] == "doc-1"
    assert first["payload"]["standard_no"] == "GB/T 3532-2022"
    assert first["payload"]["standard_status"] == "现行"
    assert first["payload"]["file_name"] == "GB-T-3532-2022.pdf"
    assert first["payload"]["page_number"] == 3
    assert first["payload"]["chunk_index"] == 1
