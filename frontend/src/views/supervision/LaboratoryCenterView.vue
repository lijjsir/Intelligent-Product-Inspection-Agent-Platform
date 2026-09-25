<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, RefreshRight } from "@element-plus/icons-vue";
import { supervisionApi } from "@/api/supervision.api";
import { STATUS_LABELS, type SupervisionRecord } from "@/types/supervision.types";
import SupervisionAgentRail from "@/components/business/supervision/SupervisionAgentRail.vue";
import SupervisionModuleHeader from "@/components/business/supervision/SupervisionModuleHeader.vue";

const router = useRouter();
const loading = ref(false);
const sessions = ref<SupervisionRecord[]>([]);
const devices = ref<SupervisionRecord[]>([]);
const filter = ref("all");

const filters = [
  { key: "all", label: "全部" },
  { key: "collecting", label: "采集中" },
  { key: "awaiting_review", label: "待复核" },
  { key: "signed", label: "已确认" },
];

const visibleSessions = computed(() =>
  filter.value === "all"
    ? sessions.value
    : sessions.value.filter((session) => session.status === filter.value),
);

const metrics = computed(() => ({
  collecting: sessions.value.filter((item) => item.status === "collecting").length,
  review: sessions.value.filter((item) => item.status === "awaiting_review").length,
  signed: sessions.value.filter((item) => item.status === "signed").length,
  online: devices.value.filter((item) => item.data.online_status === "online").length,
}));

async function load() {
  loading.value = true;
  try {
    const [sessionResult, deviceResult] = await Promise.all([
      supervisionApi.list("inspection-sessions", { page: 1, size: 200 }),
      supervisionApi.list("devices", { page: 1, size: 200 }),
    ]);
    sessions.value = sessionResult.data.data.items;
    devices.value = deviceResult.data.data.items;
  } finally {
    loading.value = false;
  }
}

function modeLabel(mode?: string) {
  return { image: "图片", measurement: "测量", mixed: "混合" }[mode || ""] || "测量";
}

function openTask(session: SupervisionRecord) {
  router.push({
    path: `/app/tasks/${session.data.task_id}`,
    query: { session: session.id },
  });
}

function openSession(session: SupervisionRecord) {
  router.push({ path: "/app/inspection-sessions", query: { record: session.id } });
}

onMounted(load);
</script>

