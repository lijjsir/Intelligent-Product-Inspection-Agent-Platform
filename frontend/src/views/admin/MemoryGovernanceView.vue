<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { extractApiErrorDetail } from "@/api/http";
import type { ApiErrorDetail } from "@/api/http";
import { meetingApi } from "@/api/meeting.api";
import { memoryGovernanceApi } from "@/api/memory-governance.api";
import { ROLE_ADMIN } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import type {
  MemoryEvidenceDetail,
  MemoryEvaluationResult,
  MemoryEventItem,
  MemoryPolicy,
  MemoryPropagationGraph,
  MemoryRollbackResult,
  MemorySearchItem,
  OrganizationGovernanceItem,
  OrganizationGovernanceOverview,
} from "@/types/governance.types";

const auth = useAuthStore();
const activeTab = ref("organization");
const organizationView = ref<"pending" | "active">("pending");
const loading = ref(false);
const policySaving = ref(false);
const searchResults = ref<MemorySearchItem[]>([]);
const organization = ref<OrganizationGovernanceOverview>({
  pending_approval: [],
  promotion_candidates: [],
  active: [],
});
const organizationLoading = ref(false);
const organizationError = ref<ApiErrorDetail | null>(null);
const evidenceDrawerVisible = ref(false);
const evidenceLoading = ref(false);
const evidenceDetail = ref<MemoryEvidenceDetail | null>(null);
const events = ref<MemoryEventItem[]>([]);
const graph = ref<MemoryPropagationGraph | null>(null);
const searchError = ref<ApiErrorDetail | null>(null);
const eventError = ref<ApiErrorDetail | null>(null);
const graphError = ref<ApiErrorDetail | null>(null);
const operationError = ref<ApiErrorDetail | null>(null);
const memoryWarnings = ref<Array<string | Record<string, unknown>>>([]);
const rollbackResult = ref<MemoryRollbackResult | null>(null);
const evaluationResult = ref<MemoryEvaluationResult | null>(null);
const policies = ref<MemoryPolicy[]>([]);
const selectedPolicyKey = ref("");
const policyForm = reactive({
  policy_type: "rollback",
  status: "active",
  configText: "{}",
});
const searchForm = reactive({
  query: "",
  top_k: 5,
});
const eventFilters = reactive({
  memory_id: "",
  event_type: "",
  trace_id: "",
});
const graphForm = reactive({
  root_memory_id: "",
  max_depth: 4,
});
const rollbackForm = reactive({
  root_memory_id: "",
  rollback_action: "degrade",
  target_memory_ids: "",
  reason: "",
  require_human_review: false,
});
const evaluationForm = reactive({
  rollback_id: "",
  trace_id: "",
  scenario: "",
});

const canEditPolicy = computed(() => auth.roles.includes(ROLE_ADMIN) || auth.role === ROLE_ADMIN);
const orgId = computed(() => auth.orgId || "");
const userId = computed(() => auth.userId || "");

onMounted(async () => {
  await Promise.all([fetchOrganizationGovernance(), fetchEvents(), fetchPolicies()]);
});

function showApiError(error: unknown, fallback: string, target?: { value: ApiErrorDetail | null }) {
  const detail = extractApiErrorDetail(error, fallback);
  if (target) target.value = detail;
  ElMessage.error(detail.message);
}

function formatApiError(error: ApiErrorDetail | null): string {
  if (!error) return "";
  const lines = [error.message];
  if (error.code) lines.push(`code: ${error.code}`);
  if (error.trace_id) lines.push(`trace_id: ${error.trace_id}`);
  if (error.suggestion) lines.push(`suggestion: ${error.suggestion}`);
  if (error.detail !== undefined && error.detail !== null) {
    lines.push(`detail: ${typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail)}`);
  }
  return lines.join("\n");
}

async function searchMemory() {
  if (!orgId.value) return;
  loading.value = true;
  searchError.value = null;
  try {
    const { data } = await memoryGovernanceApi.search({
      org_id: orgId.value,
      query: searchForm.query,
      top_k: searchForm.top_k,
    });
    searchResults.value = data.data.items;
  } catch (error: any) {
    searchResults.value = [];
    showApiError(error, "记忆检索失败", searchError);
  } finally {
    loading.value = false;
  }
}

async function fetchOrganizationGovernance() {
  organizationLoading.value = true;
  organizationError.value = null;
  try {
    const { data } = await memoryGovernanceApi.organizationOverview(100);
    organization.value = data.data;
  } catch (error: unknown) {
    organization.value = { pending_approval: [], promotion_candidates: [], active: [] };
    showApiError(error, "加载组织记忆治理失败", organizationError);
  } finally {
    organizationLoading.value = false;
  }
}

