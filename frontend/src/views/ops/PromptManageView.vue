<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  Aim,
  Connection,
  MagicStick,
  RefreshRight,
  Select,
  Warning,
} from "@element-plus/icons-vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import type {
  PromptOptimizationConfigPayload,
  PromptOptimizationRun,
  PromptOptimizationTarget,
} from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const loading = computed(() => store.loading);
const selectedTargetKey = ref("");
const pollingTimer = ref<number | null>(null);
const saving = ref(false);
const compiling = ref(false);
const rollingBack = ref(false);

const filters = reactive({
  keyword: "",
  subgraph_key: "all",
  status: "all",
  dspy_state: "all",
});

const configForm = reactive<PromptOptimizationConfigPayload>({
  module_name: "",
  compiler_version: "",
  optimizer_strategy: "bootstrap-fewshot",
  metric_names: [],
  config_payload: {},
  is_enabled: true,
});

const metricDraft = ref("");
const payloadDraft = ref('{\n  "temperature": 0.1,\n  "max_examples": 6\n}');

const overview = computed(() => store.promptOptimization?.overview);
const allTargets = computed(() => store.promptOptimization?.items ?? []);

const filteredTargets = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase();
  return allTargets.value.filter((item) => {
    if (filters.subgraph_key !== "all" && item.subgraph_key !== filters.subgraph_key) return false;
    if (filters.status !== "all" && item.current_status !== filters.status) return false;
    if (filters.dspy_state === "enabled" && !item.config.is_enabled) return false;
    if (filters.dspy_state === "disabled" && item.config.is_enabled) return false;
    if (!keyword) return true;
    return [item.node_label, item.target_key, item.module_name, item.optimization_goal]
      .some((value) => value.toLowerCase().includes(keyword));
  });
});

const groupedTargets = computed(() => {
  const groups = new Map<string, PromptOptimizationTarget[]>();
  for (const item of filteredTargets.value) {
    const current = groups.get(item.subgraph_key) ?? [];
    current.push(item);
    groups.set(item.subgraph_key, current);
  }
  return Array.from(groups.entries()).map(([key, items]) => ({
    key,
    label: key === "legacy_quality" ? "Legacy Quality 子图" : "LLM-native Quality 子图",
    items,
  }));
});

const selectedTarget = computed<PromptOptimizationTarget | null>(() => {
  if (store.promptOptimizationCurrent?.target_key === selectedTargetKey.value) {
    return store.promptOptimizationCurrent;
  }
  return filteredTargets.value.find((item) => item.target_key === selectedTargetKey.value) ?? null;
});

const selectedRuns = computed<PromptOptimizationRun[]>(() => {
  if (store.promptOptimizationRuns.length) {
    return store.promptOptimizationRuns;
  }
  return selectedTarget.value?.recent_runs ?? [];
});

const graphNodeMap = computed(() => {
  const map = new Map<string, string>();
  selectedTarget.value?.graph_context.nodes.forEach((node) => map.set(node.id, node.label));
  return map;
});

onMounted(async () => {
  await loadWorkbench();
});

onBeforeUnmount(() => {
  if (pollingTimer.value) {
    window.clearInterval(pollingTimer.value);
  }
});

watch(selectedTarget, (value) => {
  if (!value) return;
  configForm.module_name = value.config.module_name;
  configForm.compiler_version = value.config.compiler_version ?? "dspy-2.0";
  configForm.optimizer_strategy = value.config.optimizer_strategy || "bootstrap-fewshot";
  configForm.metric_names = [...value.config.metric_names];
  configForm.config_payload = { ...value.config.config_payload };
  configForm.is_enabled = value.config.is_enabled;
  metricDraft.value = value.config.metric_names.join(", ");
  payloadDraft.value = JSON.stringify(value.config.config_payload ?? {}, null, 2);
});

function statusTone(status: string) {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "warning";
  if (status === "pending") return "info";
  return "info";
}

function subgraphAccent(subgraphKey: string) {
  return subgraphKey === "legacy_quality" ? "#0f766e" : "#b45309";
}

function metricLabel(metric: string) {
  const labels: Record<string, string> = {
    faithfulness: "忠实度",
    traceability: "可追溯性",
    physical_hallucination: "物理幻觉",
    pass_rate: "通过率",
  };
  return labels[metric] ?? metric;
}

function formatMetric(value?: number | null) {
  if (value == null) return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  return new Date(value).toLocaleString();
}

