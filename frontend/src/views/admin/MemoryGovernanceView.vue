<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { memoryGovernanceApi } from "@/api/memory-governance.api";
import { ROLE_ADMIN } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import type {
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
const events = ref<MemoryEventItem[]>([]);
const graph = ref<MemoryPropagationGraph | null>(null);
const rollbackResult = ref<MemoryRollbackResult | null>(null);
const evaluationResult = ref<MemoryEvaluationResult | null>(null);
const policies = ref<MemoryPolicy[]>([]);
const selectedPolicyKey = ref("");
const policyForm = reactive({
  workspace: "governance",
  policy_type: "rollback",
  status: "active",
  configText: "{}",
});
const searchForm = reactive({
  query: "",
  workspace: "governance",
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
  await Promise.all([fetchEvents(), fetchPolicies()]);
});

async function searchMemory() {
  if (!orgId.value) return;
  loading.value = true;
  try {
    const { data } = await memoryGovernanceApi.search({
      org_id: orgId.value,
      workspace: searchForm.workspace as "governance",
      query: searchForm.query,
      top_k: searchForm.top_k,
    });
    searchResults.value = data.data.items;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "记忆检索失败");
  } finally {
    loading.value = false;
  }
}

async function fetchEvents() {
  loading.value = true;
  try {
    const { data } = await memoryGovernanceApi.listEvents({
      memory_id: eventFilters.memory_id || undefined,
      event_type: eventFilters.event_type || undefined,
      trace_id: eventFilters.trace_id || undefined,
      limit: 100,
    });
    events.value = data.data;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载记忆事件失败");
  } finally {
    loading.value = false;
  }
}

async function buildGraph() {
  if (!orgId.value) return;
  loading.value = true;
  try {
    const { data } = await memoryGovernanceApi.buildPropagationGraph({
      org_id: orgId.value,
      workspace: "governance",
      root_memory_id: graphForm.root_memory_id,
      max_depth: graphForm.max_depth,
    });
    graph.value = data.data;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "构建污染传播图失败");
  } finally {
    loading.value = false;
  }
}

async function executeRollback() {
  if (!orgId.value || !userId.value) return;
  loading.value = true;
  try {
    const traceId = `mem-rb-${Date.now()}`;
    const { data } = await memoryGovernanceApi.executeRollback({
      org_id: orgId.value,
      workspace: "governance",
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
    evaluationForm.rollback_id = data.data.rollback_id;
    ElMessage.success(data.data.approval_id ? "回滚已执行，并已生成审批留痕" : "回滚已执行");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "执行回滚失败");
  } finally {
    loading.value = false;
  }
}

async function evaluateRecovery() {
  if (!orgId.value || !evaluationForm.rollback_id) return;
  loading.value = true;
  try {
    const { data } = await memoryGovernanceApi.evaluateRecovery({
      org_id: orgId.value,
      rollback_id: evaluationForm.rollback_id,
      trace_id: evaluationForm.trace_id || undefined,
      scenario: evaluationForm.scenario || undefined,
    });
    evaluationResult.value = data.data;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "恢复验证失败");
  } finally {
    loading.value = false;
  }
}

async function fetchPolicies() {
  try {
    const { data } = await memoryGovernanceApi.listPolicies({ workspace: "governance" });
    policies.value = data.data;
    if (!selectedPolicyKey.value && policies.value.length) {
      selectedPolicyKey.value = policies.value[0].policy_key;
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载记忆策略失败");
  }
}

function loadPolicy(policy: MemoryPolicy) {
  selectedPolicyKey.value = policy.policy_key;
  policyForm.workspace = policy.workspace;
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
      workspace: policyForm.workspace as "governance",
      policy_type: policyForm.policy_type as "rollback",
      status: policyForm.status,
      config,
    });
    ElMessage.success("策略已更新");
    await fetchPolicies();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "策略保存失败");
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
              <el-select v-model="searchForm.workspace" class="!w-[180px]">
                <el-option label="治理空间" value="governance" />
              </el-select>
              <el-input-number v-model="searchForm.top_k" :min="1" :max="10" />
              <el-button type="primary" :loading="loading" @click="searchMemory">检索</el-button>
            </div>
            <el-table :data="searchResults" size="small" class="list-table" v-loading="loading">
              <el-table-column prop="memory_id" label="Memory ID" min-width="180" />
              <el-table-column prop="memory_type" label="类型" min-width="160" />
              <el-table-column prop="summary" label="摘要" min-width="240" show-overflow-tooltip />
              <el-table-column prop="score" label="召回分" width="100" />
              <el-table-column prop="trust_score" label="信任分" width="100" />
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
                description="策略配置仅 admin 可编辑，platform_operator 保持只读。"
                class="mb-4"
              />
              <el-form label-position="top">
                <el-form-item label="策略 Key">
                  <el-input :model-value="selectedPolicyKey" readonly />
                </el-form-item>
                <el-form-item label="工作区">
                  <el-input v-model="policyForm.workspace" :disabled="!canEditPolicy" />
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