<template>
  <main class="laboratory-page" v-loading="loading">
    <SupervisionModuleHeader
      index="04"
      code="LAB"
      title="实验室检测"
      agent-name="实验室检测 Agent"
      tone="violet"
      description="在检测过程中持续校验设备与测量，分离设备可信状态和产品质量状态，并根据当前证据决定下一项检测、补测或停止。"
      principle="必检项强门禁 · 设备与产品双状态分离"
    >
      <template #actions>
        <el-button :icon="RefreshRight" type="primary" @click="load">刷新数据</el-button>
      </template>
    </SupervisionModuleHeader>

    <SupervisionAgentRail class="agent-navigation" />

    <section class="device-loop" aria-label="模型与设备闭环">
      <div><span>01</span><strong>设备采集</strong><small>接收测量与时序事件</small></div>
      <i>→</i>
      <div><span>02</span><strong>证据更新</strong><small>校验设备与产品状态</small></div>
      <i>→</i>
      <div><span>03</span><strong>主动选择</strong><small>决定下一检测或补测</small></div>
      <i>→</i>
      <div><span>04</span><strong>目标判断</strong><small>继续、停止或转人工</small></div>
    </section>

    <section class="metric-strip" aria-label="实验室检测概况">
      <div>
        <span>采集中</span><strong>{{ metrics.collecting }}</strong
        ><i class="tone-blue" />
      </div>
      <div>
        <span>待专家复核</span><strong>{{ metrics.review }}</strong
        ><i class="tone-amber" />
      </div>
      <div>
        <span>已确认结果</span><strong>{{ metrics.signed }}</strong
        ><i class="tone-green" />
      </div>
      <div>
        <span>在线设备</span><strong>{{ metrics.online }}</strong
        ><i class="tone-violet" />
      </div>
    </section>

    <section class="laboratory-board">
      <div class="board-heading">
        <div>
          <h2>检测批次</h2>
          <p>实验室检测 Agent 在每个批次内分析设备、测量、正常基线与补测需求。</p>
        </div>
        <div class="status-filter" role="tablist" aria-label="检测批次状态">
          <button
            v-for="item in filters"
            :key="item.key"
            type="button"
            :class="{ active: filter === item.key }"
            @click="filter = item.key"
          >
            {{ item.label }}
          </button>
        </div>
      </div>

      <div v-if="visibleSessions.length" class="session-list">
        <article v-for="session in visibleSessions" :key="session.id" class="session-row">
          <div class="session-identity">
            <span class="session-code">{{ session.code }}</span>
            <h3>{{ session.name }}</h3>
            <p>关联任务 {{ String(session.data.task_id).slice(-8) }}</p>
          </div>
          <dl>
            <div>
              <dt>输入方式</dt>
              <dd>{{ modeLabel(session.data.input_mode) }}</dd>
            </div>
            <div>
              <dt>样品</dt>
              <dd>{{ session.data.sample_ids?.length || 0 }}</dd>
            </div>
            <div>
              <dt>设备</dt>
              <dd>{{ session.data.device_ids?.length || 0 }}</dd>
            </div>
            <div>
              <dt>检测项目</dt>
              <dd>{{ session.data.test_items?.length || 0 }}</dd>
            </div>
          </dl>
          <div class="session-action">
            <el-tag effect="plain">{{ STATUS_LABELS[session.status] || session.status }}</el-tag>
            <div>
              <button type="button" @click="openSession(session)">批次详情</button>
              <button type="button" @click="openTask(session)">进入检测任务 <ArrowRight /></button>
            </div>
          </div>
        </article>
      </div>

      <div v-else class="empty-lab">
        <span>LAB</span>
        <div>
          <strong>当前状态下没有检测批次</strong>
          <p>抽查方案确认后会自动生成批次，也可以从任务管理发起独立检测。</p>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.laboratory-page {
  max-width: 1520px;
  margin: 0 auto;
  padding: 18px 18px 40px;
}

.agent-navigation {
  margin-top: 16px;
}

.device-loop {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr) auto);
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  padding: 16px 18px;
  border: 1px solid #e2dcf5;
  border-radius: 14px;
  background: linear-gradient(100deg, #f7f4ff, #fff 58%, #f2fbff);
}

.device-loop > div {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 3px 10px;
  min-width: 0;
}

.device-loop span {
  grid-row: 1 / span 2;
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 9px;
  background: #ece5ff;
  color: #6d4bc3;
  font:
    750 10px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.device-loop strong {
  color: #25364a;
  font-size: 13px;
}

.device-loop small {
  overflow: hidden;
  color: #7b8da0;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-loop > i {
  color: #8d79c9;
  font-style: normal;
}

.laboratory-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  padding: 28px 30px;
  border: 1px solid #deded9;
  border-radius: 16px;
  background: linear-gradient(115deg, rgba(15, 118, 110, 0.07), transparent 38%), #fff;
}

