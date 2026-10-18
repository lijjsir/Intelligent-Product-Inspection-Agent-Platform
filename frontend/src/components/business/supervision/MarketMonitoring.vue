<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { marketApi } from "@/api/market-monitoring.api";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { extractApiErrorMessage } from "@/api/http";
import type { IntakeReferenceOptions, RiskCaseV4 } from "@/types/quality-risk.types";
import type {
  MarketCoverage,
  MarketFocus,
  MarketGroup,
  MarketKind,
  MarketObjectType,
  MarketReport,
  MarketSignalDetail,
  MarketStatus,
} from "@/types/market-monitoring.types";

const route = useRoute(),
  router = useRouter();
const report = ref<MarketReport | null>(null),
  error = ref(""),
  loading = ref(false);
const tab = ref(
  ["overview", "anomalies", "focus"].includes(String(route.query.tab))
    ? String(route.query.tab)
    : "overview",
);
const objectType = ref<MarketObjectType>(
  route.query.object_type === "enterprise" ? "enterprise" : "product",
);
const asOf = ref(String(route.query.as_of || "")),
  statusFilter = ref("all");
const kindLabels: Record<MarketKind, string> = {
  consumer_complaint: "投诉",
  public_opinion: "舆情",
};
const statusLabels: Record<MarketStatus, string> = {
  normal: "未触发规则",
  insufficient_coverage: "无法比较",
  quantity_growth: "数量增长线索",
  new_cluster: "新增集中线索",
};
const groups = computed(
  () =>
    report.value?.groups.filter(
      (g) =>
        statusFilter.value === "all" ||
        (statusFilter.value === "signals" ? !!g.signal_id : g.status === statusFilter.value),
    ) || [],
);
const signalCount = computed(() => report.value?.groups.filter((g) => !!g.signal_id).length || 0);
const maxDaily = computed(() =>
  Math.max(
    1,
    ...(report.value?.daily.flatMap((d) => [d.consumer_complaint, d.public_opinion]) || []),
  ),
);
const focus = ref<MarketFocus[]>([]),
  focusDialog = ref(false),
  focusSaving = ref(false),
  focusError = ref("");
const options = ref<IntakeReferenceOptions>({ products: [], enterprises: [], categories: [] });
const focusForm = reactive({
  object_type: "product" as MarketObjectType,
  object_id: "",
  reason: "",
});
const focusOptions = computed(() =>
  focusForm.object_type === "product" ? options.value.products : options.value.enterprises,
);
const detail = ref<MarketSignalDetail | null>(null),
  drawer = ref(false),
  detailLoading = ref(false),
  detailError = ref("");
const converting = ref(false),
  convertDialog = ref(false),
  targetId = ref("__new__"),
  caseOptions = ref<RiskCaseV4[]>([]);
const configOpen = ref(false),
  configSaving = ref(false),
  configError = ref(""),
  coverageRows = ref<MarketCoverage[]>([]);
const ruleForm = reactive({
  min_current: 3,
  min_increase: 3,
  growth_factor: 2,
  expected_version: 1,
  reason: "",
});
const coverageForm = reactive({ key: "", start: "", end: "", reason: "" });
let epoch = 0,
  detailEpoch = 0;
