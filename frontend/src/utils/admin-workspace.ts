// Administrator navigation describes governance duties, not every callable permission.
export const ADMIN_MENU_GROUPS = [
  {
    title: "组织与权限", icon: "Management",
    items: [
      { title: "用户管理", path: "/governance/admin/users" },
      { title: "权限管理", path: "/governance/admin/roles-orgs" },
      { title: "会议治理", path: "/governance/admin/meetings" },
    ],
  },
  {
    title: "质监基础", icon: "Files",
    items: [
      { title: "企业档案", path: "/governance/admin/enterprises" },
      { title: "产品目录", path: "/governance/admin/quality-products" },
    ],
  },
  {
    title: "标准管理",
    items: [
      { title: "标准文档库", path: "/governance/admin/inspection-standards" },
      { title: "检测要求总览", path: "/governance/admin/inspection-specs" },
    ],
  },
  {
    title: "规则与复核",
    items: [
      { title: "检测执行策略", path: "/governance/admin/ai-review-gates" },
      { title: "风险等级配置", path: "/governance/admin/risk-policies" },
    ],
  },
  {
    title: "知识治理",
    items: [
      { title: "知识准入与发布", path: "/governance/memory" },
    ],
  },
  {
    title: "审计与审批", icon: "Management",
    items: [
      { title: "日志中心", path: "/governance/admin/logs" },
      { title: "高风险操作审批", path: "/governance/admin/approvals" },
    ],
  },
];

const ADMIN_PATHS = [
  ...ADMIN_MENU_GROUPS.flatMap(group => group.items.map(item => item.path)),
  "/app/profile", "/users", "/governance/admin/product-master",
];

export function isAdminWorkspaceRoute(path: string): boolean {
  const pathname = path.split(/[?#]/)[0];
  return ADMIN_PATHS.some(base => pathname === base || pathname.startsWith(`${base}/`));
}

export function adminLandingPaths(): string[] {
  return ADMIN_MENU_GROUPS.flatMap(group => group.items.map(item => item.path));
}
