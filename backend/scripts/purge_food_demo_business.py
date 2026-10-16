"""One-time, explicitly authorized cleanup of one local demo category and its business."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict

from sqlalchemy import String, delete, func, inspect, or_, select, update

from app.models import Base
from app.models.business_number import BusinessIdentifier
from app.models.quality_risk import ProductCategory
from app.models.graph_checkpoint import GraphCheckpoint
from infra.database.session import get_session, reset_async_engine_pool

ORG_ID = '26c1c3e4-658b-498d-aab7-39b194de478c'
CATEGORY_ID = '01a0ed43-be3d-7128-a7a7-f3dac510623c'
REMOVED_PRODUCT_ID = '01a0ee00-6475-73fd-b7b4-659c2cc6cb66'
CATEGORY_CODE = 'CAT-8AC383BE'
ALLOWED = {
    'quality_products', 'quality_production_batches', 'product_identifiers', 'enterprise_product_relations',
    'quality_source_records', 'quality_evidence_items', 'quality_risk_cases', 'quality_risk_assessments',
    'physical_samples', 'quality_market_monitoring_reports', 'quality_public_opinion_reports', 'standard_execution_rules',
    'inspection_tasks', 'inspection_results', 'inspection_result_evidence', 'task_execution_events', 'stability_reports',
    'alert_events', 'result_feedbacks', 'export_jobs', 'agent_artifacts', 'rag_query_logs', 'agent_route_logs',
    'supervision_records', 'supervision_revisions', 'supervision_runs', 'supervision_dependencies', 'supervision_events',
    'business_reviews', 'measurement_batches', 'measurement_records', 'inspection_goals', 'inspection_evidence_states',
    'inspection_decisions', 'device_commands', 'audit_logs', 'audit_outbox', 'token_usage_ledger', 'message_feedbacks',
    'chat_messages', 'tool_executions', 'tool_runtime_events',
    'dataset_samples', 'rag_documents', 'rag_document_chunks', 'rag_index_jobs',
    'memory_items', 'memory_origins', 'memory_evidence', 'memory_events', 'memory_dependency_edges',
    'memory_candidate_supports', 'memory_sync_outbox',
}
NON_REFERENCE = {'org_id', 'id', 'user_id', 'actor_id', 'created_by', 'assigned_to', 'reviewed_by', 'reviewer_id', 'requester_id', 'uploaded_by'}


def predicates(table, identifiers):
    expressions = []
    for col in table.c:
        if col.name in NON_REFERENCE:
            continue
        type_name = col.type.__class__.__name__
        if type_name == 'UUIDBinary':
            expressions.append(col.in_(identifiers))
        elif type_name in {'JSON', 'String', 'Text', 'LONGTEXT'}:
            expressions.extend(col.cast(String).contains(value, autoescape=True) for value in identifiers)
            # Legacy image tasks and drafts used the category code rather than its UUID.
            if table.name in {'inspection_tasks', 'supervision_records', 'supervision_revisions'}:
                expressions.append(col.cast(String).contains(CATEGORY_CODE, autoescape=True))
    return or_(*expressions) if expressions else None


async def discover(db, lock=False):
    connection = await db.connection()
    available = set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))
    stmt = select(ProductCategory).where(ProductCategory.id == CATEGORY_ID, ProductCategory.org_id == ORG_ID,
        ProductCategory.name == '食品', ProductCategory.code == CATEGORY_CODE)
    category = await db.scalar(stmt.with_for_update() if lock else stmt)
    if not category:
        return None
    identifiers = {CATEGORY_ID, REMOVED_PRODUCT_ID}
    found = defaultdict(dict)
    for iteration in range(20):
        changed = False
        for name in sorted(ALLOWED & Base.metadata.tables.keys() & available):
            table = Base.metadata.tables[name]
            if 'org_id' not in table.c or 'id' not in table.c:
                continue
            condition = predicates(table, identifiers)
            if condition is None:
                continue
            query = select(table).where(table.c.org_id == ORG_ID, condition)
            if name == 'supervision_records':
                query = query.where(~table.c.kind.in_(['enterprises', 'regions', 'devices']))
            if lock:
                query = query.with_for_update()
            rows = (await db.execute(query)).mappings().all()
            for row in rows:
                key = str(row['id'])
                if key not in found[name]:
                    found[name][key] = dict(row)
                    identifiers.add(key)
                    if name == 'agent_artifacts' and row.get('workflow_run_id'):
                        from uuid import UUID
                        try:
                            identifiers.add(str(UUID(row['workflow_run_id'])))
                        except ValueError:
                            pass
                    changed = True
        if not changed:
            break
    else:
        raise RuntimeError('关联链超过20轮，未执行删除')
    # These derived stores need external index/storage cleanup if populated; don't silently orphan them.
    external = {'dataset_samples', 'rag_documents', 'rag_document_chunks', 'memory_items'}
    if any(found[name] for name in external):
        raise RuntimeError('发现向量库/数据集派生记录，需要单独核对存储清理，未执行删除')
    for name in ['inspection_tasks', 'supervision_runs', 'export_jobs']:
        if any(row.get('status') in {'pending', 'queued', 'running'} for row in found[name].values()):
            raise RuntimeError(f'{name}仍有运行中的工作，需先停止指定任务，未执行删除')

    checkpoint_query = select(GraphCheckpoint.id).where(or_(*[
        GraphCheckpoint.thread_id.contains(value, autoescape=True) for value in identifiers]))
    checkpoint_ids = list(await db.scalars(checkpoint_query)) if 'graph_checkpoints' in available else []
    alias_ids = list(await db.scalars(select(BusinessIdentifier.entity_id).where(
        BusinessIdentifier.org_id == ORG_ID, BusinessIdentifier.entity_id.in_(identifiers))))
    plan = {name: sorted(rows) for name, rows in sorted(found.items()) if rows}
    plan['product_categories'] = [CATEGORY_ID]
    assets = sorted(set(url for row in found['inspection_tasks'].values() for url in (row.get('image_urls') or [])))
    if checkpoint_ids:
        plan['graph_checkpoints'] = sorted(checkpoint_ids)
    if alias_ids:
        plan['business_identifiers'] = sorted(set(alias_ids))
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return {'plan': plan, 'digest': digest, 'rows': found, 'identifiers': identifiers, 'assets': assets}


async def run(apply=False, expected=None):
    try:
        async with get_session() as db:
            discovery = await discover(db, lock=apply)
            if discovery is None:
                print(json.dumps({'category_exists': False, 'deleted': False}))
                return
            plan = discovery['plan']
            print(json.dumps({'category': '食品', 'org_id': ORG_ID, 'plan_hash': discovery['digest'],
                'counts': {name: len(ids) for name, ids in plan.items()}, 'plan': plan,
                'embedded_images': sum(url.startswith('data:') for url in discovery['assets']),
                'image_paths': [urlparse(url).path[:200] for url in discovery['assets'] if not url.startswith('data:')]}, ensure_ascii=False))
            if not apply:
                return
            if not expected or expected != discovery['digest']:
                raise RuntimeError('清理范围与已核对计划不一致，未执行删除')
            if any(not url.startswith('data:') for url in discovery['assets']):
                raise RuntimeError('存在独立图片文件，需先核对引用和存储清理，未执行删除')
            affected_users = {r['user_id'] for r in discovery['rows']['token_usage_ledger'].values() if r.get('user_id')}
            before = {}
            for name in plan:
                table = Base.metadata.tables[name]
                if 'org_id' in table.c:
                    before[name] = await db.scalar(select(func.count()).select_from(table).where(table.c.org_id == ORG_ID))
            counts = {}
            for table in reversed(Base.metadata.sorted_tables):
                if table.name not in plan or table.name in {'product_categories', 'business_identifiers', 'graph_checkpoints'}:
                    continue
                # Both the tenant and the exact reviewed row IDs are mandatory for every business delete.
                outcome = await db.execute(delete(table).where(table.c.org_id == ORG_ID, table.c.id.in_(plan[table.name])))
                counts[table.name] = outcome.rowcount
            if 'graph_checkpoints' in plan:
                outcome = await db.execute(delete(GraphCheckpoint).where(GraphCheckpoint.id.in_(plan['graph_checkpoints'])))
                counts['graph_checkpoints'] = outcome.rowcount
            if 'business_identifiers' in plan:
                outcome = await db.execute(delete(BusinessIdentifier).where(BusinessIdentifier.org_id == ORG_ID,
                    BusinessIdentifier.entity_id.in_(plan['business_identifiers'])))
                counts['business_identifiers'] = outcome.rowcount
            outcome = await db.execute(delete(ProductCategory).where(ProductCategory.org_id == ORG_ID, ProductCategory.id == CATEGORY_ID))
            counts['product_categories'] = outcome.rowcount
            from app.models.token_ledger import TokenUsageLedger
            from app.models.user_token_usage import UserTokenUsageSummary
            for user_id in affected_users:
                sums = (await db.execute(select(func.coalesce(func.sum(TokenUsageLedger.prompt_tokens), 0),
                    func.coalesce(func.sum(TokenUsageLedger.completion_tokens), 0), func.coalesce(func.sum(TokenUsageLedger.total_tokens), 0),
                    func.coalesce(func.sum(TokenUsageLedger.cost_amount), 0), func.count(), func.max(TokenUsageLedger.created_at)).where(
                    TokenUsageLedger.org_id == ORG_ID, TokenUsageLedger.user_id == user_id))).one()
                await db.execute(update(UserTokenUsageSummary).where(UserTokenUsageSummary.org_id == ORG_ID,
                    UserTokenUsageSummary.user_id == user_id).values(total_prompt_tokens=sums[0], total_completion_tokens=sums[1],
                    total_tokens=sums[2], total_cost=sums[3], request_count=sums[4], last_ledger_at=sums[5]))
            # Check exact targets are gone before committing the transaction.
            for name, ids in plan.items():
                table = Base.metadata.tables[name]
                key = table.c.entity_id if name == 'business_identifiers' else table.c.id
                query = select(func.count()).select_from(table).where(key.in_(ids))
                if 'org_id' in table.c:
                    query = query.where(table.c.org_id == ORG_ID)
                if await db.scalar(query):
                    raise RuntimeError(f'{name}存在清理残留，事务回滚')
                if name in before:
                    after = await db.scalar(select(func.count()).select_from(table).where(table.c.org_id == ORG_ID))
                    if before[name] - after != len(ids):
                        raise RuntimeError(f'{name}清理数量不符合核对范围，事务回滚')
            await db.commit()
            from redis.asyncio import Redis
            from app.core.config import settings
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            cache_count = 0
            try:
                async for key in redis.scan_iter(match=f'blackboard:{ORG_ID}:*'):
                    raw = await redis.get(key)
                    try:
                        context = json.loads(raw or '{}')
                    except ValueError:
                        continue
                    if context.get('task_id') in plan.get('inspection_tasks', []) or context.get('workflow_run_id') in discovery['identifiers']:
                        cache_count += await redis.delete(key)
            finally:
                await redis.aclose()
            report = {'deleted': True, 'org_id': ORG_ID, 'counts': counts,
                'blackboards_deleted': cache_count, 'plan': plan, 'unrelated_rows_preserved': True}
            output = Path('runtime/food_demo_cleanup_result.json')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'deleted': True, 'counts': counts, 'blackboards_deleted': cache_count, 'unrelated_rows_preserved': True}, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-plan-hash')
    args = parser.parse_args()
    asyncio.run(run(args.apply, args.expected_plan_hash))