function selectTarget(item: PromptOptimizationTarget) {
  if (
    selectedTargetKey.value === item.target_key &&
    store.promptOptimizationCurrent?.target_key === item.target_key
  ) {
    return;
  }
  selectedTargetKey.value = item.target_key;
  void refreshSelectedTarget(item.target_key);
}

async function loadWorkbench() {
  const response = await store.fetchPromptOptimizationTargets();
  const nextTarget =
    response.items.find((item) => item.target_key === selectedTargetKey.value) ?? response.items[0];
  if (nextTarget) {
    selectedTargetKey.value = nextTarget.target_key;
    await refreshSelectedTarget(nextTarget.target_key);
  }
}

async function refreshSelectedTarget(targetKey = selectedTargetKey.value) {
  if (!targetKey) return;
  await Promise.all([
    store.fetchPromptOptimizationTarget(targetKey),
    store.fetchPromptOptimizationRuns(targetKey),
  ]);
}

async function refreshAll() {
  const response = await store.fetchPromptOptimizationTargets({
    subgraph_key: filters.subgraph_key === "all" ? undefined : filters.subgraph_key,
    status: filters.status === "all" ? undefined : filters.status,
    is_enabled: filters.dspy_state === "all" ? undefined : filters.dspy_state === "enabled",
  });
  const candidate =
    response.items.find((item) => item.target_key === selectedTargetKey.value) ?? response.items[0];
  if (!candidate) {
    selectedTargetKey.value = "";
    return;
  }
  selectedTargetKey.value = candidate.target_key;
  await refreshSelectedTarget(candidate.target_key);
}

async function saveConfig() {
  if (!selectedTarget.value) return;
  saving.value = true;
  try {
    configForm.metric_names = metricDraft.value.split(",").map((item) => item.trim()).filter(Boolean);
    configForm.config_payload = JSON.parse(payloadDraft.value || "{}");
    await store.updatePromptOptimizationConfig(selectedTarget.value.target_key, {
      module_name: configForm.module_name.trim(),
      compiler_version: configForm.compiler_version?.trim() || null,
      optimizer_strategy: configForm.optimizer_strategy.trim(),
      metric_names: configForm.metric_names,
      config_payload: configForm.config_payload,
      is_enabled: configForm.is_enabled,
    });
    ElMessage.success("DSPy 配置已保存");
    await refreshAll();
  } catch {
    ElMessage.error("保存失败，请检查配置项和 JSON 格式");
  } finally {
    saving.value = false;
  }
}

async function compileTarget() {
  if (!selectedTarget.value) return;
  compiling.value = true;
  try {
    await store.compilePromptOptimizationTarget(selectedTarget.value.target_key);
    ElMessage.success("编译任务已提交");
    await pollTargetState(selectedTarget.value.target_key);
  } catch {
    ElMessage.error("编译任务提交失败");
  } finally {
    compiling.value = false;
  }
}

async function rollbackTarget() {
  if (!selectedTarget.value) return;
  rollingBack.value = true;
  try {
    await store.rollbackPromptOptimizationTarget(selectedTarget.value.target_key);
    ElMessage.success("已回退到上一个稳定版本");
    await refreshAll();
  } catch {
    ElMessage.error("当前没有可回退的稳定版本");
  } finally {
    rollingBack.value = false;
  }
}

async function pollTargetState(targetKey: string) {
  if (pollingTimer.value) {
    window.clearInterval(pollingTimer.value);
    pollingTimer.value = null;
  }
  let attempts = 0;
  pollingTimer.value = window.setInterval(async () => {
    attempts += 1;
    await refreshSelectedTarget(targetKey);
    const latestStatus =
      store.promptOptimizationRuns[0]?.status || store.promptOptimizationCurrent?.current_status;
    if (latestStatus === "completed" || latestStatus === "failed" || attempts >= 12) {
      if (pollingTimer.value) {
        window.clearInterval(pollingTimer.value);
      }
      pollingTimer.value = null;
      await refreshAll();
    }
  }, 800);
}
</script>

