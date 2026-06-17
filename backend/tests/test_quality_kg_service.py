import pytest

from app.core.exceptions import ValidationError


class FakeQualityKgRepository:
    def __init__(self):
        self.schema_ensured = False
        self.ingested = []
        self.actions_by_metric = []
        self.risks_by_defect = []
        self.actions_by_defect = []
        self.standards_by_product = []
        self.clauses_by_standard = []
        self.items_by_clause = []
        self.metrics_by_item = []
        self.defects_by_metric = []
        self.causes_by_defect = []
        self.paths_by_product = []
        self.deleted_relationships = []
        self.deleted_nodes = []

    async def ensure_schema(self):
        self.schema_ensured = True

    async def ingest_chain(self, *, nodes, relationships):
        self.ingested.append({"nodes": nodes, "relationships": relationships})

    async def search_actions_by_product_and_metric(self, **kwargs):
        self.actions_by_metric.append(kwargs)
        return ["复检", "禁止放行"]

    async def search_risks_by_defect(self, **kwargs):
        self.risks_by_defect.append(kwargs)
        return ["食品接触安全风险"]

    async def search_actions_by_defect(self, **kwargs):
        self.actions_by_defect.append(kwargs)
        return ["复检"]

    async def search_standards_by_product(self, **kwargs):
        self.standards_by_product.append(kwargs)
        return ["GB 4806.4-2016"]

    async def search_clauses_by_standard(self, **kwargs):
        self.clauses_by_standard.append(kwargs)
        return ["第 4.2 条"]

    async def search_items_by_clause(self, **kwargs):
        self.items_by_clause.append(kwargs)
        return ["铅迁移量检测"]

    async def search_metrics_by_item(self, **kwargs):
        self.metrics_by_item.append(kwargs)
        return ["铅迁移量"]

    async def search_defects_by_metric(self, **kwargs):
        self.defects_by_metric.append(kwargs)
        return ["重金属迁移超标"]

    async def search_causes_by_defect(self, **kwargs):
        self.causes_by_defect.append(kwargs)
        return ["釉料重金属含量异常"]

    async def search_chain_paths_by_product(self, **kwargs):
        self.paths_by_product.append(kwargs)
        return [{"standard": "GB 4806.4-2016", "metric": "铅迁移量"}]

    async def delete_relationship(self, **kwargs):
        self.deleted_relationships.append(kwargs)
        return 1

    async def delete_node(self, **kwargs):
        self.deleted_nodes.append(kwargs)
        return 1


def ceramic_chain_payload():
    return {
        "domain": "食品接触材料",
        "product_category": " 陶瓷杯 ",
        "standard": "GB 4806.4-2016",
        "standard_clause": "第 4.2 条",
        "inspection_item": "铅迁移量检测",
        "metric": "铅迁移量",
        "defect_type": "重金属迁移超标",
        "risk_type": "食品接触安全风险",
        "cause": "釉料重金属含量异常",
        "actions": ["复检", "退回", "禁止放行"],
        "confidence": 0.9,
        "source": "inspection_result",
    }


@pytest.mark.asyncio
async def test_service_ingests_quality_chain_as_nodes_and_relationships():
    from app.services.quality_kg_schema import QualityKnowledgeChain
    from app.services.quality_kg_service import QualityKnowledgeGraphService

    repo = FakeQualityKgRepository()
    service = QualityKnowledgeGraphService(repo=repo, org_id="org-1")

    await service.ingest_chain(QualityKnowledgeChain(**ceramic_chain_payload()))

    assert repo.schema_ensured is True
    ingested = repo.ingested[0]
    node_types = {node.type for node in ingested["nodes"]}
    assert node_types == {
        "DetectionDomain",
        "ProductCategory",
        "Standard",
        "StandardClause",
        "InspectionItem",
        "Metric",
        "DefectType",
        "RiskType",
        "Cause",
        "Action",
    }
    product = next(node for node in ingested["nodes"] if node.type == "ProductCategory")
    assert product.name == "陶瓷杯"
    assert product.normalized_name == "陶瓷杯"
    assert product.id == "qkg:org-1:ProductCategory:食品接触材料:陶瓷杯"

    relationship_types = [rel.type for rel in ingested["relationships"]]
    assert relationship_types[:10] == [
        "HAS_CATEGORY",
        "APPLIES_STANDARD",
        "HAS_CLAUSE",
        "REQUIRES_ITEM",
        "HAS_METRIC",
        "INDICATES_DEFECT",
        "LEADS_TO_RISK",
        "MAY_BE_CAUSED_BY",
        "CAUSE_HANDLED_BY",
        "RISK_REQUIRES_ACTION",
    ]
    assert "DEFECT_SUGGESTS_ACTION" in relationship_types
    assert "METRIC_ABNORMAL_ACTION" in relationship_types
    assert "ITEM_DIRECT_ACTION" in relationship_types
    assert all(rel.domain == "食品接触材料" for rel in ingested["relationships"])
    assert all(rel.product_category == "陶瓷杯" for rel in ingested["relationships"])


