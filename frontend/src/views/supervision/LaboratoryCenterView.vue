<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { RefreshRight } from "@element-plus/icons-vue";
import { supervisionApi } from "@/api/supervision.api";
import { extractApiErrorMessage } from "@/api/http";
import type { SupervisionRecord } from "@/types/supervision.types";
import SupervisionModuleHeader from "@/components/business/supervision/SupervisionModuleHeader.vue";
import DemoLabWorkspace from "@/components/business/supervision/DemoLabWorkspace.vue";
import { useRuntimeContext } from "@/composables/useRuntimeContext";
import {
  sessionItemCount,
  sessionMissingConfiguration,
  sessionStatusLabel,
} from "@/utils/laboratory-session";

const runtime = useRuntimeContext(),
  route = useRoute(),
  router = useRouter();
const isDemo = computed(() => runtime.context.value?.execution_mode === "demo");
const activeView = computed(() =>
  isDemo.value ||
  route.query.view === "validation" ||
  (!!route.query.case_id && route.query.view !== "batches")
    ? "validation"
    : "batches",
);
const loading = ref(false),
  error = ref(""),
  summaryError = ref("");
const sessions = ref<SupervisionRecord[]>([]);
const filter = ref("all"),
  page = ref(1),
  total = ref<number | null>(null),
  keyword = ref("");
const metrics = ref<{ collecting: number; review: number; signed: number; online: number } | null>(
  null,
);
let epoch = 0;
const filters = [
  { key: "all", label: "全部" },
  { key: "active", label: "待准备" },
  { key: "collecting", label: "采集中" },
  { key: "awaiting_evidence", label: "待补证" },
  { key: "awaiting_review", label: "待复核" },
  { key: "signed", label: "已确认" },
];

async function load() {
  const key = ++epoch;
  await runtime.load();
  if (key !== epoch || !runtime.context.value || isDemo.value || activeView.value !== "batches")
    return;
  loading.value = true;
  error.value = "";
  summaryError.value = "";
  const [list, summary] = await Promise.allSettled([
    supervisionApi.list("inspection-sessions", {
      page: page.value,
      size: 20,
      keyword: keyword.value.trim() || undefined,
      status: filter.value === "all" ? undefined : filter.value,
    }),
    supervisionApi.laboratorySummary(),
  ]);
  if (key !== epoch) return;
  if (list.status === "fulfilled") {
    sessions.value = list.value.data.data.items;
    total.value = list.value.data.data.total;
  } else {
    sessions.value = [];
    total.value = null;
    error.value = extractApiErrorMessage(list.reason, "检测批次加载失败，请重试");
  }
  if (summary.status === "fulfilled") metrics.value = summary.value.data.data;
  else {
    metrics.value = null;
    summaryError.value = "批次统计暂不可用，已加载的批次仍可查看。";
  }
  loading.value = false;
}

function setView(view: "batches" | "validation") {
  void router.replace({ query: { ...route.query, view } });
}
function openTask(session: SupervisionRecord) {
  if (!session.data.task_id) return;
  void router.push({ path: `/app/tasks/${session.data.task_id}`, query: { session: session.id } });
}
function openSession(session: SupervisionRecord) {
  void router.push({ path: "/app/inspection-sessions", query: { record: session.id } });
}
function modeLabel(mode?: string) {
  return (
    ({ image: "图片", measurement: "测量", mixed: "混合" } as Record<string, string>)[mode || ""] ||
    "待配置"
  );
}
onMounted(load);
watch(filter, () => {
  page.value = 1;
  void load();
});
watch(activeView, () => {
  ++epoch;
  loading.value = false;
  void load();
});
onBeforeUnmount(() => {
  ++epoch;
});
</script>

