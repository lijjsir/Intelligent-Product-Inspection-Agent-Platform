"""Read-only readiness check for canonical results, without generating artifacts."""
import asyncio,argparse,json
from pathlib import Path
from sqlalchemy import select,text
from app.models.task import InspectionTask
from app.models.user import User
from app.schemas.user import CurrentUser
from app.services.task_result_bundle_service import TaskResultBundleService
from infra.database.session import get_session,reset_async_engine_pool

async def main(output):
    result={'read_only':True,'tasks':[]}
    try:
        async with get_session() as db:
            result['schema']=list(await db.scalars(text('SELECT version_num FROM alembic_version')))
            for task in (await db.scalars(select(InspectionTask).where(InspectionTask.deleted_at.is_(None)))).all():
                user=await db.get(User,task.created_by)
                if not user or user.role not in {'user','expert'}:continue
                bundle=await TaskResultBundleService(db,CurrentUser(user_id=user.id,org_id=user.org_id,role=user.role)).summary(task.id)
                result['tasks'].append({'stored_status':task.status,'stage':bundle['scope']['stage'],'has_execution':bool(bundle['execution']),
                    'has_auxiliary':bool(bundle['auxiliary']),'has_visible_risk':bool(bundle['risks']),'can_export':bundle['can_export'],
                    'product_verdict':bundle['scope']['product_verdict'],'current_issues':bundle['execution']['current_source_issues'] if bundle['execution'] else []})
    finally:await reset_async_engine_pool()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);asyncio.run(main(parser.parse_args().output))
