<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, DataAnalysis, Plus, RefreshRight } from "@element-plus/icons-vue";
import { extractApiErrorMessage } from "@/api/http";
import { formatServerDateTime } from "@/utils/date-time";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { resultApi } from "@/api/result.api";
import { useAuthStore } from "@/stores/auth.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import { useRiskAnalysisJob } from '@/composables/useRiskAnalysisJob';
import DemoRiskWorkflowPanel from "@/components/business/quality-risk/DemoRiskWorkflowPanel.vue";
import RiskLabPanel from "@/components/business/quality-risk/RiskLabPanel.vue";
import SupervisionModuleHeader from "@/components/business/supervision/SupervisionModuleHeader.vue";
import {
  RECORD_TYPE_LABELS,
  type QualityRecordType,
  type QualitySourceRecord,
  type RiskAssessmentV4,
  type RiskCaseV4,
  type RiskWorkspace,
} from "@/types/quality-risk.types";

const auth = useAuthStore();
const references = useQualityReferenceStore();
const route = useRoute();
const router = useRouter();
const rows = ref<RiskCaseV4[]>([]);
const policies = ref<any[]>([]);
const workspace = ref<RiskWorkspace | null>(null);
const analysisCaseId=computed(()=>String(route.query.case_id||''));
const analysisJobs=useRiskAnalysisJob(analysisCaseId,async()=>{await refreshLatest();});
const analysisActive=analysisJobs.active;
const jobLabels:Record<string,string>={queued:'排队中',running:'分析中',succeeded:'草稿已生成',completed_with_warnings:'草稿需人工核对',failed:'分析未完成',stale:'材料或版本已变化',cancelled:'排队已取消'};
const detailLoading = ref(false),
  analyzing = ref(false),
  reviewing = ref(false),
  creating = ref(false);
const detailError = ref(""),
  listError = ref("");
function initialTab() { return ['laboratory','reports','sampling','sources','versions'].includes(String(route.query.tab)) ? String(route.query.tab) : 'assessment'; }
const detailTab = ref(initialTab());
let detailEpoch = 0;
const caseStatuses: Record<string, string> = {
  collecting: "资料收集中",
  awaiting_evidence: "待补充证据",
  awaiting_review: "待独立复核",
  risk_assessed: "已确认",
  demo_draft: "演示草稿",
  demo_submitted: "演示待独立复核",
  demo_reviewed: "演示复核通过",
};
const assessmentStatuses: Record<string, string> = {
  draft: "研判草稿",
  awaiting_review: "待独立复核",
  accepted: "已确认",
  awaiting_evidence: "待补证",
  rejected: "已退回",
  needs_reassessment: "来源变化，待重新研判",
  demo_draft: "演示草稿",
  demo_submitted: "演示待独立复核",
  demo_reviewed: "演示复核通过",
  demo_revise: "演示退回修改",
  demo_request_evidence: "演示退回补证",
};
const trustLabels: Record<string, string> = {
  verified: "已核验",
  needs_review: "待独立复核",
  unverified: "未核验",
  pending_review: "待复核",
  blocked: "核验受阻",
  insufficient: "证据不足",
};
const scopeLabels: Record<string, string> = {
  category: "产品类别",
  enterprise: "企业",
  product: "具体产品",
  production_batch: "生产批次",
  individual_unit: "单件",
  mixed: "混合对象",
};
const policyId = ref("");
const inspectionExecutionRunId = ref(String(route.query.execution_run_id || ""));
const executionOptions = ref<any[]>([]);
const sourceRecords = ref<QualitySourceRecord[]>([]);
const total = ref(0);
const page = ref(1);
const keyword = ref("");
const status = ref("");
const listLoading = ref(false);
const sourceLoading = ref(false);
const dialog = ref(false),
  sourcesDialog = ref(false),
  sourcesSaving = ref(false);
const extraSourceIds = ref<string[]>([]);
const selected = ref<RiskCaseV4 | null>(null);
const assessment = ref<RiskAssessmentV4 | null>(null);
const expertLevel = ref<"" | "low" | "medium" | "high" | "critical">("");
const expertRiskType = ref("");
const historicalConfirmed = ref(false), conflictResolution = ref("");
const isHistorical = computed(() => selected.value?.assessment_purpose === 'historical_review' || selected.value?.scope.case_mode === 'public_historical_review');
const historicalReports = computed(() => workspace.value?.records.filter(record => record.record_type === 'inspection_report') || []);

const form = reactive({
  assessment_purpose: "current_supervision",
  historical_period: "",
  title: "",
  scope_type: "category",
  scope_value: "",
  source_record_ids: [] as string[],
});

const canCreate = computed(() => ["admin", "user", "expert"].includes(auth.role));
const isExpert = computed(() => auth.role === "expert");
const canAnalyze = computed(() => ["user", "expert"].includes(auth.role));
const isLatest = computed(
  () => !!assessment.value && assessment.value.id === workspace.value?.assessment_versions[0]?.id,
);
const canReview = computed(
  () =>
    isExpert.value &&
    !analysisActive.value &&
    isLatest.value &&
    !!assessment.value &&
    assessment.value.submitted_by !== auth.userId &&
    assessment.value.status !== "accepted",
);
const versions = computed(() => workspace.value?.assessment_versions || []);
const scopeOptions = computed(() => {
  if (form.scope_type === "category")
    return references.categories.map((item) => ({ value: item.id, label: item.name }));
  if (form.scope_type === "product")
    return references.products.map((item) => ({
      value: item.id,
      label: [item.category_name, item.brand, item.name, item.model].filter(Boolean).join(" · "),
    }));
  if (form.scope_type === "enterprise")
    return Array.from(
      new Set(
        sourceRecords.value
          .map((item) => String(item.enterprise_ref.name || "").trim())
          .filter(Boolean),
      ),
    ).map((name) => ({ value: name, label: name }));
  const key = form.scope_type === "production_batch" ? "production_batch_ref" : "unit_serial_ref";
  if (["production_batch", "individual_unit"].includes(form.scope_type))
    return Array.from(
      new Set(
        sourceRecords.value
          .map((item) => String(item.product_ref[key] || "").trim())
          .filter(Boolean),
      ),
    ).map((name) => ({ value: name, label: name }));
  return [];
});
const riskLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
  unknown: "待确认",
};