async function openEvidence(row: OrganizationGovernanceItem) {
  evidenceDrawerVisible.value = true;
  evidenceLoading.value = true;
  evidenceDetail.value = null;
  try {
    const { data } = await memoryGovernanceApi.evidenceDetail(row.memory_id);
    evidenceDetail.value = data.data;
  } catch (error: unknown) {
    showApiError(error, "加载记忆证据失败", organizationError);
  } finally {
    evidenceLoading.value = false;
  }
}

async function approveOrganizationShare(row: OrganizationGovernanceItem) {
  if (!row.share_request_id) return;
  const confirmed = await confirmGovernanceAction(
    "批准后将新增组织共享绑定，并进入组织检索索引；原范围记忆继续保留。",
    "批准组织共享",
    "批准并生效",
  );
  if (!confirmed) return;
  organizationLoading.value = true;
  organizationError.value = null;
  try {
    await meetingApi.approveMemoryShare(row.share_request_id, "管理员批准进入组织共享范围");
    ElMessage.success("审批已通过，记忆已进入组织范围同步流程");
    await Promise.all([fetchOrganizationGovernance(), fetchEvents()]);
  } catch (error: unknown) {
    showApiError(error, "批准组织共享失败", organizationError);
  } finally {
    organizationLoading.value = false;
  }
}

async function rejectOrganizationShare(row: OrganizationGovernanceItem) {
  if (!row.share_request_id) return;
  let reason = "";
  try {
    const result = await ElMessageBox.prompt(
      "拒绝只终止本次组织共享申请，原会议室、个人、任务或其他主范围记忆不会删除。",
      "拒绝组织共享",
      {
        confirmButtonText: "确认拒绝",
        cancelButtonText: "取消",
        inputType: "textarea",
        inputPlaceholder: "请填写拒绝理由",
        inputValidator: (value) => Boolean(String(value || "").trim()) || "拒绝理由不能为空",
        type: "warning",
      },
    );
    reason = String(result.value || "").trim();
  } catch {
    return;
  }
  organizationLoading.value = true;
  try {
    await meetingApi.rejectMemoryShare(row.share_request_id, reason);
    ElMessage.success("组织共享申请已拒绝，原范围记忆不受影响");
    await fetchOrganizationGovernance();
  } catch (error: unknown) {
    showApiError(error, "拒绝组织共享失败", organizationError);
  } finally {
    organizationLoading.value = false;
  }
}

async function contestOrganizationMemory(memoryId: string) {
  const confirmed = await confirmGovernanceAction(
    "标记争议后会暂停该组织记忆的继续使用，并记录冲突证据，便于后续复核。",
    "标记组织记忆争议",
    "标记争议",
  );
  if (!confirmed) return;
  organizationLoading.value = true;
  organizationError.value = null;
  try {
    await memoryGovernanceApi.contestCandidate(memoryId);
    ElMessage.success("组织记忆已标记争议");
    await fetchOrganizationGovernance();
  } catch (error: unknown) {
    showApiError(error, "标记组织记忆争议失败", organizationError);
  } finally {
    organizationLoading.value = false;
  }
}

async function isolateOrganizationMemory(memoryId: string) {
  const confirmed = await confirmGovernanceAction(
    "隔离会立即将该组织记忆移出组织检索范围，但保留内容及审计记录，便于后续复核。",
    "隔离组织记忆",
    "确认隔离",
  );
  if (!confirmed) return;
  organizationLoading.value = true;
  organizationError.value = null;
  try {
    await memoryGovernanceApi.isolateCandidate(memoryId);
    ElMessage.success("组织记忆已隔离");
    await fetchOrganizationGovernance();
  } catch (error: unknown) {
    showApiError(error, "隔离组织记忆失败", organizationError);
  } finally {
    organizationLoading.value = false;
  }
}

async function revokeOrganizationBinding(row: OrganizationGovernanceItem) {
  let reason = "";
  try {
    const result = await ElMessageBox.prompt(
      "撤销后该记忆不再从组织范围召回，但原主范围仍保留。",
      "撤销组织共享",
      {
        confirmButtonText: "确认撤销",
        cancelButtonText: "取消",
        inputType: "textarea",
        inputPlaceholder: "请填写撤销理由",
        inputValidator: (value) => Boolean(String(value || "").trim()) || "撤销理由不能为空",
        type: "warning",
      },
    );
    reason = String(result.value || "").trim();
  } catch {
    return;
  }
  organizationLoading.value = true;
  try {
    await memoryGovernanceApi.revokeOrganizationBinding(row.memory_id, reason);
    ElMessage.success("组织共享绑定已撤销，原主范围不受影响");
    await fetchOrganizationGovernance();
  } catch (error: unknown) {
    showApiError(error, "撤销组织共享失败", organizationError);
  } finally {
    organizationLoading.value = false;
  }
}

async function fetchEvents() {
  loading.value = true;
  eventError.value = null;
  try {
    const { data } = await memoryGovernanceApi.listEvents({
      memory_id: eventFilters.memory_id || undefined,
      event_type: eventFilters.event_type || undefined,
      trace_id: eventFilters.trace_id || undefined,
      limit: 100,
    });
    events.value = data.data;
  } catch (error: any) {
    showApiError(error, "加载记忆事件失败", eventError);
  } finally {
    loading.value = false;
  }
}

