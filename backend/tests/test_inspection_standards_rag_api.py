import pytest

from app.api.v1 import inspection_standards as standards_api
from app.schemas.user import CurrentUser


def current_user(role: str) -> CurrentUser:
    return CurrentUser(user_id=f"{role}-1", org_id="org-1", role=role, roles=[role])


@pytest.mark.asyncio
async def test_scan_inspection_standard_library_endpoint(monkeypatch):
    class FakeService:
        def __init__(self, db, org_id, user_id=None):
            self.db = db
            self.org_id = org_id
            self.user_id = user_id

        async def scan_library(self, library_id):
            return {
                "library_id": library_id,
                "scanned_count": 2,
                "created_count": 2,
                "updated_count": 0,
                "documents": [],
            }

    monkeypatch.setattr(standards_api, "InspectionStandardLibraryService", FakeService)

    response = await standards_api.scan_inspection_standard("lib-1", current=current_user("admin"), db=object())

    assert response.data["library_id"] == "lib-1"
    assert response.data["scanned_count"] == 2


@pytest.mark.asyncio
async def test_index_inspection_standard_library_endpoint(monkeypatch):
    class FakeService:
        def __init__(self, db, org_id, user_id=None):
            self.db = db
            self.org_id = org_id
            self.user_id = user_id

        async def index_library(self, library_id, *, reindex=False):
            assert reindex is False
            return {
                "library_id": library_id,
                "document_count": 1,
                "indexed_document_count": 1,
                "chunk_count": 8,
                "failed_count": 0,
            }

    monkeypatch.setattr(standards_api, "InspectionStandardLibraryService", FakeService)

    response = await standards_api.index_inspection_standard("lib-1", current=current_user("admin"), db=object())

    assert response.data["chunk_count"] == 8
    assert response.data["failed_count"] == 0


@pytest.mark.asyncio
async def test_list_inspection_standard_documents_endpoint(monkeypatch):
    class FakeService:
        def __init__(self, db, org_id, user_id=None):
            self.db = db
            self.org_id = org_id
            self.user_id = user_id

        async def list_documents(self, library_id):
            return [
                {
                    "id": "doc-1",
                    "library_id": library_id,
                    "standard_no": "GB/T 3532-2022",
                    "standard_name": "日用瓷器",
                    "domain": "日用陶瓷",
                    "product_category": "日用瓷器",
                    "standard_level": "GB/T",
                    "standard_status": "现行",
                    "file_name": "GB-T-3532-2022.pdf",
                    "file_path": "standard/current/ceramic/GB-T-3532-2022.pdf",
                    "file_hash": "abc",
                    "file_size": 100,
                    "page_count": 12,
                    "chunk_count": 16,
                    "qdrant_collection": "default",
                    "import_status": "completed",
                    "last_indexed_at": None,
                    "error_message": None,
                    "created_at": None,
                    "updated_at": None,
                }
            ]

    monkeypatch.setattr(standards_api, "InspectionStandardLibraryService", FakeService)

    response = await standards_api.list_inspection_standard_documents("lib-1", current=current_user("admin"), db=object())

    assert response.data[0]["standard_no"] == "GB/T 3532-2022"


@pytest.mark.asyncio
async def test_retrieve_standards_endpoint(monkeypatch):
    class FakeService:
        def __init__(self, db, org_id, user_id=None):
            self.db = db
            self.org_id = org_id
            self.user_id = user_id

        async def retrieve(self, payload):
            return {
                "hits": [
                    {
                        "id": "hit-1",
                        "title": "GB/T 3532-2022 日用瓷器 第3页 第1段",
                        "source": "GB/T 3532-2022",
                        "quote": "裂纹判定依据",
                        "score": 0.91,
                        "standard_no": "GB/T 3532-2022",
                        "standard_name": "日用瓷器",
                        "domain": "日用陶瓷",
                        "product_category": "日用瓷器",
                        "page_number": 3,
                        "chunk_index": 1,
                        "payload": {"standard_status": "现行"},
                    }
                ],
                "hit_count": 1,
                "candidate_count": 1,
                "latency_ms": 12.5,
            }

    monkeypatch.setattr(standards_api, "InspectionStandardLibraryService", FakeService)

    payload = standards_api.StandardRetrieveRequest(query="陶瓷杯口沿裂纹是否合格", domain="日用陶瓷")
    response = await standards_api.retrieve_standards(payload, current=current_user("admin"), db=object())

    assert response.data["hits"][0]["standard_no"] == "GB/T 3532-2022"
