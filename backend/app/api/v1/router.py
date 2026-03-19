from fastapi import APIRouter

from app.api.v1 import auth, users, tasks, results, stability, alerts, tools, analytics, agent

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
router.include_router(results.router, prefix="/results", tags=["results"])
router.include_router(stability.router, prefix="/stability", tags=["stability"])
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
router.include_router(tools.router, prefix="/tools", tags=["tools"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(agent.router, prefix="/agent", tags=["agent"])
