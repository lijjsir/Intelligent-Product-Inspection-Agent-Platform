<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { extractApiErrorDetail } from "@/api/http";
import type { ApiErrorDetail } from "@/api/http";
import { memoryGovernanceApi } from "@/api/memory-governance.api";
import { ROLE_ADMIN } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import type {
  CandidateMemoryItem,
  MemoryEvaluationResult,
  MemoryEventItem,
  MemoryPolicy,
  MemoryPropagationGraph,
  MemoryRollbackResult,
  MemorySearchItem,
} from "@/types/governance.types";

const auth = useAuthStore();
const activeTab = ref("search");
const loading = ref(false);
const policySaving = ref(false);
const searchResults = ref<MemorySearchItem[]>([]);
const candidates = ref<CandidateMemoryItem[]>([]);
const events = ref<MemoryEventItem[]>([]);
const graph = ref<MemoryPropagationGraph | null>(null);
const searchError = ref<ApiErrorDetail | null>(null);
const candidateError = ref<ApiErrorDetail | null>(null);
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
const candidateFilters = reactive({
  status: "candidate",
  memory_type: "",
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
  await Promise.all([fetchCandidates(), fetchEvents(), fetchPolicies()]);
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

async function fetchCandidates() {
  loading.value = true;
  candidateError.value = null;
  try {
    const { data } = await memoryGovernanceApi.listCandidates({
      status: candidateFilters.status || "candidate",
      memory_type: candidateFilters.memory_type || undefined,
      limit: 100,
    });
    candidates.value = data.data;
  } catch (error: any) {
    showApiError(error, "加载候选记忆失败", candidateError);
  } finally {
    loading.value = false;
  }
}

async function evaluateCandidate(memoryId: string) {
  loading.value = true;
  candidateError.value = null;
  try {
    const { data } = await memoryGovernanceApi.evaluateCandidate(memoryId);
    ElMessage.success(data.data.promoted ? "候选记忆已晋升" : "晋升评估已完成");
    await fetchCandidates();
  } catch (error: any) {
    showApiError(error, "晋升评估失败", candidateError);
  } finally {
    loading.value = false;
  }
}

async function batchEvaluateCandidates() {
  loading.value = true;
  candidateError.value = null;
  try {
    const { data } = await memoryGovernanceApi.evaluateCandidateBatch(100);
    const promoted = data.data.filter((item) => item.promoted).length;
    ElMessage.success(`批量评估完成，晋升 ${promoted} 条`);
    await fetchCandidates();
  } catch (error: any) {
    showApiError(error, "批量评估失败", candidateError);
  } finally {
    loading.value = false;
  }
}

async function approveCandidate(memoryId: string) {
  loading.value = true;
  candidateError.value = null;
  try {
    await memoryGovernanceApi.approveCandidate(memoryId);
    ElMessage.success("候选记忆已确认");
    await fetchCandidates();
  } catch (error: any) {
    showApiError(error, "确认候选失败", candidateError);
  } finally {
    loading.value = false;
  }
}

async function rejectCandidate(memoryId: string) {
  loading.value = true;
  candidateError.value = null;
  try {
    await memoryGovernanceApi.rejectCandidate(memoryId);
    ElMessage.success("候选记忆已拒绝");
    await fetchCandidates();
  } catch (error: any) {
    showApiError(error, "拒绝候选失败", candidateError);
  } finally {
    loading.value = false;
  }
}

async function isolateCandidate(memoryId: string) {
  loading.value = true;
  candidateError.value = null;
  try {
    await memoryGovernanceApi.isolateCandidate(memoryId);
    ElMessage.success("候选记忆已隔离");
    await fetchCandidates();
  } catch (error: any) {
    showApiError(error, "隔离候选失败", candidateError);
  } finally {
    loading.value = false;
  }
}

async function contestCandidate(memoryId: string) {
  loading.value = true;
  candidateError.value = null;
  try {
    await memoryGovernanceApi.contestCandidate(memoryId);
    ElMessage.success("候选记忆已标记争议");
    await fetchCandidates();
  } catch (error: any) {
    showApiError(error, "标记争议失败", candidateError);
  } finally {
    loading.value = false;
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
      <p class="mt-2 text-sm text-zinc-500">完成记忆检索、事件查看、污染传播、回滚执行和恢复验证；策略配置仅管理员可编辑。</p>
    </div>

    <div class="card-surface p-4">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="记忆检索" name="search">
          <div class="flex flex-col gap-4">
            <div class="flex flex-wrap gap-3">
              <el-input v-model="searchForm.query" class="!w-[320px]" placeholder="输入关键词检索治理记忆" />
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

        <el-tab-pane label="候选池" name="candidates">
          <div class="flex flex-col gap-4">
            <div class="flex flex-wrap gap-3">
              <el-select v-model="candidateFilters.status" class="!w-[160px]">
                <el-option label="候选" value="candidate" />
                <el-option label="争议" value="contested" />
                <el-option label="隔离" value="isolated" />
                <el-option label="已禁用" value="disabled" />
                <el-option label="已激活" value="active" />
              </el-select>
              <el-input v-model="candidateFilters.memory_type" class="!w-[220px]" placeholder="按 memory_type 筛选" />
              <el-button type="primary" :loading="loading" @click="fetchCandidates">查询</el-button>
              <el-button :loading="loading" @click="batchEvaluateCandidates">批量评估</el-button>
            </div>
            <el-alert v-if="candidateError" type="error" show-icon :closable="false" title="候选池操作失败" :description="formatApiError(candidateError)" />
            <el-table :data="candidates" size="small" class="list-table" v-loading="loading">
              <el-table-column prop="memory_id" label="Memory ID" min-width="170" />
              <el-table-column prop="memory_type" label="类型" min-width="150" />
              <el-table-column prop="status" label="状态" width="100" />
              <el-table-column prop="summary" label="摘要" min-width="260" show-overflow-tooltip />
              <el-table-column prop="support_count" label="支持" width="80" />
              <el-table-column prop="rag_evidence_count" label="RAG" width="80" />
              <el-table-column prop="agent_verifier_count" label="Agent" width="90" />
              <el-table-column prop="conflict_count" label="冲突" width="80" />
              <el-table-column prop="promotion_score" label="晋升分" width="100" />
              <el-table-column label="最近支持" min-width="160">
                <template #default="{ row }">{{ formatDateTime(row.last_supported_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" fixed="right" width="300">
                <template #default="{ row }">
                  <div class="flex flex-wrap gap-2">
                    <el-button size="small" @click="evaluateCandidate(row.memory_id)">评估</el-button>
                    <el-button size="small" type="success" @click="approveCandidate(row.memory_id)">确认</el-button>
                    <el-button size="small" type="warning" @click="contestCandidate(row.memory_id)">争议</el-button>
                    <el-button size="small" @click="isolateCandidate(row.memory_id)">隔离</el-button>
                    <el-button size="small" type="danger" @click="rejectCandidate(row.memory_id)">拒绝</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
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
                    <el-option label="分支" value="branch" />
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
  </div>
</template>
