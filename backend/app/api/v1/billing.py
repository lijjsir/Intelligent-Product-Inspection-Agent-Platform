from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.governance import (
    BillingBucket,
    BillingQuery,
    BillingSummaryResponse,
    CurrentUserTokenUsageResponse,
    TokenLedgerResponse,
    UserTokenUsageSummaryResponse,
)
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
    service = BillingService(db, current.org_id, actor_role=current.role)
    data = await service.get_summary(query)
    return ResponseEnvelope(
        data=BillingSummaryResponse(
            granularity=data["granularity"],
            total_tokens=data["total_tokens"],
            total_cost=data["total_cost"],
            buckets=[BillingBucket(**item) for item in data["buckets"]],
            ledger_items=[TokenLedgerResponse.model_validate(item) for item in data["ledger_items"]],
            user_summaries=[UserTokenUsageSummaryResponse(**item) for item in data["user_summaries"]],
        )
    )


@router.get("/me", response_model=ResponseEnvelope[CurrentUserTokenUsageResponse])
async def get_current_user_token_usage(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = BillingService(db, current.org_id, actor_role=current.role)
    data = await service.get_current_user_summary(user_id=current.user_id)
    return ResponseEnvelope(data=CurrentUserTokenUsageResponse(**data))

