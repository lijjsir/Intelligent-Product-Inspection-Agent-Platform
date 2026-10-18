<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { riskCompletionApi, type RiskReport, type ReportSummary } from "@/api/risk-completion.api";
import { exportApi } from "@/api/export.api";
import { extractApiErrorMessage } from "@/api/http";
import { useRuntimeContext } from "@/composables/useRuntimeContext";
import type { RiskAssessmentV4, RiskCaseV4, RiskWorkspace } from "@/types/quality-risk.types";
import { formatServerDateTime } from "@/utils/date-time";
import { ReportExportError, waitForReportExport } from "@/utils/wait-for-report-export";
import { useAuthStore } from "@/stores/auth.store";
const auth = useAuthStore();
const route = useRoute(),
  router = useRouter(),
  runtime = useRuntimeContext();
const loading = ref(false),
  saving = ref(false),
  error = ref("");
const cases = ref<RiskCaseV4[]>([]),
  rows = ref<ReportSummary[]>([]),
  selected = ref<RiskReport | null>(null),
  workspace = ref<RiskWorkspace | null>(null),
  assessment = ref<RiskAssessmentV4 | null>(null);
const caseId = computed(() =>
  typeof route.query.case_id === "string" ? route.query.case_id : undefined,
);
const isDemo = computed(() => runtime.context.value?.execution_mode === "demo");
const basis = computed(() => isDemo.value ? assessment.value?.demo_validation?.basis_hash : workspace.value?.workflow_context?.basis_hash);
const canGenerate = computed(
  () =>
    assessment.value?.id === workspace.value?.latest_assessment?.id &&
    (isDemo.value ? assessment.value?.status === "demo_reviewed" && assessment.value.demo_validation?.is_current : workspace.value?.workflow_context?.eligible && assessment.value?.status === "accepted") &&
    [assessment.value?.submitted_by, assessment.value?.reviewed_by].includes(auth.userId),
);
let epoch = 0;
let alive = true;
async function load() {
  const key = ++epoch;
  const requestedCase = caseId.value;
  const pinned = typeof route.query.assessment_id === "string" ? route.query.assessment_id : null;
  const requestedReport = typeof route.query.report === "string" ? route.query.report : null;
  loading.value = true;
  error.value = "";
  rows.value = [];
  selected.value = null;
  workspace.value = null;
  assessment.value = null;
  try {
    await runtime.load();
    const [list, options] = await Promise.all([
      riskCompletionApi.reports(requestedCase),
      qualityRiskApi.riskCases({ page: 1, size: 200 }),
    ]);
    const w = requestedCase ? (await qualityRiskApi.riskWorkspace(requestedCase)).data.data : null;
    if (pinned && !w?.assessment_versions.some((v) => v.id === pinned))
      throw new Error("指定研判不属于当前事项");
    const a = pinned
      ? (await qualityRiskApi.assessment(pinned)).data.data
      : w?.latest_assessment || null;
    const report = requestedReport
      ? (await riskCompletionApi.report(requestedReport)).data.data
      : null;
    if (report && requestedCase && report.snapshot.case_id !== requestedCase)
      throw new Error("报告不属于当前事项");
    if (key !== epoch) return;
    rows.value = list.data.data;
    cases.value = options.data.data.items;
    if (w && !cases.value.some((c) => c.id === w.case.id)) cases.value.push(w.case);
    workspace.value = w;
    assessment.value = a;
    selected.value = report;
  } catch (e) {
    if (key === epoch) error.value = extractApiErrorMessage(e, "研判报告加载失败");
  } finally {
    if (key === epoch) loading.value = false;
  }
}
async function generate() {
  const a = assessment.value;
  const targetCase = caseId.value,
    targetEpoch = epoch;
  if (!targetCase || !a || !basis.value || !canGenerate.value || loading.value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const report = (
      await riskCompletionApi.createReport(targetCase, a.id, basis.value)
    ).data.data;
    if (!alive || targetCase !== caseId.value || targetEpoch !== epoch) return;
    await router.replace({ query: { ...route.query, report: report.id } });
    await load();
    ElMessage.success("研判报告已固定，未创建检测任务");
  } catch (e) {
    if (alive && targetCase === caseId.value)
      error.value = extractApiErrorMessage(e, "生成失败，请核对版本与复核");
  } finally {
    saving.value = false;
  }
}
async function download(format: "pdf" | "docx") {
  if (!selected.value) return;
  const report = selected.value;
  saving.value = true;
  error.value = "";
  try {
    const initial = (await riskCompletionApi.exportReport(report.id, format)).data.data;
    const job = await waitForReportExport(
      initial,
      async (id) => (await exportApi.detail(id, 5000)).data.data,
    );
    const data = (await exportApi.download(job.id)).data;
    if (!alive || selected.value?.id !== report.id) return;
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = report.title + "." + format;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    if (alive && selected.value?.id === report.id)
      error.value =
        e instanceof ReportExportError
          ? e.message
          : extractApiErrorMessage(e, "导出失败，请重试并核对来源权限");
  } finally {
    saving.value = false;
  }
}
watch(() => [route.query.case_id, route.query.assessment_id, route.query.report], load);
onMounted(load);
onBeforeUnmount(() => {
  alive = false;
  ++epoch;
});
</script>
<template>
  <main class="risk-report-center" v-loading="loading">
    <header>
      <div>
        <p>质量监督 · 成果留存</p>
        <h1>报告中心</h1>
        <p>独立研判报告保存对象、证据、结论、限制、独立复核与抽查建议，不依赖检测任务。</p>
      </div>
      <div class="actions">
        <el-button @click="load">刷新报告</el-button
        ><el-button @click="router.push('/app/export')">检测任务报告</el-button>
      </div>
    </header>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-alert
      v-if="!runtime.context.value"
      type="info"
      title="正在核对运行环境，请稍候或刷新重试。"
      :closable="false"
    />
    <template v-else
      ><el-alert v-if="isDemo"
        type="warning"
        title="演示报告使用模拟资料和人工研判，未调用真实模型；不构成正式风险结论或检测报告。"
        :closable="false"
      />
      <section>
        <label for="report-case">来源事项</label
        ><select
          id="report-case"
          :value="caseId || ''"
          :disabled="saving"
          @change="
            router.replace({
              query: { case_id: ($event.target as HTMLSelectElement).value || undefined },
            })
          "
        >
          <option value="">全部事项</option>
          <option v-for="row in cases" :key="row.id" :value="row.id">
            {{ row.code }} · {{ row.title }}
          </option>
        </select>
        <p v-if="assessment">
          当前选择研判第 {{ assessment.version }} 版；{{
            canGenerate
              ? "本版独立复核通过，可保存报告快照。"
              : "须使用最新、依据有效且独立复核通过的版本。"
          }}
        </p>
        <el-button v-if="caseId" type="primary" :disabled="!canGenerate || saving" @click="generate"
          >{{ isDemo ? "生成本版演示研判报告" : "生成本版研判报告" }}</el-button
        >
      </section>
      <section>
        <h2>研判报告记录</h2>
        <el-empty v-if="!rows.length" description="暂无可访问的研判报告" :image-size="60" /><button
          v-for="row in rows"
          :key="row.id"
          class="report-row"
          :disabled="saving"
          @click="router.replace({ query: { ...route.query, report: row.id } })"
        >
          <strong>{{ row.title }}</strong
          ><span
            >{{
              row.effective_status === "historical_snapshot"
                ? "历史快照，需核对当前依据"
                : isDemo ? "演示固定快照" : "已固定快照"
            }}
            · {{ formatServerDateTime(row.frozen_at) }}</span
          >
        </button>
      </section>
      <section v-if="selected" class="report-preview">
        <header>
          <h2>{{ selected.title }}</h2>
          <div class="actions">
            <el-button :disabled="saving" @click="download('pdf')">导出 PDF</el-button
            ><el-button :disabled="saving" @click="download('docx')">导出 Word</el-button>
          </div>
        </header>
        <el-alert
          v-for="issue in selected.source_issues"
          :key="issue"
          type="warning"
          :title="issue"
          :closable="false"
        />
        <el-button
          @click="
            router.push({
              path: '/app/risk-assessments',
              query: {
                case_id: selected.snapshot.case_id,
                assessment_id: selected.snapshot.assessment_id,
              },
            })
          "
          >查看原研判版本</el-button
        >
        <article v-for="(section, i) in selected.sections" :key="i">
          <h3>{{ section.title }}</h3>
          <p v-for="(line, n) in section.paragraphs" :key="n">{{ line }}</p>
        </article>
      </section>
    </template>
  </main>
