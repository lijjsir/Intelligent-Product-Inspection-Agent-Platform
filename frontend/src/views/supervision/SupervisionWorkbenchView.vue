<script setup lang="ts">
import { computed,onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, Plus, RefreshRight } from "@element-plus/icons-vue";
import BusinessTodoPanel from "@/components/business/supervision/BusinessTodoPanel.vue";
import { supervisionApi } from "@/api/supervision.api";
import { qualityRiskApi } from "@/api/quality-risk.api";
import DemoWalkthrough from '@/components/business/supervision/DemoWalkthrough.vue';
import { useRuntimeContext } from '@/composables/useRuntimeContext';
import { useAuthStore } from '@/stores/auth.store';

const router = useRouter();
const runtime=useRuntimeContext(),auth=useAuthStore();
const demoExpert=computed(()=>runtime.context.value?.execution_mode==='demo'&&auth.primaryRole==='expert'&&auth.hasPermission('quality_material_read_business'));
function showDemo(){document.getElementById('demo-case-guide')?.scrollIntoView({block:'start'});}
const loading = ref(false);
const labEnabled = ref<boolean | null>(null);
const loadFailures = ref<string[]>([]);
const stats = reactive<{ todos: number | null; sources: number | null; cases: number | null; plans: number | null }>({ todos: null, sources: null, cases: null, plans: null });

const agents = [
  {
    order: "01",
    code: "MKT",
    name: "市场监控 Agent",
    action: "持续发现变化",
    description: "分析企业、产品、地区、市场分布与抽查覆盖，识别优先关注对象",
    path: "/app/quality-analytics",
    color: "#0b63ce",
  },
  {
    order: "02",
    code: "VOC",
    name: "舆情监测 Agent",
    action: "核实风险线索",
    description: "从投诉、舆情、图片与附件中分离事实、情绪、推测和证据缺口",
    path: "/app/risk-cases",
    color: "#087f8c",
  },
  {
    order: "03",
    code: "SAM",
    name: "监督抽查 Agent",
    action: "生成抽查方案",
    description: "结合确认风险、产品覆盖和资源约束安排抽查",
    path: "/app/sampling-plans",
    color: "#c96a0a",
  },
  {
    order: "04",
    code: "LAB",
    name: "实验室检测 Agent",
    action: "设备闭环取证",
    description: "仅在抽查需要实物验证时校验设备与测量，提出下一检测、补测或停止建议",
    path: "/app/laboratory",
    color: "#6d4bc3",
  },
];

const capabilities = [
  { code: "PERCEIVE", title: "风险感知", description: "从市场与舆情中发现问题", color: "#0b63ce" },
  { code: "REASON", title: "可信推理", description: "基于证据、标准和边界判断", color: "#087f8c" },
  { code: "DECIDE", title: "动态决策", description: "制定抽查与下一步检测策略", color: "#c96a0a" },
  {
    code: "COLLAB",
    title: "协同应用",
    description: "连接人员、Agent 与设备执行",
    color: "#6d4bc3",
  },
];

async function loadOverview() {
  if (loading.value) return;
  loading.value = true;
  const results = await Promise.allSettled([
    supervisionApi.todos(),
    qualityRiskApi.records({ page: 1, size: 1 }),
    qualityRiskApi.riskCases({ page: 1, size: 1 }),
    supervisionApi.list("sampling-plans", { page: 1, size: 1 }),
    supervisionApi.settings(),
  ]);
  const [todos, sources, cases, plans, settings] = results;
  stats.todos = todos.status === "fulfilled" ? todos.value.data.data.length : null;
  stats.sources = sources.status === "fulfilled" ? sources.value.data.data.total : null;
  stats.cases = cases.status === "fulfilled" ? cases.value.data.data.total : null;
  stats.plans = plans.status === "fulfilled" ? plans.value.data.data.total : null;
  labEnabled.value = settings.status === "fulfilled" ? settings.value.data.data.laboratory_validation_enabled : null;
  const labels = ["待办", "原始资料", "风险线索", "抽查方案", "实验室状态"];
  loadFailures.value = results.flatMap((result, index) => result.status === "rejected" ? [labels[index]] : []);
  loading.value = false;
}

