from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.governance import BillingQuery, BillingSummaryResponse, BillingBucket, TokenLedgerResponse
from app.schemas.user import CurrentUser
from app.services.billing_service import BillingService


router = APIRouter()


@router.get("/summary", response_model=ResponseEnvelope[BillingSummaryResponse])
async def get_billing_summary(
    query: BillingQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("billing", current.role)
    service = BillingService(db, current.org_id)
    data = await service.get_summary(query)
    return ResponseEnvelope(
        data=BillingSummaryResponse(
            granularity=data["granularity"],
            total_tokens=data["total_tokens"],
            total_cost=data["total_cost"],
            buckets=[BillingBucket(**item) for item in data["buckets"]],
            ledger_items=[TokenLedgerResponse.model_validate(item) for item in data["ledger_items"]],
        )
    )