</template>
<style scoped>
.risk-report-center {
  max-width: 1200px;
  margin: auto;
  padding: 28px;
  display: grid;
  gap: 20px;
  min-width: 0;
}
header,
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
  flex-wrap: wrap;
}
h1 {
  font-size: 25px;
  margin: 8px 0;
}
h2 {
  font-size: 19px;
  margin: 0 0 12px;
}
h3 {
  font-size: 17px;
  margin: 24px 0 10px;
}
p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.8;
  margin: 8px 0;
  color: var(--el-text-color-regular);
}
section {
  padding: 22px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  min-width: 0;
}
.report-row {
  display: flex;
  gap: 14px;
  justify-content: space-between;
  flex-wrap: wrap;
  width: 100%;
  min-height: 48px;
  padding: 16px;
  margin: 8px 0;
  text-align: left;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
  color: inherit;
  cursor: pointer;
}
.report-row:focus-visible {
  outline: 2px solid var(--el-color-primary);
}
label {
  display: block;
  margin-bottom: 8px;
}
select {
  min-height: 44px;
  width: 100%;
  max-width: 100%;
  padding: 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 5px;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
}
.actions :deep(.el-button) {
  margin-left: 0;
}
:deep(.el-button) {
  min-height: 44px;
}
@media (max-width: 700px) {
  .risk-report-center {
    padding: 16px;
    gap: 16px;
  }
  section {
    padding: 16px;
  }
  .report-row {
    font-size: 14px;
  }
  header {
    align-items: stretch;
  }
  .actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