onMounted(()=>{void runtime.load();void loadOverview();});
</script>

<template>
  <main class="quality-desk" :class="{'demo-desk':demoExpert}">
    <section class="desk-hero">
      <div class="hero-copy">
        <div class="hero-kicker"><span /> QUALITY SUPERVISION</div>
        <h1 v-if="demoExpert">质量风险分析演示<br /><em>从来源资料，走到研判与报告</em></h1>
        <h1 v-else>让每一次监管判断<br /><em>都有证据、有边界、可执行</em></h1>
        <p v-if="demoExpert">使用同一模拟案例查看数据接入、异常发现、风险研判、协同复核、抽查建议和报告。实验室验证可按证据需要选择。</p>
        <p v-else>
          市场监控、舆情监测、监督抽查和实验室检测共享质量知识与可信能力，在统一风险决策中心形成闭环。
        </p>
        <div class="hero-actions">
          <el-button v-if="demoExpert" type="primary" @click="showDemo">从案例导览开始</el-button>
          <el-button v-else type="primary" :icon="Plus" @click="router.push('/app/quality-data')">
            接入质量数据
          </el-button>
          <el-button @click="router.push('/app/risk-assessments')">进入风险研判</el-button>
        </div>
      </div>

      <div class="hero-status" v-loading="loading">
        <div class="status-heading">
          <span>当前组织</span>
          <button type="button" aria-label="刷新工作台数据" @click="loadOverview">
            <RefreshRight />
          </button>
        </div>
        <div class="metric-grid">
          <div>
            <strong>{{ stats.todos ?? '—' }}</strong
            ><span>待我处理</span>
          </div>
          <div>
            <strong>{{ stats.sources ?? '—' }}</strong
            ><span>原始资料</span>
          </div>
          <div>
            <strong>{{ stats.cases ?? '—' }}</strong
            ><span>风险线索</span>
          </div>
          <div>
            <strong>{{ stats.plans ?? '—' }}</strong
            ><span>抽查方案</span>
          </div>
        </div>
      </div>
    </section>

    <el-alert v-if="loadFailures.length" class="overview-error" type="warning" :closable="false" :title="`${loadFailures.join('、')}未能加载，请刷新重试。`" />
    <DemoWalkthrough v-if="demoExpert" id="demo-case-guide" />

    <section v-if="!demoExpert" class="capability-band" aria-label="质监大模型核心能力">
      <article
        v-for="item in capabilities"
        :key="item.code"
        :style="{ '--capability-color': item.color }"
      >
        <span>{{ item.code }}</span>
        <strong>{{ item.title }}</strong>
        <p>{{ item.description }}</p>
      </article>
    </section>

    <section v-if="!demoExpert" class="workflow-section" aria-labelledby="agent-flow-title">
      <header class="section-heading">
        <div>
          <span>闭环协作链</span>
          <h2 id="agent-flow-title">四个业务 Agent，协同完成监管闭环</h2>
        </div>
        <p>风险判断、证据约束和人工复核是共用机制，不再额外设置第五个 Agent。</p>
      </header>

      <ol class="agent-line">
        <li v-for="agent in agents" :key="agent.code" :style="{ '--agent-color': agent.color }">
          <router-link
            :to="agent.code === 'LAB' && !labEnabled ? '/app/workbench' : agent.path"
            class="agent-step"
            :class="{ disabled: agent.code === 'LAB' && !labEnabled }"
            :aria-disabled="agent.code === 'LAB' && !labEnabled"
          >
            <div class="step-rail">
              <span>{{ agent.order }}</span>
            </div>
            <div class="step-body">
              <div class="step-meta">
                <span>{{ agent.code }}</span
                ><b>{{ agent.action }}</b>
              </div>
              <h3>{{ agent.name }}</h3>
              <p>{{ agent.description }}</p>
              <span class="step-link">{{ agent.code === 'LAB' && labEnabled === null ? '实验室状态暂不可用' : agent.code === 'LAB' && !labEnabled ? '抽查需要实物验证时启用' : '进入对应模块' }} <ArrowRight v-if="agent.code !== 'LAB' || labEnabled" /></span>
            </div>
          </router-link>
        </li>
      </ol>
    </section>

    <BusinessTodoPanel />
  </main>