<template>
  <div class="workbench-page">
    <section class="hero-panel">
      <div class="hero-copy">
        <div class="eyebrow">Governance Workspace</div>
        <h1>DSPy 优化工作台</h1>
        <p>
          自动发现 LangGraph 子图中需要做提示词优化的节点，在一个界面里完成配置、编译、评测、
          版本回退和图谱上下文查看。这里展示的是系统自动识别的优化位点，而不是人工维护的原始 Prompt。
        </p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" :icon="RefreshRight" @click="refreshAll">刷新位点</el-button>
      </div>
    </section>

    <section class="overview-grid">
      <el-card shadow="never" class="overview-card">
        <div class="overview-icon mint"><el-icon><Aim /></el-icon></div>
        <div class="overview-label">已发现位点</div>
        <div class="overview-value">{{ overview?.total_targets ?? 0 }}</div>
      </el-card>
      <el-card shadow="never" class="overview-card">
        <div class="overview-icon amber"><el-icon><MagicStick /></el-icon></div>
        <div class="overview-label">启用 DSPy</div>
        <div class="overview-value">{{ overview?.enabled_targets ?? 0 }}</div>
      </el-card>
      <el-card shadow="never" class="overview-card">
        <div class="overview-icon blue"><el-icon><Select /></el-icon></div>
        <div class="overview-label">最近编译成功</div>
        <div class="overview-value">{{ overview?.successful_runs ?? 0 }}</div>
      </el-card>
      <el-card shadow="never" class="overview-card danger-card">
        <div class="overview-icon rose"><el-icon><Warning /></el-icon></div>
        <div class="overview-label">待处理异常</div>
        <div class="overview-value">{{ (overview?.failed_runs ?? 0) + (overview?.pending_runs ?? 0) }}</div>
      </el-card>
    </section>

    <section class="workbench-grid">
      <el-card shadow="never" class="sidebar-card">
        <template #header>
          <div class="section-header">
            <div>
              <div class="section-title">自动发现位点</div>
              <div class="section-subtitle">按子图浏览 DSPy 优化目标</div>
            </div>
          </div>
        </template>

        <div class="filter-stack">
          <el-input
            v-model="filters.keyword"
            placeholder="搜索节点名称、模块名或优化目标"
            clearable
          />
          <div class="filter-row">
            <el-select v-model="filters.subgraph_key">
              <el-option label="全部子图" value="all" />
              <el-option label="Legacy Quality" value="legacy_quality" />
              <el-option label="LLM-native Quality" value="llm_native_quality" />
            </el-select>
            <el-select v-model="filters.status">
              <el-option label="全部状态" value="all" />
              <el-option label="idle" value="idle" />
              <el-option label="pending" value="pending" />
              <el-option label="running" value="running" />
              <el-option label="completed" value="completed" />
              <el-option label="failed" value="failed" />
            </el-select>
          </div>
          <el-segmented
            v-model="filters.dspy_state"
            :options="[
              { label: '全部', value: 'all' },
              { label: '已启用', value: 'enabled' },
              { label: '已关闭', value: 'disabled' },
            ]"
          />
        </div>

        <div class="target-groups" v-loading="loading">
          <div v-for="group in groupedTargets" :key="group.key" class="target-group">
            <div class="group-title">{{ group.label }}</div>
            <button
              v-for="item in group.items"
              :key="item.target_key"
              type="button"
              class="target-card"
              :class="{ active: selectedTargetKey === item.target_key, inactive: !item.config.is_active_target }"
              :style="{ '--accent': subgraphAccent(item.subgraph_key) }"
              @click="selectTarget(item)"
            >
              <div class="target-card-top">
                <div>
                  <div class="target-label">{{ item.node_label }}</div>
                  <div class="target-key">{{ item.target_key }}</div>
                </div>
                <el-tag :type="statusTone(item.current_status)" size="small">{{ item.current_status }}</el-tag>
              </div>
              <div class="target-meta">
                <span>{{ item.module_name }}</span>
                <span>{{ item.current_artifact_version || "未生成版本" }}</span>
              </div>
              <div class="target-metrics">
                <span>忠实度 {{ formatMetric(item.latest_metrics?.faithfulness) }}</span>
                <span>可追溯 {{ formatMetric(item.latest_metrics?.traceability) }}</span>
              </div>
              <div class="target-alert" v-if="item.config.latest_error_message">
                最近异常：{{ item.config.latest_error_message }}
              </div>
              <div class="target-alert muted" v-else-if="!item.config.is_active_target">
                该位点已从当前代码目录移除，配置以失效位点形式保留。
              </div>
            </button>
          </div>
          <el-empty
            v-if="!filteredTargets.length"
            description="没有符合筛选条件的优化位点"
            :image-size="90"
          />
        </div>
      </el-card>

      <div class="detail-column" v-if="selectedTarget">
        <el-card shadow="never" class="detail-hero">
          <div class="detail-hero-content">
            <div>
              <div class="detail-eyebrow">{{ selectedTarget.subgraph_key }}</div>
              <h2>{{ selectedTarget.node_label }}</h2>
              <p>{{ selectedTarget.optimization_goal }}</p>
            </div>
            <div class="detail-actions">
              <el-tag :type="selectedTarget.config.is_enabled ? 'success' : 'info'">
                {{ selectedTarget.config.is_enabled ? "DSPy 已启用" : "DSPy 已关闭" }}
              </el-tag>
              <el-button
                type="primary"
                :loading="compiling"
                :disabled="!selectedTarget.supports_compile || !selectedTarget.config.is_active_target"
                @click="compileTarget"
              >
                触发编译
              </el-button>
              <el-button :loading="rollingBack" @click="rollbackTarget">回退稳定版本</el-button>
            </div>
          </div>

          <div class="version-strip">
            <div class="version-pill">
              <span class="label">当前生效版本</span>
              <strong>{{ selectedTarget.config.current_artifact_version || "未生成" }}</strong>
            </div>
            <div class="version-pill">
              <span class="label">上一个稳定版本</span>
              <strong>{{ selectedTarget.config.previous_artifact_version || "暂无" }}</strong>
            </div>
            <div class="version-pill danger">
              <span class="label">最近失败版本</span>
              <strong>{{ selectedTarget.config.latest_failed_artifact_version || "无" }}</strong>
            </div>
          </div>
        </el-card>

        <div class="detail-grid">
          <el-card shadow="never" class="panel-card">
            <template #header>
              <div class="section-header">
                <div>
                  <div class="section-title">DSPy 配置</div>
                  <div class="section-subtitle">节点级优化参数和策略</div>
                </div>
                <el-tag type="info">{{ selectedTarget.module_name }}</el-tag>
              </div>
            </template>

            <el-form label-position="top" class="config-form">
              <div class="config-row">
                <el-form-item label="模块名称">
                  <el-input v-model="configForm.module_name" />
                </el-form-item>
                <el-form-item label="编译版本">
                  <el-input v-model="configForm.compiler_version" placeholder="例如 dspy-2.0" />
                </el-form-item>
              </div>

              <div class="config-row">
                <el-form-item label="优化策略">
                  <el-input v-model="configForm.optimizer_strategy" placeholder="bootstrap-fewshot" />
                </el-form-item>
                <el-form-item label="评测指标">
                  <el-input
                    v-model="metricDraft"
                    placeholder="用逗号分隔，例如 faithfulness, traceability, pass_rate"
                  />
                </el-form-item>
              </div>

              <el-form-item label="配置载荷 JSON">
                <el-input
                  v-model="payloadDraft"
                  type="textarea"
                  :rows="8"
                  placeholder='{"temperature": 0.1, "max_examples": 6}'
                />
              </el-form-item>

              <div class="config-footer">
                <div class="switch-line">
                  <span>启用 DSPy 优化</span>
                  <el-switch v-model="configForm.is_enabled" />
                </div>
                <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
              </div>
            </el-form>
          </el-card>

          <el-card shadow="never" class="panel-card">
            <template #header>
              <div class="section-header">
                <div>
                  <div class="section-title">最近评测</div>
                  <div class="section-subtitle">当前位点最近一次有效指标快照</div>
                </div>
              </div>
            </template>

            <div class="metric-grid">
              <div
                v-for="(value, key) in selectedTarget.latest_metrics || {}"
                :key="key"
                class="metric-stat"
              >
                <span>{{ metricLabel(key) }}</span>
                <strong>{{ formatMetric(value) }}</strong>
              </div>
              <div v-if="!selectedTarget.latest_metrics" class="metric-stat">
                <span>暂无评测结果</span>
                <strong>--</strong>
              </div>
            </div>

            <el-descriptions :column="1" border>
              <el-descriptions-item label="最近编译时间">
                {{ formatDateTime(selectedTarget.config.last_compiled_at) }}
              </el-descriptions-item>
              <el-descriptions-item label="最近评测时间">
                {{ formatDateTime(selectedTarget.config.last_evaluated_at) }}
              </el-descriptions-item>
              <el-descriptions-item label="最近错误">
                {{ selectedTarget.config.latest_error_message || "无" }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card shadow="never" class="panel-card full-width">
            <template #header>
              <div class="section-header">
                <div>
                  <div class="section-title">编译与回退记录</div>
                  <div class="section-subtitle">展示该位点最近的编译、失败与回退动作</div>
                </div>
              </div>
            </template>

            <div class="run-list" v-if="selectedRuns.length">
              <div v-for="run in selectedRuns" :key="run.id" class="run-item">
                <div class="target-card-top">
                  <div class="run-title">
                    <strong>{{ run.run_type }}</strong>
                    <div class="target-key">{{ run.artifact_version || "未生成产物版本" }}</div>
                  </div>
                  <el-tag :type="statusTone(run.status)">{{ run.status }}</el-tag>
                </div>
                <div class="target-meta">
                  <span>编译器 {{ run.compiler_version || "--" }}</span>
                  <span>开始 {{ formatDateTime(run.started_at) }}</span>
                  <span>结束 {{ formatDateTime(run.finished_at) }}</span>
                </div>
                <div class="target-metrics" v-if="run.metrics_snapshot">
                  <span v-for="(value, key) in run.metrics_snapshot" :key="key">
                    {{ metricLabel(key) }} {{ formatMetric(value) }}
                  </span>
                </div>
                <div v-if="run.error_message" class="target-alert run-error">
                  {{ run.error_message }}
                </div>
              </div>
            </div>
            <el-empty v-else description="该位点还没有运行记录" :image-size="90" />
          </el-card>

          <el-card shadow="never" class="panel-card full-width">
            <template #header>
              <div class="section-header">
                <div>
                  <div class="section-title">图谱上下文</div>
                  <div class="section-subtitle">说明该位点在 LangGraph 子图中的前后节点关系</div>
                </div>
                <el-tag type="warning">
                  <el-icon><Connection /></el-icon>
                  <span style="margin-left: 6px">{{ selectedTarget.graph_context.focus_node_label }}</span>
                </el-tag>
              </div>
            </template>

            <div class="graph-columns">
              <div class="graph-block">
                <div class="graph-label">上游节点</div>
                <div class="chip-list">
                  <el-tag
                    v-for="nodeId in selectedTarget.graph_context.upstream_nodes"
                    :key="nodeId"
                    effect="plain"
                  >
                    {{ graphNodeMap.get(nodeId) || nodeId }}
                  </el-tag>
                  <span v-if="!selectedTarget.graph_context.upstream_nodes.length" class="empty-copy">无</span>
                </div>
              </div>

              <div class="graph-focus">
                <div class="focus-badge">{{ selectedTarget.graph_context.focus_node_label }}</div>
                <div class="target-key">{{ selectedTarget.graph_context.focus_node_id }}</div>
              </div>

              <div class="graph-block">
                <div class="graph-label">下游节点</div>
                <div class="chip-list">
                  <el-tag
                    v-for="nodeId in selectedTarget.graph_context.downstream_nodes"
                    :key="nodeId"
                    effect="plain"
                  >
                    {{ graphNodeMap.get(nodeId) || nodeId }}
                  </el-tag>
                  <span v-if="!selectedTarget.graph_context.downstream_nodes.length" class="empty-copy">无</span>
                </div>
              </div>
            </div>

            <div class="graph-node-cloud">
              <div
                v-for="node in selectedTarget.graph_context.nodes"
                :key="node.id"
                class="cloud-node"
                :class="{ focused: node.id === selectedTarget.graph_context.focus_node_id }"
              >
                <strong>{{ node.label }}</strong>
                <span>{{ node.id }}</span>
                <span>{{ node.kind }}</span>
              </div>
            </div>
          </el-card>
        </div>
      </div>

      <div v-else class="empty-detail">
        <el-empty description="请选择左侧自动发现的 DSPy 优化位点" :image-size="110" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.workbench-page {
  min-height: 100%;
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(15, 118, 110, 0.08), transparent 24%),
    radial-gradient(circle at left bottom, rgba(245, 158, 11, 0.1), transparent 26%),
    linear-gradient(180deg, #f8fbfd 0%, #eef3f7 100%);
}

.hero-panel,
.overview-card,
.sidebar-card,
.panel-card,
.detail-hero,
.empty-detail {
  border-radius: 24px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(14px);
}

.hero-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 28px 30px;
  margin-bottom: 20px;
}