async function buildGraph() {
  if (!orgId.value) return;
  loading.value = true;
  graphError.value = null;
  try {
    const { data } = await memoryGovernanceApi.buildPropagationGraph({
      org_id: orgId.value,
      root_memory_id: graphForm.root_memory_id,
      max_depth: graphForm.max_depth,
    });
    graph.value = data.data;
  } catch (error: any) {
    showApiError(error, "构建污染传播图失败", graphError);
  } finally {
    loading.value = false;
  }
}

async function executeRollback() {
  if (!orgId.value || !userId.value) return;
  loading.value = true;
  operationError.value = null;
  memoryWarnings.value = [];
  try {
    const traceId = `mem-rb-${Date.now()}`;
    const { data } = await memoryGovernanceApi.executeRollback({
      org_id: orgId.value,
      operator_id: userId.value,
      trace_id: traceId,
      root_memory_id: rollbackForm.root_memory_id,
      rollback_action: rollbackForm.rollback_action as "delete" | "degrade" | "isolate" | "patch" | "branch",
      target_memory_ids: rollbackForm.target_memory_ids.split(",").map((item) => item.trim()).filter(Boolean),
      reason: rollbackForm.reason,
      require_human_review: rollbackForm.require_human_review,
      propagation_graph: graph.value ? { node_count: graph.value.nodes.length, root_memory_id: graph.value.root_memory_id } : null,
    });
    rollbackResult.value = data.data;
    memoryWarnings.value = data.warnings || [];
    evaluationForm.rollback_id = data.data.rollback_id;
    ElMessage.success(data.data.approval_id ? "回滚已执行，并已生成审批留痕" : "回滚已执行");
  } catch (error: any) {
    showApiError(error, "执行回滚失败", operationError);
  } finally {
    loading.value = false;
  }
}

async function evaluateRecovery() {
  if (!orgId.value || !evaluationForm.rollback_id) return;
  loading.value = true;
  operationError.value = null;
  try {
    const { data } = await memoryGovernanceApi.evaluateRecovery({
      org_id: orgId.value,
      rollback_id: evaluationForm.rollback_id,
      trace_id: evaluationForm.trace_id || undefined,
      scenario: evaluationForm.scenario || undefined,
    });
    evaluationResult.value = data.data;
  } catch (error: any) {
    showApiError(error, "恢复验证失败", operationError);
  } finally {
    loading.value = false;
  }
}

function formatWarning(warning: string | Record<string, unknown>): string {
  return typeof warning === "string" ? warning : JSON.stringify(warning);
}

async function fetchPolicies() {
  try {
    const { data } = await memoryGovernanceApi.listPolicies();
    policies.value = data.data;
    if (!selectedPolicyKey.value && policies.value.length) {
      selectedPolicyKey.value = policies.value[0].policy_key;
    }
  } catch (error: any) {
    showApiError(error, "加载记忆策略失败");
  }
}

function loadPolicy(policy: MemoryPolicy) {
  selectedPolicyKey.value = policy.policy_key;
  policyForm.policy_type = policy.policy_type;
  policyForm.status = policy.status;
  policyForm.configText = JSON.stringify(policy.config || {}, null, 2);
}

async function savePolicy() {
  if (!canEditPolicy.value || !selectedPolicyKey.value) return;
  policySaving.value = true;
  try {
    const config = JSON.parse(policyForm.configText || "{}");
    await memoryGovernanceApi.upsertPolicy(selectedPolicyKey.value, {
      policy_type: policyForm.policy_type as "rollback",
      status: policyForm.status,
      config,
    });
    ElMessage.success("策略已更新");
    await fetchPolicies();
  } catch (error: any) {
    showApiError(error, "策略保存失败");
  } finally {
    policySaving.value = false;
  }
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function sourceKindLabel(value?: string | null) {
  return {
    meeting: "会议室",
    task: "正式任务",
    inspection_task: "质检任务",
    rag: "RAG",
    agent: "Agent",
    chat: "AI 对话",
    human_review: "人工录入",
    organization_governance: "组织治理",
  }[String(value || "")] || value || "数据质量异常：来源缺失";
}

function scopeLabel(type?: string | null, id?: string | null) {
  const label = {
    org_space: "组织空间",
    meeting_room: "会议室",
    user: "个人",
    task: "任务",
    rag_space: "RAG 空间",
    agent: "Agent",
    collab_thread: "协作线程",
  }[String(type || "")] || type || "数据质量异常：主范围缺失";
  return id && !["current", "org", "organization"].includes(id) ? `${label} · ${id}` : label;
}

function reviewLabel(status: string) {
  return {
    candidate: "待审核",
    approved: "已批准",
    disputed: "有争议",
    rejected: "已拒绝",
    isolated: "已隔离",
    superseded: "已替代",
  }[status] || status;
}

function reviewType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "approved") return "success";
  if (status === "candidate" || status === "disputed") return "warning";
  if (status === "rejected" || status === "isolated") return "danger";
  return "info";
}

