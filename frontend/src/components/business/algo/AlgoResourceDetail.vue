<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import type {
  SummaryArtifactItem,
  SummaryHighlightItem,
  SummaryLogItem,
  SummaryMetricItem,
} from "@/types/algo-workspace.types";

const props = withDefaults(defineProps<{
  title: string;
  store: {
    current: any;
    loading: boolean;
    fetchOne: (id: string) => Promise<any>;
    removeOne: (id: string) => Promise<void>;
    launchOne?: (id: string) => Promise<any>;
    cancelOne?: (id: string) => Promise<any>;
  };
  backPath?: string;
  relationSections?: Array<{ label: string; value: (item: any) => string | null | undefined }>;
  intro?: string;
  highlights?: SummaryHighlightItem[];
  metrics?: SummaryMetricItem[];
  artifacts?: SummaryArtifactItem[];
  logs?: SummaryLogItem[];
  rawConfig?: unknown;
  rawResource?: unknown;
  collapseRawByDefault?: boolean;
  autoRefreshWhenRunning?: boolean;
  autoRefreshIntervalMs?: number;
}>(), {
  relationSections: () => [],
  highlights: () => [],
  metrics: () => [],
  artifacts: () => [],
  logs: () => [],
  collapseRawByDefault: true,
  autoRefreshWhenRunning: false,
  autoRefreshIntervalMs: 15000,
});

const route = useRoute();
const router = useRouter();
const resourceId = computed(() => String(route.params.id || ""));
const current = computed(() => props.store.current);
const actionLoading = ref("");
const configExpanded = ref(!props.collapseRawByDefault);
const resourceExpanded = ref(!props.collapseRawByDefault);
let pollingTimer: ReturnType<typeof setInterval> | null = null;

