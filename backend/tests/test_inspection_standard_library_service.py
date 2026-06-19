from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.standard_pdf_importer import StandardPdfImporter


@pytest.mark.asyncio
async def test_standard_pdf_importer_deletes_all_points_for_library_with_one_filter_call():
    calls = []

    class FakeIndexer:
        async def delete_by_filter(self, payload_filter):
            calls.append(payload_filter)

    importer = StandardPdfImporter(org_id="org-1", indexer=FakeIndexer())

    await importer.delete_library_points(library_id="lib-1")

    assert calls == [{"org_id": "org-1", "library_id": "lib-1"}]


@pytest.mark.asyncio
async def test_delete_item_bulk_deletes_qdrant_points_documents_and_chunks():
    calls = []
    library = SimpleNamespace(id="lib-1", org_id="org-1", deleted_at=None)
    service = InspectionStandardLibraryService(session=object(), org_id="org-1")

    class FakeLibraryRepo:
        async def get(self, org_id, library_id):
            calls.append(("get", org_id, library_id))
            return library

        async def soft_delete(self, item):
            calls.append(("soft_delete_library", item.id))

    class FakeDocumentRepo:
        async def soft_delete_by_library(self, org_id, library_id):
            calls.append(("soft_delete_documents", org_id, library_id))
            return 17

    class FakeChunkRepo:
        async def soft_delete_by_library(self, library_id):
            calls.append(("soft_delete_chunks", library_id))
            return 823

    class FakeImporter:
        async def delete_library_points(self, library_id):
            calls.append(("delete_library_points", library_id))

    service._repo = FakeLibraryRepo()
    service._document_repo = FakeDocumentRepo()
    service._chunk_repo = FakeChunkRepo()
    service._importer = FakeImporter()

    await service.delete_item("lib-1")

    assert calls == [
        ("get", "org-1", "lib-1"),
        ("delete_library_points", "lib-1"),
        ("soft_delete_chunks", "lib-1"),
        ("soft_delete_documents", "org-1", "lib-1"),
        ("soft_delete_library", "lib-1"),
    ]


@pytest.mark.asyncio
async def test_normalize_payload_ignores_import_mode_action_field():
    service = InspectionStandardLibraryService(session=object(), org_id="org-1")

    async def fake_ensure_rag_spaces_exist(rag_space_ids):
        return None

    service._ensure_rag_spaces_exist = fake_ensure_rag_spaces_exist

    payload = await service._normalize_payload(
        {
            "name": "日用陶瓷标准库",
            "product_family": "ceramic",
            "domain": "日用陶瓷",
            "rag_space_ids": ["space-1"],
            "import_mode": "scan_and_index",
        }
    )

    assert "import_mode" not in payload


@pytest.mark.asyncio
async def test_index_document_clears_existing_chunks_when_extracted_pdf_text_is_unreadable():
    calls = []
    service = InspectionStandardLibraryService(session=object(), org_id="org-1")
    library = SimpleNamespace(id="lib-1", rag_space_ids=[], chunk_strategy="heading_then_size")
    document = SimpleNamespace(
        id="doc-1",
        standard_no="GB/T 3532-2022",
        standard_name="Ceramic",
        domain="ceramic",
        product_category="ceramic",
        standard_level="GB/T",
        standard_status="current",
        file_path="bad.pdf",
        file_name="bad.pdf",
        chunk_count=12,
        import_status="completed",
        error_message=None,
    )

    class FakeSession:
        async def flush(self):
            calls.append(("flush",))

    class FakeImporter:
        async def index_document(self, **kwargs):
            raise ValidationError("unreadable PDF text extracted from bad.pdf")

    class FakeChunkRepo:
        async def soft_delete_by_document(self, document_id):
            calls.append(("soft_delete_chunks_for_document", document_id))
            return 12

    service._session = FakeSession()
    service._importer = FakeImporter()
    service._chunk_repo = FakeChunkRepo()

    await service._index_document(library, document, reindex=False)

    assert ("soft_delete_chunks_for_document", "doc-1") in calls
    assert document.chunk_count == 0
    assert document.import_status == "failed"
    assert "unreadable PDF text" in document.error_message
