"""Read current public-case readiness without approving, publishing or executing."""
import asyncio
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.models.task import InspectionTask
from app.models.quality_risk import QualitySourceRecord, QualityRiskCase
from app.models.supervision import SupervisionRecord
from app.schemas.market_monitoring import MarketScan
from app.services.market_monitoring_service import MarketMonitoringService
from app.services.quality_risk_service import QualityRiskService
from app.services.risk_lab_service import RiskLabService
from infra.database.session import get_session, reset_async_engine_pool
from scripts.import_quality_public_cases import actors


async def main():
    root = Path("runtime/real_quality_case_20261023")
    index = json.loads((root / "case-index.json").read_text(encoding="utf-8"))
    output = {"read_only_business_audit": True, "organization": index["organization"], "human_approvals_performed_by_import": False, "new_physical_tests_performed": False, "cases": []}
    try:
        async with get_session() as db:
            org, users = await actors(db)
            service = QualityRiskService(db, users["expert"])
            for key, case_id in index["cases"].items():
                workspace = await service.risk_workspace(case_id)
                assessment = workspace["latest_assessment"] or {}
                models = assessment.get("model_versions") or {}
                context = workspace.get("workflow_context") or {}
                output["cases"].append({"key": key, "case_id": case_id, "title": workspace["case"]["title"], "case_status": workspace["case"]["status"],
                    "assessment_purpose": workspace["case"].get("assessment_purpose"), "purpose_review": assessment.get("purpose_review"), "analysis_origin":assessment.get("analysis_origin"),
                    "assessment_id": assessment.get("id"), "version": assessment.get("version"), "risk_level": assessment.get("risk_level"),
                    "llm_called": models.get("llm_called"), "model_success": models.get("model_success"), "attempted_calls": models.get("attempted_calls"), "successful_calls": models.get("successful_calls"),
                    "summary": (models.get("analysis_summary") or {}).get("summary"), "limitations": (models.get("analysis_summary") or {}).get("limitations"),
                    "missing_inputs": assessment.get("missing_inputs"), "conflicts": assessment.get("conflicts"), "source_blockers": (assessment.get("source_validation") or {}).get("blockers"),
                    "submitted_by": assessment.get("submitted_by"), "reviewed_by": assessment.get("reviewed_by"), "downstream_eligible": context.get("eligible"), "downstream_blockers": context.get("blockers"),
                    "record_ids": [r["id"] for r in workspace["records"]], "data_natures": sorted({r["data_nature"] for r in workspace["records"]})})
            lab = await RiskLabService(db, users["expert"]).list(index["cases"]["main"])
            output["laboratory_returns"] = [{key: row.get(key) for key in ["id", "status", "case_id", "assessment_version", "record_ids", "task_id", "verification_path", "request_stage"]} for row in lab]
            monitor = await MarketMonitoringService(db, users["expert"]).report(MarketScan(as_of=date(2022,4,25), object_type="product"))
            output["historical_monitoring"] = {"as_of": monitor["as_of"], "totals": monitor["totals"], "groups": [{key: row.get(key) for key in ["object_id", "object_name", "status", "current_count", "previous_count", "signal_id"]} for row in monitor["groups"]], "notice": monitor["notice"]}
            sources = list(await db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id == org.id, QualitySourceRecord.deleted_at.is_(None))))
            cases = list(await db.scalars(select(QualityRiskCase).where(QualityRiskCase.org_id == org.id, QualityRiskCase.deleted_at.is_(None))))
            tasks = list(await db.scalars(select(InspectionTask).where(InspectionTask.org_id == org.id, InspectionTask.deleted_at.is_(None))))
            plans = list(await db.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id == org.id, SupervisionRecord.kind == "sampling-plans")))
            output["cleanup_verification"] = {"food_placeholder_active": any(r.content.get("text") == "过期食品售卖" for r in sources), "food_cases_active": any(r.title == "过期食品售卖" for r in cases),
                "test_plan_active": any(r.name == "测试" for r in plans), "active_tasks": len(tasks), "preserved_original_report_task": any(r.id == "01a13879-0890-7980-9e72-05638bde71b8" for r in tasks), "active_raw_records": len(sources)}
            save = root / "live-readiness.json"
            save.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(json.dumps({"output": str(save), "cases": [{key: row[key] for key in ["key", "version", "risk_level", "model_success", "source_blockers", "downstream_eligible"]} for row in output["cases"]], "cleanup": output["cleanup_verification"]}, ensure_ascii=False), flush=True)
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    asyncio.run(main())