function syncLabel(status: string) {
  return { pending: "等待", processing: "同步中", success: "成功", failed: "失败" }[status] || status;
}

function syncType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "processing") return "warning";
  return "info";
}

function evidenceRoleLabel(role: string) {
  return {
    origin: "原始来源",
    support: "独立支持",
    rag: "RAG 佐证",
    agent_verification: "Agent 复核",
    human_confirmation: "人工确认",
    opposition: "反对证据",
    conflict: "冲突证据",
  }[role] || role;
}

async function confirmGovernanceAction(
  message: string,
  title: string,
  confirmButtonText: string,
  type: "warning" | "error" = "warning",
) {
  try {
    await ElMessageBox.confirm(message, title, {
      confirmButtonText,
      cancelButtonText: "取消",
      type,
      distinguishCancelAndClose: true,
    });
    return true;
  } catch {
    return false;
  }
}

function graphStats() {
  if (!graph.value) return [];
  return [
    { label: "节点总数", value: graph.value.nodes.length },
    { label: "直接污染", value: graph.value.direct_contaminated.length },
    { label: "间接污染", value: graph.value.indirect_contaminated.length },
    { label: "疑似边界", value: graph.value.suspected.length },
  ];
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">记忆治理</h2>
      <p class="mt-2 text-sm text-zinc-500">完成组织共享审批、组织记忆维护、组织记忆检索、事件查看、污染传播、回滚与恢复验证；策略配置仅管理员可编辑。</p>
    </div>

    <div class="card-surface p-4">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="组织记忆检索" name="search">
          <div class="flex flex-col gap-4">
              <div class="flex flex-wrap gap-3">
              <el-input v-model="searchForm.query" class="!w-[320px]" placeholder="输入关键词检索组织记忆" />
              <el-input-number v-model="searchForm.top_k" :min="1" :max="10" />
              <el-button type="primary" :loading="loading" @click="searchMemory">检索</el-button>
            </div>
            <el-alert v-if="searchError" type="error" show-icon :closable="false" title="记忆检索失败" :description="formatApiError(searchError)" />
            <el-table :data="searchResults" size="small" class="list-table" v-loading="loading">
              <el-table-column prop="memory_id" label="Memory ID" min-width="180" />
              <el-table-column prop="memory_type" label="类型" min-width="160" />
              <el-table-column prop="summary" label="摘要" min-width="240" show-overflow-tooltip />
              <el-table-column prop="score" label="召回分" width="100" />
              <el-table-column prop="trust_score" label="信任分" width="100" />
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="组织治理" name="organization">
          <div class="organization-governance" v-loading="organizationLoading">
            <div class="organization-toolbar">
              <div>
                <h3>组织记忆</h3>
                <p>处理组织共享申请，维护已经生效的组织范围绑定。</p>
              </div>
              <el-button :loading="organizationLoading" @click="fetchOrganizationGovernance">刷新</el-button>
            </div>
            <el-alert
              v-if="organizationError"
              type="error"
              show-icon
              :closable="false"
              title="组织记忆治理加载失败"
              :description="formatApiError(organizationError)"
            />

            <div class="organization-switcher" role="tablist" aria-label="组织记忆视图">
              <button
                type="button"
                role="tab"
                :aria-selected="organizationView === 'pending'"
                :class="['organization-switcher__item', { active: organizationView === 'pending' }]"
                @click="organizationView = 'pending'"
              >
                <span>待组织审批</span><strong>{{ organization.pending_approval.length }}</strong>
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="organizationView === 'active'"
                :class="['organization-switcher__item', { active: organizationView === 'active' }]"
                @click="organizationView = 'active'"
              >
                <span>已生效组织记忆</span><strong>{{ organization.active.length }}</strong>
              </button>
            </div>

            <section v-if="organizationView === 'pending'" class="governance-table" aria-labelledby="pending-approval-heading">
              <div class="governance-table__head">
                <div><h3 id="pending-approval-heading">待组织审批</h3><p>局部范围发起的组织共享申请，批准后才会创建组织绑定。</p></div>
              </div>
              <el-table :data="organization.pending_approval" size="small" class="list-table" empty-text="当前没有待组织审批的记忆">
                <el-table-column prop="summary" label="记忆" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }"><strong>{{ row.summary }}</strong><small class="table-subtext">{{ row.memory_id }} · {{ row.memory_type }}</small></template>
                </el-table-column>
                <el-table-column label="来源与主范围" min-width="230">
                  <template #default="{ row }"><span :class="{ 'data-quality-error': !row.primary_origin }">{{ sourceKindLabel(row.primary_origin?.origin_kind) }}</span><small class="table-subtext">{{ scopeLabel(row.home_scope?.scope_type, row.home_scope?.scope_id) }}</small></template>
                </el-table-column>
                <el-table-column label="目标与转换" min-width="290">
                  <template #default="{ row }">
                    <span>{{ scopeLabel(row.target_scope?.scope_type, row.target_scope?.scope_id) }}</span>
                    <small class="table-subtext">映射 {{ row.mapping_version || "旧记录" }} · {{ row.interpolation_strategy || "-" }}</small>
                    <small v-if="row.unmapped_fields?.length" class="table-subtext data-quality-error">待处理字段 {{ row.unmapped_fields.length }}</small>
                    <small v-else class="table-subtext">转换原因：{{ String(row.mapping_plan?.transform_reason || row.share_reason || "-") }}</small>
                  </template>
                </el-table-column>
                <el-table-column label="证据" width="250"><template #default="{ row }"><div class="evidence-pills"><span>原始 {{ row.evidence.origin }}</span><span>独立 {{ row.evidence.independent_support }}</span><span>RAG {{ row.evidence.rag }}</span><span>Agent {{ row.evidence.agent_verification }}</span><span :class="{ danger: row.evidence.conflict || row.evidence.opposition }">反对/冲突 {{ row.evidence.opposition + row.evidence.conflict }}</span></div></template></el-table-column>
                <el-table-column prop="share_reason" label="申请理由" min-width="200" show-overflow-tooltip />
                <el-table-column label="申请时间" width="170"><template #default="{ row }">{{ formatDateTime(row.requested_at) }}</template></el-table-column>
                <el-table-column label="操作" fixed="right" width="260"><template #default="{ row }"><div class="approval-actions"><el-button @click="openEvidence(row)">查看证据</el-button><el-button type="success" :disabled="Boolean(row.unmapped_fields?.length)" @click="approveOrganizationShare(row)">批准并生效</el-button><el-button type="danger" plain @click="rejectOrganizationShare(row)">拒绝</el-button></div></template></el-table-column>
              </el-table>
            </section>

            <section v-else class="governance-table" aria-labelledby="active-memory-heading">
              <div class="governance-table__head">
                <div><h3 id="active-memory-heading">已生效组织记忆</h3><p>已具有有效组织范围绑定；撤销绑定不会删除原主范围记忆。</p></div>
              </div>
              <el-table :data="organization.active" size="small" class="list-table" empty-text="当前没有已生效组织记忆">
                <el-table-column prop="summary" label="记忆" min-width="280" show-overflow-tooltip><template #default="{ row }"><strong>{{ row.summary }}</strong><small class="table-subtext">{{ row.memory_id }} · {{ row.memory_type }}</small></template></el-table-column>
                <el-table-column label="来源与主范围" min-width="230"><template #default="{ row }"><span>{{ sourceKindLabel(row.primary_origin?.origin_kind) }}</span><small class="table-subtext">{{ scopeLabel(row.home_scope?.scope_type, row.home_scope?.scope_id) }}</small></template></el-table-column>
                <el-table-column label="审核状态" width="120"><template #default="{ row }"><el-tag :type="reviewType(row.review_status)">{{ reviewLabel(row.review_status) }}</el-tag></template></el-table-column>
                <el-table-column label="证据" width="250"><template #default="{ row }"><div class="evidence-pills"><span>原始 {{ row.evidence.origin }}</span><span>独立 {{ row.evidence.independent_support }}</span><span>RAG {{ row.evidence.rag }}</span><span>Agent {{ row.evidence.agent_verification }}</span><span>人工 {{ row.evidence.human_confirmation }}</span></div></template></el-table-column>
                <el-table-column label="同步状态" width="150"><template #default="{ row }"><el-tag :type="syncType(row.sync.vector_status)">向量 {{ syncLabel(row.sync.vector_status) }}</el-tag><el-tag class="ml-1" :type="syncType(row.sync.graph_status)">图 {{ syncLabel(row.sync.graph_status) }}</el-tag></template></el-table-column>
                <el-table-column label="操作" fixed="right" width="360"><template #default="{ row }"><div class="memory-actions"><el-button @click="openEvidence(row)">证据详情</el-button><el-button class="memory-action--contest" @click="contestOrganizationMemory(row.memory_id)">标记争议</el-button><el-button class="memory-action--isolate" @click="isolateOrganizationMemory(row.memory_id)">隔离</el-button><el-button type="warning" plain @click="revokeOrganizationBinding(row)">撤销组织绑定</el-button></div></template></el-table-column>
              </el-table>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane label="事件流" name="events">
          <div class="flex flex-col gap-4">
            <div class="flex flex-wrap gap-3">
              <el-input v-model="eventFilters.memory_id" class="!w-[220px]" placeholder="按 memory_id 筛选" />
              <el-input v-model="eventFilters.event_type" class="!w-[220px]" placeholder="按 event_type 筛选" />
              <el-input v-model="eventFilters.trace_id" class="!w-[220px]" placeholder="按 trace_id 筛选" />
              <el-button type="primary" :loading="loading" @click="fetchEvents">查询</el-button>
            </div>
            <el-alert v-if="eventError" type="error" show-icon :closable="false" title="事件加载失败" :description="formatApiError(eventError)" />
            <el-table :data="events" size="small" class="list-table" v-loading="loading">
              <el-table-column prop="event_id" label="事件 ID" min-width="180" />
              <el-table-column prop="event_type" label="事件类型" min-width="180" />
              <el-table-column prop="source_kind" label="来源" width="140" />
              <el-table-column prop="trace_id" label="Trace ID" min-width="180" />
              <el-table-column label="时间" min-width="180">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="污染传播" name="graph">
          <div class="flex flex-col gap-4">
            <div class="flex flex-wrap gap-3">
              <el-input v-model="graphForm.root_memory_id" class="!w-[320px]" placeholder="输入 root_memory_id" />
              <el-input-number v-model="graphForm.max_depth" :min="1" :max="10" />
              <el-button type="primary" :loading="loading" @click="buildGraph">构建传播图</el-button>
            </div>
            <el-alert v-if="graphError" type="error" show-icon :closable="false" title="传播图构建失败" :description="formatApiError(graphError)" />
            <section class="grid gap-4 md:grid-cols-4" v-if="graph">
              <el-card v-for="item in graphStats()" :key="item.label" shadow="never">
                <div class="text-sm text-zinc-500">{{ item.label }}</div>
                <div class="mt-2 text-2xl font-semibold text-zinc-900">{{ item.value }}</div>
              </el-card>
            </section>
            <el-table :data="graph?.nodes || []" size="small" class="list-table" v-loading="loading">
              <el-table-column prop="memory_id" label="Memory ID" min-width="180" />
              <el-table-column prop="classification" label="分类" min-width="160" />
              <el-table-column prop="depth" label="深度" width="80" />
              <el-table-column prop="edge_type" label="边类型" min-width="160" />
              <el-table-column label="影响来源" min-width="220">
                <template #default="{ row }">{{ row.affected_by.join(", ") || "-" }}</template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="回滚与验证" name="rollback">
          <el-alert
            v-if="operationError"
            class="mb-4"
            type="error"
            show-icon
            :closable="false"
            title="内存治理操作失败"
            :description="formatApiError(operationError)"
          />
          <el-alert
            v-if="memoryWarnings.length"
            class="mb-4"
            type="warning"
            show-icon
            :closable="false"
            title="内存同步警告"
          >
            <ul class="m-0 pl-4">
              <li v-for="(warning, index) in memoryWarnings" :key="index">{{ formatWarning(warning) }}</li>
            </ul>
          </el-alert>
          <div class="grid gap-4 xl:grid-cols-2">
            <el-card shadow="never">
              <template #header>执行回滚</template>
              <el-form label-position="top">
                <el-form-item label="根记忆 ID">
                  <el-input v-model="rollbackForm.root_memory_id" />
                </el-form-item>
                <el-form-item label="回滚动作">
                  <el-select v-model="rollbackForm.rollback_action">
                    <el-option label="降级" value="degrade" />
                    <el-option label="隔离" value="isolate" />
                    <el-option label="删除" value="delete" />
                    <el-option label="补丁" value="patch" />
                  </el-select>
                </el-form-item>
                <el-form-item label="目标记忆 ID">
                  <el-input v-model="rollbackForm.target_memory_ids" type="textarea" :rows="4" placeholder="多个 ID 用逗号分隔" />
                </el-form-item>
                <el-form-item label="原因">
                  <el-input v-model="rollbackForm.reason" type="textarea" :rows="3" />
                </el-form-item>
                <el-form-item>
                  <el-switch v-model="rollbackForm.require_human_review" active-text="要求人工复核" />
                </el-form-item>
                <el-button type="danger" :loading="loading" @click="executeRollback">执行回滚</el-button>
              </el-form>
              <el-alert
                v-if="rollbackResult?.approval_id"
                class="mt-4"
                type="warning"
                show-icon
                title="本次回滚已生成高风险审批留痕"
                :description="`审批单 ID: ${rollbackResult.approval_id}`"
              />
            </el-card>

            <el-card shadow="never">
              <template #header>恢复验证</template>
              <el-form label-position="top">
                <el-form-item label="回滚 ID">
                  <el-input v-model="evaluationForm.rollback_id" />
                </el-form-item>
                <el-form-item label="Trace ID">
                  <el-input v-model="evaluationForm.trace_id" />
                </el-form-item>
                <el-form-item label="场景说明">
                  <el-input v-model="evaluationForm.scenario" />
                </el-form-item>
                <el-button type="primary" :loading="loading" @click="evaluateRecovery">执行验证</el-button>
              </el-form>
            </el-card>
          </div>

          <div class="grid gap-4 xl:grid-cols-2 mt-4">
            <el-card shadow="never">
              <template #header>回滚结果</template>
              <el-descriptions v-if="rollbackResult" :column="1" border>
                <el-descriptions-item label="回滚 ID">{{ rollbackResult.rollback_id }}</el-descriptions-item>
                <el-descriptions-item label="动作">{{ rollbackResult.action }}</el-descriptions-item>
                <el-descriptions-item label="影响数量">{{ rollbackResult.affected_count }}</el-descriptions-item>
                <el-descriptions-item label="复核状态">{{ rollbackResult.review_status }}</el-descriptions-item>
                <el-descriptions-item label="审批单 ID">{{ rollbackResult.approval_id || "-" }}</el-descriptions-item>
              </el-descriptions>
              <el-empty v-else description="尚未执行回滚" />
            </el-card>

            <el-card shadow="never">
              <template #header>验证结果</template>
              <el-descriptions v-if="evaluationResult" :column="1" border>
                <el-descriptions-item label="验证 ID">{{ evaluationResult.evaluation_id }}</el-descriptions-item>
                <el-descriptions-item label="回滚 ID">{{ evaluationResult.rollback_id }}</el-descriptions-item>
                <el-descriptions-item label="结论">{{ evaluationResult.conclusion || "-" }}</el-descriptions-item>
              </el-descriptions>
              <el-empty v-else description="尚未执行恢复验证" />
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="策略配置" name="policies">
          <div class="grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
            <el-card shadow="never">
              <template #header>策略列表</template>
              <el-table :data="policies" size="small" class="list-table" @row-click="loadPolicy">
                <el-table-column prop="policy_key" label="策略键" min-width="160" />
                <el-table-column prop="policy_type" label="类型" min-width="140" />
                <el-table-column prop="status" label="状态" width="100" />
                <el-table-column prop="version" label="版本" width="80" />
              </el-table>
            </el-card>
            <el-card shadow="never">
              <template #header>策略编辑</template>
              <el-alert
                v-if="!canEditPolicy"
                type="info"
                show-icon
                title="当前账号仅可只读查看策略"
                description="策略配置仅 admin 可编辑，请通过管理员流程调整策略。"
                class="mb-4"
              />
              <el-form label-position="top">
                <el-form-item label="策略 Key">
                  <el-input :model-value="selectedPolicyKey" readonly />
                </el-form-item>
                <el-form-item label="策略类型">
                  <el-input v-model="policyForm.policy_type" :disabled="!canEditPolicy" />
                </el-form-item>
                <el-form-item label="状态">
                  <el-input v-model="policyForm.status" :disabled="!canEditPolicy" />
                </el-form-item>
                <el-form-item label="配置 JSON">
                  <el-input v-model="policyForm.configText" type="textarea" :rows="14" :readonly="!canEditPolicy" />
                </el-form-item>
                <el-button v-if="canEditPolicy" type="primary" :loading="policySaving" @click="savePolicy">保存策略</el-button>
              </el-form>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-drawer v-model="evidenceDrawerVisible" title="记忆证据与范围" size="min(760px, 94vw)">
      <div v-loading="evidenceLoading" class="evidence-drawer">
        <template v-if="evidenceDetail">
          <section>
            <h3>原始来源</h3>
            <div v-if="evidenceDetail.origins.length" class="origin-list">
              <article v-for="origin in evidenceDetail.origins" :key="origin.id">
                <strong>{{ sourceKindLabel(origin.origin_kind) }} · {{ origin.source_type }}</strong>
                <p>{{ origin.source_id }}</p>
                <small>{{ formatDateTime(origin.occurred_at) }} · Trace {{ origin.trace_id || "-" }}</small>
                <pre v-if="origin.source_span">{{ JSON.stringify(origin.source_span, null, 2) }}</pre>
              </article>
            </div>
            <el-alert v-else type="error" show-icon :closable="false" title="缺少原始来源证据" description="该记忆必须进入迁移复核，不能提交组织审批。" />
          </section>

          <section>
            <h3>分项证据</h3>
            <el-table :data="evidenceDetail.evidence" size="small" empty-text="暂无证据记录">
              <el-table-column label="角色" width="120"><template #default="{ row }">{{ evidenceRoleLabel(row.evidence_role) }}</template></el-table-column>
              <el-table-column label="来源" min-width="170"><template #default="{ row }">{{ sourceKindLabel(row.source_kind) }} · {{ row.source_id }}</template></el-table-column>
              <el-table-column prop="confidence" label="置信度" width="90" />
              <el-table-column label="时间" width="170"><template #default="{ row }">{{ formatDateTime(row.occurred_at) }}</template></el-table-column>
            </el-table>
          </section>

          <section>
            <h3>访问范围绑定</h3>
            <el-table :data="evidenceDetail.scopes" size="small" empty-text="暂无范围绑定">
              <el-table-column label="范围" min-width="220"><template #default="{ row }">{{ scopeLabel(row.scope_type, row.scope_id) }}</template></el-table-column>
              <el-table-column prop="binding_kind" label="类型" width="90" />
              <el-table-column prop="binding_status" label="状态" width="100" />
              <el-table-column label="批准时间" width="170"><template #default="{ row }">{{ formatDateTime(row.approved_at) }}</template></el-table-column>
            </el-table>
          </section>

          <section>
            <h3>业务适用条件</h3>
            <pre class="applicability-json">{{ JSON.stringify(evidenceDetail.applicability || {}, null, 2) }}</pre>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.organization-governance {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.organization-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 2px 0 14px;
  border-bottom: 1px solid #e4e4e7;
}