@pytest.mark.asyncio
async def test_service_rejects_sparse_quality_chain():
    from app.services.quality_kg_schema import QualityKnowledgeChain
    from app.services.quality_kg_service import QualityKnowledgeGraphService

    service = QualityKnowledgeGraphService(repo=FakeQualityKgRepository(), org_id="org-1")
    payload = {
        "domain": "食品接触材料",
        "product_category": "陶瓷杯",
        "standard": "GB 4806.4-2016",
    }

    with pytest.raises(ValidationError, match="at least two"):
        await service.ingest_chain(QualityKnowledgeChain(**payload))


@pytest.mark.asyncio
async def test_service_normalizes_query_inputs_before_delegating():
    from app.services.quality_kg_service import QualityKnowledgeGraphService

    repo = FakeQualityKgRepository()
    service = QualityKnowledgeGraphService(repo=repo, org_id="org-1")

    actions = await service.search_actions_by_product_and_metric(
        domain=" 食品接触材料 ",
        product_category=" 陶瓷杯 ",
        metric=" 铅迁移量 ",
    )
    risks = await service.search_risks_by_defect(
        domain="食品接触材料",
        defect_type=" 重金属迁移超标 ",
    )
    standards = await service.search_standards_by_product(
        domain="食品接触材料",
        product_category=" 陶瓷杯 ",
    )

    assert actions == ["复检", "禁止放行"]
    assert risks == ["食品接触安全风险"]
    assert standards == ["GB 4806.4-2016"]
    assert repo.actions_by_metric[0] == {
        "org_id": "org-1",
        "domain": "食品接触材料",
        "product_category": "陶瓷杯",
        "metric": "铅迁移量",
    }
    assert repo.risks_by_defect[0]["defect_type"] == "重金属迁移超标"
    assert repo.standards_by_product[0]["product_category"] == "陶瓷杯"


@pytest.mark.asyncio
async def test_service_exposes_all_documented_question_queries():
    from app.services.quality_kg_service import QualityKnowledgeGraphService

    repo = FakeQualityKgRepository()
    service = QualityKnowledgeGraphService(repo=repo, org_id="org-1")

    assert await service.search_clauses_by_standard(" 食品接触材料 ", " GB 4806.4-2016 ") == ["第 4.2 条"]
    assert await service.search_items_by_clause("食品接触材料", " 第 4.2 条 ") == ["铅迁移量检测"]
    assert await service.search_metrics_by_item("食品接触材料", " 铅迁移量检测 ") == ["铅迁移量"]
    assert await service.search_defects_by_metric("食品接触材料", " 铅迁移量 ") == ["重金属迁移超标"]
    assert await service.search_causes_by_defect("食品接触材料", " 重金属迁移超标 ") == ["釉料重金属含量异常"]
    assert await service.search_chain_paths_by_product("食品接触材料", " 陶瓷杯 ") == [
        {"standard": "GB 4806.4-2016", "metric": "铅迁移量"}
    ]

    assert repo.clauses_by_standard[0]["standard"] == "gb 4806.4-2016"
    assert repo.items_by_clause[0]["standard_clause"] == "第 4.2 条"
    assert repo.metrics_by_item[0]["inspection_item"] == "铅迁移量检测"
    assert repo.defects_by_metric[0]["metric"] == "铅迁移量"
    assert repo.causes_by_defect[0]["defect_type"] == "重金属迁移超标"
    assert repo.paths_by_product[0]["product_category"] == "陶瓷杯"


@pytest.mark.asyncio
async def test_service_deletes_relationships_and_nodes_through_admin_operations():
    from app.services.quality_kg_schema import QualityKgNodeDelete, QualityKgRelationshipDelete
    from app.services.quality_kg_service import QualityKnowledgeGraphService

    repo = FakeQualityKgRepository()
    service = QualityKnowledgeGraphService(repo=repo, org_id="org-1")

    deleted_edges = await service.delete_relationship(
        QualityKgRelationshipDelete(
            relation_type="HAS_METRIC",
            start_node_id="qkg:org-1:InspectionItem:食品接触材料:铅迁移量检测",
            end_node_id="qkg:org-1:Metric:食品接触材料:铅迁移量",
            domain="食品接触材料",
            product_category="陶瓷杯",
        )
    )
    deleted_nodes = await service.delete_node(
        QualityKgNodeDelete(node_id="qkg:org-1:Metric:食品接触材料:铅迁移量")
    )

    assert deleted_edges == 1
    assert deleted_nodes == 1
    assert repo.deleted_relationships[0]["relation_type"] == "HAS_METRIC"
    assert repo.deleted_relationships[0]["domain"] == "食品接触材料"
    assert repo.deleted_nodes[0] == {
        "org_id": "org-1",
        "node_id": "qkg:org-1:Metric:食品接触材料:铅迁移量",
    }


@pytest.mark.asyncio
async def test_service_ingests_completed_result_quality_kg_chains_only_when_explicit():
    from app.services.quality_kg_service import QualityKnowledgeGraphService

    repo = FakeQualityKgRepository()
    service = QualityKnowledgeGraphService(repo=repo, org_id="org-1")

    empty_count = await service.ingest_completed_result({"reasoning_chain": {"defects": []}})
    ingested_count = await service.ingest_completed_result(
        {
            "reasoning_chain": {
                "quality_kg_chains": [ceramic_chain_payload()],
            }
        }
    )

    assert empty_count == 0
    assert ingested_count == 1
    assert repo.schema_ensured is True
    assert len(repo.ingested) == 1