function day(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
function explanation(g: MarketGroup) {
  if (g.status === "insufficient_coverage")
    return `来源覆盖不足：${g.uncovered_sources.join("、")}。不能将缺少记录视为零。`;
  return (
    `上期 ${g.previous_count} 条 → 本期 ${g.current_count} 条，增加 ${g.current_count - g.previous_count} 条` +
    (g.growth_percent === null
      ? "；上期为零，不计算增长百分比。"
      : `（${g.growth_percent.toFixed(0)}%）。`)
  );
}
function raw(id: string) {
  void router.push({ path: "/app/quality-data", query: { record: id } });
}
function openCase(id: string) {
  void router.push({ path: "/app/risk-assessments", query: { case_id: id } });
}
async function syncQuery() {
  await router.replace({
    query: {
      ...route.query,
      tab: tab.value,
      object_type: objectType.value,
      as_of: asOf.value || undefined,
    },
  });
}
async function load() {
  const current = ++epoch;
  loading.value = true;
  error.value = "";
  try {
    const [result, focuses] = await Promise.all([
      marketApi.scan({ as_of: asOf.value || undefined, object_type: objectType.value }),
      marketApi.focuses(),
    ]);
    if (current !== epoch) return;
    report.value = result.data.data;
    if (!asOf.value) asOf.value = report.value.as_of;
    focus.value = focuses.data.data;
    await syncQuery();
  } catch (e) {
    if (current === epoch) {
      report.value = null;
      error.value = extractApiErrorMessage(e);
    }
  } finally {
    if (current === epoch) loading.value = false;
  }
}
async function showSignal(id: string) {
  const current = ++detailEpoch;
  drawer.value = true;
  detail.value = null;
  detailError.value = "";
  detailLoading.value = true;
  try {
    const result = await marketApi.signal(id);
    if (current === detailEpoch) detail.value = result.data.data;
  } catch (e) {
    if (current === detailEpoch) detailError.value = extractApiErrorMessage(e);
  } finally {
    if (current === detailEpoch) detailLoading.value = false;
  }
}
function selectSignal(id: string) {
  if (route.query.signal === id) void showSignal(id);
  else void router.replace({ query: { ...route.query, signal: id } });
}
function closeDetail() {
  ++detailEpoch;
  if (route.query.signal) {
    const q = { ...route.query };
    delete q.signal;
    void router.replace({ query: q });
  }
}
async function prepareConversion() {
  if (!detail.value) return;
  detailError.value = "";
  try {
    const result = await qualityRiskApi.riskCases({ page: 1, size: 100 });
    const s = detail.value.snapshot;
    caseOptions.value = result.data.data.items.filter(
      (c) => c.scope[`${s.object_type}_id`] === s.object_id,
    );
    targetId.value = "__new__";
    convertDialog.value = true;
  } catch (e) {
    detailError.value = extractApiErrorMessage(e);
  }
}
async function convert() {
  if (!detail.value) return;
  converting.value = true;
  detailError.value = "";
  try {
    const result = (
      await marketApi.convert(
        detail.value.id,
        targetId.value === "__new__" ? undefined : targetId.value,
      )
    ).data.data;
    convertDialog.value = false;
    ElMessage.success(result.reused ? "已返回原研判事项" : "已关联原始资料，可继续研判");
    openCase(result.case.id);
  } catch (e) {
    detailError.value = extractApiErrorMessage(e);
    convertDialog.value = false;
  } finally {
    converting.value = false;
  }
}
async function searchObjects(keyword = "") {
  try {
    options.value = (await qualityRiskApi.intakeReferences(keyword)).data.data;
  } catch (e) {
    focusError.value = extractApiErrorMessage(e);
  }
}
async function addFocus(group?: MarketGroup) {
  focusError.value = "";
  focusForm.object_type = group?.object_type || objectType.value;
  focusForm.object_id = group?.object_id || "";
  focusForm.reason = "";
  await searchObjects(group?.object_name || "");
  focusDialog.value = true;
}
async function saveFocus() {
  if (!focusForm.object_id || !focusForm.reason.trim()) {
    focusError.value = "请选择已确认对象并填写关注依据";
    return;
  }
  focusSaving.value = true;
  focusError.value = "";
  try {
    const r = (await marketApi.addFocus(focusForm)).data.data;
    focus.value = (await marketApi.focuses()).data.data;
    focusDialog.value = false;
    ElMessage.success(r.reused ? "对象已在关注列表中" : "已加入重点对象");
  } catch (e) {
    focusError.value = extractApiErrorMessage(e);
  } finally {
    focusSaving.value = false;
  }
}
async function removeFocus(item: MarketFocus) {
  try {
    const result = await ElMessageBox.prompt("填写取消关注的依据，历史记录会保留。", "取消关注", {
      inputValidator: (value) => !!value?.trim() || "请填写依据",
      inputPlaceholder: "取消关注依据",
    });
    await marketApi.removeFocus(item.id, result.value);
    focus.value = (await marketApi.focuses()).data.data;
  } catch (e) {
    if (e !== "cancel" && e !== "close") error.value = extractApiErrorMessage(e);
  }
}
async function openConfig() {
  if (!report.value) return;
  configOpen.value = true;
  configError.value = "";
  const r = report.value.rule;
  Object.assign(ruleForm, {
    min_current: r.min_current,
    min_increase: r.min_increase,
    growth_factor: r.growth_factor,
    expected_version: r.version,
    reason: "",
  });
  coverageForm.key = "";
  coverageForm.reason = "";
  try {
    coverageRows.value = (await marketApi.coverage()).data.data;
  } catch (e) {
    configError.value = extractApiErrorMessage(e);
  }
}
async function saveRule() {
  if (!ruleForm.reason.trim()) {
    configError.value = "请填写规则调整依据";
    return;
  }
  configSaving.value = true;
  configError.value = "";
  try {
    await marketApi.rule(ruleForm);
    configOpen.value = false;
    await load();
  } catch (e) {
    configError.value = extractApiErrorMessage(e);
  } finally {
    configSaving.value = false;
  }
}
function toLocalInput(value: string) {
  return new Date(new Date(value).getTime() + 8 * 3600000).toISOString().slice(0, 16);
}
function chooseCoverage(key: string) {
  const c = coverageRows.value[Number(key)]?.coverage;
  coverageForm.start = c?.start_at ? toLocalInput(c.start_at) : "";
  coverageForm.end = c?.end_at ? toLocalInput(c.end_at) : "";
}
async function saveCoverage() {
  const item = coverageRows.value[Number(coverageForm.key)];
  if (
    !item ||
    coverageForm.key === "" ||
    !coverageForm.start ||
    !coverageForm.end ||
    !coverageForm.reason.trim()
  ) {
    configError.value = "请选择来源、完整起止时间并填写核对依据";
    return;
  }
  configSaving.value = true;
  configError.value = "";
  try {
    await marketApi.setCoverage({
      source_id: item.source_id,
      record_type: item.record_type,
      start_at: coverageForm.start + ":00+08:00",
      end_at: coverageForm.end + ":00+08:00",
      reason: coverageForm.reason,
    });
    configOpen.value = false;
    await load();
  } catch (e) {
    configError.value = extractApiErrorMessage(e);
  } finally {
    configSaving.value = false;
  }
}
watch(tab, () => void syncQuery());
watch(
  () => route.query.signal,
  (id) => {
    if (id) void showSignal(String(id));
    else drawer.value = false;
  },
);
onMounted(async () => {
  await load();
  if (route.query.signal) await showSignal(String(route.query.signal));
});
</script>

<template>
  <section class="market-monitor">
    <header class="market-header">
      <div>
        <p class="eyebrow">质量监督 / 持续观察</p>
        <h1>市场监控</h1>
        <p>从接入资料发现数量变化，将值得核查的线索交给研判。</p>
      </div>
      <el-button :disabled="!report" @click="openConfig">规则与覆盖</el-button>
    </header>
    <form class="monitor-toolbar" @submit.prevent="load">
      <label
        >观察对象<el-select v-model="objectType" aria-label="观察对象" style="width: 140px"
          ><el-option label="产品" value="product" /><el-option
            label="企业"
            value="enterprise" /></el-select
      ></label>
      <label
        >截止日（北京时间）<el-input
          v-model="asOf"
          type="date"
          aria-label="统计截止日"
          style="width: 175px"
      /></label>
      <el-button type="primary" native-type="submit" :loading="loading">刷新监测</el-button
      ><span class="toolbar-note">截止日当天不计入；留空使用今天</span>
    </form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="spaced" />
    <el-alert v-if="report?.demo_anchor_as_of" type="info" :closable="false" :title="`演示数据固定统计日期为 ${report.demo_anchor_as_of}，当前截止日为 ${report.as_of}。这些是模拟数据，不代表今日实时市场。`" />
    <el-skeleton v-if="loading && !report" :rows="6" animated />
    <template v-if="report">
      <div class="window-strip">
        <span
          ><b>上期</b> {{ day(report.windows.previous_start) }} —
          {{ day(report.windows.current_start) }} 前</span
        ><span
          ><b>本期</b> {{ day(report.windows.current_start) }} —
          {{ day(report.windows.end) }} 前</span
        ><el-tag v-if="report.execution_mode === 'demo'" type="warning"
          >演示 · 全部为模拟资料</el-tag
        >
      </div>
      <el-tabs v-model="tab" class="market-tabs">
        <el-tab-pane label="市场概览" name="overview">
          <div class="overview-metrics">
            <article v-for="kind in ['consumer_complaint', 'public_opinion'] as const" :key="kind">
              <span>{{ kindLabels[kind] }}资料 · 本期</span
              ><strong>{{ report.totals[kind].current }}<small>条</small></strong>
              <p>上期 {{ report.totals[kind].previous }} 条 · 按发生时间统计</p>
            </article>
            <article class="signal-metric">
              <span>待核查数量线索</span><strong>{{ signalCount }}<small>条</small></strong
              ><el-button
                link
                type="primary"
                @click="
                  tab = 'anomalies';
                  statusFilter = 'signals';
                "
                >查看异常监测 →</el-button
              >
            </article>
          </div>
          <section class="monitor-panel">
            <div class="section-title">
              <h2>接入资料变化</h2>
              <span>投诉与舆情分别计数，不代表市场发生率</span>
            </div>
            <div class="trend-legend"><span>■ 投诉</span><span>▤ 舆情</span></div>
            <div
              class="daily-chart"
              role="img"
              aria-label="十四个完整日的投诉与舆情数量，详细数据见下方表格"
            >
              <div
                v-for="(d, i) in report.daily"
                :key="d.day"
                class="daily-column"
                :class="{ 'period-divider': i === 7 }"
              >
                <div class="bars">
                  <i :style="{ height: `${(d.consumer_complaint / maxDaily) * 100}%` }" /><i
                    :style="{ height: `${(d.public_opinion / maxDaily) * 100}%` }"
                  />
                </div>
                <span>{{ d.day.slice(5) }}</span>
              </div>
            </div>
            <details class="trend-data">
              <summary>查看每日数量明细</summary>
              <table>
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>投诉</th>
                    <th>舆情</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="d in report.daily" :key="d.day">
                    <td>{{ d.day }}</td>
                    <td>{{ d.consumer_complaint }}</td>
                    <td>{{ d.public_opinion }}</td>
                  </tr>
                </tbody>
              </table>
            </details>
          </section>
          <section class="monitor-panel data-quality">
            <h2>资料整理</h2>
            <p>缺少时间的资料不参加窗口比较；对象未确认的资料不归入企业或产品线索。</p>
            <details
              v-for="entry in [
                { title: '缺少发生时间', rows: report.missing_time },
                { title: '对象待确认', rows: report.pending_objects },
                { title: '来源已停用或撤回', rows: report.unavailable_sources },
              ]"
              :key="entry.title"
            >
              <summary>
                {{ entry.title }} <b>{{ entry.rows.length }}</b>
              </summary>
              <p v-if="!entry.rows.length">暂无待整理资料</p>
              <div v-for="r in entry.rows" :key="r.id" class="source-row">
                <span>{{ kindLabels[r.record_type] }} · {{ r.text }}</span
                ><el-button link type="primary" @click="raw(r.id)">整理原始资料</el-button>
              </div>
            </details>
          </section>
        </el-tab-pane>
        <el-tab-pane label="异常监测" name="anomalies">
          <div class="rule-note">
            <b>数量规则 v{{ report.rule.version }}</b
            ><span
              >本期 ≥ {{ report.rule.min_current }} 条、至少增加
              {{ report.rule.min_increase }} 条、达到上期
              {{ report.rule.growth_factor }} 倍。上期为零时不计算增长百分比。</span
            >
          </div>
          <div class="list-toolbar">
            <h2>按{{ objectType === "product" ? "产品" : "企业" }}观察</h2>
            <el-select v-model="statusFilter" aria-label="线索状态" style="width: 180px"
              ><el-option label="全部观察结果" value="all" /><el-option
                label="仅数量线索"
                value="signals" /><el-option
                label="无法比较"
                value="insufficient_coverage" /><el-option label="未触发规则" value="normal"
            /></el-select>
          </div>
          <el-empty v-if="!groups.length" description="当前窗口没有符合筛选条件的观察结果" />
          <article
            v-for="g in groups"
            :key="g.object_id + g.record_type"
            class="signal-card"
            :class="{ flagged: g.signal_id }"
          >
            <div class="signal-heading">
              <div>
                <el-tag size="small" effect="plain">{{ kindLabels[g.record_type] }}</el-tag>
                <h3>{{ g.object_name }}</h3>
              </div>
              <el-tag
                :type="
                  g.status === 'insufficient_coverage'
                    ? 'info'
                    : g.signal_id
                      ? 'warning'
                      : 'success'
                "
                >{{ statusLabels[g.status] }}</el-tag
              >
            </div>
            <div class="signal-body">
              <div class="count-pair">
                <span
                  >上期 <b>{{ g.previous_count }}</b></span
                ><span aria-hidden="true">→</span
                ><span
                  >本期 <b>{{ g.current_count }}</b></span
                >
              </div>
              <p>{{ explanation(g) }}</p>
            </div>
            <footer>
              <span
                >{{ g.source_record_ids.length }} 条原始资料 ·
                {{ g.signal_id ? "规则线索，尚需研判" : "按来源覆盖与数量规则判断" }}</span
              >
              <div>
                <el-button @click="addFocus(g)">关注对象</el-button
                ><el-button
                  v-if="g.signal_id"
                  type="primary"
                  plain
                  @click="selectSignal(g.signal_id)"
                  >查看线索依据</el-button
                >
              </div>
            </footer>
          </article>
        </el-tab-pane>
        <el-tab-pane label="重点对象" name="focus">
          <div class="list-toolbar">
            <div>
              <h2>持续关注的企业与产品</h2>
              <p>供本单位持续观察，不直接进入抽查候选。</p>
            </div>
            <el-button type="primary" @click="addFocus()">添加重点对象</el-button>
          </div>
          <el-empty
            v-if="!focus.length"
            description="尚未添加重点对象，可从异常监测加入或选择已有档案"
          />
          <article v-for="item in focus" :key="item.id" class="focus-card">
            <div>
              <el-tag effect="plain">{{ item.object_type === "product" ? "产品" : "企业" }}</el-tag>
              <h3>{{ item.object_name }}</h3>
              <el-tag v-if="!item.available" type="info">档案已停用</el-tag>
              <p>{{ item.reason }}</p>
              <small>{{ day(item.at) }} 加入关注</small>
            </div>
            <div>
              <el-button
                v-if="item.available"
                @click="
                  router.push({
                    path: '/app/quality-data',
                    query: { [item.object_type + '_id']: item.object_id },
                  })
                "
                >查看关联资料</el-button
              ><el-button @click="removeFocus(item)">取消关注</el-button>
            </div>
          </article>
        </el-tab-pane>
      </el-tabs>
      <p class="monitor-footnote">
        {{ report.notice }} 仅比较已接入来源的记录数量，资料覆盖声明不代表整个市场覆盖。
      </p>
    </template>
    <el-drawer v-model="drawer" title="数量线索依据" size="min(760px, 100%)" @closed="closeDetail">
      <el-skeleton v-if="detailLoading" :rows="6" animated /><el-alert
        v-if="detailError"
        :title="detailError"
        type="error"
        :closable="false"
        class="spaced"
      />
      <template v-if="detail"
        ><el-tag v-if="detail.snapshot.execution_mode === 'demo'" type="warning"
          >演示线索 · 模拟资料</el-tag
        >
        <h2 class="detail-title">{{ detail.name }}</h2>
        <el-alert
          v-if="!detail.is_current"
          title="统计依据已变化。此处保留原快照，请重新扫描后核对；尚未转换的旧线索不能转研判。"
          type="warning"
          :closable="false"
          class="spaced"
        />
        <p>
          上期 {{ day(detail.snapshot.windows.previous_start) }} 至
          {{ day(detail.snapshot.windows.current_start) }} 前；本期至
          {{ day(detail.snapshot.windows.end) }} 前（北京时间）。
        </p>
        <div class="rule-note">
          规则 {{ detail.snapshot.rule.algorithm }} / v{{ detail.snapshot.rule.version }}：本期 ≥
          {{ detail.snapshot.rule.min_current }}，增加 ≥
          {{ detail.snapshot.rule.min_increase }}，倍数 ≥ {{ detail.snapshot.rule.growth_factor }}。
        </div>
        <p class="snapshot-count">
          上期 {{ detail.snapshot.previous_count }} 条 → 本期 {{ detail.snapshot.current_count }} 条
        </p>
        <p>以下引用扫描时的来源记录；资料撤回或对象变动会使快照失效。</p>
        <div v-for="r in detail.records" :key="r.id" class="source-row">
          <div>
            <small
              >{{ r.occurred_at ? day(r.occurred_at) : "发生时间未知" }} ·
              {{ r.external_record_id || r.id }}</small
            >
            <p>{{ r.text }}</p>
          </div>
          <el-button link type="primary" @click="raw(r.id)">查看原文与附件</el-button>
        </div>
        <div class="detail-actions">
          <el-button
            v-if="detail.snapshot.case_id"
            type="primary"
            @click="openCase(detail.snapshot.case_id)"
            >进入已关联研判事项</el-button
          ><el-button
            v-else
            type="primary"
            :disabled="!detail.is_current"
            @click="prepareConversion"
            >转为研判事项</el-button
          ><span>只关联资料，不生成风险结论或启动检测。</span>
        </div>
      </template>
    </el-drawer>
    <el-dialog v-model="convertDialog" title="关联研判事项" width="min(540px, 94vw)"
      ><p>原始资料与统计快照将保留引用，无需重新录入。</p>
      <el-form label-position="top"
        ><el-form-item label="目标事项"
          ><el-select v-model="targetId" style="width: 100%"
            ><el-option label="新建研判事项" value="__new__" /><el-option
              v-for="c in caseOptions"
              :key="c.id"
              :label="`${c.code} · ${c.title}`"
              :value="c.id" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button @click="convertDialog = false">取消</el-button
        ><el-button type="primary" :loading="converting" @click="convert"
          >确认关联并进入研判</el-button
        ></template
      ></el-dialog
    >
    <el-dialog v-model="focusDialog" title="添加重点对象" width="min(540px, 94vw)"
      ><el-alert v-if="focusError" :title="focusError" type="error" :closable="false" /><el-form
        label-position="top"
        ><el-form-item label="对象类型"
          ><el-radio-group
            v-model="focusForm.object_type"
            @change="
              focusForm.object_id = '';
              searchObjects();
            "
            ><el-radio-button value="product">产品</el-radio-button
            ><el-radio-button value="enterprise">企业</el-radio-button></el-radio-group
          ></el-form-item
        ><el-form-item label="已有档案"
          ><el-select
            v-model="focusForm.object_id"
            filterable
            remote
            :remote-method="searchObjects"
            placeholder="搜索并选择已确认对象"
            style="width: 100%"
            ><el-option
              v-for="o in focusOptions"
              :key="o.id"
              :value="o.id"
              :label="o.name" /></el-select></el-form-item
        ><el-form-item label="关注依据"
          ><el-input
            v-model="focusForm.reason"
            type="textarea"
            :rows="3"
            maxlength="1000" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="focusDialog = false">取消</el-button
        ><el-button type="primary" :loading="focusSaving" @click="saveFocus"
          >保存关注</el-button
        ></template
      ></el-dialog
    >
    <el-dialog v-model="configOpen" title="规则与资料覆盖" width="min(680px, 94vw)"
      ><el-alert v-if="configError" :title="configError" type="error" :closable="false" /><el-tabs
        ><el-tab-pane label="数量规则"
          ><p>调整后生成新版本，原线索保留生成时的规则快照。</p>
          <el-form label-position="top"
            ><div class="rule-inputs">
              <el-form-item label="本期最少条数"
                ><el-input-number
                  v-model="ruleForm.min_current"
                  :min="1"
                  :max="100000" /></el-form-item
              ><el-form-item label="最少增加条数"
                ><el-input-number
                  v-model="ruleForm.min_increase"
                  :min="1"
                  :max="100000" /></el-form-item
              ><el-form-item label="至少达到上期倍数"
                ><el-input-number v-model="ruleForm.growth_factor" :min="1" :max="100" :step="0.5"
              /></el-form-item>
            </div>
            <el-form-item label="调整依据"
              ><el-input
                v-model="ruleForm.reason"
                type="textarea"
                maxlength="1000" /></el-form-item></el-form
          ><el-button type="primary" :loading="configSaving" @click="saveRule"
            >保存新规则版本</el-button
          ></el-tab-pane
        ><el-tab-pane label="来源覆盖"
          ><p>
            仅在核对资料接入的完整起止范围后填写。覆盖不足时显示“无法比较”，发生时间未知的资料始终单列。
          </p>
          <el-form label-position="top"
            ><el-form-item label="来源与资料类型"
              ><el-select v-model="coverageForm.key" style="width: 100%" @change="chooseCoverage"
                ><el-option
                  v-for="(c, i) in coverageRows"
                  :key="i"
                  :label="`${c.source_name} / ${kindLabels[c.record_type]}${c.coverage ? '（已有声明）' : '（未声明）'}`"
                  :value="String(i)" /></el-select
            ></el-form-item>
            <div class="coverage-inputs">
              <el-form-item label="覆盖开始（北京时间，含）"
                ><el-input v-model="coverageForm.start" type="datetime-local" /></el-form-item
              ><el-form-item label="覆盖结束（北京时间，不含）"
                ><el-input v-model="coverageForm.end" type="datetime-local"
              /></el-form-item>
            </div>
            <el-form-item label="核对依据"
              ><el-input
                v-model="coverageForm.reason"
                type="textarea"
                maxlength="1000" /></el-form-item></el-form
          ><el-button type="primary" :loading="configSaving" @click="saveCoverage"
            >记录覆盖声明</el-button
          ></el-tab-pane
        ></el-tabs
      ></el-dialog
    >
  </section>
