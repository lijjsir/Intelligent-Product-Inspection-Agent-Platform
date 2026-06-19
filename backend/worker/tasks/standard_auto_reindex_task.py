"""Periodic task to auto-reindex inspection standard libraries with auto_reindex=True."""

from __future__ import annotations

from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from infra.database.session import get_session
from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.standard_auto_reindex_task.run_standard_auto_reindex")
def run_standard_auto_reindex():
    return run_celery_async(_run_standard_auto_reindex())


async def _run_standard_auto_reindex() -> dict[str, int]:
    indexed: int = 0
    failed: int = 0
    async with get_session() as session:
        repo = InspectionStandardLibraryRepository(session)
        # List all active libraries (non-paginated to cover all orgs)
        from app.models.inspection_standard_library import InspectionStandardLibrary
        from sqlalchemy import select

        result = await session.execute(
            select(InspectionStandardLibrary).where(
                InspectionStandardLibrary.auto_reindex.is_(True),
                InspectionStandardLibrary.is_active.is_(True),
                InspectionStandardLibrary.deleted_at.is_(None),
            )
        )
        libraries = list(result.scalars().all())
        for library in libraries:
            org_id = str(library.org_id) if library.org_id else ""
            if not org_id:
                continue
            try:
                service = InspectionStandardLibraryService(session, org_id)
                result_index = await service.index_library(str(library.id), reindex=True)
                indexed += int(result_index.get("indexed_document_count") or 0)
                failed += int(result_index.get("failed_count") or 0)
            except Exception:
                failed += 1
        await session.commit()
    return {"indexed": indexed, "failed": failed, "library_count": len(libraries)}
