import { computed } from "vue";
import { useAuthStore } from "@/stores/auth.store";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_EXPERT,
} from "@/constants/roles";

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

export function isMenuGroup(entry: MenuItem | MenuGroup): entry is MenuGroup {
  return "items" in entry;
}

export function toggleActiveMenuGroupTitle(activeTitles: string[], title: string) {
  return activeTitles.includes(title)
    ? activeTitles.filter((item) => item !== title)
    : [...activeTitles, title];
}

export function resolveMenuGroupLandingPath(group: MenuGroup) {
  return group.items.find((item) => !item.placeholder)?.path;
}

export function useMenu() {
  const auth = useAuthStore();

  const primaryRole = computed(() => auth.primaryRole || auth.roles[0] || "");

  const showWorkspaceGroups = computed(() => primaryRole.value === ROLE_ADMIN);

  const menu = computed<MenuStructure>(() => {
    const role = primaryRole.value;

    if (role === ROLE_ADMIN) {
      return getAdminMenu();
    }
    if (role === ROLE_APP_DEVELOPER) {
      return getAppDeveloperMenu();
    }
    if (role === ROLE_PLATFORM_OPERATOR) {
      return getPlatformOperatorMenu();
    }
    if (role === ROLE_ALGORITHM_ENGINEER) {
      return getAlgorithmEngineerMenu();
    }
    if (role === ROLE_EXPERT) {
      return getExpertMenu();
    }
    // user (default)
    return getUserMenu();
  });

  return { menu, primaryRole, showWorkspaceGroups };
}

function getAdminMenu(): MenuStructure {
  return [
    ...getCollaborationMenuItems(),
    {
      title: "组织与人员",
      icon: "Management",
      items: [
        { title: "用户管理", path: "/governance/admin/users" },
        { title: "权限与组织", path: "/governance/admin/roles-orgs" },
      ],
    },
    {
      title: "质监基础",
      icon: "Files",
      items: [
        { title: "监管对象", path: "/governance/admin/enterprises" },
        { title: "产品与批次", path: "/governance/admin/product-master" },
        { title: "设备资源", path: "/governance/admin/devices" },
      ],
    },
    {
      title: "标准与知识",
      items: [
        { title: "检测标准", path: "/governance/admin/inspection-standards" },
        { title: "自动判定规则", path: "/governance/admin/inspection-specs" },
        { title: "记忆治理", path: "/governance/memory" },
      ],
    },
    {
      title: "系统治理",
      icon: "Management",
      items: [
        { title: "存储/基础设施", path: "/governance/admin/infrastructure" },
        { title: "告警规则", path: "/governance/admin/alert-rules" },
        { title: "计费管理", path: "/ops/billing" },
        { title: "分析中心", path: "/governance/quality/analysis-center" },
        { title: "日志中心", path: "/governance/admin/logs" },
        { title: "高风险审批", path: "/governance/admin/approvals" },
      ],
    },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getAppDeveloperMenu(): MenuStructure {
  return [
    ...getCollaborationMenuItems(),
    { title: "Agent 管理", path: "/ops/agents" },
    { title: "设备连接", path: "/ops/devices" },
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
    { title: "设备管理", path: "/ops/devices" },
    { title: "市场监控", path: "/app/quality-analytics" },
    { title: "分析中心", path: "/ops/analytics" },
    { title: "告警管理", path: "/ops/alerts" },
    { title: "模型观测", path: "/ops/calls" },
    { title: "Agent 查看", path: "/ops/agents" },
    { title: "自动判定规则", path: "/ops/inspection-specs" },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getAlgorithmEngineerMenu(): MenuStructure {
  return [
    ...getCollaborationMenuItems(),
    { title: "任务管理", path: "/app/tasks" },
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
      { title: "市场监控", path: "/app/quality-analytics" },
      { title: "舆情监测", path: "/app/risk-cases" },
      { title: "监督抽查", path: "/app/sampling-plans" },
      {
        title: "实验室检测",
        path: "/app/laboratory",
        activeMatchPaths: ["/app/inspection-sessions", "/app/samples"],
      },
    ],
  };
}

function getTaskResultGroup(): MenuGroup {
  return {
    title: "任务与结果",
    icon: "List",
    items: [
      { title: "任务管理", path: "/app/tasks" },
      { title: "检测结果", path: "/app/results" },
    ],
  };
}

function getUserMenu(): MenuStructure {
  return [
    { title: "AI 对话", path: "/app/chat" },
    getQualitySupervisionGroup(),
    getTaskResultGroup(),
    ...getCollaborationMenuItems(),
    { title: "报告导出", path: "/app/export" },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getExpertMenu(): MenuStructure {
  return [
    { title: "AI 对话", path: "/app/chat" },
    getQualitySupervisionGroup(),
    getTaskResultGroup(),
    ...getCollaborationMenuItems(),
    { title: "RAG 空间", path: "/app/rag-spaces" },
    { title: "报告导出", path: "/app/export" },
    { title: "个人设置", path: "/app/profile" },
  ];
}
