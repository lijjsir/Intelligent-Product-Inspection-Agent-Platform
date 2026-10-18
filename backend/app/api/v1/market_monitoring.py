from uuid import UUID
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.schemas.common import ResponseEnvelope
from app.schemas.market_monitoring import MarketScan, MarketRuleUpdate, MarketCoverage, SignalConversion, MarketFocus, FocusRemoval
from app.services.market_monitoring_service import MarketMonitoringService

router = APIRouter(prefix="/market-monitoring", tags=["market-monitoring"])


def service(current=Depends(get_current_user), db=Depends(get_db)):
    return MarketMonitoringService(db, current)


@router.get("")
async def query(as_of: date | None = None, object_type: Literal["product", "enterprise"] = "product", svc=Depends(service)):
    return ResponseEnvelope(data=await svc.report(MarketScan(as_of=as_of, object_type=object_type)))


@router.post("/scan")
async def scan(payload: MarketScan, svc=Depends(service)):
    data = await svc.report(payload, persist=True)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.patch("/rule")
async def rule(payload: MarketRuleUpdate, svc=Depends(service)):
    data = await svc.update_rule(payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/coverage")
async def coverage(svc=Depends(service)):
    return ResponseEnvelope(data=await svc.coverage())


@router.put("/coverage")
async def set_coverage(payload: MarketCoverage, svc=Depends(service)):
    data = await svc.set_coverage(payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/signals/{signal_id}")
async def detail(signal_id: UUID, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.detail(str(signal_id)))


@router.post("/signals/{signal_id}/risk-case")
async def convert(signal_id: UUID, payload: SignalConversion, svc=Depends(service)):
    data = await svc.convert(str(signal_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/focus-objects")
async def focuses(svc=Depends(service)):
    return ResponseEnvelope(data=await svc.focus_list())


@router.post("/focus-objects")
async def add_focus(payload: MarketFocus, svc=Depends(service)):
    data = await svc.add_focus(payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/focus-objects/{record_id}/archive")
async def remove_focus(record_id: UUID, payload: FocusRemoval, svc=Depends(service)):
    data = await svc.remove_focus(str(record_id), payload.reason)
    await svc.db.commit()
    return ResponseEnvelope(data=data)
