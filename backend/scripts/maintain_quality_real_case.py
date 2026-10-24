"""Tenant-scoped cleanup of confirmed development fixtures; backup before mutation.

The real public report, public product catalogs and research datasets are preserved.
No account, credential, standard publication, or human approval is modified.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.models import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.task import InspectionTask
from app.models.quality_risk import (
    QualityDataSource, QualityEvidenceItem, QualityRiskAssessment,
    QualityRiskCase, QualitySourceRecord,
)
from app.models.supervision import SupervisionRecord
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService
from app.services.task_service import TaskService
from infra.database.session import get_session, reset_async_engine_pool

TEST_TASK_SOURCES = {
    "chat_attachment_resolution_test", "chat_attachment_resolution_test_v2",
    "chat_attachment_resolution_test_v3", "p1p2_execution_acceptance",
    "report_task_acceptance", "formal_standard_requirement_acceptance",
}
BACKUP_TABLES = (
    "inspection_tasks", "inspection_results", "stability_reports", "alerts",
    "quality_source_records", "quality_evidence_items", "quality_risk_cases",
    "quality_risk_assessments", "quality_data_sources", "supervision_records",
    "supervision_revisions", "supervision_runs", "business_reviews",
    "supervision_dependencies", "measurement_records", "measurement_batches",
    "inspection_execution_runs", "inspection_execution_actions", "physical_samples",
)


def is_confirmed_test_task(task):
    return (task.meta_data or {}).get("source") in TEST_TASK_SOURCES


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def cleanup(args):
    if args.org != "cqupt":
        raise SystemExit("This maintenance request is scoped to cqupt only.")
    if str(settings.app_env).lower() not in {"dev", "development", "test", "local"}:
        raise SystemExit("Refusing development-fixture cleanup outside a development environment.")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        async with get_session() as db:
            org = await db.scalar(select(Organization).where(Organization.slug == args.org))
            if not org:
                raise RuntimeError("Target organization not found")
            expert = await db.scalar(select(User).where(User.org_id == org.id, User.username == "expert", User.role == "expert", User.is_active.is_(True)))
            admin = await db.scalar(select(User).where(User.org_id == org.id, User.username == "admin", User.role == "admin", User.is_active.is_(True)))
            if not expert or not admin:
                raise RuntimeError("Expected existing organization actors not found")
            if args.purge_backed_up_children:
                backup_path = output / "before-cleanup.json"
                backup = json.loads(backup_path.read_text(encoding="utf-8"))
                if backup["organization"]["id"] != org.id:
                    raise RuntimeError("Recovery snapshot belongs to a different organization")
                manifest = json.loads((output / "cleanup-manifest.json").read_text(encoding="utf-8"))
                task_ids = {row["id"] for row in manifest["tasks"] if row["source"] in TEST_TASK_SOURCES}
                for task_id in task_ids:
                    task = await db.get(InspectionTask, task_id)
                    if not task or task.org_id != org.id or not task.deleted_at or not is_confirmed_test_task(task):
                        raise RuntimeError("Fixture parent is not the withdrawn, audited test task")
                sessions = {row["id"] for row in backup["tables"]["supervision_records"] if row["kind"] == "inspection-sessions" and row["data"].get("task_id") in task_ids}
                runs = {row["id"] for row in backup["tables"].get("inspection_execution_runs", []) if row["task_id"] in task_ids}
                references = list(await db.scalars(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id == org.id, QualityRiskAssessment.deleted_at.is_(None))))
                business_records = list(await db.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id == org.id)))
                if any(any(run_id in json.dumps(row.model_versions or {}) for run_id in runs) for row in references) or any(any(run_id in json.dumps(row.data or {}) for run_id in runs) for row in business_records):
                    raise RuntimeError("A surviving business record references these test results; stop for an explicit dependency audit")
                purged = {}
                for name, column, ids in (
                    ("inspection_execution_actions", "run_id", runs),
                    ("inspection_execution_runs", "task_id", task_ids),
                    ("measurement_records", "session_id", sessions),
                    ("measurement_batches", "session_id", sessions),
                ):
                    table = Base.metadata.tables.get(name)
                    if table is not None and ids:
                        result = await db.execute(delete(table).where(table.c.org_id == org.id, table.c[column].in_(ids)))
                        purged[name] = result.rowcount
                await db.commit()
                result = {"applied": True, "org": org.slug, "purged_fixture_children": purged, "backup": str(backup_path)}
                dump_json(output / "linked-cleanup-result.json", result)
                print(json.dumps(result, ensure_ascii=False))
                return
            tasks = list(await db.scalars(select(InspectionTask).where(InspectionTask.org_id == org.id, InspectionTask.deleted_at.is_(None))))
            selected_tasks = [task for task in tasks if is_confirmed_test_task(task)]
            selected_ids = {task.id for task in selected_tasks}
            records = list(await db.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id == org.id)))
            selected_records = [row for row in records if
                (row.kind == "inspection-sessions" and row.data.get("task_id") in selected_ids)
                or (row.kind == "sampling-plans" and row.name == "测试" and not row.data.get("candidates") and row.status != "approved")]
            food = list(await db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id == org.id, QualitySourceRecord.deleted_at.is_(None))))
            food = [row for row in food if args.include_confirmed_manual and row.content.get("text") == "过期食品售卖" and not row.provenance.get("origin_label")]
            food_ids = {row.id for row in food}
            cases = list(await db.scalars(select(QualityRiskCase).where(QualityRiskCase.org_id == org.id, QualityRiskCase.deleted_at.is_(None))))
            cases = [row for row in cases if food_ids.intersection(row.source_record_ids or []) and set(row.source_record_ids or []) <= food_ids]
            manual_enterprises = [row for row in records if args.include_confirmed_manual and row.kind == "enterprises" and row.name == "志远"]
            manifest = {
                "organization": {"id": org.id, "slug": org.slug, "name": org.name},
                "mode": "apply" if args.apply_cleanup else "audit_only",
                "tasks": [{"id": t.id, "source": t.meta_data.get("source"), "status": t.status} for t in selected_tasks],
                "supervision_records": [{"id": r.id, "kind": r.kind, "name": r.name} for r in selected_records],
                "confirmed_manual_records": [r.id for r in food],
                "confirmed_manual_cases": [r.id for r in cases],
                "confirmed_manual_enterprises": [r.id for r in manual_enterprises],
                "preserved_tasks": [{"id": t.id, "product_id": t.product_id, "reason": "No explicit fixture marker; includes the genuine public-report case"} for t in tasks if t.id not in selected_ids],
            }
            dump_json(output / "cleanup-manifest.json", manifest)
            if not args.apply_cleanup:
                print(json.dumps(manifest, ensure_ascii=False))
                return
            backup_path = output / "before-cleanup.json"
            if backup_path.exists():
                raise RuntimeError("Backup already exists; choose a new output directory to prevent overwriting recovery data")
            backup = {"organization": manifest["organization"], "created_at_utc": datetime.now(timezone.utc).isoformat(), "tables": {}}
            for name in BACKUP_TABLES:
                table = Base.metadata.tables.get(name)
                if table is not None and "org_id" in table.c:
                    backup["tables"][name] = [dict(row) for row in (await db.execute(select(table).where(table.c.org_id == org.id))).mappings()]
            dump_json(backup_path, backup)
            backup_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()
            service = TaskService(db, org.id, actor_user_id=expert.id, actor_role="expert")
            for task in selected_tasks:
                await service.delete_task(task.id)
            root_ids = {row.id for row in selected_records}
            # These fixture journals belong only to the explicitly selected rows.
            for name in ("business_reviews", "supervision_revisions", "supervision_runs"):
                table = Base.metadata.tables.get(name)
                if table is not None and root_ids:
                    await db.execute(delete(table).where(table.c.org_id == org.id, table.c.record_id.in_(root_ids)))
            table = Base.metadata.tables.get("supervision_dependencies")
            if table is not None and root_ids:
                await db.execute(delete(table).where(table.c.org_id == org.id, or_(table.c.source_id.in_(root_ids), table.c.target_id.in_(root_ids))))
            for row in selected_records:
                await db.delete(row)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            case_ids = {row.id for row in cases}
            for row in food + cases:
                row.deleted_at = now
            if food_ids:
                for row in await db.scalars(select(QualityEvidenceItem).where(QualityEvidenceItem.org_id == org.id, QualityEvidenceItem.source_record_id.in_(food_ids))):
                    row.deleted_at = now
            if case_ids:
                for row in await db.scalars(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id == org.id, QualityRiskAssessment.risk_case_id.in_(case_ids))):
                    row.deleted_at = now
            for source_id in {row.source_id for row in food}:
                active = list(await db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id == org.id, QualitySourceRecord.source_id == source_id, QualitySourceRecord.deleted_at.is_(None))))
                source = await db.get(QualityDataSource, source_id)
                if not active and source and source.code == "123456" and source.name == "北京投诉":
                    source.deleted_at = now
            foundation = QualityRiskService(db, CurrentUser(user_id=admin.id, org_id=org.id, role="admin"))
            for enterprise in manual_enterprises:
                await foundation.delete_foundation("enterprise", enterprise.id)
            await db.commit()
            result = {"applied": True, "org": org.slug, "tasks_removed_from_business_lists": len(selected_tasks), "fixture_business_records_deleted": len(selected_records), "manual_sources_withdrawn": len(food), "manual_cases_withdrawn": len(cases), "manual_enterprises_deleted": len(manual_enterprises), "backup": str(backup_path), "backup_sha256": backup_hash}
            dump_json(output / "cleanup-result.json", result)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply-cleanup", action="store_true")
    parser.add_argument("--include-confirmed-manual", action="store_true")
    parser.add_argument("--purge-backed-up-children", action="store_true")
    asyncio.run(cleanup(parser.parse_args()))
