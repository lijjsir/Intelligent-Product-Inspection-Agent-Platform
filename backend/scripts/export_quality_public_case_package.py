"""Export only public-case material; exclude backups, sessions and credentials."""
import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.quality_risk_service import QualityRiskService
from infra.database.session import get_session, reset_async_engine_pool
from scripts.import_quality_public_cases import actors, REPORT_URL, CQ_URL, CHARGER_URL, NEWS_URL


async def main():
    root = Path("runtime/real_quality_case_20261023").resolve()
    index = json.loads((root / "case-index.json").read_text(encoding="utf-8"))
    public = root / "public-package"
    public.mkdir(exist_ok=True)
    source_assets = [
        ("report.pdf", "JG2128520085-official-original.pdf", REPORT_URL),
        ("gb17761_2018.pdf", "GB17761-2018-historical.pdf", "https://scjgj.pds.gov.cn/attach/0/1908231116143354011.pdf"),
        ("cq_cases.txt", "CQ-enforcement-cases-20251219.txt", CQ_URL),
        ("samr_2024.txt", "SAMR-quality-supervision-20250407.txt", CHARGER_URL),
    ]
    manifest = []
    for source_name, target_name, url in source_assets:
        source = root / "sources" / source_name
        destination = public / target_name
        shutil.copyfile(source, destination)
        manifest.append({"file": target_name, "source_url": url, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size, "scope": "Public original PDF or explicitly extracted public webpage text"})
    manifest.append({"source_url": NEWS_URL, "file": None, "note": "Publication checked through web search and cross-checked against official original report. Local direct request returned 405; no local webpage original is claimed."})
    try:
        async with get_session() as db:
            _, users = await actors(db)
            service = QualityRiskService(db, users["expert"])
            records = []
            for key, record_id in index["records"].items():
                record = await service.record(record_id)
                records.append({"key": key, "local_record_id": record.id, "record_type": record.record_type, "occurred_at": record.occurred_at.isoformat() if record.occurred_at else None, "content": record.content, "provenance": record.provenance, "data_nature": record.data_nature, "object_references_in_current_installation": record.product_ref})
            (public / "public-facts-and-provenance.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        await reset_async_engine_pool()
    (public / "source-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(root / "live-readiness.json", public / "current-workflow-readiness.json")
    shutil.copyfile(root / "case-index.json", public / "current-installation-case-index.json")
    docs = Path(__file__).resolve().parents[2] / "docs" / "质量监督真实材料案例与当前验收状态_2026-10-23.md"
    # The host docs folder is outside the backend container's bind mount. A host
    # copy can be supplied as package-guide.md before this export is requested.
    guide = root / "package-guide.md"
    if guide.exists():
        shutil.copyfile(guide, public / "README.md")
    elif docs.exists():
        shutil.copyfile(docs, public / "README.md")
    else:
        (public / "README.md").write_text("Public historical cases, not new physical inspection or human approvals. Object IDs refer to the existing cqupt installation. See source-manifest.json and current-workflow-readiness.json. Backups and authentication sessions are intentionally excluded.\n", encoding="utf-8")
    archive_path = root / "quality-public-cases-20261023.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for path in sorted(public.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    print(json.dumps({"archive": str(archive_path), "public_files": len(list(public.iterdir())), "bytes": archive_path.stat().st_size, "contains_database_backup": False, "contains_auth_session": False}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
