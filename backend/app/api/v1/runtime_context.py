from fastapi import APIRouter

from app.core.config import settings
from app.core.quality_demo import runtime_context
from app.schemas.common import ResponseEnvelope

router = APIRouter()


@router.get("/runtime-context", response_model=ResponseEnvelope[dict])
async def get_runtime_context():
    # Public configuration contains no credentials or infrastructure addresses.
    return ResponseEnvelope(data=runtime_context(settings))