.eyebrow {
  margin: 0 0 9px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

h1 {
  margin: 0;
  font-size: 34px;
  letter-spacing: -0.035em;
}

.laboratory-header span,
.board-heading p,
.session-identity p,
.empty-lab p {
  color: #71717a;
  font-size: 13px;
}

.laboratory-header span {
  display: block;
  margin-top: 8px;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.header-actions :deep(.el-button) {
  min-height: 40px;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 18px 0;
  overflow: hidden;
  border: 1px solid #dce6f0;
  border-radius: 14px;
  background: #fff;
}

.metric-strip > div {
  position: relative;
  min-height: 100px;
  padding: 22px 24px;
}

.metric-strip > div + div {
  border-left: 1px solid #ecece8;
}

.metric-strip span,
.metric-strip strong {
  display: block;
}

.metric-strip span {
  color: #71717a;
  font-size: 12px;
}

.metric-strip strong {
  margin-top: 9px;
  font:
    700 30px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.metric-strip i {
  position: absolute;
  top: 24px;
  right: 22px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.tone-blue {
  background: #2563eb;
}
.tone-amber {
  background: #d97706;
}
.tone-green {
  background: #0f766e;
}
.tone-violet {
  background: #7c3aed;
}

.laboratory-board {
  overflow: hidden;
  border: 1px solid #dce6f0;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(16, 42, 67, 0.05);
}

.board-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px 20px;
  border-bottom: 1px solid #ecece8;
}

.board-heading h2 {
  margin: 0 0 5px;
  font-size: 22px;
}

.board-heading p,
.empty-lab p,
.session-identity p {
  margin: 0;
}

.status-filter {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: #f4f4f2;
}

.status-filter button {
  min-height: 34px;
  padding: 0 13px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #71717a;
  cursor: pointer;
}

.status-filter button.active {
  background: #111214;
  color: #fff;
}

.session-list {
  padding: 0 24px;
}

.session-row {
  display: grid;
  grid-template-columns: minmax(220px, 1.1fr) minmax(360px, 1.4fr) minmax(170px, 0.6fr);
  align-items: center;
  gap: 28px;
  padding: 22px 2px;
}

.session-row + .session-row {
  border-top: 1px solid #ecece8;
}

.session-code {
  color: #0f766e;
  font:
    700 11px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.session-identity h3 {
  margin: 7px 0 5px;
  font-size: 16px;
}

.session-row dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
}

.session-row dl div {
  padding: 4px 14px;
  border-left: 1px solid #ecece8;
}

.session-row dt {
  color: #a1a1aa;
  font-size: 11px;
}

.session-row dd {
  margin: 6px 0 0;
  font:
    650 16px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.session-action {
  display: flex;
  align-items: flex-end;
  flex-direction: column;
  gap: 12px;
}

.session-action button {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: #111214;
  font-weight: 700;
  cursor: pointer;
}

.session-action > div {
  display: flex;
  align-items: center;
  gap: 16px;
}

.session-action svg {
  width: 15px;
}

.empty-lab {
  display: flex;
  align-items: center;
  gap: 18px;
  min-height: 150px;
  padding: 30px;
}

.empty-lab > span {
  display: grid;
  width: 58px;
  height: 58px;
  place-items: center;
  border-radius: 12px;
  background: #e8f7f3;
  color: #0f766e;
  font:
    800 12px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.empty-lab strong {
  display: block;
  margin-bottom: 6px;
}

@media (max-width: 960px) {
  .device-loop {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .device-loop > i {
    display: none;
  }
  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .metric-strip > div:nth-child(3) {
    border-top: 1px solid #ecece8;
    border-left: 0;
  }
  .metric-strip > div:nth-child(4) {
    border-top: 1px solid #ecece8;
  }
  .session-row {
    grid-template-columns: 1fr;
    gap: 16px;
  }
  .session-action {
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .laboratory-page {
    padding: 4px 0 28px;
  }
  .device-loop {
    grid-template-columns: 1fr;
  }
  .laboratory-header,
  .board-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .header-actions {
    width: 100%;
  }
  .header-actions :deep(.el-button) {
    flex: 1;
    min-height: 44px;
  }
  .metric-strip > div {
    padding: 18px;
  }
  .status-filter {
    width: 100%;
    overflow-x: auto;
  }
  .session-list {
    padding: 0 16px;
  }
  .session-row dl {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .session-row dl div:nth-child(3) {
    margin-top: 12px;
  }
}
</style>
