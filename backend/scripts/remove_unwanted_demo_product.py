"""Remove only the exact convenience-noodle record explicitly identified by the user."""
import argparse
import asyncio
import json

from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.quality_risk import QualityProduct
from app.models.user import User
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService
from infra.database.session import get_session, reset_async_engine_pool


async def main(apply):
    try:
        async with get_session() as db:
            rows = list(await db.scalars(select(QualityProduct).where(
                QualityProduct.name == "方便面", QualityProduct.brand == "统一",
                QualityProduct.model == "红烧牛肉面", QualityProduct.deleted_at.is_(None))))
            print(json.dumps({"matches": len(rows), "records": [{"id": r.id, "org_id": r.org_id, "name": r.name,
                "brand": r.brand, "model": r.model} for r in rows]}, ensure_ascii=False))
            if not apply:
                return
            if len(rows) != 1:
                raise RuntimeError("匹配不唯一，未删除任何记录")
            row = rows[0]
            actor = await db.scalar(select(User).where(User.org_id == row.org_id, User.role == "admin", User.is_active.is_(True)))
            if not actor:
                raise RuntimeError("找不到该组织的管理员，未删除")
            svc = QualityRiskService(db, CurrentUser(user_id=actor.id, org_id=row.org_id, role="admin"))
            try:
                result = await svc.delete_foundation("product", row.id)
            except AppError as exc:
                print(json.dumps({"deleted": False, "reason": exc.message}, ensure_ascii=False))
                return
            await db.commit()
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
