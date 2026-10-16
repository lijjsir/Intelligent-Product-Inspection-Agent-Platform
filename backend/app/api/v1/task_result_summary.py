from fastapi import APIRouter,Depends,Query
from app.api.v1.deps import get_db,get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.task_result_bundle_service import TaskResultBundleService

router=APIRouter()

@router.get('/execution-options',response_model=ResponseEnvelope[list[dict]])
async def execution_options(current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role('result',current.role);require_role('task',current.role);require_role('inspection_execution',current.role)
    from sqlalchemy import select
    from app.models.inspection_execution import InspectionExecutionRun
    from app.models.task import InspectionTask
    from app.services.inspection_execution_service import InspectionExecutionService
    query=select(InspectionExecutionRun.id,InspectionTask.id).join(InspectionTask,InspectionTask.id==InspectionExecutionRun.task_id).where(
        InspectionExecutionRun.org_id==current.org_id,InspectionTask.org_id==current.org_id,InspectionTask.deleted_at.is_(None),InspectionExecutionRun.status=='accepted')
    if str(current.role)=='user':query=query.where(InspectionTask.created_by==current.user_id)
    rows=(await db.execute(query.order_by(InspectionExecutionRun.created_at.desc()).limit(200))).all()
    output=[]
    for run_id,task_id in rows:
        run=await db.get(InspectionExecutionRun,run_id)
        task=await db.get(InspectionTask,task_id)
        issues=await InspectionExecutionService(db,current).validity(run)
        output.append({'id':run.id,'task_id':task.id,'row_version':run.row_version,'label':f"{run.snapshot.get('product_category','')} · {task.product_id} · 版本{run.row_version}",
            'issues':issues,'scope':(run.snapshot.get('task_context') or {}).get('scope') or {}})
    return ResponseEnvelope(data=output)

@router.get('/unified',response_model=ResponseEnvelope[dict])
async def unified(page:int=Query(1,ge=1),size:int=Query(20,ge=1,le=50),product_id:str|None=None,task_id:str|None=None,verdict:str|None=None,
    model_key:str|None=None,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role('result',current.role);require_role('task',current.role)
    return ResponseEnvelope(data=await TaskResultBundleService(db,current).list_results(page,size,product_id,task_id,verdict,model_key))

@router.get('/report-tasks',response_model=ResponseEnvelope[list[dict]])
async def report_tasks(limit:int=Query(default=100,ge=1,le=200),current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role('report_read',current.role)
    require_role('task',current.role);require_role('result',current.role)
    return ResponseEnvelope(data=await TaskResultBundleService(db,current).report_tasks(limit))

@router.get('/by-task/{task_id}/summary',response_model=ResponseEnvelope[dict])
async def summary(task_id:str,execution_run_id:str|None=None,legacy_only:bool=False,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role('result',current.role)
    return ResponseEnvelope(data=await TaskResultBundleService(db,current).summary(task_id,execution_run_id=execution_run_id,legacy_only=legacy_only))