.organization-toolbar h3,
.organization-toolbar p {
  margin: 0;
}

.organization-toolbar h3 {
  color: #18181b;
  font-size: 16px;
  font-weight: 700;
}

.organization-toolbar p {
  margin-top: 5px;
  color: #71717a;
  font-size: 13px;
  line-height: 1.5;
}

.organization-switcher {
  display: inline-flex;
  align-self: flex-start;
  gap: 4px;
  padding: 4px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #f4f4f5;
}

.organization-switcher__item {
  display: inline-flex;
  min-width: 172px;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  border: 0;
  border-radius: 6px;
  color: #71717a;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  transition: color 160ms ease, background-color 160ms ease, box-shadow 160ms ease;
}

.organization-switcher__item strong {
  display: inline-flex;
  min-width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #52525b;
  background: #e4e4e7;
  font-size: 11px;
}

.organization-switcher__item:hover {
  color: #27272a;
}

.organization-switcher__item.active {
  color: #18181b;
  background: #fff;
  box-shadow: 0 1px 3px rgb(24 24 27 / 10%);
}

.organization-switcher__item.active strong {
  color: #fff;
  background: #18181b;
}

.governance-table {
  overflow: hidden;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fff;
}

.governance-table__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 14px;
  border-bottom: 1px solid #e4e4e7;
  background: #fafafa;
}