</template>

<style scoped>
.quality-desk {
  --desk-ink: #102a43;
  max-width: 1540px;
  margin: 0 auto;
  padding: 14px 16px 36px;
  color: var(--desk-ink);
}

.overview-error {
  margin-top: 16px;
}
.demo-desk .desk-hero{background:#0b416b;box-shadow:0 16px 36px rgba(7,65,124,.12);}
.demo-desk .hero-kicker{color:#c8e3f0;}

.desk-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.55fr);
  min-height: 310px;
  overflow: hidden;
  border: 1px solid #0a4f99;
  border-radius: 20px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.055) 1px, transparent 1px),
    radial-gradient(circle at 78% 18%, rgba(29, 180, 203, 0.34), transparent 27%),
    linear-gradient(125deg, #062f61 0%, #075aa8 58%, #087f8c 100%);
  background-size: 34px 34px;
  color: #fff;
  box-shadow: 0 22px 60px rgba(7, 65, 124, 0.2);
}

.desk-hero::after {
  position: absolute;
  right: 25%;
  bottom: -210px;
  width: 420px;
  height: 420px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 50%;
  content: "";
}

.hero-copy {
  z-index: 1;
  padding: 38px 44px 34px;
}

.hero-kicker {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
  color: #b5b7bc;
  font:
    700 11px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
  letter-spacing: 0.16em;
}

.hero-kicker span {
  width: 30px;
  height: 2px;
  background: #5eead4;
}

.hero-copy h1 {
  max-width: 760px;
  margin: 0;
  font-size: clamp(34px, 4vw, 58px);
  font-weight: 760;
  letter-spacing: -0.045em;
  line-height: 1.08;
}

.hero-copy h1 em {
  color: #bdefff;
  font-style: normal;
}

.hero-copy > p {
  max-width: 690px;
  margin: 20px 0 0;
  color: #c8c9cd;
  font-size: 15px;
  line-height: 1.75;
}

.hero-actions {
  display: flex;
  gap: 10px;
  margin-top: 28px;
}

.hero-actions :deep(.el-button) {
  min-height: 42px;
  border-color: rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
}

.hero-actions :deep(.el-button--primary) {
  border-color: #fff;
  background: #fff;
  color: #074f93;
}

.hero-status {
  z-index: 1;
  align-self: stretch;
  margin: 18px;
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.09);
  backdrop-filter: blur(8px);
}

.capability-band {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  margin-top: 18px;
  border: 1px solid #d6e4f1;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(16, 42, 67, 0.05);
}

.capability-band article {
  position: relative;
  min-height: 112px;
  padding: 20px 22px;
}

.capability-band article + article {
  border-left: 1px solid #e3edf6;
}

.capability-band article::after {
  position: absolute;
  right: 22px;
  bottom: 0;
  left: 22px;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: var(--capability-color);
  content: "";
}

.capability-band span,
.capability-band strong {
  display: block;
}

.capability-band span {
  color: var(--capability-color);
  font:
    700 10px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
  letter-spacing: 0.12em;
}

.capability-band strong {
  margin-top: 10px;
  color: #102a43;
  font-size: 17px;
}

.capability-band p {
  margin: 7px 0 0;
  color: #71869b;
  font-size: 12px;
  line-height: 1.55;
}

.status-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #c8c9cd;
  font-size: 13px;
}

.status-heading button {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: transparent;
  color: #fff;
  cursor: pointer;
}

.status-heading svg {
  width: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 22px;
}

.metric-grid div {
  min-height: 88px;
  padding: 14px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}

.metric-grid div:nth-child(odd) {
  border-right: 1px solid rgba(255, 255, 255, 0.12);
}

.metric-grid strong,
.metric-grid span {
  display: block;
}

