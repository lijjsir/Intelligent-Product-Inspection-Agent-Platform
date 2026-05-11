from fastapi import APIRouter

from app.api.v1 import (
    agent,
    agent_ops,
    alerts,
    analytics,
    auth,
    chat,
    billing,
    feedbacks,
    inspection_specs,
    memory,
    model_configs,
    quality,
    rag_spaces,
    results,
    stability,
    streams,
    tasks,
    tools,
    users,
)

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
router.include_router(agent_ops.router, tags=["agent-ops"])
router.include_router(chat.router, tags=["chat"])
router.include_router(rag_spaces.router, tags=["rag-spaces"])
router.include_router(streams.router, tags=["streams"])
router.include_router(model_configs.router, prefix="/model-configs", tags=["model-configs"])
router.include_router(inspection_specs.router, prefix="/inspection-specs", tags=["inspection-specs"])
router.include_router(billing.router, prefix="/billing", tags=["billing"])
router.include_router(feedbacks.router, prefix="/feedbacks", tags=["feedbacks"])
router.include_router(quality.router, prefix="/quality", tags=["quality"])
router.include_router(memory.router, prefix="/memory", tags=["memory"])
