"""Read-only verification of a published standard requirement and execution review.

The script deliberately does not create, approve, publish, or modify anything.
It is intended for deployment smoke checks after standard admission or execution
changes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.models.inspection_execution import InspectionExecutionRun
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument
from app.models.standard_admission import StandardDocumentRevision
from infra.database.session import get_session, reset_async_engine_pool


async def verify(org_id: str, standard_no: str, measurement_key: str, task_id: str | None = None) -> dict:
    async with get_session() as session:
        revisions = (
            await session.execute(
                select(StandardDocumentRevision, StandardDocument, InspectionStandardLibrary)
                .join(StandardDocument, StandardDocument.id == StandardDocumentRevision.document_id)
                .join(InspectionStandardLibrary, InspectionStandardLibrary.id == StandardDocument.library_id)
                .where(
                    StandardDocumentRevision.org_id == org_id,
                    StandardDocumentRevision.review_status == "approved",
                    StandardDocumentRevision.publication_status == "published",
                    StandardDocument.deleted_at.is_(None),
                    InspectionStandardLibrary.deleted_at.is_(None),
                    InspectionStandardLibrary.is_active.is_(True),
                )
            )
        ).all()

        matches: list[dict] = []
        for revision, document, library in revisions:
            if revision.snapshot.get("standard_no") != standard_no:
                continue
            for candidate in revision.candidates_json or []:
                if candidate.get("status") != "confirmed" or candidate.get("measurement_key") != measurement_key:
                    continue
                matches.append(
                    {
                        "revision_id": revision.id,
                        "document_id": document.id,
                        "library_id": library.id,
                        "candidate_id": candidate.get("id"),
                        "standard_no": standard_no,
                        "clause_no": candidate.get("clause_no"),
                        "indicator": candidate.get("indicator"),
                        "measurement_key": measurement_key,
                        "execution_mode": candidate.get("execution_mode"),
                        "operator": candidate.get("operator"),
                        "unit": candidate.get("unit"),
                        "numeric_lower": candidate.get("numeric_lower"),
                        "numeric_upper": candidate.get("numeric_upper"),
                    }
                )

        runs = (
            await session.execute(
                select(InspectionExecutionRun)
                .where(
                    InspectionExecutionRun.org_id == org_id,
                    InspectionExecutionRun.status == "accepted",
                    *( [InspectionExecutionRun.task_id == task_id] if task_id else [] ),
                )
                .order_by(InspectionExecutionRun.created_at.desc())
                .limit(200)
            )
        ).scalars().all()

        accepted: list[dict] = []
        for run in runs:
            source_refs = run.snapshot.get("source_refs") or []
            if not any(
                ref.get("revision_id") == item["revision_id"] and ref.get("candidate_id") == item["candidate_id"]
                for item in matches
                for ref in source_refs
            ):
                continue
            accepted.append(
                {
                    "run_id": run.id,
                    "task_id": run.task_id,
                    "status": run.status,
                    "reviewed_by": run.reviewed_by,
                    "item_verdict": (run.evaluation or {}).get("item_verdict"),
                    "product_verdict": (run.evaluation or {}).get("product_verdict"),
                    "current_source_issues": [],
                }
            )

    report = {
        "org_id": org_id,
        "standard_no": standard_no,
        "measurement_key": measurement_key,
        "published_requirement_count": len(matches),
        "accepted_execution_count": len(accepted),
        "published_requirements": matches,
        "accepted_executions": accepted,
        "passed": bool(matches and accepted),
        "notice": "只读检查；未写入标准、任务、执行记录或复核状态。",
    }
    return report


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--standard-no", required=True)
    parser.add_argument("--measurement-key", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = await verify(args.org_id, args.standard_no, args.measurement_key, args.task_id)
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, default=str))
    await reset_async_engine_pool()
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