.governance-table__head h3 {
  margin: 0;
  color: #18181b;
  font-size: 14px;
  font-weight: 700;
}

.governance-table__head p {
  margin: 4px 0 0;
  color: #71717a;
  font-size: 12px;
  line-height: 1.5;
}

.approval-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.approval-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.table-subtext {
  display: block;
  max-width: 220px;
  overflow: hidden;
  color: #71717a;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.evidence-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.evidence-pills span {
  padding: 2px 6px;
  border-radius: 999px;
  color: #3f3f46;
  background: #f4f4f5;
  font-size: 11px;
  line-height: 1.5;
}

.evidence-pills span.danger {
  color: #991b1b;
  background: #fef2f2;
}

.data-quality-error {
  color: #b91c1c;
  font-weight: 650;
}

.memory-actions,
.memory-action-group {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
}

.memory-actions {
  flex-wrap: wrap;
  gap: 6px;
}

.memory-action-group {
  gap: 6px;
}

.memory-actions :deep(.el-button) {
  min-height: 34px;
  margin-left: 0;
  font-weight: 600;
  transition: color 180ms ease, background-color 180ms ease, border-color 180ms ease;
}

.memory-action--contest {
  color: #92400e;
  border-color: #fbbf24;
  background: #fffbeb;
}

.memory-action--contest:not(.is-disabled):hover,
.memory-action--contest:not(.is-disabled):focus-visible {
  color: #fff;
  border-color: #b45309;
  background: #b45309;
}

