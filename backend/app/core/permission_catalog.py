"""Display labels for the real backend authorization keys (not simulated CRUD)."""
from app.core.permissions import PERMISSIONS, PERMISSION_DEPENDENCIES

GROUPS = [
    {"key": "inspection", "label": "检测与分析"},
    {"key": "collaboration", "label": "对话与协作"},
    {"key": "algorithm", "label": "算法与模型"},
    {"key": "application", "label": "应用与智能体"},
    {"key": "standard", "label": "标准管理"},
    {"key": "knowledge", "label": "知识治理"},
    {"key": "strategy", "label": "规则与复核"},
    {"key": "monitor", "label": "监控与告警"},
    {"key": "organization", "label": "人员与权限"},
    {"key": "governance", "label": "系统治理"},
]

LABELS = {
    "task": ("inspection", "检测任务", "使用"),
    "result": ("inspection", "检测结果", "查看"),
    "stability": ("inspection", "稳定性评估", "查看"),
    "analytics": ("inspection", "分析中心", "查看"),
    "quality": ("inspection", "质监业务", "访问"),
    "quality_material_submit": ("inspection", "资料接入", "提交"),
    "quality_material_read_own": ("inspection", "本人提交记录", "查看"),
    "quality_material_read_business": ("inspection", "授权业务资料", "查看"),
    "quality_ingestion_manage": ("inspection", "资料导入记录", "管理"),
    "quality_delete": ("inspection", "质监业务", "删除"),
    "feedback": ("inspection", "异常反馈", "使用"),
    "report_generate": ("inspection", "检测报告", "生成与管理记录"),
    "report_read": ("inspection", "检测报告", "查看与下载"),
    "chat": ("collaboration", "AI 对话", "使用"),
    "collab": ("collaboration", "历史协作记录", "查阅"),
    "meeting": ("collaboration", "会议室", "参与"),
    "meeting_admin": ("collaboration", "会议管理", "管理"),
    "dataset": ("algorithm", "数据接入", "管理数据集"),
    "algo_workspace": ("algorithm", "训练与评测", "使用"),
    "model_config_read": ("algorithm", "模型配置", "查看"),
    "model_config": ("algorithm", "模型配置", "管理"),
    "gpu_infra": ("algorithm", "GPU 调度", "管理"),
    "agent_ops_read": ("application", "Agent 管理", "查看"),
    "agent_ops": ("application", "Agent 管理", "管理"),
    "tool": ("application", "工具管理", "管理"),
    "prompt_admin": ("application", "Prompt 管理", "管理"),
    "inspection_spec_read": ("strategy", "检测执行策略", "查看"),
    "inspection_spec": ("strategy", "检测执行策略", "配置"),
    "inspection_standard_library_read": ("standard", "标准文档库", "查看"),
    "inspection_standard_library": ("standard", "标准文档库", "维护与上传"),
    "standard_admission_submit": ("standard", "标准准入", "提交与补充来源"),
    "standard_admission_review": ("standard", "标准准入", "专业核验"),
    "standard_admission_publish": ("standard", "标准准入", "发布与撤回"),
    "standard_review_assign": ("standard", "标准审核任务", "分派与调整"),
    "product_master_read": ("foundation", "产品目录", "查看目录"),
    "product_master": ("foundation", "产品目录", "维护目录"),
    "alert": ("monitor", "告警管理", "使用"),
    "alert_rule_read": ("monitor", "告警规则", "查看"),
    "alert_rule": ("monitor", "告警规则", "管理"),
    "user": ("organization", "用户管理", "管理"),
    "organization": ("organization", "组织管理", "管理"),
    "role_read": ("organization", "权限管理", "查看"),
    "approval_create": ("governance", "审批申请", "发起"),
    "approval_read": ("governance", "审批申请", "查看"),
    "approval": ("governance", "高风险操作审批", "审批"),
    "audit": ("governance", "审计记录", "查看"),
    "audit_log": ("governance", "审计日志", "查看"),
    "auth_log": ("governance", "登录日志", "查看"),
    "billing": ("governance", "计费管理", "管理"),
    "infrastructure": ("governance", "存储与基础设施", "管理"),
    "memory_governance": ("knowledge", "知识准入与发布", "管理"),
    "memory_policy": ("knowledge", "知识治理策略", "配置"),
    "knowledge_candidate_submit": ("knowledge", "知识候选", "提交本人或授权来源"),
    "knowledge_read": ("knowledge", "知识资料与候选", "查看授权内容"),
    "knowledge_review": ("knowledge", "知识准入", "专业核验"),
    "knowledge_share_decide": ("knowledge", "知识共享", "审批组织使用范围"),
    "knowledge_publish": ("knowledge", "知识发布", "发布与撤回"),
    "inspection_execution": ("inspection", "标准要求执行", "执行授权任务"),
    "inspection_execution_review": ("inspection", "标准执行结果", "独立专业复核"),
}

GROUPS.insert(4, {"key": "foundation", "label": "质监基础"})

DESCRIPTIONS = {
    "standard_admission_publish": "管理员默认负责标准启用、发布和撤回；领域专家须经明确授权后执行发布。",
    "standard_review_assign": "向本组织具备专业核验权限的专家分派具体标准修订，记录领域、期限和调整原因。",
    "task": "访问任务、创建与执行的能力还受角色业务边界约束；普通用户仅限本人任务。",
    "result": "普通用户只查看本人任务结果；专家在授权范围内查看和复核。",
    "quality": "对应质监工作台、市场监控、舆情监测和风险研判；不等于产品或标准维护。",
    "quality_ingestion_manage": "导入记录的处理仍按记录归属和业务授权限制，普通用户仅限本人提交。",
    "product_master_read": "产品目录完整浏览；任务和资料表单的名称选项不属于此权限。",
    "product_master": "维护产品类别、产品和批次，当前只开放管理员。",
    "algo_workspace": "对应训练、微调、测试集、离线评测、在线验证及部署等算法流程。",
    "inspection_spec_read": "读取检测执行策略，不包括标准文档浏览或策略修改。",
    "inspection_standard_library": "维护标准库并上传标准文档；查看权限单独控制。",
    "role_read": "读取角色和权限矩阵；授予或撤销授权还必须是管理员。",
    "report_generate": "生成或清理导出记录，仍须能访问对应任务和结果；不修改或签发检测结论。",
    "report_read": "查看导出记录并下载文件，普通用户仅本人任务的报告。与异常反馈权限无关。",
}

ROLE_PRESENTATION = {
    "quality": {
        "algorithm_engineer": {"name": "质量评测数据", "action": "访问评测", "description": "质量评分与可信度等评测接口；不开放质监业务档案管理。"},
        "app_developer": {"name": "质量评测数据", "action": "访问评测", "description": "质量评分与可信度等评测接口；不开放质监业务档案管理。"},
    },
    "quality_ingestion_manage": {
        "user": {"action": "处理本人导入", "description": "仅处理本人提交的导入记录，不开放其他用户或全组织的记录。"},
    },
}


def permission_catalog():
    return [
        {"key": key, "group": group, "name": name, "action": action, "description": DESCRIPTIONS.get(key, ""), "role_presentation": ROLE_PRESENTATION.get(key, {}), "requires": sorted(PERMISSION_DEPENDENCIES.get(key, set()))}
        for key, (group, name, action) in LABELS.items() if key in PERMISSIONS
    ]