function applyAssessment(value: RiskAssessmentV4 | null) {
  historicalConfirmed.value = false;
  conflictResolution.value = "";
  assessment.value = value;
  expertLevel.value = !value || value.risk_level === "unknown" ? "" : value.risk_level;
  expertRiskType.value = value?.risk_type || "";
}
async function openCase(id: string, focusDetail = false) {
  const epoch = ++detailEpoch;
  workspace.value = null;
  selected.value = null;
  applyAssessment(null);
  detailLoading.value = true;
  detailError.value = "";
  try {
    const value = (await qualityRiskApi.riskWorkspace(id)).data.data;
    if (epoch !== detailEpoch) return;
    let restored = value.latest_assessment;
    const pinnedId = String(route.query.assessment_id || "");
    if (pinnedId && pinnedId !== restored?.id) {
      if (!value.assessment_versions.some((v) => v.id === pinnedId)) {
        detailError.value = "指定研判版本不属于当前事项或已不可访问";
        return;
      }
      restored = (await qualityRiskApi.assessment(pinnedId)).data.data;
      if (epoch !== detailEpoch) return;
    }
    workspace.value = value;
    selected.value = value.case;
    applyAssessment(restored);
  } catch (error) {
    if (epoch === detailEpoch)
      detailError.value = extractApiErrorMessage(error, "研判事项未能加载，请重试");
  } finally {
    if (epoch === detailEpoch) {
      detailLoading.value = false;
      if (focusDetail) {
        await nextTick();
        if (epoch === detailEpoch) showCaseDetail();
      }
    }
  }
}
async function selectVersion(id: string) {
  const pinned = id === workspace.value?.latest_assessment?.id ? undefined : id;
  if (String(route.query.assessment_id || "") === String(pinned || ""))
    await openCase(String(route.query.case_id));
  else await router.replace({ query: { ...route.query, assessment_id: pinned } });
}
async function refreshLatest() {
  if (route.query.assessment_id) {
    const query = { ...route.query };
    delete query.assessment_id;
    await router.replace({ query });
    await load();
  } else await refresh();
}
async function load() {
  listLoading.value = true;
  listError.value = "";
  try {
    const response = await qualityRiskApi.riskCases({
      page: page.value,
      size: 20,
      keyword: keyword.value || undefined,
      status: status.value || undefined,
    });
    rows.value = response.data.data.items;
    total.value = response.data.data.total;
  } catch (error) {
    rows.value = [];
    total.value = 0;
    listError.value = extractApiErrorMessage(error, "研判事项列表未能加载");
  } finally {
    listLoading.value = false;
  }
}
async function refresh() {
  await load();
  if (route.query.case_id) await openCase(String(route.query.case_id));
  await loadOptions();
}
function search() {
  page.value = 1;
  void load();
}
async function loadOptions() {
  const result = await Promise.allSettled([
    qualityRiskApi.policies().then((response) => {
      policies.value = response.data.data.filter((item: any) => item.status === "published");
    }),
    auth.hasPermission("inspection_execution") && auth.hasPermission("result")
      ? resultApi.executionOptions().then((response) => {
          executionOptions.value = response.data.data;
        })
      : Promise.resolve(),
  ]);
  if (result.some((item) => item.status === "rejected"))
    ElMessage.warning("部分可选规则或检测证据未能加载，可刷新重试");
}
watch(
  () => [route.query.case_id, route.query.assessment_id],
  ([value]) => {
    detailTab.value = initialTab();
    if (value) void openCase(String(value), true);
    else {
      ++detailEpoch;
      selected.value = null;
      workspace.value = null;
      applyAssessment(null);
      detailLoading.value = false;
      detailError.value = "";
    }
  },
);
function closeCase() {
  const query = { ...route.query };
  delete query.case_id;
  delete query.assessment_id;
  delete query.tab;
  void router.push({ query }).then(async () => { await nextTick(); showRegister(); });
}
function showCaseDetail() {
  const detail = document.getElementById('risk-case-detail');
  detail?.scrollIntoView({ block: 'start' });
  detail?.focus({ preventScroll: true });
}
function showRegister() {
  const register = document.getElementById('risk-case-register');
  register?.scrollIntoView({ block: 'start' });
  register?.focus({ preventScroll: true });
}
function caseStatusTone(value: string): 'success' | 'warning' | 'info' {
  return value === 'risk_assessed' ? 'success' : value === 'awaiting_evidence' ? 'warning' : 'info';
}
function caseRowClass({ row }: { row: RiskCaseV4 }) { return row.id === selected.value?.id ? 'is-selected-case' : ''; }
function viewSampling() {
  if (selected.value)
    void router.push({ path: workspace.value?.workflow_context?.execution_mode === "business" ? "/app/risk-sampling" : "/app/sampling-plans", query: { case_id: selected.value.id } });
}
async function searchSources(keyword = "") {
  sourceLoading.value = true;
  try {
    sourceRecords.value = (
      await qualityRiskApi.records({ page: 1, size: 50, keyword: keyword || undefined })
    ).data.data.items;
  } finally {
    sourceLoading.value = false;
  }
}
async function openSources() {
  extraSourceIds.value = [];
  sourcesDialog.value = true;
  await searchSources();
}
async function attachSources() {
  if (!selected.value || !extraSourceIds.value.length || sourcesSaving.value) return;
  const id = selected.value.id;
  sourcesSaving.value = true;
  try {
    await qualityRiskApi.appendRiskSources(id, extraSourceIds.value);
    sourcesDialog.value = false;
    ElMessage.success("资料已关联；请生成新版研判，历史结论与复核记录继续保留");
    await load();
    if (route.query.case_id === id) await openCase(id);
  } finally {
    sourcesSaving.value = false;
  }
}
async function openCreate() {
  Object.assign(form, {
    assessment_purpose: "current_supervision",
    historical_period: "",
    title: "",
    scope_type: "category",
    scope_value: "",
    source_record_ids: [],
  });
  dialog.value = true;
  sourceLoading.value = true;
  try {
    await Promise.all([searchSources(), references.loadProducts()]);
  } finally {
    sourceLoading.value = false;
  }
}

