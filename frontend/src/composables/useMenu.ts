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
}

export interface MenuGroup {
  title: string;
  icon?: string;
  items: MenuItem[];
}

export type MenuStructure = (MenuItem | MenuGroup)[];

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
    {
      title: "应用工作台",
      icon: "Monitor",
      items: [
        { title: "Dashboard", path: "/app/dashboard" },
        { title: "任务管理", path: "/app/tasks" },
        { title: "检测结果", path: "/app/results" },
        { title: "反馈管理", path: "/app/feedbacks" },
      ],
    },
    {
      title: "运维工作台",
      icon: "Setting",
      items: [
        { title: "Agent 管理", path: "/ops/agents" },
        { title: "Prompt 管理", path: "/ops/prompts" },
        { title: "RAG 分析", path: "/ops/rag" },
        { title: "分析看板", path: "/ops/analytics" },
        { title: "计费管理", path: "/ops/billing" },
      ],
    },
    {
      title: "治理工作台",
      icon: "Management",
      items: [
        { title: "用户管理", path: "/governance/admin/users" },
        { title: "角色与菜单", path: "/governance/admin/roles", placeholder: true },
        { title: "租户/组织", path: "/governance/admin/orgs", placeholder: true },
        { title: "模型配置", path: "/governance/admin/models" },
        { title: "存储/基础设施", path: "/governance/admin/infrastructure", placeholder: true },
        { title: "GPU 调度", path: "/governance/admin/gpu" },
        { title: "检测标准", path: "/governance/admin/inspection-specs" },
        { title: "分析中心", path: "/governance/quality/analysis-center" },
        { title: "记忆治理", path: "/governance/memory", placeholder: true },
        { title: "登录日志", path: "/governance/admin/auth-logs", placeholder: true },
        { title: "审计日志", path: "/governance/admin/audit-logs", placeholder: true },
        { title: "高风险审批", path: "/governance/admin/approvals", placeholder: true },
      ],
    },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getAppDeveloperMenu(): MenuStructure {
  return [
    { title: "Agent 管理", path: "/ops/agents" },
    { title: "路由策略", path: "/ops/agents/intent-routes" },
    { title: "Prompt 管理", path: "/ops/prompts" },
    { title: "DSPy 优化", path: "/ops/prompts/dspy", placeholder: true },
    { title: "RAG 分析", path: "/ops/rag" },
    { title: "召回策略", path: "/ops/rag/policies", placeholder: true },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getPlatformOperatorMenu(): MenuStructure {
  return [
    { title: "Agent 管理", path: "/ops/agents" },
    { title: "模板审核", path: "/ops/templates/review", placeholder: true },
    { title: "发布协同", path: "/ops/releases", placeholder: true },
    { title: "模型版本", path: "/ops/models/versions", placeholder: true },
    { title: "调用监控", path: "/ops/models/monitor", placeholder: true },
    { title: "数据质量", path: "/ops/data-quality", placeholder: true },
    { title: "标注任务", path: "/ops/label-tasks", placeholder: true },
    { title: "数据审核", path: "/ops/data-review", placeholder: true },
    { title: "用户行为分析", path: "/ops/analytics/behavior", placeholder: true },
    { title: "业务报表", path: "/ops/analytics/reports", placeholder: true },
    { title: "成本分析", path: "/ops/analytics/cost", placeholder: true },
    { title: "分析中心", path: "/governance/quality/analysis-center" },
    { title: "记忆治理", path: "/governance/memory", placeholder: true },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getAlgorithmEngineerMenu(): MenuStructure {
  return [
    { title: "数据接入", path: "/ops/data/import", placeholder: true },
    { title: "数据处理", path: "/ops/data/processing", placeholder: true },
    { title: "测试集管理", path: "/ops/data/eval-sets", placeholder: true },
    { title: "训练任务", path: "/ops/training/jobs", placeholder: true },
    { title: "微调管理", path: "/ops/training/fine-tune", placeholder: true },
    { title: "离线评测", path: "/ops/eval/offline", placeholder: true },
    { title: "在线验证", path: "/ops/eval/online", placeholder: true },
    { title: "实验追踪", path: "/ops/experiments", placeholder: true },
    { title: "部署记录", path: "/ops/deployments", placeholder: true },
    { title: "模型配置", path: "/governance/admin/models" },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getUserMenu(): MenuStructure {
  return [
    { title: "AI 检测对话", path: "/app/chat" },
    { title: "任务管理", path: "/app/tasks" },
    { title: "检测结果", path: "/app/results" },
    { title: "证据溯源", path: "/app/results/:id", placeholder: true },
    { title: "异常反馈", path: "/app/feedbacks" },
    { title: "报告导出", path: "/app/export", placeholder: true },
    { title: "个人设置", path: "/app/profile" },
  ];
}

function getExpertMenu(): MenuStructure {
  return [
    { title: "AI 检测对话", path: "/app/chat" },
    { title: "RAG 空间", path: "/app/rag-spaces" },
    { title: "任务管理", path: "/app/tasks" },
    { title: "检测结果", path: "/app/results" },
    { title: "证据溯源", path: "/app/results/:id", placeholder: true },
    { title: "异常反馈", path: "/app/feedbacks" },
    { title: "报告导出", path: "/app/export", placeholder: true },
    { title: "个人设置", path: "/app/profile" },
  ];
}