</template>

<style scoped>
.market-header,
.list-toolbar,
.section-title,
.signal-heading,
.signal-heading > div,
.signal-card footer,
.focus-card,
.detail-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.market-header {
  align-items: flex-start;
  margin-bottom: 24px;
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  letter-spacing: 1px;
}
h1 {
  font-size: 28px;
  margin: 0 0 8px;
  font-weight: 650;
}
h2 {
  font-size: 17px;
  margin: 0;
}
h3 {
  font-size: 16px;
  margin: 0;
}
p {
  line-height: 1.7;
}
.market-header p:last-child,
.list-toolbar p {
  color: var(--el-text-color-secondary);
  margin: 6px 0 0;
  font-size: 14px;
}
.monitor-toolbar {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  padding: 18px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}
.monitor-toolbar label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.toolbar-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-bottom: 8px;
}
.window-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px 24px;
  padding: 20px 0 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.window-strip b {
  margin-right: 6px;
}
.market-tabs {
  margin-top: 10px;
}
.overview-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin: 12px 0 20px;
}
.overview-metrics article {
  border: 1px solid var(--el-border-color-light);
  padding: 20px;
  border-radius: 8px;
  background: var(--el-bg-color);
}
.overview-metrics article > span {
  font-size: 14px;
}
.overview-metrics strong {
  display: block;
  font-size: 38px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-top: 10px;
  line-height: 1.3;
}
.overview-metrics small {
  font-size: 13px;
  font-weight: 400;
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}
.overview-metrics p {
  font-size: 12px;
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
}
.overview-metrics .signal-metric {
  border-top: 3px solid var(--el-color-warning);
  padding-top: 18px;
}
.signal-metric .el-button {
  margin-top: 8px;
}
.monitor-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 18px;
  background: var(--el-bg-color);
}
.section-title {
  align-items: baseline;
  flex-wrap: wrap;
}
.section-title > span,
.monitor-footnote {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.8;
}
.trend-legend {
  display: flex;
  justify-content: flex-end;
  gap: 18px;
  font-size: 12px;
  margin-top: 18px;
}
.trend-legend span:first-child {
  color: var(--el-color-primary);
}
.trend-legend span:last-child {
  color: #66867d;
}
.daily-chart {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.daily-column {
  flex: 1;
  min-width: 0;
  text-align: center;
}
.daily-column > span {
  display: block;
  font-size: 10px;
  margin-top: 8px;
}
.bars {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  height: 125px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.bars i {
  width: 26%;
  min-height: 1px;
  background: var(--el-color-primary);
  border-radius: 2px 2px 0 0;
}
.bars i:last-child {
  background: repeating-linear-gradient(0deg, #66867d, #66867d 3px, #9db4ad 3px, #9db4ad 5px);
}
.period-divider {
  border-left: 1px dashed var(--el-border-color);
  padding-left: 8px;
}
details summary {
  cursor: pointer;
  font-size: 13px;
  padding: 12px 0;
}
details summary:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 3px;
}
.trend-data {
  margin-top: 10px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
td,
th {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid var(--el-border-color-light);
}
.data-quality > p {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.data-quality details {
  border-top: 1px solid var(--el-border-color-light);
}
.data-quality b {
  margin-left: 8px;
}
.rule-note {
  background: var(--el-fill-color-light);
  border-left: 3px solid var(--el-color-primary);
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.8;
  margin: 8px 0 20px;
}
.rule-note b {
  display: block;
}
.list-toolbar {
  margin: 20px 0;
}
.signal-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  margin-bottom: 14px;
  padding: 20px;
  background: var(--el-bg-color);
}
.signal-card.flagged {
  border-left: 3px solid var(--el-color-warning);
}
.signal-body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  align-items: center;
  gap: 20px;
  margin: 18px 0;
}
.signal-body p {
  margin: 0;
  font-size: 13px;
}
.count-pair {
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.count-pair b {
  font-size: 26px;
  margin-left: 6px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.signal-card footer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 14px;
}
.signal-card footer > span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.focus-card {
  padding: 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  margin-bottom: 14px;
}
.focus-card h3 {
  display: inline-block;
  margin: 0 10px;
}
.focus-card p {
  margin: 12px 0 6px;
  font-size: 14px;
}
.focus-card small {
  color: var(--el-text-color-secondary);
}
.spaced {
  margin: 16px 0;
}
.detail-title {
  margin: 18px 0 14px;
}
.snapshot-count {
  font-size: 24px;
  font-weight: 600;
}
.source-row {
  padding: 14px 0;
  border-top: 1px solid var(--el-border-color-light);
  display: flex;
  gap: 16px;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.source-row > div {
  min-width: 0;
}
.source-row small {
  overflow-wrap: anywhere;
  color: var(--el-text-color-secondary);
}
.source-row p {
  margin: 8px 0 0;
}
.source-row > .el-button {
  flex-shrink: 0;
}
.detail-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 24px;
}
.detail-actions > span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.rule-inputs,
.coverage-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
.monitor-footnote {
  margin: 14px 0;
}
@media (max-width: 700px) {
  .market-header {
    gap: 8px;
  }
  .market-header h1 {
    font-size: 24px;
  }
  .market-header > .el-button {
    padding: 10px;
  }
  .monitor-toolbar {
    gap: 12px;
    padding: 14px;
  }
  .toolbar-note {
    width: 100%;
    padding: 0;
  }
  .overview-metrics {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .overview-metrics article {
    padding: 16px;
  }
  .overview-metrics article:last-child {
    grid-column: 1/-1;
  }
  .overview-metrics strong {
    font-size: 32px;
  }
  .window-strip {
    gap: 8px;
  }
  .window-strip > span {
    width: 100%;
  }
  .monitor-panel,
  .signal-card,
  .focus-card {
    padding: 16px;
  }
  .section-title > span {
    font-size: 11px;
  }
  .daily-chart {
    gap: 3px;
  }
  .daily-column > span {
    font-size: 12px;
    writing-mode: vertical-rl;
    margin: 8px auto 0;
    height: 32px;
  }
  .bars {
    height: 90px;
    gap: 2px;
  }
  .bars i {
    width: 38%;
  }
  .period-divider {
    padding-left: 3px;
  }
  .signal-heading {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 10px;
  }
  .signal-heading > div {
    align-items: flex-start;
    gap: 8px;
  }
  .signal-body {
    grid-template-columns: 1fr;
    gap: 10px;
    margin: 12px 0;
  }
  .signal-card footer,
  .focus-card {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }
  .signal-card footer > div,
  .focus-card > div:last-child {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .signal-card .el-button + .el-button,
  .focus-card .el-button + .el-button {
    margin: 0;
  }
  .source-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }
  .list-toolbar {
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
  }
  .rule-inputs .el-form-item,
  .coverage-inputs .el-form-item {
    width: 100%;
    margin-bottom: 8px;
  }
  :deep(.el-button) {
    min-height: 44px;
  }
}
</style>