async function saveCase() {
  if (form.assessment_purpose === 'historical_review' && !form.historical_period.trim()) {
    ElMessage.warning('请填写历史资料对应的时期'); return;
  }
  if (!form.title.trim() || !form.scope_value.trim() || !form.source_record_ids.length) {
    ElMessage.warning("请填写标题、研判范围并选择至少一条原始资料");
    return;
  }
  if (creating.value) return;
  creating.value = true;
  try {
    const category = references.categories.find((item) => item.id === form.scope_value);
    const product = references.products.find((item) => item.id === form.scope_value);
    const scope = {
      ...(form.assessment_purpose === 'historical_review' ? { historical_period: form.historical_period.trim() } : {}),
      name: category?.name || product?.name || form.scope_value,
      ...(category ? { category_id: category.id } : {}),
      ...(product ? { product_id: product.id, category_id: product.category_id } : {}),
      ...(form.scope_type === "enterprise" ? { enterprise_name: form.scope_value } : {}),
      ...(form.scope_type === "production_batch" ? { production_batch_ref: form.scope_value } : {}),
      ...(form.scope_type === "individual_unit" ? { unit_serial_ref: form.scope_value } : {}),
    };
    const result = await qualityRiskApi.createRiskCase({
      assessment_purpose: form.assessment_purpose,
      title: form.title,
      scope_type: form.scope_type,
      scope,
      source_record_ids: form.source_record_ids,
    });
    selected.value = result.data.data;
    assessment.value = null;
    dialog.value = false;
    ElMessage.success("风险线索已建立，原始资料和证据保持关联");
    await load();
    await router.push({ query: { ...route.query, case_id: result.data.data.id } });
  } finally {
    creating.value = false;
  }
}

async function selectCase(row: RiskCaseV4) {
  if (route.query.case_id === row.id) await openCase(row.id, true);
  else await router.push({ query: { ...route.query, case_id: row.id } });
}

async function analyze() {
  if (!selected.value || analyzing.value || analysisActive.value || !canAnalyze.value) return;
  const requestedCase=selected.value.id;
  analyzing.value = true;
  try {
    const job=await analysisJobs.submit(
      workspace.value?.latest_assessment?.id || null,
      policyId.value || undefined,
      isHistorical.value ? undefined : inspectionExecutionRunId.value || undefined,
    );
    if(job)ElMessage.success('分析请求已保存，可离开页面，重新打开后继续查看进度');
  } catch(error) {
    if(route.query.case_id===requestedCase)detailError.value=extractApiErrorMessage(error,'请求未提交，请刷新核对当前版本后重试');
  } finally {
    analyzing.value = false;
  }
}
async function refreshHistoricalReview() {
  if (!selected.value || !assessment.value || analyzing.value || !isExpert.value) return;
  const caseId = selected.value.id, sourceId = assessment.value.id;
  analyzing.value = true;
  try {
    await qualityRiskApi.refreshHistoricalReview(caseId, sourceId);
    ElMessage.success('已核验原证据并整理复核要求；沿用分析来源已记录，未重新调用模型');
    if (route.query.case_id === caseId) await refreshLatest();
  } finally { analyzing.value = false; }
}
async function review(decision: "accept" | "request_evidence") {
  if (!selected.value || !canReview.value || reviewing.value) return;
  if (decision === "accept" && assessment.value?.source_validation?.blockers?.length) {
    ElMessage.warning("请先处理来源核验阻断项并重新生成草稿");
    return;
  }
  if (decision === 'accept' && !expertLevel.value) {
    ElMessage.warning('请明确选择有依据的风险等级；仍无法确认时请退回补证'); return;
  }
  if (decision === 'accept' && isHistorical.value && (!historicalConfirmed.value || (assessment.value?.conflicts.length && !conflictResolution.value.trim()))) {
    ElMessage.warning('请确认历史原件与范围，并填写已有冲突的核对意见'); return;
  }
  const caseId = selected.value.id;
  reviewing.value = true;
  const assessmentId = assessment.value?.id;
  try {
    const prompt = await ElMessageBox.prompt(
      decision === "accept" ? "填写独立复核依据。" : "说明需要补充的材料。",
      decision === "accept" ? "通过风险研判" : "退回补证",
      { inputType: "textarea", inputValidator: (value: string) => !!value.trim() || "请填写意见" },
    );
    if (route.query.case_id !== caseId || assessment.value?.id !== assessmentId) return;
    await qualityRiskApi.reviewRisk(caseId, decision, prompt.value, {
      assessment_id: assessmentId,
      ...(decision === 'accept' && isHistorical.value ? {historical_scope_confirmed: historicalConfirmed.value, conflict_resolution: conflictResolution.value.trim() || null} : {}),
      ...(decision === "accept"
        ? { risk_level: expertLevel.value || undefined, risk_type: expertRiskType.value || null }
        : {}),
    });
    ElMessage.success(decision === "accept" ? "风险研判已确认" : "已退回补证");
    await load();
    if (route.query.case_id === caseId) await openCase(caseId);
  } catch (error) {
    if (error !== "cancel" && error !== "close") throw error;
  } finally {
    reviewing.value = false;
  }
}
function sourceLabel(id: string) {
  const row = sourceRecords.value.find((item) => item.id === id);
  if (!row) return id;
  return `${RECORD_TYPE_LABELS[row.record_type as QualityRecordType]} · ${row.content.text || row.external_record_id || row.id}`;
}

onMounted(() => {
  void load();
  void loadOptions();
  if (route.query.case_id) void openCase(String(route.query.case_id), true);
});
</script>

