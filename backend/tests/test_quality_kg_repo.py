import pytest


@pytest.mark.asyncio
async def test_quality_kg_repo_ensures_schema_for_documented_labels_and_indexes(monkeypatch):
    from app.repositories import quality_kg_repo as repo_mod

    executed: list[str] = []

    class FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, cypher):
            executed.append(cypher)

    class FakeDriver:
        def session(self, database):
            assert database == "neo4j"
            return FakeSessionCtx()

    class FakeAsyncGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            assert uri == "bolt://neo4j:7687"
            assert auth == ("neo4j", "secret")
            return FakeDriver()

    monkeypatch.setattr(repo_mod, "AsyncGraphDatabase", FakeAsyncGraphDatabase)

    repo = repo_mod.Neo4jQualityKgRepository("bolt://neo4j:7687", "neo4j", "secret")
    await repo.ensure_schema()

    assert any("FOR (n:DetectionDomain)" in cypher for cypher in executed)
    assert any("FOR (n:Action)" in cypher for cypher in executed)
    assert any("product_category_name" in cypher for cypher in executed)
    assert any("metric_name" in cypher for cypher in executed)


@pytest.mark.asyncio
async def test_quality_kg_repo_merges_nodes_and_relationships(monkeypatch):
    from app.repositories import quality_kg_repo as repo_mod
    from app.services.quality_kg_schema import QualityKgNode, QualityKgRelationship

    executed: list[tuple[str, dict]] = []

    class FakeResult:
        async def consume(self):
            return None

    class FakeTx:
        async def run(self, query, params):
            executed.append((query, params))
            return FakeResult()

    class FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute_write(self, fn, query, params):
            return await fn(FakeTx(), query, params)

    class FakeDriver:
        def session(self, database):
            return FakeSessionCtx()

    class FakeAsyncGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return FakeDriver()

    monkeypatch.setattr(repo_mod, "AsyncGraphDatabase", FakeAsyncGraphDatabase)

    repo = repo_mod.Neo4jQualityKgRepository("bolt://neo4j:7687", "neo4j", "secret")
    await repo.ingest_chain(
        nodes=[
            QualityKgNode(
                id="qkg:org-1:DetectionDomain:食品接触材料:食品接触材料",
                org_id="org-1",
                type="DetectionDomain",
                name="食品接触材料",
                normalized_name="食品接触材料",
                domain="食品接触材料",
            ),
            QualityKgNode(
                id="qkg:org-1:ProductCategory:食品接触材料:陶瓷杯",
                org_id="org-1",
                type="ProductCategory",
                name="陶瓷杯",
                normalized_name="陶瓷杯",
                domain="食品接触材料",
            ),
        ],
        relationships=[
            QualityKgRelationship(
                type="HAS_CATEGORY",
                start_node_id="qkg:org-1:DetectionDomain:食品接触材料:食品接触材料",
                end_node_id="qkg:org-1:ProductCategory:食品接触材料:陶瓷杯",
                org_id="org-1",
                domain="食品接触材料",
                product_category="陶瓷杯",
                confidence=0.9,
                source="inspection_result",
            )
        ],
    )

    node_query, node_params = executed[0]
    rel_query, rel_params = executed[-1]
    assert "MERGE (n:DetectionDomain {id: $id})" in node_query
    assert node_params["normalized_name"] == "食品接触材料"
    assert "MERGE (src)-[r:HAS_CATEGORY" in rel_query
    assert "count = coalesce(r.count, 0) + 1" in rel_query
    assert rel_params["confidence"] == 0.9


def test_quality_kg_repo_rejects_unknown_relationship_type():
    from app.repositories.quality_kg_repo import validate_relationship_type

    with pytest.raises(ValueError, match="Unsupported quality KG relationship type"):
        validate_relationship_type("DROP_ALL")


@pytest.mark.asyncio
async def test_quality_kg_repo_supports_all_documented_read_queries():
    from app.repositories import quality_kg_repo as repo_mod

    repo = object.__new__(repo_mod.Neo4jQualityKgRepository)
    calls: list[tuple[str, dict]] = []
    responses = [
        [{"clause": "第 4.2 条"}],
        [{"item": "铅迁移量检测"}],
        [{"metric": "铅迁移量"}],
        [{"defect": "重金属迁移超标"}],
        [{"cause": "釉料重金属含量异常"}],
        [{"standard": "GB 4806.4-2016", "standard_clause": "第 4.2 条", "inspection_item": "铅迁移量检测", "metric": "铅迁移量"}],
    ]

    async def fake_execute_read(query, params):
        calls.append((query, params))
        return responses.pop(0)

    repo._execute_read = fake_execute_read

    assert await repo.search_clauses_by_standard(org_id="org-1", domain="食品接触材料", standard="gb 4806.4-2016") == ["第 4.2 条"]
    assert await repo.search_items_by_clause(org_id="org-1", domain="食品接触材料", standard_clause="第 4.2 条") == ["铅迁移量检测"]
    assert await repo.search_metrics_by_item(org_id="org-1", domain="食品接触材料", inspection_item="铅迁移量检测") == ["铅迁移量"]
    assert await repo.search_defects_by_metric(org_id="org-1", domain="食品接触材料", metric="铅迁移量") == ["重金属迁移超标"]
    assert await repo.search_causes_by_defect(org_id="org-1", domain="食品接触材料", defect_type="重金属迁移超标") == ["釉料重金属含量异常"]
    assert await repo.search_chain_paths_by_product(org_id="org-1", domain="食品接触材料", product_category="陶瓷杯") == [
        {
            "standard": "GB 4806.4-2016",
            "standard_clause": "第 4.2 条",
            "inspection_item": "铅迁移量检测",
            "metric": "铅迁移量",
        }
    ]

    assert "HAS_CLAUSE" in calls[0][0]
    assert "REQUIRES_ITEM" in calls[1][0]
    assert "HAS_METRIC" in calls[2][0]
    assert "INDICATES_DEFECT" in calls[3][0]
    assert "MAY_BE_CAUSED_BY" in calls[4][0]
    assert calls[5][1]["product_category"] == "陶瓷杯"


@pytest.mark.asyncio
async def test_quality_kg_repo_deletes_relationships_and_nodes():
    from app.repositories import quality_kg_repo as repo_mod

    repo = object.__new__(repo_mod.Neo4jQualityKgRepository)
    calls: list[tuple[str, dict]] = []
    responses = [[{"deleted": 1}], [{"deleted": 2}]]

    async def fake_execute_read(query, params):
        calls.append((query, params))
        return responses.pop(0)

    repo._execute_read = fake_execute_read

    deleted_edges = await repo.delete_relationship(
        org_id="org-1",
        relation_type="HAS_METRIC",
        start_node_id="start",
        end_node_id="end",
        domain="食品接触材料",
        product_category="陶瓷杯",
    )
    deleted_nodes = await repo.delete_node(org_id="org-1", node_id="node-1")

    assert deleted_edges == 1
    assert deleted_nodes == 2
    assert "MATCH (src {id: $start_node_id})-[r:HAS_METRIC" in calls[0][0]
    assert "DETACH DELETE n" in calls[1][0]
