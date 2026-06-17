from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from time import time

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.quality_kg_schema import QualityKnowledgeChain
from app.services.quality_kg_service import QualityKnowledgeGraphService


def _sample_chain() -> QualityKnowledgeChain:
    return QualityKnowledgeChain(
        domain="食品接触材料",
        product_category="陶瓷杯",
        standard="GB 4806.4-2016",
        standard_clause="第 4.2 条",
        inspection_item="铅迁移量检测",
        metric="铅迁移量",
        defect_type="重金属迁移超标",
        risk_type="食品接触安全风险",
        cause="釉料重金属含量异常",
        actions=["复检", "退回", "禁止放行"],
        confidence=0.9,
        source="neo4j_verification",
    )


async def main() -> None:
    org_id = os.getenv("QUALITY_KG_VERIFY_ORG_ID") or f"quality-kg-verify-{int(time())}"
    service = QualityKnowledgeGraphService(org_id=org_id)
    chain = _sample_chain()

    await service.ingest_chain(chain)
    standards = await service.search_standards_by_product("食品接触材料", "陶瓷杯")
    clauses = await service.search_clauses_by_standard("食品接触材料", "GB 4806.4-2016")
    items = await service.search_items_by_clause("食品接触材料", "第 4.2 条")
    metrics = await service.search_metrics_by_item("食品接触材料", "铅迁移量检测")
    defects = await service.search_defects_by_metric("食品接触材料", "铅迁移量")
    risks = await service.search_risks_by_defect("食品接触材料", "重金属迁移超标")
    causes = await service.search_causes_by_defect("食品接触材料", "重金属迁移超标")
    actions = await service.search_actions_by_product_and_metric("食品接触材料", "陶瓷杯", "铅迁移量")
    paths = await service.search_chain_paths_by_product("食品接触材料", "陶瓷杯")

    expected = {
        "standards": "GB 4806.4-2016" in standards,
        "clauses": "第 4.2 条" in clauses,
        "items": "铅迁移量检测" in items,
        "metrics": "铅迁移量" in metrics,
        "defects": "重金属迁移超标" in defects,
        "risks": "食品接触安全风险" in risks,
        "causes": "釉料重金属含量异常" in causes,
        "actions": {"复检", "禁止放行"}.issubset(set(actions)),
        "paths": bool(paths),
    }
    failed = [name for name, ok in expected.items() if not ok]
    if failed:
        raise SystemExit(f"Quality KG Neo4j verification failed: {', '.join(failed)}")
    print(f"Quality KG Neo4j verification passed for org_id={org_id}")


if __name__ == "__main__":
    asyncio.run(main())