<template>
  <main class="risk-page">
    <SupervisionModuleHeader title="风险研判" tone="cyan" description="汇合市场与舆情证据，在同一事项中形成研判、独立复核和后续处理建议。" principle="新证据进入原事项并形成新版研判；需要实物验证时，再进入实验室检测。">
      <template #actions>
        <el-button v-if="isExpert" @click="router.push('/app/risk-assessments/records/risk-cases')">历史风险记录</el-button>
        <el-button v-if="isExpert" @click="router.push('/app/risk-policies')"
          >风险等级规则</el-button
        ><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate"
          >新建研判事项</el-button
        >
      </template>
    </SupervisionModuleHeader>

    <div class="risk-layout" :class="{ detailed: route.query.case_id }">
      <section id="risk-case-register" class="case-list" tabindex="-1" aria-label="研判事项台账">
        <header>
          <div>
            <p>RISK REGISTER</p>
            <h2>研判事项台账</h2>
          </div>
          <el-button :icon="RefreshRight" @click="refresh">刷新</el-button>
        </header>
        <div class="filters">
          <el-input
            v-model="keyword"
            aria-label="搜索风险标题"
            clearable
            placeholder="搜索风险标题"
            @keyup.enter="search"
          /><el-select v-model="status" aria-label="事项状态筛选" clearable placeholder="全部状态" @change="search"
            ><el-option label="收集中" value="collecting" /><el-option
              label="待补证"
              value="awaiting_evidence" /><el-option
              label="待复核"
              value="awaiting_review" /><el-option label="已确认" value="risk_assessed"
          /></el-select>
        </div>
        <el-alert v-if="listError" :title="listError" type="error" :closable="false" />
        <el-table
          class="case-table"
          :data="rows"
          v-loading="listLoading"
          highlight-current-row
          :row-class-name="caseRowClass"
          @row-click="selectCase"
        >
          <el-table-column prop="code" label="编号" width="175" />
          <el-table-column prop="title" label="风险对象" min-width="230">
            <template #default="{ row }"><button type="button" class="case-title-button" @click.stop="selectCase(row)">{{ row.title }}</button></template>
          </el-table-column>
          <el-table-column label="范围" width="120"
            ><template #default="{ row }">{{
              scopeLabels[row.scope_type] || row.scope_type
            }}</template></el-table-column
          >
          <el-table-column label="证据" width="70"
            ><template #default="{ row }">{{ row.evidence_ids.length }}</template></el-table-column
          >
          <el-table-column label="状态" width="110"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.status === 'risk_assessed'
                    ? 'success'
                    : row.status === 'awaiting_evidence'
                      ? 'warning'
                      : 'info'
                "
                >{{ caseStatuses[row.status] || row.status }}</el-tag
              ></template
            ></el-table-column
          >
        </el-table>
        <div class="case-cards" v-loading="listLoading">
          <button v-for="row in rows" :key="row.id" type="button" class="case-card"
            :aria-pressed="row.id === selected?.id" @click="selectCase(row)">
            <span class="case-card-heading"><span class="case-code">{{ row.code }}</span><el-tag :type="caseStatusTone(row.status)">{{ caseStatuses[row.status] || row.status }}</el-tag></span>
            <span class="case-card-title">{{ row.title }}</span>
            <span class="case-card-meta"><span>范围：{{ scopeLabels[row.scope_type] || row.scope_type }}</span><span>证据：{{ row.evidence_ids.length }} 项</span></span>
          </button>
          <el-empty v-if="!rows.length && !listLoading" description="暂无符合条件的研判事项" :image-size="60" />
        </div>
        <el-pagination
          v-model:current-page="page"
          :page-size="20"
          :total="total"
          layout="prev, pager, next"
          @current-change="load"
        />
      </section>

      <aside
        v-if="route.query.case_id"
        id="risk-case-detail"
        class="case-detail"
        tabindex="-1"
        v-loading="detailLoading"
        aria-label="研判事项详情"
      >
        <el-alert
          v-if="detailError"
          :title="detailError"
          type="error"
          :closable="false"
        /><el-button v-if="detailError" @click="openCase(String(route.query.case_id))"
          >重试详情</el-button
        >
        <template v-if="selected && workspace">
          <div class="detail-head">
            <div>
              <small>{{ selected.code }}</small>
              <h2>{{ selected.title }}</h2>
            </div>
            <div class="detail-navigation"><el-button text @click="showRegister">返回台账</el-button><el-button text @click="closeCase">收起</el-button></div>
          </div>
          <div class="scope-card">
            <el-tag size="small">{{ isHistorical ? '历史资料复盘' : '当前监管研判' }}</el-tag>
            <span>当前研判范围</span
            ><strong>{{ selected.scope.name || selected.scope_type }}</strong
            ><small
              >来源记录 {{ selected.source_record_ids.length }} 条 · 可引用证据
              {{ selected.evidence_ids.length }} 项</small
            >
            <small v-if="isHistorical">资料时期：{{ selected.scope.historical_period || '待明确' }}；仅针对原资料记载的对象。</small>
          </div>
          <section v-if="analysisJobs.job.value" class="analysis-job-status" aria-live="polite">
            <el-alert :type="['failed','stale','completed_with_warnings'].includes(analysisJobs.job.value.status)?'warning':analysisJobs.job.value.status==='succeeded'?'success':'info'" :closable="false"
              :title="jobLabels[analysisJobs.job.value.status]" :description="analysisJobs.job.value.message" />
            <p v-if="analysisActive" class="muted">任务在后台运行，关闭页面不会取消；请勿重复提交。</p>
            <el-button link type="primary" @click="analysisJobs.loadLatest">刷新任务进度</el-button>
            <el-button v-if="analysisJobs.job.value.status==='queued' && analysisJobs.job.value.created_by===auth.userId" link
              :loading="analysisJobs.cancelling.value" @click="analysisJobs.cancel">取消排队</el-button>
          </section>
          <el-alert v-if="analysisJobs.connectionError.value" type="warning" :closable="false" :title="analysisJobs.connectionError.value" />
          <div class="followup-actions">
            <el-button
              v-for="signalId in (selected.scope.market_signal_ids as string[]) || []"
              :key="signalId"
              @click="
                router.push({
                  path: '/app/quality-analytics',
                  query: { tab: 'anomalies', signal: signalId },
                })
              "
              >查看市场线索依据</el-button
            >
            <el-button
              v-if="isExpert && !isHistorical"
              :disabled="
                !assessment ||
                !isLatest ||
                assessment.status !== 'accepted' ||
                assessment.effective_status === 'needs_reassessment'
              "
              @click="viewSampling"
              >查看抽查候选</el-button
            ><el-button
              v-if="canCreate"
              :disabled="analyzing || analysisActive || reviewing || detailLoading"
              @click="openSources"
              >关联补充资料</el-button
            >
          </div>
          <template v-if="workspace.workflow_context?.execution_mode === 'business' && workspace.workflow_context.can_author && !workspace.workflow_context.eligible">
            <el-alert v-for="(blocker, index) in workspace.workflow_context.blockers" :key="index"
              type="info" :closable="false" :title="(isHistorical ? '复盘报告尚不可生成：' : '后续处理暂不可用：') + blocker.message" />
          </template>
          <el-tabs v-model="detailTab">
            <el-tab-pane label="研判结论" name="assessment">
              <DemoRiskWorkflowPanel
                v-if="workspace.demo_context?.enabled"
                :case-id="selected.id"
                :assessment="assessment"
                :is-latest="isLatest"
                :context="workspace.demo_context"
                :records="workspace.records"
                @changed="refreshLatest"
                @reload="refreshLatest"
              />
              <template v-else>
                <div v-if="canAnalyze" class="action-row risk-inputs">
                  <el-select
                    v-model="policyId"
                    :disabled="analysisActive"
                    clearable
                    placeholder="选择已发布风险等级规则（可选）"
                    ><el-option
                      v-for="item in policies"
                      :key="item.id"
                      :label="`${item.name} · ${item.version}`"
                      :value="item.id" /></el-select
                  ><el-select
                    v-if="
                      !isHistorical && auth.hasPermission('inspection_execution') && auth.hasPermission('result')
                    "
                    v-model="inspectionExecutionRunId"
                    :disabled="analysisActive"
                    clearable
                    filterable
                    placeholder="关联已复核的检测证据（可选）"
                    ><el-option
                      v-for="run in executionOptions"
                      :key="run.id"
                      :value="run.id"
                      :label="run.label + (run.issues.length ? '（来源需核验）' : '')"
                      :disabled="!!run.issues.length" /></el-select
                  ><el-button
                    type="primary"
                    :icon="DataAnalysis"
                    :loading="analyzing || analysisActive"
                    :disabled="detailLoading || reviewing"
                    @click="analyze"
                    >生成风险研判草稿</el-button
                  >
                  <el-button v-if="isHistorical && isExpert && assessment?.analysis_summary?.summary && !assessment.purpose_review?.purpose"
                    :loading="analyzing" :disabled="detailLoading || analysisActive || reviewing" @click="refreshHistoricalReview">整理此版历史复核要求</el-button>
                </div>
                <el-empty
                  v-if="!assessment"
                  description="尚未生成研判草稿；原始资料已关联，可先查看资料后开始分析。"
                  :image-size="70"
                />
                <template v-if="assessment">
                  <div class="version-bar">
                    <span>第 {{ assessment.version }} 版</span
                    ><el-tag :type="assessment.status === 'accepted' ? 'success' : 'info'">{{
                      assessmentStatuses[assessment.effective_status || assessment.status] ||
                      assessment.status
                    }}</el-tag
                    ><span v-if="!isLatest">历史版本，仅供查阅</span>
                  </div>
                  <section class="assessment-card">
                    <el-alert v-if="assessment.analysis_origin" type="info" :closable="false"
                      :title="`本版沿用第 ${assessment.analysis_origin.version} 版已保存的模型分析，已重新核验原证据；仅整理复核要求，未重新调用模型，仍需独立复核。`" />
                    <section v-if="isHistorical" class="historical-sources">
                      <h3>原始资料记载</h3>
                      <p>以下是历史原件的摘录，供复核人逐项核对。</p>
                      <article v-for="record in historicalReports" :key="record.id">
                        <strong>{{ record.content.report_no }} · {{ record.content.issued_date }}</strong>
                        <p>{{ record.content.documentary_verdict || record.content.conclusion }}</p>
                        <ul>
                          <li v-for="(reading, index) in record.content.transcribed_values || []" :key="index">
                            {{ reading.indicator }}：{{ reading.value }} {{ reading.unit }}；原件第 {{ reading.original_pdf_page }} 页；原报告：{{ reading.documentary_verdict }}
                          </li>
                        </ul>
                        <el-button link type="primary" @click="router.push({ path: '/app/quality-data', query: { record: record.id } })">核对报告原件与出处</el-button>
                      </article>
                      <el-button v-if="!historicalReports.length" link type="primary" @click="detailTab = 'sources'">查看原通报与执法资料</el-button>
                    </section>
                    <section v-if="assessment.analysis_summary?.summary">
                      <h3>{{ isHistorical ? (assessment.status === 'accepted' ? '平台复盘分析（已独立复核）' : '平台复盘分析（待独立核对）') : '平台分析摘要' }}</h3>
                      <p>{{ assessment.analysis_summary.summary }}</p>
                    </section>
                    <div class="assessment-title">
                      <span>{{ isHistorical ? '历史风险信号等级' : '风险等级' }}</span
                      ><el-tag
                        :type="
                          assessment.risk_level === 'high' || assessment.risk_level === 'critical'
                            ? 'danger'
                            : assessment.risk_level === 'unknown'
                              ? 'info'
                              : 'warning'
                        "
                        >{{ riskLabels[assessment.risk_level] }}</el-tag
                      >
                    </div>
                    <dl>
                      <dt>风险类型</dt>
                      <dd>{{ assessment.risk_type || "待专家识别" }}</dd>
                      <dt>政策版本</dt>
                      <dd>{{ assessment.policy_version || "未指定" }}</dd>
                      <dt>可信状态</dt>
                      <dd>{{ trustLabels[assessment.trust_status] || assessment.trust_status }}</dd>
                      <dt>风险概率</dt>
                      <dd>
                        {{
                          assessment.probability == null
                            ? "未校准，不展示概率"
                            : assessment.probability
                        }}
                      </dd>
                    </dl>
                    <el-alert
                      v-if="assessment.missing_inputs.length"
                      type="warning"
                      :closable="false"
                      :title="`${isHistorical ? '确认前需处理' : '仍需补充'}：${assessment.missing_inputs.join('、')}`"
                    />
                    <section v-if="assessment.source_validation?.blockers?.length">
                      <h3>确认前必须处理</h3>
                      <ul>
                        <li
                          v-for="(issue, index) in assessment.source_validation.blockers"
                          :key="index"
                        >
                          {{ issue.message }}
                        </li>
                      </ul>
                    </section>
                    <section v-if="assessment.source_validation?.uncertainties?.length">
                      <h3>{{ isHistorical ? '结论范围与资料限制' : '保留的不确定性' }}</h3>
                      <ul>
                        <li
                          v-for="issue in assessment.source_validation.uncertainties"
                          :key="issue"
                        >
                          {{ issue }}
                        </li>
                      </ul>
                    </section>
                    <el-alert
                      type="info"
                      :closable="false"
                      title="风险确认仅适用于本案风险信号和建议；不表示产品整体合格或不合格，也不补造未知发生概率。"
                    />
                    <el-alert
                      v-if="
                        assessment.standard_matches.some(
                          (item: any) => item.kind === 'inspection_execution',
                        )
                      "
                      type="info"
                      :closable="false"
                      title="本次风险研判已引用标准要求执行快照；项目判定与风险等级仍分别复核。"
                    />
                    <div v-if="assessment.possible_causes.length">
                      <h3>可能成因</h3>
                      <p>{{ assessment.possible_causes.join("；") }}</p>
                    </div>
                    <div v-if="assessment.recommendations.length">
                      <h3>监管建议</h3>
                      <p>{{ assessment.recommendations.join("；") }}</p>
                    </div>
                    <div v-if="canReview" class="expert-confirm">
                      <h3>专家确认</h3>
                      <el-input v-model="expertRiskType" placeholder="确认风险类型" />
                      <el-select v-model="expertLevel" placeholder="请明确选择风险等级"
                        ><el-option label="低" value="low" /><el-option
                          label="中"
                          value="medium" /><el-option label="高" value="high" /><el-option
                          label="严重"
                          value="critical"
                      /></el-select>
                      <template v-if="isHistorical">
                        <el-checkbox v-model="historicalConfirmed">已核对原件、对象和时期，确认结论仅限所列历史资料</el-checkbox>
                        <el-form-item v-if="assessment.conflicts.length" label="冲突核对与保留依据" required>
                          <el-input v-model="conflictResolution" type="textarea" :rows="3" maxlength="4000" placeholder="逐项说明核对结果；仍未知的内容须保留为限制" />
                        </el-form-item>
                      </template>
                    </div>
                  </section>
                  <div v-if="canReview" class="review-actions">
                    <el-button
                      type="primary"
                      :icon="CircleCheck"
                      :loading="reviewing"
                      :disabled="!expertLevel || !!assessment.source_validation?.blockers?.length || detailLoading || (isHistorical && (!historicalConfirmed || (!!assessment.conflicts.length && !conflictResolution.trim())))"
                      @click="review('accept')"
                      >独立复核通过</el-button
                    ><el-button
                      :disabled="reviewing || detailLoading"
                      @click="review('request_evidence')"
                      >退回补证</el-button
                    >
                  </div>
                  <section v-if="assessment.standard_matches.length" class="evidence-section">
                    <h3>引用标准与检测依据</h3>
                    <ul>
                      <li v-for="(match, index) in assessment.standard_matches" :key="index">
                        {{
                          match.standard_no ||
                          match.standard_name ||
                          match.name ||
                          match.kind ||
                          "关联依据"
                        }}<span v-if="match.clause_ref || match.clause_no">
                          · {{ match.clause_ref || match.clause_no }}</span
                        >
                        <p v-if="match.reason || match.summary">
                          {{ match.reason || match.summary }}
                        </p>
                      </li>
                    </ul>
                  </section>
                  <section v-if="assessment.conflicts.length" class="evidence-section">
                    <h3>证据冲突</h3>
                    <ul>
                      <li v-for="(conflict, index) in assessment.conflicts" :key="index">
                        {{
                          typeof conflict === "string"
                            ? conflict
                            : conflict.message || conflict.reason || conflict.conflict || JSON.stringify(conflict)
                        }}
                      </li>
                    </ul>
                  </section>
                  <section v-if="assessment.review_comment" class="review-note">
                    <h3>复核意见</h3>
                    <p>{{ assessment.review_comment }}</p>
                    <small>{{
                      assessment.reviewed_at
                        ? formatServerDateTime(assessment.reviewed_at)
                        : "复核时间未记录"
                    }}</small>
                  </section>
                  <el-alert
                    v-if="
                      isLatest &&
                      assessment.status !== 'accepted' &&
                      assessment.submitted_by === auth.userId
                    "
                    type="info"
                    :closable="false"
                    title="本版草稿由你提交，需由另一位专家独立复核。"
                  />
                </template>
              </template>
            </el-tab-pane>
            <el-tab-pane :label="`原始资料（${workspace.records.length}）`" name="sources">
              <el-alert
                v-if="workspace.unavailable_source_ids.length"
                type="warning"
                :closable="false"
                :title="`${workspace.unavailable_source_ids.length} 条关联资料已不可用或无权查看，请核对证据范围。`"
              />
              <article v-for="record in workspace.records" :key="record.id" class="source-record">
                <div>
                  <el-tag size="small" effect="plain">{{
                    RECORD_TYPE_LABELS[record.record_type]
                  }}</el-tag
                  ><small>{{ record.display_no || record.external_record_id || "原始资料" }}</small>
                </div>
                <p>{{ record.content.text || record.content.description || "附件或结构化资料" }}</p>
                <dl>
                  <dt>原始出处</dt>
                  <dd>{{ record.provenance.origin_label || "未知" }}</dd>
                  <dt>发生时间</dt>
                  <dd>
                    {{ record.occurred_at ? formatServerDateTime(record.occurred_at) : "未提供" }}
                  </dd>
                  <dt>接收时间</dt>
                  <dd>{{ formatServerDateTime(record.received_at) }}</dd>
                </dl>
                <el-button
                  v-if="auth.hasPermission('quality_material_read_business')"
                  link
                  type="primary"
                  @click="router.push({ path: '/app/quality-data', query: { record: record.id } })"
                  >查看原件与附件</el-button
                >
              </article>
            </el-tab-pane>
            <el-tab-pane v-if="workspace.workflow_context?.can_author && !isHistorical" label="抽查建议" name="sampling">
              <el-alert type="info" :closable="false" title="最新研判独立复核通过后，可以编写抽查建议。建议保留来源版本与证据，不启动检测。" />
              <el-button style="margin-top:16px;min-height:44px" type="primary" @click="viewSampling">查看本事项抽查建议</el-button>
            </el-tab-pane>
            <el-tab-pane v-if="workspace.workflow_context?.can_author" label="可选验证" name="laboratory" lazy>
              <RiskLabPanel :case-id="selected.id" :assessment="assessment" :is-latest="isLatest" :context="workspace.workflow_context" @changed="refreshLatest" />
            </el-tab-pane>
            <el-tab-pane v-if="workspace.workflow_context?.can_author" :label="isHistorical ? '复盘报告' : '研判报告'" name="reports">
              <el-alert type="info" :closable="false" :title="isHistorical ? '独立复核后生成历史资料复盘报告，分别保存原报告记载、平台分析和结论限制。' : '独立研判报告固定对象、证据、结论、限制、复核和抽查建议。不经过实验室也能生成报告。'" />
              <el-button style="margin-top:16px;min-height:44px" type="primary" @click="router.push({path:'/app/risk-reports',query:{case_id:selected.id,assessment_id:assessment?.id}})">查看本版研判报告</el-button>
            </el-tab-pane>
            <el-tab-pane :label="`版本与复核（${versions.length}）`" name="versions">
              <el-empty v-if="!versions.length" description="尚无研判版本" :image-size="70" />
              <button
                v-for="version in versions"
                :key="version.id"
                class="version-item"
                :class="{ active: assessment?.id === version.id }"
                :disabled="detailLoading || analyzing || reviewing"
                @click="
                  selectVersion(version.id).then(() => {
                    detailTab = 'assessment';
                  })
                "
              >
                <strong>第 {{ version.version }} 版</strong
                ><span
                  >{{ assessmentStatuses[version.status] || version.status }} · 风险{{
                    riskLabels[version.risk_level]
                  }}</span
                ><small>{{
                  version.created_at ? formatServerDateTime(version.created_at) : "生成时间未记录"
                }}</small>
              </button>
            </el-tab-pane>
          </el-tabs>
        </template>
      </aside>
    </div>

    <el-dialog
      v-model="sourcesDialog"
      title="关联补充资料"
      width="min(640px,94vw)"
      :close-on-click-modal="false"
    >
      <p>引用已接入的原始资料。新增证据后需要重新生成研判草稿，历史版本继续保留。</p>
      <el-select
        v-model="extraSourceIds"
        multiple
        filterable
        remote
        :remote-method="searchSources"
        :loading="sourceLoading"
        placeholder="搜索并选择已有资料"
        style="width: 100%"
        ><el-option
          v-for="record in sourceRecords"
          :key="record.id"
          :value="record.id"
          :label="sourceLabel(record.id)"
          :disabled="selected?.source_record_ids.includes(record.id)"
      /></el-select>
      <template #footer
        ><el-button :disabled="sourcesSaving" @click="sourcesDialog = false">取消</el-button
        ><el-button
          type="primary"
          :loading="sourcesSaving"
          :disabled="!extraSourceIds.length"
          @click="attachSources"
          >关联到本事项</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="dialog"
      title="新建研判事项"
      width="min(760px, 94vw)"
      top="5vh"
      :close-on-click-modal="false"
    >
      <el-form label-position="top" v-loading="sourceLoading">
        <el-form-item label="研判用途" required>
          <el-select v-model="form.assessment_purpose" aria-label="研判用途">
            <el-option label="当前监管研判" value="current_supervision" />
            <el-option label="历史资料复盘" value="historical_review" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.assessment_purpose === 'historical_review'" label="历史资料时期" required>
          <el-input v-model="form.historical_period" maxlength="128" placeholder="例如：2021—2022年，保留资料原有时间精度" />
        </el-form-item>
        <el-form-item label="风险线索标题" required
          ><el-input v-model="form.title" placeholder="例如：电动自行车充电温升异常"
        /></el-form-item>
        <div class="form-grid">
          <el-form-item label="研判对象类型" required
            ><el-select v-model="form.scope_type" @change="form.scope_value = ''"
              ><el-option label="按产品类别研判" value="category" /><el-option
                label="按企业研判"
                value="enterprise" /><el-option
                label="按具体产品/型号研判"
                value="product" /><el-option
                label="按真实生产批次研判"
                value="production_batch" /><el-option
                label="按具体单件研判"
                value="individual_unit" /><el-option
                label="多个对象联合研判"
                value="mixed" /></el-select></el-form-item
          ><el-form-item label="具体研判对象" required
            ><el-select
              v-model="form.scope_value"
              filterable
              allow-create
              default-first-option
              placeholder="选择已有对象；来源中出现的新对象可直接输入"
              ><el-option
                v-for="item in scopeOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select
          ></el-form-item>
        </div>
        <el-form-item label="关联原始资料" required
          ><el-select
            v-model="form.source_record_ids"
            multiple
            filterable
            remote
            :remote-method="searchSources"
            :loading="sourceLoading"
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择投诉、报告、图片或其他原始资料"
            ><el-option
              v-for="item in sourceRecords"
              :key="item.id"
              :label="sourceLabel(item.id)"
              :value="item.id" /></el-select
        ></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" :loading="creating" @click="saveCase"
          >建立事项</el-button
        ></template
      >
    </el-dialog>
  </main>
