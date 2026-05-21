import type {
  AgentDefinition,
  AgentLifecycleStatus,
  AgentRuntimeInstance,
  AgentRuntimeOverview,
  AgentTopology,
  TopologyNode,
} from "@/types/agent-ops.types";

export function isDeprecatedLifecycle(status?: AgentLifecycleStatus | null) {
  return status === "deprecated";
}

export function isPlannedLifecycle(status?: AgentLifecycleStatus | null) {
  return status === "planned";
}

export function isRuntimeVisibleAgent(agent: AgentRuntimeInstance) {
  return !isDeprecatedLifecycle(agent.lifecycle_status) && !isPlannedLifecycle(agent.lifecycle_status);
}

export function isDefinitionVisibleAgent(agent: AgentDefinition) {
  return !isDeprecatedLifecycle(agent.lifecycle_status);
}

export function visibleDefinitionAgents(agents: AgentDefinition[]) {
  return agents.filter(isDefinitionVisibleAgent);
}

export function visibleRuntimeAgents(agents: AgentRuntimeInstance[]) {
  return agents.filter(isRuntimeVisibleAgent);
}

export function buildDefinitionCards(agents: AgentDefinition[]) {
  const visible = visibleDefinitionAgents(agents);
  return [
    { key: "core", label: "核心 Agent", value: visible.filter((item) => item.group_key === "core").length, tone: "#0f766e" },
    { key: "planned", label: "规划中 Agent", value: visible.filter((item) => item.lifecycle_status === "planned").length, tone: "#b45309" },
    { key: "routable", label: "参与路由", value: visible.filter((item) => item.route_enabled).length, tone: "#2563eb" },
    { key: "abnormal", label: "异常 Agent", value: visible.filter((item) => item.runtime_status === "degraded").length, tone: "#dc2626" },
  ];
}

export function buildRuntimeCards(overview: AgentRuntimeOverview | null, runtimeAgents: AgentRuntimeInstance[]) {
  const visible = visibleRuntimeAgents(runtimeAgents);
  const pausedRoutes = visible.filter((item) => item.route_enabled === false).length;
  const running = visible.filter((item) => item.runtime_status === "running").length;
  const degraded = visible.filter((item) => item.runtime_status === "degraded").length;
  return [
    { key: "running", label: "运行中", value: running, tone: "#0f766e" },
    { key: "paused", label: "已暂停路由", value: pausedRoutes, tone: "#d97706" },
    { key: "degraded", label: "降级/异常", value: degraded, tone: "#dc2626" },
    { key: "latency", label: "平均延迟", value: `${Math.round(overview?.avg_latency_ms ?? 0)} ms`, tone: "#7c3aed" },
  ];
}

export function groupLabel(value: string) {
  const map: Record<string, string> = { core: "核心", memory: "记忆治理", planned: "规划中", legacy: "历史兼容" };
  return map[value] || value;
}

export function groupTagType(value: string) {
  const map: Record<string, string> = { core: "", memory: "warning", planned: "info", legacy: "info" };
  return map[value] || "info";
}

export function lifecycleLabel(value: string) {
  const map: Record<string, string> = {
    active: "已接入",
    partial: "部分接入",
    planned: "规划中",
    legacy: "历史兼容",
    deprecated: "已废弃",
  };
  return map[value] || value;
}

export function lifecycleTagType(value: string) {
  const map: Record<string, string> = {
    active: "success",
    partial: "warning",
    planned: "info",
    legacy: "info",
    deprecated: "danger",
  };
  return map[value] || "info";
}

export function runtimeStatusTagType(value: string) {
  const map: Record<string, string> = {
    running: "success",
    stopped: "info",
    degraded: "warning",
    maintenance: "danger",
    readonly: "info",
  };
  return map[value] || "info";
}

export function topologyNodeColor(node: Pick<TopologyNode, "kind" | "status" | "lifecycle_status">) {
  if (node.kind === "system" || node.kind === "root") return "#6366f1";
  if (node.lifecycle_status === "planned") return "#d1d5db";
  if (node.lifecycle_status === "deprecated") return "#f97316";
  if (node.status === "running") return "#0f766e";
  if (node.status === "degraded") return "#eab308";
  if (node.status === "stopped" || node.status === "maintenance" || node.status === "readonly") return "#94a3b8";
  if (node.kind === "agent") return "#2563eb";
  return "#475569";
}

export function topologyLegend(mode: "design" | "runtime") {
  if (mode === "runtime") {
    return [
      { label: "系统路由骨架", color: "#6366f1" },
      { label: "运行中 Agent", color: "#0f766e" },
      { label: "已暂停/已停止 Agent", color: "#94a3b8" },
      { label: "降级 Agent", color: "#eab308" },
    ];
  }
  return [
    { label: "系统路由骨架", color: "#6366f1" },
    { label: "已接入 Agent", color: "#0f766e" },
    { label: "已暂停/未运行 Agent", color: "#94a3b8" },
    { label: "规划中 Agent", color: "#d1d5db" },
  ];
}

export function runtimeModeHint() {
  return "平均延迟 = total_latency_ms / execution_count。拓扑会按当前 Agent 注册、路由状态和运行态实时刷新。";
}

export function filterTopologyOptions(agents: AgentDefinition[]) {
  const options = visibleDefinitionAgents(agents)
    .map((item) => ({ label: item.name, value: item.subgraph_key }));
  return [{ label: "全部 Agent", value: "all" }, ...options];
}

export function topologyHasNodes(topology: AgentTopology | null) {
  return Boolean(topology?.nodes?.length);
}
