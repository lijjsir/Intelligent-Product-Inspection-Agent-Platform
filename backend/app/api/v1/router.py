from fastapi import APIRouter

from app.api.v1 import (
    admin_meetings,
    algo_runtime,
    algo_workspace,
    agent,
    agent_ops,
    approvals,
    alert_rules,
    alerts,
    audit_logs,
    auth_logs,
    analytics,
    auth,
    chat,
    billing,
    datasets,
    feedbacks,
    gpu_nodes,
    organizations,
    inspection_specs,
    inspection_standards,
    infrastructure,
    langfuse_proxy,
    memory,
    meetings,
    model_configs,
    prompt_admin,
    quality,
    rag_spaces,
    roles,
    results,
    stability,
    streams,
    tasks,
    tools,
    users,
)

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
router.include_router(results.router, prefix="/results", tags=["results"])
router.include_router(stability.router, prefix="/stability", tags=["stability"])
router.include_router(alert_rules.router, prefix="/alerts", tags=["alert-rules"])
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
router.include_router(tools.router, prefix="/tools", tags=["tools"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(agent.router, prefix="/agent", tags=["agent"])
router.include_router(agent_ops.router, tags=["agent-ops"])
router.include_router(prompt_admin.router, tags=["prompt-admin"])
router.include_router(chat.router, tags=["chat"])
router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
router.include_router(algo_workspace.router, tags=["algo-workspace"])
router.include_router(algo_runtime.router, tags=["algo-runtime"])
router.include_router(meetings.router, tags=["meetings"])
router.include_router(admin_meetings.router, tags=["admin-meetings"])
router.include_router(rag_spaces.router, tags=["rag-spaces"])
router.include_router(streams.router, tags=["streams"])
router.include_router(model_configs.router, prefix="/model-configs", tags=["model-configs"])
router.include_router(inspection_standards.router, prefix="/inspection-standards", tags=["inspection-standards"])
router.include_router(inspection_specs.router, prefix="/inspection-specs", tags=["inspection-specs"])
router.include_router(billing.router, prefix="/billing", tags=["billing"])
router.include_router(infrastructure.router, prefix="/infrastructure", tags=["infrastructure"])
router.include_router(auth_logs.router, prefix="/auth-logs", tags=["auth-logs"])
router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit-logs"])
router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
router.include_router(feedbacks.router, prefix="/feedbacks", tags=["feedbacks"])
router.include_router(gpu_nodes.router, tags=["gpu-nodes"])
router.include_router(quality.router, prefix="/quality", tags=["quality"])
router.include_router(langfuse_proxy.router, tags=["langfuse"])
router.include_router(memory.router, prefix="/memory", tags=["memory"])