.metric-grid strong {
  font:
    650 30px/1.1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.metric-grid span {
  margin-top: 8px;
  color: #aaacb2;
  font-size: 12px;
}

.workflow-section {
  margin: 28px 0 20px;
  padding: 26px;
  border: 1px solid #d6e4f1;
  border-radius: 16px;
  background: linear-gradient(180deg, #fff, #fbfdff);
  box-shadow: 0 10px 30px rgba(16, 42, 67, 0.05);
}

.section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  margin-bottom: 22px;
}

.section-heading span {
  color: #71717a;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.section-heading h2 {
  margin: 5px 0 0;
  font-size: 24px;
  letter-spacing: -0.025em;
}

.section-heading p {
  max-width: 520px;
  color: #71717a;
  font-size: 13px;
  line-height: 1.6;
  text-align: right;
}

.agent-line {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  padding: 0;
  list-style: none;
}

.agent-line li + li {
  border-left: 1px solid #e4e4e0;
}

.agent-step {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  min-height: 190px;
  color: inherit;
  text-decoration: none;
}

.step-rail {
  position: relative;
  padding-top: 2px;
  color: var(--agent-color);
  font:
    700 11px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.step-rail::after {
  position: absolute;
  top: 30px;
  bottom: 10px;
  left: 3px;
  width: 3px;
  border-radius: 3px;
  background: var(--agent-color);
  content: "";
  opacity: 0.8;
}

.step-body {
  padding: 0 18px 0 4px;
}

.step-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #71717a;
  font-size: 11px;
}

.step-meta span {
  padding: 3px 6px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--agent-color) 10%, white);
  color: var(--agent-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.step-meta b {
  font-weight: 600;
}

.step-body h3 {
  margin: 14px 0 8px;
  font-size: 17px;
}

.step-body p {
  min-height: 62px;
  margin: 0;
  color: #68686f;
  font-size: 13px;
  line-height: 1.65;
}

.step-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  color: #27272a;
  font-size: 12px;
  font-weight: 700;
}
.agent-step.disabled {
  cursor: default;
  opacity: 0.72;
}

.step-link svg {
  width: 14px;
  transition: transform 180ms ease;
}

.agent-step:hover .step-link svg,
.agent-step:focus-visible .step-link svg {
  transform: translateX(4px);
}

.agent-step:focus-visible {
  outline: 2px solid var(--agent-color);
  outline-offset: 4px;
}

@media (max-width: 1080px) {
  .desk-hero {
    grid-template-columns: 1fr;
  }
  .hero-status {
    margin-top: 0;
  }
  .agent-line {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 22px 0;
  }
  .capability-band {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .capability-band article:nth-child(3) {
    border-top: 1px solid #e3edf6;
    border-left: 0;
  }
  .capability-band article:nth-child(4) {
    border-top: 1px solid #e3edf6;
  }
  .agent-line li:nth-child(3) {
    border-left: 0;
  }
}

@media (max-width: 640px) {
  .quality-desk {
    padding: 4px 0 24px;
  }
  .desk-hero {
    border-radius: 14px;
  }
  .hero-copy {
    padding: 28px 22px 24px;
  }
  .hero-copy h1 {
    font-size: 34px;
  }
  .hero-actions {
    align-items: stretch;
    flex-direction: column;
  }
  .hero-status {
    margin: 0 12px 12px;
  }
  .workflow-section {
    padding: 20px 16px;
  }
  .capability-band {
    grid-template-columns: 1fr;
  }
  .capability-band article + article,
  .capability-band article:nth-child(4) {
    border-top: 1px solid #e3edf6;
    border-left: 0;
  }
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
  .section-heading p {
    text-align: left;
  }
  .agent-line {
    grid-template-columns: 1fr;
  }
  .agent-line li + li,
  .agent-line li:nth-child(3) {
    padding-top: 18px;
    border-top: 1px solid #e4e4e0;
    border-left: 0;
  }
  .agent-step {
    min-height: 158px;
  }
  .step-body p {
    min-height: 0;
  }
}
</style>
