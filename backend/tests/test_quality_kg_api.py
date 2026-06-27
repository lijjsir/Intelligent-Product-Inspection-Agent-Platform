import pytest

from app.schemas.user import CurrentUser


def current_user(role: str = "expert") -> CurrentUser:
    return CurrentUser(user_id=f"{role}-1", org_id="org-1", role=role, roles=[role])


def ceramic_chain_payload():
    return {
        "domain": "食品接触材料",
        "product_category": "陶瓷杯",
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
async def test_create_quality_kg_chain_api(monkeypatch):
    from app.api.v1 import quality_kg as api
    from app.services.quality_kg_schema import QualityKnowledgeChain

    calls = []

    class FakeService:
        def __init__(self, *, org_id):
            self.org_id = org_id

        async def ingest_chain(self, chain):
            calls.append((self.org_id, chain))

    monkeypatch.setattr(api, "QualityKnowledgeGraphService", FakeService)

    response = await api.create_quality_chain(
        payload=QualityKnowledgeChain(**ceramic_chain_payload()),
        current=current_user(),
    )

    assert response.data == {
        "success": True,
        "message": "quality knowledge chain ingested",
    }
    assert calls[0][0] == "org-1"
    assert calls[0][1].metric == "铅迁移量"


@pytest.mark.asyncio
async def test_create_quality_kg_chains_batch_api(monkeypatch):
    from app.api.v1 import quality_kg as api
    from app.services.quality_kg_schema import QualityKnowledgeChainBatch

    calls = []

    class FakeService:
        def __init__(self, *, org_id):
            self.org_id = org_id

        async def ingest_chains(self, chains):
            calls.append((self.org_id, chains))

    monkeypatch.setattr(api, "QualityKnowledgeGraphService", FakeService)

    response = await api.create_quality_chains_batch(
        payload=QualityKnowledgeChainBatch(items=[ceramic_chain_payload()]),
        current=current_user(),
    )

    assert response.data == {"success": True, "ingested": 1}
    assert calls[0][0] == "org-1"
    assert len(calls[0][1]) == 1


@pytest.mark.asyncio
async def test_query_quality_kg_api(monkeypatch):
    from app.api.v1 import quality_kg as api

    class FakeService:
        def __init__(self, *, org_id):
            self.org_id = org_id

        async def search_standards_by_product(self, domain, product_category):
            return ["GB 4806.4-2016"]

        async def search_actions_by_product_and_metric(self, domain, product_category, metric):
            return ["复检", "禁止放行"]

        async def search_risks_by_defect(self, domain, defect_type):
            return ["食品接触安全风险"]

        async def search_actions_by_defect(self, domain, defect_type):
            return ["复检"]

        async def search_clauses_by_standard(self, domain, standard):
            return ["第 4.2 条"]

        async def search_items_by_clause(self, domain, standard_clause):
            return ["铅迁移量检测"]

        async def search_metrics_by_item(self, domain, inspection_item):
            return ["铅迁移量"]

        async def search_defects_by_metric(self, domain, metric):
            return ["重金属迁移超标"]

        async def search_causes_by_defect(self, domain, defect_type):
            return ["釉料重金属含量异常"]

        async def search_chain_paths_by_product(self, domain, product_category):
            return [{"standard": "GB 4806.4-2016", "metric": "铅迁移量"}]

    monkeypatch.setattr(api, "QualityKnowledgeGraphService", FakeService)

    standards = await api.get_standards_by_product(
        product_category="陶瓷杯",
        domain="食品接触材料",
        current=current_user(),
    )
    metric_actions = await api.get_actions_by_metric(
        domain="食品接触材料",
        metric="铅迁移量",
        product_category="陶瓷杯",
        current=current_user(),
    )
    defect_actions = await api.get_defect_actions(
        defect_type="重金属迁移超标",
        domain="食品接触材料",
        current=current_user(),
    )
    clauses = await api.get_clauses_by_standard(
        standard="GB 4806.4-2016",
        domain="食品接触材料",
        current=current_user(),
    )
    items = await api.get_items_by_clause(
        standard_clause="第 4.2 条",
        domain="食品接触材料",
        current=current_user(),
    )
    metrics = await api.get_metrics_by_item(
        inspection_item="铅迁移量检测",
        domain="食品接触材料",
        current=current_user(),
    )
    defects = await api.get_defects_by_metric(
        metric="铅迁移量",
        domain="食品接触材料",
        current=current_user(),
    )
    causes = await api.get_causes_by_defect(
        defect_type="重金属迁移超标",
        domain="食品接触材料",
        current=current_user(),
    )
    paths = await api.get_chain_paths_by_product(
        product_category="陶瓷杯",
        domain="食品接触材料",
        current=current_user(),
    )

    assert standards.data == {"standards": ["GB 4806.4-2016"]}
    assert metric_actions.data == {"actions": ["复检", "禁止放行"]}
    assert defect_actions.data == {
        "risks": ["食品接触安全风险"],
        "actions": ["复检"],
    }
    assert clauses.data == {"clauses": ["第 4.2 条"]}
    assert items.data == {"items": ["铅迁移量检测"]}
    assert metrics.data == {"metrics": ["铅迁移量"]}
    assert defects.data == {"defects": ["重金属迁移超标"]}
    assert causes.data == {"causes": ["釉料重金属含量异常"]}
    assert paths.data == {"paths": [{"standard": "GB 4806.4-2016", "metric": "铅迁移量"}]}


@pytest.mark.asyncio
async def test_admin_quality_kg_delete_api(monkeypatch):
    from app.api.v1 import quality_kg as api
    from app.services.quality_kg_schema import QualityKgNodeDelete, QualityKgRelationshipDelete

    calls = []

    class FakeService:
        def __init__(self, *, org_id):
            self.org_id = org_id

        async def delete_relationship(self, payload):
            calls.append(("relationship", self.org_id, payload))
            return 1

        async def delete_node(self, payload):
            calls.append(("node", self.org_id, payload))
            return 1

    monkeypatch.setattr(api, "QualityKnowledgeGraphService", FakeService)

    edge_response = await api.delete_quality_relationship(
        payload=QualityKgRelationshipDelete(
            relation_type="HAS_METRIC",
            start_node_id="qkg:org-1:InspectionItem:食品接触材料:铅迁移量检测",
            end_node_id="qkg:org-1:Metric:食品接触材料:铅迁移量",
            domain="食品接触材料",
            product_category="陶瓷杯",
        ),
        current=current_user("admin"),
    )
    node_response = await api.delete_quality_node(
        payload=QualityKgNodeDelete(node_id="qkg:org-1:Metric:食品接触材料:铅迁移量"),
        current=current_user("admin"),
    )

    assert edge_response.data == {"deleted": 1}
    assert node_response.data == {"deleted": 1}
    assert calls[0][0] == "relationship"
    assert calls[1][0] == "node"
