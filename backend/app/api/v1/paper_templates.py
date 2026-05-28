from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.services.paper_template_index_service import PaperTemplateIndexService

router = APIRouter(prefix="/paper-templates", tags=["paper-templates"])


@router.post("/import")
async def import_template(
    template_id: str = Form(...),
    template_name: str = Form(...),
    guide_file: UploadFile = File(...),
    school_name: str | None = Form(None),
    degree_type: str | None = Form(None),
    version: str | None = Form(None),
    description: str | None = Form(None),
    org_id: str = Form("default"),
    db: AsyncSession = Depends(get_db),
):
    """Import a writing guide, split into clauses, and index into MySQL + Qdrant."""
    content = await guide_file.read()
    service = PaperTemplateIndexService(db, org_id=org_id)
    result = await service.index_template(
        template_id=template_id,
        template_name=template_name,
        guide_file_bytes=content,
        guide_file_name=guide_file.filename or "writing-guide.docx",
        school_name=school_name,
        degree_type=degree_type,
        version=version,
        description=description,
    )
    return result


@router.get("/{template_id}/clauses")
async def list_clauses(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all clauses for a template."""
    from app.repositories.paper_template_repo import PaperTemplateClauseRepository
    repo = PaperTemplateClauseRepository(db)
    clauses = await repo.list_by_template(template_id)
    return {
        "template_id": template_id,
        "clauses": [
            {
                "clause_id": c.clause_id,
                "section_title": c.section_title,
                "clause_title": c.clause_title,
                "category": c.category,
                "target_type": c.target_type,
            }
            for c in clauses
        ],
    }
