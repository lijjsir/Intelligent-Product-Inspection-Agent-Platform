from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.paper_review_runtime_service import PaperReviewRuntimeService

router = APIRouter(prefix="/paper-review-runtime", tags=["paper-review-runtime"])


@router.get("/health", response_model=ResponseEnvelope[dict])
async def paper_review_runtime_health(
    current: CurrentUser = Depends(get_current_user),
):
    require_role("infrastructure", current.role)
    return ResponseEnvelope(data=await PaperReviewRuntimeService.diagnose())
