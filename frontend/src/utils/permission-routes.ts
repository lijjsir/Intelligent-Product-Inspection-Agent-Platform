// Match real API access keys. Unmapped routes retain their existing role rules
// and business data boundaries; a grant does not bypass tenant or owner checks.
const routePermissions: Array<[RegExp, string[]]> = [
  [/^\/app\/risk-reports(?:\/|$)/, ["quality", "quality_material_read_business", "report_read"]],
  [/^\/app\/export(?:\/|$)/, ["report_generate", "report_read"]],
  [/^\/app\/quality-data(?:\/|$)/, ["quality_material_read_business"]],
  [/^\/app\/standard-reviews(?:\/|$)/, ["inspection_standard_library_read"]],
  [/^\/governance\/admin\/roles-orgs(?:\/|$)/, ["role_read"]],
  [/^\/(?:governance\/admin\/users|users)(?:\/|$)/, ["user"]],
  [/^\/(?:ops\/models\/config|governance\/admin\/models)(?:\/|$)/, ["model_config_read"]],
  [/^\/governance\/admin\/gpu(?:\/|$)/, ["gpu_infra"]],
  [/^\/ops\/data\/(?:import|processing)(?:\/|$)/, ["dataset"]],
  [/^\/ops\/(?:data\/eval-sets|training|eval|deployments)(?:\/|$)/, ["algo_workspace"]],
  [/^\/ops\/agents\/intent-routes(?:\/|$)/, ["agent_ops"]],
  [/^\/ops\/agents(?:\/|$)/, ["agent_ops_read"]],
  [/^\/ops\/prompts(?:\/|$)/, ["prompt_admin"]],
  [/^\/ops\/tools(?:\/|$)/, ["tool"]],
  [/^\/(?:app|ops)\/tasks(?:\/|$)/, ["task"]],
  [/^\/app\/results(?:\/|$)/, ["result"]],
  [/^\/app\/stability(?:\/|$)/, ["stability"]],
  [/^\/app\/chat(?:\/|$)/, ["chat"]],
  [/^\/app\/meetings(?:\/|$)/, ["meeting"]],
  [/^\/app\/collab(?:\/|$)/, ["collab"]],
  [/^\/app\/feedbacks(?:\/|$)/, ["feedback"]],
  [/^\/ops\/(?:analytics|dashboard)(?:\/|$)/, ["analytics"]],
  [/^\/ops\/alerts(?:\/|$)/, ["alert"]],
  [/^\/governance\/admin\/alert-rules(?:\/|$)/, ["alert_rule_read"]],
  [/^\/governance\/admin\/inspection-standards(?:\/|$)/, ["inspection_standard_library_read"]],
  [/^\/governance\/admin\/inspection-specs(?:\/|$)/, ["inspection_standard_library_read"]],
  [/^\/(?:governance\/admin|ops)\/ai-review-gates(?:\/|$)/, ["inspection_spec_read"]],
  [/^\/governance\/admin\/infrastructure(?:\/|$)/, ["infrastructure"]],
  [/^\/governance\/admin\/approvals(?:\/|$)/, ["approval"]],
  [/^\/governance\/admin\/meetings(?:\/|$)/, ["meeting_admin"]],
  [/^\/governance\/admin\/logs(?:\/|$)/, ["auth_log", "audit_log"]],
  [/^\/governance\/memory(?:\/|$)/, ["memory_governance"]],
  [/^\/app\/rag-spaces(?:\/|$)/, ["knowledge_read"]],
  [/^\/ops\/billing(?:\/|$)/, ["billing"]],
];

export function permissionsForRoute(path: string): string[] | undefined {
  const pathname = path.split(/[?#]/)[0];
  return routePermissions.find(([pattern]) => pattern.test(pathname))?.[1];
}

export function isStandardManagementRoute(path: string) {
  return /^\/(?:governance\/admin|ops)\/(?:inspection-standards|inspection-specs|ai-review-gates)(?:\/|$)/.test(
    path.split(/[?#]/)[0],
  );
}

export function ordinaryUserTaskRedirect(path: string, taskId?: string): string | undefined {
  if (isStandardManagementRoute(path)) return "/app/tasks";
  if (path === "/app/export")
    return taskId ? `/app/results/${encodeURIComponent(taskId)}` : "/app/tasks";
  return undefined;
}