.eyebrow,
.detail-eyebrow {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 6px 12px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-copy h1 {
  margin: 12px 0 10px;
  font-size: 34px;
  line-height: 1.15;
  color: #0f172a;
}

.hero-copy p {
  max-width: 760px;
  margin: 0;
  color: #475569;
  line-height: 1.8;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.overview-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
  padding: 22px;
}

.overview-icon {
  display: inline-flex;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  font-size: 20px;
}

.overview-icon.mint {
  background: rgba(15, 118, 110, 0.12);
  color: #0f766e;
}

.overview-icon.amber {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}

.overview-icon.blue {
  background: rgba(37, 99, 235, 0.12);
  color: #2563eb;
}

.overview-icon.rose {
  background: rgba(225, 29, 72, 0.12);
  color: #be123c;
}

.overview-label {
  color: #64748b;
  font-size: 13px;
}

.overview-value {
  font-size: 30px;
  font-weight: 700;
  color: #0f172a;
}

.danger-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(255, 241, 242, 0.9));
}

.workbench-grid {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.sidebar-card :deep(.el-card__body),
.panel-card :deep(.el-card__body) {
  padding: 18px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
}

.section-subtitle {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.filter-stack {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.filter-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.target-groups {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.target-group {
  display: grid;
  gap: 12px;
}

.group-title {
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}

.target-card {
  width: 100%;
  padding: 16px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-left: 4px solid var(--accent);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.98));
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.target-card:hover,
.target-card.active {
  transform: translateY(-2px);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.08);
  border-color: rgba(15, 23, 42, 0.12);
}

.target-card.inactive {
  opacity: 0.72;
}

.target-card-top,
.target-meta,
.target-metrics {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.target-label {
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.target-key {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
  word-break: break-all;
}

.target-meta,
.target-metrics {
  margin-top: 10px;
  color: #475569;
  font-size: 12px;
  flex-wrap: wrap;
}

.target-alert {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(190, 24, 93, 0.08);
  color: #9f1239;
  font-size: 12px;
  line-height: 1.6;
}

.target-alert.muted {
  background: rgba(100, 116, 139, 0.08);
  color: #475569;
}

.detail-column {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.detail-hero {
  padding: 24px 24px 20px;
  background:
    radial-gradient(circle at top right, rgba(251, 191, 36, 0.18), transparent 32%),
    linear-gradient(135deg, #fffdf7 0%, #ffffff 52%, #f0fdfa 100%);
}

.detail-hero-content {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.detail-hero h2 {
  margin: 10px 0 8px;
  font-size: 28px;
  color: #0f172a;
}

.detail-hero p {
  margin: 0;
  max-width: 720px;
  color: #475569;
  line-height: 1.7;
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.version-strip,
.metric-grid {
  display: grid;
  gap: 12px;
}

.version-strip {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 18px;
}

.version-pill,
.metric-stat,
.graph-block,
.graph-focus,
.cloud-node,
.run-item {
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: #fff;
}

.version-pill {
  padding: 14px 16px;
  background: rgba(15, 118, 110, 0.08);
}

.version-pill.danger {
  background: rgba(190, 24, 93, 0.08);
}

.version-pill .label,
.metric-stat span,
.graph-label {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.version-pill strong,
.metric-stat strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 18px;
}

.panel-card.full-width {
  grid-column: 1 / -1;
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.config-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.switch-line {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #334155;
  font-size: 13px;
}

.metric-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 16px;
}

.metric-stat {
  padding: 14px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(241, 245, 249, 0.92));
}

.metric-stat strong {
  font-size: 22px;
}

.run-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.run-item {
  padding: 14px;
}

.run-title strong {
  color: #0f172a;
  font-size: 14px;
}

.run-error {
  background: rgba(225, 29, 72, 0.08);
  color: #9f1239;
}

.graph-columns {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 14px;
  align-items: center;
}

.graph-block,
.graph-focus {
  min-height: 126px;
  padding: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.96));
}

.graph-label {
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 12px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.graph-focus {
  text-align: center;
  min-width: 210px;
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.98), rgba(236, 253, 245, 0.96));
}

.focus-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 16px;
  border-radius: 999px;
  background: #0f172a;
  color: #fff;
  font-weight: 700;
}

.graph-node-cloud {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-top: 18px;
}

.cloud-node {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
}

.cloud-node.focused {
  border-color: rgba(245, 158, 11, 0.5);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.98), rgba(255, 255, 255, 1));
}

.empty-copy {
  color: #94a3b8;
  font-size: 13px;
}

.empty-detail {
  display: grid;
  place-items: center;
  min-height: 620px;
  padding: 40px 24px;
  border-style: dashed;
}

@media (max-width: 1400px) {
  .workbench-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hero-panel,
  .detail-hero-content,
  .config-footer,
  .graph-columns {
    display: grid;
    grid-template-columns: 1fr;
  }

  .overview-grid,
  .version-strip,
  .metric-grid,
  .config-row,
  .filter-row {
    grid-template-columns: 1fr;
  }
}
</style>