</template>

<style scoped>
.risk-page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px;
  color: #20364a;
}
.risk-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 22px;
  border-bottom: 1px solid #dbe5ea;
}
.hero-copy p,
.case-list header p {
  margin: 0 0 7px;
  color: #087f8c;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
}
.hero-copy h1 {
  margin: 0;
  font-size: 28px;
}
.hero-copy span {
  display: block;
  margin-top: 10px;
  max-width: 760px;
  color: #607386;
  font-size: 14px;
  line-height: 1.7;
}
.hero-actions,
.followup-actions,
.version-bar,
.review-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.hero-actions .el-button,
.followup-actions .el-button,
.review-actions .el-button {
  margin: 0;
}
.risk-layout {
  display: grid;
  gap: 20px;
  margin-top: 22px;
}
.risk-layout.detailed {
  grid-template-columns: minmax(0, 1fr);
}
.case-list,
.case-detail {
  min-width: 0;
  padding: 22px;
  border: 1px solid #dbe5ea;
  border-radius: 8px;
  background: #fff;
  align-self: start;
}
.case-detail {
  border-top: 3px solid #087f8c;
}
.case-list { container-type: inline-size; }
.case-list, .case-detail { scroll-margin-top: 20px; }
.case-table :deep(.cell) { white-space: normal; overflow-wrap: anywhere; line-height: 1.7; }
.case-table :deep(.el-tag) { max-width: 100%; height: auto; min-height: 24px; padding: 3px 8px; white-space: normal; line-height: 1.5; }
.case-table :deep(.el-tag__content) { min-width: 0; white-space: normal; overflow-wrap: anywhere; }
.case-table :deep(.is-selected-case > td.el-table__cell) { background: var(--el-color-primary-light-9); }
.case-title-button { display: block; width: 100%; min-height: 44px; border: 0; padding: 0; background: transparent; color: var(--el-color-primary); font: inherit; line-height: 1.7; text-align: left; white-space: normal; overflow-wrap: anywhere; cursor: pointer; }
.case-title-button:focus-visible, .case-card:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 3px; }
.case-cards { display: none; gap: 12px; }
.case-card { display: grid; gap: 12px; width: 100%; padding: 16px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-bg-color); color: inherit; font: inherit; text-align: left; cursor: pointer; }
.case-card[aria-pressed="true"] { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.case-card-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.case-code { min-width: 0; color: var(--el-text-color-secondary); font-size: 12px; overflow-wrap: anywhere; }
.case-card-heading :deep(.el-tag) { flex-shrink: 0; max-width: 50%; height: auto; min-height: 24px; padding: 3px 8px; white-space: normal; line-height: 1.5; }
.case-card-heading :deep(.el-tag__content) { min-width: 0; white-space: normal; overflow-wrap: anywhere; }
.case-card-title { font-size: 15px; line-height: 1.7; overflow-wrap: anywhere; }
.case-card-meta { display: flex; flex-wrap: wrap; gap: 8px 20px; color: var(--el-text-color-secondary); font-size: 13px; }
.detail-navigation { display: flex; align-items: center; flex-wrap: wrap; flex-shrink: 0; }
@container (max-width: 740px) {
  .case-table { display: none; }
  .case-cards { display: grid; }
}
.case-list > header,
.detail-head,
.assessment-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.case-list h2,
.detail-head h2 {
  margin: 0;
  font-size: 20px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.detail-head small {
  color: #607386;
  font-size: 12px;
}
.filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px;
  gap: 10px;
  margin: 18px 0;
}
.el-pagination {
  margin-top: 18px;
  max-width: 100%;
  overflow: auto;
}
.scope-card {
  display: grid;
  gap: 8px;
  margin: 18px 0;
  padding: 16px;
  background: #f0f7f7;
  border-left: 2px solid #087f8c;
}
.scope-card span,
.scope-card small {
  color: #607386;
  font-size: 12px;
}
.scope-card strong {
  font-size: 17px;
  overflow-wrap: anywhere;
}
.scope-card :deep(.el-tag) { justify-self: start; }
.followup-actions,
.version-bar {
  margin: 16px 0;
}
.version-bar {
  color: #607386;
  font-size: 13px;
}
.risk-inputs {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
  margin: 16px 0;
}
.assessment-card {
  padding: 18px;
  border: 1px solid #dbe5ea;
  border-radius: 6px;
}
.assessment-title {
  margin-bottom: 16px;
  font-weight: 600;
}
.assessment-card dl,
.source-record dl {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 10px;
  font-size: 13px;
}
.assessment-card dt,
.source-record dt {
  color: #607386;
}
.assessment-card dd,
.source-record dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.assessment-card p,
.source-record p,
.review-note p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
  font-size: 14px;
}
.assessment-card h3,
.review-note h3,
.evidence-section h3 {
  font-size: 15px;
}
.case-detail .el-alert {
  margin: 14px 0;
}
.case-detail :deep(.el-alert__description) {
  overflow-wrap: anywhere;
}
.expert-confirm {
  display: grid;
  gap: 10px;
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid #dbe5ea;
}
.historical-sources { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #dbe5ea; }
.historical-sources li { line-height: 1.8; overflow-wrap: anywhere; }
.expert-confirm :deep(.el-checkbox) { height: auto; align-items: flex-start; }
.expert-confirm :deep(.el-checkbox__label) { white-space: normal; line-height: 1.6; }
.review-actions {
  margin-top: 16px;
}
.review-note,
.evidence-section {
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid #dbe5ea;
}
.review-note small,
.source-record small {
  color: #607386;
  font-size: 12px;
}
.evidence-section li {
  overflow-wrap: anywhere;
  line-height: 1.7;
  font-size: 14px;
}
.source-record {
  padding: 18px 0;
  border-bottom: 1px solid #dbe5ea;
}
.source-record > div {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.version-item {
  display: grid;
  gap: 8px;
  width: 100%;
  padding: 16px;
  text-align: left;
  border: 1px solid #dbe5ea;
  border-radius: 6px;
  background: #fff;
  margin: 12px 0;
  color: #20364a;
  cursor: pointer;
}
.version-item.active {
  border-color: #087f8c;
  background: #f0f7f7;
}
.version-item:focus-visible {
  outline: 2px solid #087f8c;
  outline-offset: 2px;
}
.version-item small {
  color: #607386;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.el-select {
  width: 100%;
}
@media (max-width: 600px) {
  .detail-head { flex-direction: column; align-items: stretch; }
  .detail-navigation { justify-content: flex-end; }
  .risk-page {
    padding: 14px;
  }
  .risk-hero {
    flex-direction: column;
  }
  .case-list,
  .case-detail {
    padding: 16px;
  }
  .filters,
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .hero-actions .el-button,
  .followup-actions .el-button,
  .review-actions .el-button {
    min-height: 44px;
  }
}
</style>