function statusTagType(status?: string | null) {
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "info";
  return "primary";
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.length ? JSON.stringify(value, null, 2) : "[]";
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

async function load() {
  if (!resourceId.value) return;
  await props.store.fetchOne(resourceId.value);
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

function syncPolling() {
  stopPolling();
  if (!props.autoRefreshWhenRunning) return;
  const status = String(current.value?.status || "");
  if (!["queued", "running"].includes(status) || !resourceId.value) return;
  pollingTimer = setInterval(() => {
    load().catch(() => {});
  }, Math.max(Number(props.autoRefreshIntervalMs || 15000), 3000));
}

async function handleLaunch() {
  if (!resourceId.value || !props.store.launchOne) return;
  actionLoading.value = "launch";
  try {
    await props.store.launchOne(resourceId.value);
    ElMessage.success("已启动");
    await load();
  } finally {
    actionLoading.value = "";
  }
}

async function handleCancel() {
  if (!resourceId.value || !props.store.cancelOne) return;
  actionLoading.value = "cancel";
  try {
    await props.store.cancelOne(resourceId.value);
    ElMessage.success("已取消");
    await load();
  } finally {
    actionLoading.value = "";
  }
}

async function handleDelete() {
  if (!resourceId.value) return;
  await ElMessageBox.confirm("确定删除该记录吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  actionLoading.value = "delete";
  try {
    await props.store.removeOne(resourceId.value);
    ElMessage.success("已删除");
    if (props.backPath) {
      await router.push(props.backPath);
      return;
    }
    router.back();
  } finally {
    actionLoading.value = "";
  }
}

onMounted(load);
watch(() => route.params.id, load);
watch(() => current.value?.status, syncPolling, { immediate: true });
watch(() => props.autoRefreshWhenRunning, syncPolling);
onBeforeUnmount(stopPolling);
</script>

<template>
  <div class="detail-page">
    <section class="hero">
      <div class="hero-header">
        <div class="hero-copy">
          <el-button link type="primary" @click="props.backPath ? router.push(props.backPath) : router.back()">返回</el-button>
          <h2>{{ current?.name || title }}</h2>
          <p>{{ current?.description || props.intro || "资源详情页，展示基础信息、执行状态和结果摘要。" }}</p>
        </div>
        <div class="hero-actions">
          <el-button
            v-if="store.launchOne && ['draft', 'failed'].includes(current?.status || '')"
            type="primary"
            :loading="actionLoading === 'launch'"
            @click="handleLaunch"
          >
            启动
          </el-button>
          <el-button
            v-if="store.cancelOne && ['queued', 'running'].includes(current?.status || '')"
            type="warning"
            :loading="actionLoading === 'cancel'"
            @click="handleCancel"
          >
            取消
          </el-button>
          <el-button type="danger" :loading="actionLoading === 'delete'" @click="handleDelete">删除</el-button>
        </div>
      </div>
    </section>

    <section class="detail-grid" v-loading="store.loading">
      <article class="card-surface p-5">
        <div class="section-head">
          <h3>概览</h3>
          <el-tag :type="statusTagType(current?.status)">{{ current?.status || "-" }}</el-tag>
        </div>
        <div class="overview-list">
          <div><span>创建时间</span><strong>{{ current?.created_at || "-" }}</strong></div>
          <div><span>更新时间</span><strong>{{ current?.updated_at || "-" }}</strong></div>
          <div><span>执行模式</span><strong>{{ current?.execution_mode || "-" }}</strong></div>
          <div><span>执行任务 ID</span><strong class="mono break-all">{{ current?.executor_job_id || "-" }}</strong></div>
          <div><span>开始时间</span><strong>{{ current?.started_at || "-" }}</strong></div>
          <div><span>完成时间</span><strong>{{ current?.completed_at || "-" }}</strong></div>
          <div v-for="section in props.relationSections" :key="section.label">
            <span>{{ section.label }}</span>
            <strong class="mono break-all">{{ section.value(current) || "-" }}</strong>
          </div>
        </div>
      </article>

      <article v-if="props.highlights.length" class="card-surface p-5">
        <div class="section-head">
          <h3>关键指标</h3>
          <span class="section-tip">优先展示最需要关注的结果</span>
        </div>
        <div class="highlight-grid">
          <div v-for="item in props.highlights" :key="item.label" class="highlight-card" :data-tone="item.tone || 'primary'">
            <div class="highlight-label">{{ item.label }}</div>
            <div class="highlight-value">
              {{ formatValue(item.value) }}
              <span v-if="item.unit" class="highlight-unit">{{ item.unit }}</span>
            </div>
            <div v-if="item.hint" class="highlight-hint">{{ item.hint }}</div>
          </div>
        </div>
      </article>
    </section>

    <section class="summary-shell">
      <article class="card-surface p-5">
        <div class="section-head">
          <h3>结果摘要</h3>
          <span class="section-tip">结构化展示指标、产物和日志</span>
        </div>

        <div class="summary-grid">
          <section class="summary-panel">
            <div class="summary-head">
              <h4>指标</h4>
              <span class="summary-count">{{ props.metrics.length }}</span>
            </div>
            <el-empty v-if="!props.metrics.length" description="暂无指标" />
            <div v-else class="metric-list">
              <div v-for="item in props.metrics" :key="item.key" class="metric-row">
                <span class="metric-key">{{ item.label }}</span>
                <el-tooltip
                  v-if="formatValue(item.value).length > 56"
                  :content="formatValue(item.value)"
                  placement="top-start"
                >
                  <strong class="metric-value clamp-two">{{ formatValue(item.value) }}</strong>
                </el-tooltip>
                <strong v-else class="metric-value">{{ formatValue(item.value) }}</strong>
              </div>
            </div>
          </section>

          <section class="summary-panel">
            <div class="summary-head">
              <h4>产物</h4>
              <span class="summary-count">{{ props.artifacts.length }}</span>
            </div>
            <el-empty v-if="!props.artifacts.length" description="暂无产物" />
            <div v-else class="artifact-list">
              <article v-for="(item, index) in props.artifacts" :key="`${item.title}-${index}`" class="artifact-card">
                <div class="artifact-title-row">
                  <strong class="artifact-title">{{ item.title }}</strong>
                  <span v-if="item.type" class="artifact-type">{{ item.type }}</span>
                </div>
                <div v-if="item.subtitle" class="artifact-subtitle">{{ item.subtitle }}</div>
                <div v-if="item.path" class="artifact-path mono break-all">{{ item.path }}</div>
                <div v-if="item.link" class="artifact-link">
                  <a :href="item.link" target="_blank" rel="noreferrer">打开链接</a>
                </div>
                <dl v-if="item.meta && Object.keys(item.meta).length" class="artifact-meta">
                  <div v-for="(value, key) in item.meta" :key="String(key)">
                    <dt>{{ key }}</dt>
                    <dd>{{ formatValue(value) }}</dd>
                  </div>
                </dl>
              </article>
            </div>
          </section>

          <section class="summary-panel">
            <div class="summary-head">
              <h4>日志</h4>
              <span class="summary-count">{{ props.logs.length }}</span>
            </div>
            <el-empty v-if="!props.logs.length" description="暂无日志" />
            <div v-else class="log-list">
              <article v-for="(item, index) in props.logs" :key="`${item.timestamp || 'log'}-${index}`" class="log-item">
                <div class="log-meta">
                  <span v-if="item.level" class="log-level">{{ item.level }}</span>
                  <span v-if="item.timestamp" class="log-time mono">{{ item.timestamp }}</span>
                </div>
                <div class="log-text">{{ item.text }}</div>
              </article>
            </div>
          </section>
        </div>
      </article>
    </section>

    <slot />

    <section class="raw-shell">
      <article class="card-surface p-5">
        <button class="raw-toggle" type="button" @click="configExpanded = !configExpanded">
          <span>配置 JSON</span>
          <span>{{ configExpanded ? "收起" : "展开" }}</span>
        </button>
        <div v-if="configExpanded" class="raw-body">
          <pre class="detail-json">{{ JSON.stringify(props.rawConfig ?? current?.config_json ?? {}, null, 2) }}</pre>
        </div>
      </article>

      <article class="card-surface p-5">
        <button class="raw-toggle" type="button" @click="resourceExpanded = !resourceExpanded">
          <span>完整资源</span>
          <span>{{ resourceExpanded ? "收起" : "展开" }}</span>
        </button>
        <div v-if="resourceExpanded" class="raw-body">
          <pre class="detail-json">{{ JSON.stringify(props.rawResource ?? current, null, 2) }}</pre>
        </div>
      </article>
    </section>

  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero {
  padding: 24px;
  border-radius: 24px;
  background: linear-gradient(135deg, #f4f8ef, #fff6e8);
}

.hero-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
}

.hero-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero h2 {
  margin: 0;
  font-size: 28px;
  color: #17212c;
}

.hero p {
  margin: 0;
  color: #536171;
  max-width: 72ch;
}

.detail-grid,
.raw-shell {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}

.section-head,
.summary-head,
.raw-toggle {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.section-head h3,
.summary-head h4 {
  margin: 0;
}

.section-tip,
.summary-count {
  color: #64748b;
  font-size: 13px;
}

.overview-list {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.overview-list > div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.overview-list span {
  color: #64748b;
}

.summary-shell {
  display: flex;
}

.highlight-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.highlight-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  min-height: 124px;
}

.highlight-card[data-tone="success"] {
  border-color: #bbf7d0;
  background: linear-gradient(180deg, #f7fee7, #ecfccb);
}

.highlight-card[data-tone="warning"] {
  border-color: #fde68a;
  background: linear-gradient(180deg, #fffbeb, #fef3c7);
}

.highlight-card[data-tone="danger"] {
  border-color: #fecaca;
  background: linear-gradient(180deg, #fef2f2, #fee2e2);
}

.highlight-label {
  color: #64748b;
  font-size: 13px;
}

.highlight-value {
  margin-top: 12px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.2;
  word-break: break-word;
}

.highlight-unit {
  margin-left: 4px;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
}

.highlight-hint {
  margin-top: 10px;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.summary-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.summary-panel {
  min-height: 360px;
  max-height: 460px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #e2e8f0;
  background: #fcfdff;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.metric-list,
.artifact-list,
.log-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
  padding-right: 4px;
}

.metric-row {
  display: grid;
  grid-template-columns: minmax(92px, 132px) minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
}

.metric-key {
  color: #64748b;
  font-size: 13px;
}

.metric-value {
  color: #0f172a;
  font-weight: 600;
  white-space: pre-wrap;
  word-break: break-word;
}

.artifact-card,
.log-item {
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  padding: 14px;
}

.artifact-title-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.artifact-title {
  color: #0f172a;
  word-break: break-word;
}

.artifact-type {
  color: #475569;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eff6ff;
}

.artifact-subtitle,
.artifact-link,
.artifact-path,
.log-text {
  margin-top: 8px;
}

.artifact-subtitle,
.artifact-path,
.log-text {
  color: #334155;
  line-height: 1.6;
  word-break: break-word;
}

.artifact-link a {
  color: #2563eb;
}

.artifact-meta {
  display: grid;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
}

.artifact-meta > div {
  display: grid;
  gap: 4px;
}

.artifact-meta dt {
  color: #64748b;
}

.artifact-meta dd {
  margin: 0;
  color: #0f172a;
  white-space: pre-wrap;
  word-break: break-word;
}

.log-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
}

.log-level {
  padding: 2px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
}

.raw-toggle {
  width: 100%;
  background: transparent;
  border: 0;
  padding: 0;
  cursor: pointer;
  font: inherit;
  color: #0f172a;
}

.raw-body {
  margin-top: 16px;
}

.detail-json {
  max-height: 360px;
  overflow: auto;
  background: #101827;
  color: #dbe7f3;
  padding: 16px;
  border-radius: 16px;
  font-size: 12px;
  margin: 0;
}

.mono {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

.clamp-two {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 1279px) {
  .summary-grid {
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }
}

@media (max-width: 767px) {
  .hero-header,
  .overview-list > div,
  .section-head,
  .summary-head,
  .raw-toggle {
    flex-direction: column;
    align-items: flex-start;
  }

  .metric-row {
    grid-template-columns: 1fr;
  }

  .summary-panel {
    min-height: 0;
    max-height: none;
  }
}
</style>