.memory-action--isolate {
  color: #6d28d9;
  border-color: #c4b5fd;
  background: #f5f3ff;
}

.memory-action--isolate:not(.is-disabled):hover,
.memory-action--isolate:not(.is-disabled):focus-visible {
  color: #fff;
  border-color: #6d28d9;
  background: #6d28d9;
}

@media (prefers-reduced-motion: reduce) {
  .memory-actions :deep(.el-button) {
    transition: none;
  }
}

.evidence-drawer {
  display: flex;
  min-height: 240px;
  flex-direction: column;
  gap: 24px;
}

.evidence-drawer section h3 {
  margin: 0 0 10px;
  color: #18181b;
  font-size: 15px;
  font-weight: 700;
}

.origin-list {
  display: grid;
  gap: 10px;
}

.origin-list article {
  padding: 12px 14px;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fafafa;
}

.origin-list p,
.origin-list small {
  display: block;
  margin: 5px 0 0;
  color: #52525b;
  overflow-wrap: anywhere;
}

.origin-list pre,
.applicability-json {
  overflow: auto;
  margin: 10px 0 0;
  padding: 12px;
  border-radius: 8px;
  color: #27272a;
  background: #f4f4f5;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

@media (max-width: 760px) {
  .organization-toolbar {
    flex-direction: column;
  }

  .organization-toolbar :deep(.el-button) {
    width: 100%;
    min-height: 44px;
  }

  .organization-switcher {
    width: 100%;
  }

  .organization-switcher__item {
    min-width: 0;
    flex: 1;
  }
}

</style>