<template>
  <main class="laboratory-page">
    <SupervisionModuleHeader
      title="实验室检测"
      tone="violet"
      description="围绕检测任务组织样品、设备和测量；将验证证据返回风险事项，支持后续研判。"
      principle="已有报告可直接引用；新的检测关联任务，并按检测方式准备样品、设备与项目。"
    >
      <template #actions>
        <el-button @click="router.push('/app/tasks')">检测任务</el-button>
        <el-button type="primary" @click="setView('validation')">从风险事项发起验证</el-button>
      </template>
    </SupervisionModuleHeader>
    <el-alert
      v-if="!runtime.context.value"
      title="运行环境暂未就绪，请重试后继续。"
      type="info"
      :closable="false"
    >
      <template #default><el-button link @click="load">重试加载</el-button></template>
    </el-alert>
    <template v-else>
      <nav class="lab-views" aria-label="实验室业务视图">
        <button
          type="button"
          :aria-pressed="activeView === 'batches'"
          :disabled="isDemo"
          @click="setView('batches')"
        >
          检测批次<span>样品、设备与执行</span>
        </button>
        <button
          type="button"
          :aria-pressed="activeView === 'validation'"
          @click="setView('validation')"
        >
          验证与回流<span>关联风险事项与证据</span>
        </button>
        <span v-if="isDemo" class="environment-note">演示环境 · 使用模拟验证资料</span>
      </nav>
      <DemoLabWorkspace v-if="activeView === 'validation'" embedded />
      <section v-else class="laboratory-board" aria-labelledby="batch-title" :aria-busy="loading">
        <header class="board-heading">
          <div>
            <h2 id="batch-title">
              检测批次 <span v-if="total !== null">{{ total }}</span>
            </h2>
            <p>打开批次查看配置与依据，进入关联任务完成测量、复核和结果确认。</p>
          </div>
          <el-button :icon="RefreshRight" :loading="loading" @click="load">刷新批次</el-button>
        </header>
        <div class="batch-summary" aria-label="实验室检测概况">
          <span
            >采集中 <b>{{ metrics?.collecting ?? "—" }}</b></span
          ><span
            >待复核 <b>{{ metrics?.review ?? "—" }}</b></span
          >
          <span
            >已确认 <b>{{ metrics?.signed ?? "—" }}</b></span
          ><span
            >在线设备 <b>{{ metrics?.online ?? "—" }}</b></span
          >
        </div>
        <el-alert v-if="summaryError" :title="summaryError" type="warning" :closable="false" />
        <form
          class="batch-toolbar"
          @submit.prevent="
            page = 1;
            load();
          "
        >
          <div class="status-filter" aria-label="检测批次状态">
            <button
              v-for="item in filters"
              :key="item.key"
              type="button"
              :aria-pressed="filter === item.key"
              @click="filter = item.key"
            >
              {{ item.label }}
            </button>
          </div>
          <div class="batch-search">
            <el-input
              v-model="keyword"
              aria-label="实验室批次搜索"
              placeholder="按批次编号或名称搜索"
              :maxlength="200"
              clearable
            /><el-button native-type="submit" :disabled="loading">搜索</el-button>
          </div>
        </form>
        <el-alert v-if="error" :title="error" type="error" :closable="false"
          ><template #default
            ><el-button link @click="load">重试批次列表</el-button></template
          ></el-alert
        >
        <el-skeleton v-else-if="loading && !sessions.length" :rows="4" animated />
        <div v-else-if="sessions.length" class="session-list" v-loading="loading">
          <article v-for="session in sessions" :key="session.id" class="session-row">
            <div class="session-heading">
              <div>
                <span class="session-code">{{ session.display_no || session.code }}</span>
                <h3>{{ session.name }}</h3>
              </div>
              <el-tag effect="plain">{{ sessionStatusLabel(session) }}</el-tag>
            </div>
            <dl class="session-facts">
              <div>
                <dt>输入方式</dt>
                <dd>{{ modeLabel(session.data.input_mode) }}</dd>
              </div>
              <div>
                <dt>关联样品</dt>
                <dd>{{ session.data.sample_ids?.length || 0 }}</dd>
              </div>
              <div>
                <dt>关联设备</dt>
                <dd>{{ session.data.device_ids?.length || 0 }}</dd>
              </div>
              <div>
                <dt>检测项目</dt>
                <dd>
                  {{
                    session.data.input_mode === "image" && !sessionItemCount(session)
                      ? "按任务标准"
                      : sessionItemCount(session)
                  }}
                </dd>
              </div>
            </dl>
            <p
              v-if="
                sessionMissingConfiguration(session).length &&
                !['signed', 'closed', 'archived'].includes(session.status)
              "
              class="configuration-notice"
            >
              <strong>配置待完善</strong>{{ sessionMissingConfiguration(session).join(" · ") }}
            </p>
            <footer class="session-footer">
              <span
                >{{
                  session.data.task_id
                    ? `关联任务 ${String(session.data.task_id).slice(-8)}`
                    : "尚未关联检测任务"
                }}<template v-if="session.data.plan_id"> · 来自抽查计划</template></span
              >
              <div>
                <el-button @click="openSession(session)">批次详情</el-button
                ><el-button
                  type="primary"
                  plain
                  :disabled="!session.data.task_id"
                  @click="openTask(session)"
                  >{{
                    sessionMissingConfiguration(session).length ? "完善配置与执行" : "进入检测任务"
                  }}</el-button
                >
              </div>
            </footer>
          </article>
        </div>
        <el-empty v-else description="当前条件下没有检测批次" :image-size="70"
          ><p class="empty-note">
            新的验证需求可从风险事项发起；已有检测任务请在任务内登记样品并配置批次。
          </p>
          <el-button @click="router.push('/app/tasks')">查看检测任务</el-button></el-empty
        >
        <el-pagination
          v-if="!error && total"
          layout="prev, pager, next, total"
          :page-size="20"
          :total="total"
          :current-page="page"
          :disabled="loading"
          @current-change="
            page = $event;
            load();
          "
        />
      </section>
    </template>
  </main>
