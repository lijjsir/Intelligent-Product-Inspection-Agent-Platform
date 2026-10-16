"""Exercise deployed result reads without exporting or changing business records.

Access tokens stay in memory. Only counts, HTTP statuses and schema are recorded.
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx
from sqlalchemy import select, text

from app.core.security import create_access_token
from app.models.task import InspectionTask
from app.models.user import User
from infra.database.session import get_session, reset_async_engine_pool


async def main(output):
    result = {"read_only": True, "http_checks": []}
    try:
        async with get_session() as db:
            result["snapshot_column_type"] = await db.scalar(text(
                "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='export_jobs' AND COLUMN_NAME='config_json'"
            ))
            tasks = (await db.scalars(select(InspectionTask).where(InspectionTask.deleted_at.is_(None)))).all()
            checked_owners = set()
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30) as client:
                for task in tasks:
                    actor = await db.get(User, task.created_by)
                    if not actor or actor.role not in {"user", "expert"}:
                        continue
                    token = create_access_token(actor.id, {"org_id": actor.org_id, "role": actor.role})
                    headers = {"Authorization": "Bearer " + token}
                    if actor.id not in checked_owners:
                        checked_owners.add(actor.id)
                        for path in ["/api/v1/results/unified", "/api/v1/results/report-tasks", "/api/v1/exports"]:
                            response = await client.get(path, headers=headers)
                            result["http_checks"].append({"endpoint": path, "status": response.status_code})
                            if response.status_code != 200:
                                print(json.dumps(result, ensure_ascii=False))
                            assert response.status_code == 200, "Deployed result list read failed"
                    response = await client.get(f"/api/v1/results/by-task/{task.id}/summary", headers=headers)
                    result["http_checks"].append({"endpoint": "task_summary", "status": response.status_code})
                    assert response.status_code == 200, "Deployed result summary read failed"
                    assert response.json()["data"]["scope"]["product_verdict"] == "not_assessed"
            result["owners_checked"] = len(checked_owners)
            result["all_product_scopes_bounded"] = True
    finally:
        await reset_async_engine_pool()
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args().output))
