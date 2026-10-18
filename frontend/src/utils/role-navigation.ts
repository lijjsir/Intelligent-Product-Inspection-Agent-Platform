import { ADMIN_MENU_GROUPS } from "@/utils/admin-workspace";
import { ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_EXPERT } from "@/constants/roles";

export interface MenuItem {
  title: string;
  path: string;
  icon?: string;
  placeholder?: boolean;
  activeMatchPaths?: string[];
}

export interface MenuGroup {
  title: string;
  icon?: string;
  items: MenuItem[];
}

export type MenuStructure = (MenuItem | MenuGroup)[];

export function roleMenuFor(role: string): MenuStructure {
  if (role === ROLE_ADMIN) return getAdminMenu();
  if (role === ROLE_APP_DEVELOPER) return getAppDeveloperMenu();
  if (role === ROLE_PLATFORM_OPERATOR) return getPlatformOperatorMenu();
  if (role === ROLE_ALGORITHM_ENGINEER) return getAlgorithmEngineerMenu();
  if (role === ROLE_EXPERT) return getExpertMenu();
  return getUserMenu();
}

export function roleMenuPaths(role: string): string[] {
  return roleMenuFor(role).flatMap(entry => "items" in entry ? entry.items.map(item => item.path) : [entry.path]);
}

function getAdminMenu(): MenuStructure {
  return [
    ...ADMIN_MENU_GROUPS.flatMap<MenuItem | MenuGroup>(group =>
      group.title === "知识治理"
        ? group.items.map(item => ({ ...item }))
        : [{ ...group, items: group.items.map(item => ({ ...item })) }],
    ),
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getAppDeveloperMenu(): MenuStructure {
  return [
    ...getCollaborationMenuItems(),
    { title: "Agent 管理", path: "/ops/agents" },
    { title: "路由策略", path: "/ops/agents/intent-routes" },
    { title: "Prompt 管理", path: "/ops/prompts" },
    { title: "RAG 分析", path: "/ops/rag" },
    {
      title: "工具管理",
      items: [
        { title: "工具总览", path: "/ops/tools" },
        { title: "工具库", path: "/ops/tools/catalog" },
        { title: "外部导入", path: "/ops/tools/import" },
        { title: "Agent 绑定", path: "/ops/tools/bindings" },
        { title: "执行监控", path: "/ops/tools/executions" },
      ],
    },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getPlatformOperatorMenu(): MenuStructure {
  return [
    ...getCollaborationMenuItems(),
    { title: "平台运营工作台", path: "/ops/dashboard" },
    { title: "任务查看", path: "/ops/tasks" },
    { title: "市场监控", path: "/app/quality-analytics" },
    { title: "分析中心", path: "/ops/analytics" },
    { title: "告警管理", path: "/ops/alerts" },
    { title: "模型观测", path: "/ops/calls" },
    { title: "Agent 查看", path: "/ops/agents" },
    { title: "检测执行策略", path: "/ops/ai-review-gates" },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getAlgorithmEngineerMenu(): MenuStructure {
  return [
    ...getCollaborationMenuItems(),
    { title: "数据接入", path: "/ops/data/import" },
    { title: "已授权业务样本", path: "/ops/data/business-samples" },
    { title: "正常响应基线", path: "/ops/data/baselines" },
    { title: "测试集管理", path: "/ops/data/eval-sets" },
    { title: "训练任务", path: "/ops/training/jobs" },
    { title: "微调管理", path: "/ops/training/fine-tune" },
    { title: "离线评测", path: "/ops/eval/offline" },
    { title: "概率校准评测", path: "/ops/eval/calibration" },
    { title: "在线验证", path: "/ops/eval/online" },
    { title: "实验追踪", path: "/ops/experiments" },
    { title: "部署记录", path: "/ops/deployments" },
    { title: "模型配置", path: "/governance/admin/models" },
    { title: "GPU 调度", path: "/governance/admin/gpu" },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getCollaborationMenuItems(): MenuItem[] {
  return [
    { title: "会议室", path: "/app/meetings" },
    { title: "协作中心", path: "/app/collab" },
  ];
}

function getQualitySupervisionGroup(): MenuGroup {
  return {
    title: "质量监督",
    icon: "Operation",
    items: [
      { title: "质监工作台", path: "/app/workbench" },
      { title: "数据采集", path: "/app/quality-data" },
      { title: "市场监控", path: "/app/quality-analytics" },
      { title: "风险研判", path: "/app/risk-assessments" },
      { title: "监督抽查", path: "/app/sampling-plans", activeMatchPaths: ["/app/risk-sampling"] },
    ],
  };
}

function getUserMenu(): MenuStructure {
  return [
    { title: "AI 对话", path: "/app/chat" },
    {
      title: "我的任务",
      icon: "List",
      items: [
        { title: "任务列表", path: "/app/tasks" },
        { title: "检测结果", path: "/app/results", activeMatchPaths: ["/app/export"] },
      ],
    },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getExpertMenu(): MenuStructure {
  return [
    { title: "AI 对话", path: "/app/chat" },
    getQualitySupervisionGroup(),
    { title: "实验室检测", path: "/app/laboratory", activeMatchPaths: ["/app/inspection-sessions", "/app/samples"] },
    { title: "检测任务", path: "/app/tasks" },
    { title: "检测结果", path: "/app/results" },
    { title: "协同中心", path: "/app/collab", activeMatchPaths: ["/app/meetings"] },
    { title: "报告中心", path: "/app/risk-reports", activeMatchPaths: ["/app/export"] },
    { title: "标准与知识", items: [
      { title: "标准审核", path: "/app/standard-reviews", activeMatchPaths: ["/governance/admin/inspection-standards"] },
      { title: "知识资料", path: "/app/rag-spaces" },
    ] },
    { title: "个人设置", path: "/app/profile" },
  ];
}