</template>

<style scoped>
.laboratory-page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px;
  color: var(--piap-ink);
}
.lab-views {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 20px;
  border-bottom: 1px solid var(--piap-line);
}
.lab-views > button {
  padding: 12px 20px;
  min-height: 64px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  text-align: left;
  color: var(--el-text-color-regular);
  font-weight: 650;
  cursor: pointer;
}
.lab-views > button span {
  display: block;
  margin-top: 5px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.lab-views > button[aria-pressed="true"] {
  border-bottom-color: var(--piap-blue);
  color: var(--piap-blue);
}
.lab-views > button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.environment-note {
  margin-left: auto;
  color: #8c621b;
  font-size: 12px;
}
.laboratory-board {
  padding: 22px;
  border: 1px solid var(--piap-line);
  border-radius: 12px;
  background: #fff;
}
.board-heading,
.session-heading,
.session-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 19px;
}
h2 span {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  font-weight: 400;
}
.board-heading p {
  margin: 7px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.batch-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 28px;
  padding: 16px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.batch-summary b {
  margin-left: 7px;
  color: var(--piap-ink);
  font-variant-numeric: tabular-nums;
}
.batch-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 0;
  border-top: 1px solid var(--piap-line);
  border-bottom: 1px solid var(--piap-line);
}
.status-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.status-filter button {
  min-height: 38px;
  padding: 7px 12px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--el-text-color-regular);
  cursor: pointer;
}
.status-filter button[aria-pressed="true"] {
  border-color: #c8d9f7;
  background: #edf3ff;
  color: var(--piap-blue);
}
.batch-search {
  display: flex;
  gap: 8px;
  width: min(100%, 360px);
}
.session-row {
  padding: 22px 0;
  border-bottom: 1px solid var(--piap-line);
}
.session-row:last-child {
  border-bottom: 0;
}
.session-code {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
h3 {
  margin: 5px 0 0;
  font-size: 16px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.session-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.session-facts dt {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.session-facts dd {
  margin: 5px 0 0;
  font-size: 15px;
  font-weight: 650;
}
.configuration-notice {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #fff8e9;
  color: #83581a;
  font-size: 12px;
  line-height: 1.8;
  border-radius: 6px;
}
.configuration-notice strong {
  font-weight: 650;
}
.session-footer {
  margin-top: 14px;
}
.session-footer > span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.session-footer > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.session-footer :deep(.el-button) {
  margin: 0;
  min-height: 38px;
}
.empty-note {
  max-width: 480px;
  margin: 0 0 14px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.8;
}
.el-pagination {
  margin-top: 18px;
  max-width: 100%;
  overflow: auto;
}
button:focus-visible {
  outline: 2px solid var(--piap-blue);
  outline-offset: 3px;
}
@media (max-width: 640px) {
  .laboratory-page {
    padding: 12px;
  }
  .laboratory-board {
    padding: 16px;
  }
  .board-heading {
    align-items: flex-start;
  }
  .board-heading > .el-button {
    flex: 0 0 auto;
  }
  .lab-views > button {
    padding: 10px 12px;
  }
  .environment-note {
    width: 100%;
    margin: 0 0 10px 12px;
  }
  .status-filter button {
    min-height: 44px;
  }
  .session-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .session-footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .session-footer :deep(.el-button) {
    min-height: 44px;
  }
  .batch-search {
    width: 100%;
  }
}
</style>
