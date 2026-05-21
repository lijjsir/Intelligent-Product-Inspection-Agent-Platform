<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

const props = defineProps<{
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
}>();

const route = useRoute();
const router = useRouter();
const resourceId = computed(() => String(route.params.id || ""));
const current = computed(() => props.store.current);
const resultSummary = computed(() => {
  const value = current.value?.result_summary;
  if (!value || typeof value !== "object") {
    return { artifacts: [], metrics: {}, logs: [] };
  }
  return {
    artifacts: Array.isArray(value.artifacts) ? value.artifacts : [],
    metrics: value.metrics && typeof value.metrics === "object" ? value.metrics : {},
    logs: Array.isArray(value.logs) ? value.logs : [],
  };
});

function statusTagType(status?: string | null) {
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "info";
  return "primary";
}

async function load() {
  if (!resourceId.value) return;
  await props.store.fetchOne(resourceId.value);
}

async function handleLaunch() {
  if (!resourceId.value || !props.store.launchOne) return;
  await props.store.launchOne(resourceId.value);
  ElMessage.success("已启动");
  await load();
}

async function handleCancel() {
  if (!resourceId.value || !props.store.cancelOne) return;
  await props.store.cancelOne(resourceId.value);
  ElMessage.success("已取消");
  await load();
}

async function handleDelete() {
  if (!resourceId.value) return;
  await ElMessageBox.confirm("确定删除该记录吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  await props.store.removeOne(resourceId.value);
  ElMessage.success("已删除");
  if (props.backPath) {
    await router.push(props.backPath);
    return;
  }
  router.back();
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <div class="flex flex-col gap-5">
    <section class="hero">
      <div class="hero-header">
        <div>
          <el-button link type="primary" @click="props.backPath ? router.push(props.backPath) : router.back()">返回</el-button>
          <h2>{{ current?.name || title }}</h2>
          <p>{{ current?.description || props.intro || "资源详情骨架页，展示基础信息、执行状态和结果摘要。" }}</p>
        </div>
        <div class="hero-actions">
          <el-button v-if="store.launchOne && ['draft', 'failed'].includes(current?.status || '')" type="primary" @click="handleLaunch">启动</el-button>
          <el-button v-if="store.cancelOne && ['queued', 'running'].includes(current?.status || '')" type="warning" @click="handleCancel">取消</el-button>
          <el-button type="danger" @click="handleDelete">删除</el-button>
        </div>
      </div>
    </section>

    <section class="detail-grid" v-loading="store.loading">
      <article class="card-surface p-4">
        <h3>概览</h3>
        <div class="overview-list">
          <div><span>状态</span><strong><el-tag :type="statusTagType(current?.status)">{{ current?.status || "-" }}</el-tag></strong></div>
          <div><span>创建时间</span><strong>{{ current?.created_at || "-" }}</strong></div>
          <div><span>更新时间</span><strong>{{ current?.updated_at || "-" }}</strong></div>
          <div><span>执行模式</span><strong>{{ current?.execution_mode || "-" }}</strong></div>
          <div><span>执行任务 ID</span><strong class="break-all">{{ current?.executor_job_id || "-" }}</strong></div>
          <div><span>开始时间</span><strong>{{ current?.started_at || "-" }}</strong></div>
          <div><span>完成时间</span><strong>{{ current?.completed_at || "-" }}</strong></div>
          <div v-for="section in props.relationSections || []" :key="section.label">
            <span>{{ section.label }}</span>
            <strong class="break-all">{{ section.value(current) || "-" }}</strong>
          </div>
        </div>
      </article>

      <article class="card-surface p-4">
        <h3>配置 JSON</h3>
        <pre class="detail-json">{{ JSON.stringify(current?.config_json || {}, null, 2) }}</pre>
      </article>
    </section>

    <section class="detail-grid">
      <article class="card-surface p-4">
        <h3>结果摘要</h3>
        <div class="summary-grid">
          <div>
            <h4>Artifacts</h4>
            <el-empty v-if="!resultSummary.artifacts.length" description="暂无 artifacts" />
            <ul v-else>
              <li v-for="(item, index) in resultSummary.artifacts" :key="index">{{ JSON.stringify(item) }}</li>
            </ul>
          </div>
          <div>
            <h4>Metrics</h4>
            <el-empty v-if="!Object.keys(resultSummary.metrics).length" description="暂无 metrics" />
            <pre v-else class="detail-json small">{{ JSON.stringify(resultSummary.metrics, null, 2) }}</pre>
          </div>
          <div>
            <h4>Logs</h4>
            <el-empty v-if="!resultSummary.logs.length" description="暂无 logs" />
            <ul v-else>
              <li v-for="(item, index) in resultSummary.logs" :key="index">{{ String(item) }}</li>
            </ul>
          </div>
        </div>
      </article>
    </section>

    <section class="card-surface p-4" v-loading="store.loading">
      <h3>完整资源</h3>
      <pre class="detail-json">{{ JSON.stringify(current, null, 2) }}</pre>
    </section>
  </div>
</template>

<style scoped>
.hero {
  padding: 24px;
  border-radius: 24px;
  background: linear-gradient(135deg, #f4f8ef, #fff6e8);
}

.hero-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero h2 {
  margin: 8px 0;
  font-size: 28px;
  color: #17212c;
}

.hero p {
  margin: 0;
  color: #536171;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}

.overview-list {
  display: grid;
  gap: 12px;
}

.overview-list > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.overview-list span {
  color: #64748b;
}

.detail-json {
  max-height: 640px;
  overflow: auto;
  background: #101827;
  color: #dbe7f3;
  padding: 16px;
  border-radius: 16px;
  font-size: 12px;
}

.detail-json.small {
  max-height: 240px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
</style>
