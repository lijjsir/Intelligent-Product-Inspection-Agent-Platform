"""Prepare five-minute sessions for checking existing admin and expert pages; never print tokens."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import User
from app.models.inspection_spec import InspectionSpecItem
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from infra.database.session import get_session, reset_async_engine_pool

ORG_ID = "26c1c3e4-658b-498d-aab7-39b194de478c"
AUTH = Path("runtime/mvtec_catalog_view_auth.json")
REPORT = Path("runtime/mvtec_detection_options.json")


async def main():
    try:
        async with get_session() as db:
            sessions = {}
            for role in ("admin", "expert"):
                actor = await db.scalar(select(User).where(User.org_id == ORG_ID, User.role == role,
                    User.username == role, User.is_active.is_(True)))
                assert actor, f"缺少现有 {role} 账号，未新建账号"
                sessions[role] = {"piap_token": create_access_token(actor.id, {"org_id": actor.org_id,
                    "role": actor.role, "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())}),
                    "piap_role": actor.role, "piap_roles": json.dumps([role]), "piap_user_id": actor.id,
                    "piap_org_id": actor.org_id, "piap_username": actor.username}
            service = InspectionStandardLibraryService(db, ORG_ID)
            choices = await service.list_task_choices()
            configs = []
            for choice in choices:
                library = await db.get(InspectionStandardLibrary, choice["id"])
                items = list(await db.scalars(select(InspectionSpecItem).where(
                    InspectionSpecItem.spec_row_id == library.inspection_spec_id,
                    InspectionSpecItem.deleted_at.is_(None))))
                configs.append({**choice, "defect_types": [item.defect_type for item in items]})
            REPORT.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")
            AUTH.write_text(json.dumps(sessions), encoding="utf-8")
            print(json.dumps({"prepared_roles": list(sessions), "choices": configs}, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    asyncio.run(main())
