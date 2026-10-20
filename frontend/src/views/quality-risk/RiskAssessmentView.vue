<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, DataAnalysis, Plus, RefreshRight } from "@element-plus/icons-vue";
import { extractApiErrorMessage } from "@/api/http";
import { formatServerDateTime } from "@/utils/date-time";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { resultApi } from "@/api/result.api";
import { useAuthStore } from "@/stores/auth.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import DemoRiskWorkflowPanel from "@/components/business/quality-risk/DemoRiskWorkflowPanel.vue";
import RiskLabPanel from "@/components/business/quality-risk/RiskLabPanel.vue";
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
const expertLevel = ref<"low" | "medium" | "high" | "critical">("medium");
const expertRiskType = ref("");

const form = reactive({
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
  assessment.value = value;
  expertLevel.value = !value || value.risk_level === "unknown" ? "medium" : value.risk_level;
  expertRiskType.value = value?.risk_type || "";
}
async function openCase(id: string) {
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
    if (epoch === detailEpoch) detailLoading.value = false;
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
    if (value) void openCase(String(value));
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
  void router.push({ query });
}
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
      name: category?.name || product?.name || form.scope_value,
      ...(category ? { category_id: category.id } : {}),
      ...(product ? { product_id: product.id, category_id: product.category_id } : {}),
      ...(form.scope_type === "enterprise" ? { enterprise_name: form.scope_value } : {}),
      ...(form.scope_type === "production_batch" ? { production_batch_ref: form.scope_value } : {}),
      ...(form.scope_type === "individual_unit" ? { unit_serial_ref: form.scope_value } : {}),
    };
    const result = await qualityRiskApi.createRiskCase({
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
  if (route.query.case_id === row.id) await openCase(row.id);
  else await router.push({ query: { ...route.query, case_id: row.id } });
}

async function analyze() {
  if (!selected.value || analyzing.value || !canAnalyze.value) return;
  const caseId = selected.value.id;
  analyzing.value = true;
  try {
    await qualityRiskApi.analyzeRisk(
      caseId,
      policyId.value || undefined,
      inspectionExecutionRunId.value || undefined,
    );
    ElMessage.success("风险研判草稿已保存，请核对证据并提交独立复核");
    await load();
    if (route.query.case_id === caseId) {
      await openCase(caseId);
      detailTab.value = "assessment";
    }
  } finally {
    analyzing.value = false;
  }
}
async function review(decision: "accept" | "request_evidence") {
  if (!selected.value || !canReview.value || reviewing.value) return;
  if (decision === "accept" && assessment.value?.source_validation?.blockers?.length) {
    ElMessage.warning("请先处理来源核验阻断项并重新生成草稿");
    return;
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
    if (route.query.case_id !== caseId) return;
    await qualityRiskApi.reviewRisk(caseId, decision, prompt.value, {
      assessment_id: assessmentId,
      ...(decision === "accept"
        ? { risk_level: expertLevel.value, risk_type: expertRiskType.value || null }
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
  if (route.query.case_id) void openCase(String(route.query.case_id));
});
</script>

<template>
  <main class="risk-page">
    <header class="risk-hero">
      <div class="hero-copy">
        <p>SHARED RISK ASSESSMENT</p>
        <h1>风险研判</h1>
        <span
          >汇合市场与舆情证据，形成可复核的风险类型、影响范围、依据和监管建议。资料、历史版本和复核意见在同一事项中持续关联。</span
        >
      </div>
      <div class="hero-actions">
        <el-button v-if="isExpert" @click="router.push('/app/risk-policies')"
          >风险等级规则</el-button
        ><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate"
          >新建研判事项</el-button
        >
      </div>
    </header>

    <div class="risk-layout" :class="{ detailed: route.query.case_id }">
      <section class="case-list">
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
            clearable
            placeholder="搜索风险标题"
            @keyup.enter="search"
          /><el-select v-model="status" clearable placeholder="全部状态" @change="search"
            ><el-option label="收集中" value="collecting" /><el-option
              label="待补证"
              value="awaiting_evidence" /><el-option
              label="待复核"
              value="awaiting_review" /><el-option label="已确认" value="risk_assessed"
          /></el-select>
        </div>
        <el-alert v-if="listError" :title="listError" type="error" :closable="false" />
        <el-table
          :data="rows"
          v-loading="listLoading"
          highlight-current-row
          @row-click="selectCase"
        >
          <el-table-column prop="code" label="编号" width="160" />
          <el-table-column prop="title" label="风险对象" min-width="210" />
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
        class="case-detail"
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
            <el-button text @click="closeCase">收起</el-button>
          </div>
          <div class="scope-card">
            <span>当前研判范围</span
            ><strong>{{ selected.scope.name || selected.scope_type }}</strong
            ><small
              >来源记录 {{ selected.source_record_ids.length }} 条 · 可引用证据
              {{ selected.evidence_ids.length }} 项</small
            >
          </div>
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
              v-if="isExpert"
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
              :disabled="analyzing || reviewing || detailLoading"
              @click="openSources"
              >关联补充资料</el-button
            >
          </div>
          <template v-if="workspace.workflow_context?.execution_mode === 'business' && workspace.workflow_context.can_author && !workspace.workflow_context.eligible">
            <el-alert v-for="(blocker, index) in workspace.workflow_context.blockers" :key="index"
              type="info" :closable="false" :title="'正式下游暂不可用：' + blocker.message" />
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
                    clearable
                    placeholder="选择已发布风险等级规则（可选）"
                    ><el-option
                      v-for="item in policies"
                      :key="item.id"
                      :label="`${item.name} · ${item.version}`"
                      :value="item.id" /></el-select
                  ><el-select
                    v-if="
                      auth.hasPermission('inspection_execution') && auth.hasPermission('result')
                    "
                    v-model="inspectionExecutionRunId"
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
                    :loading="analyzing"
                    :disabled="detailLoading || reviewing"
                    @click="analyze"
                    >生成风险研判草稿</el-button
                  >
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
                    <div class="assessment-title">
                      <span>风险等级</span
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
                      :title="`仍需补充：${assessment.missing_inputs.join('、')}`"
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
                      <h3>保留的不确定性</h3>
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
                      <el-select v-model="expertLevel"
                        ><el-option label="低" value="low" /><el-option
                          label="中"
                          value="medium" /><el-option label="高" value="high" /><el-option
                          label="严重"
                          value="critical"
                      /></el-select>
                    </div>
                  </section>
                  <div v-if="canReview" class="review-actions">
                    <el-button
                      type="primary"
                      :icon="CircleCheck"
                      :loading="reviewing"
                      :disabled="!!assessment.source_validation?.blockers?.length || detailLoading"
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
                            : conflict.message || conflict.reason || JSON.stringify(conflict)
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
            <el-tab-pane v-if="workspace.workflow_context?.can_author" label="抽查建议" name="sampling">
              <el-alert type="info" :closable="false" title="最新研判独立复核通过后，可以编写抽查建议。建议保留来源版本与证据，不启动检测。" />
              <el-button style="margin-top:16px;min-height:44px" type="primary" @click="viewSampling">查看本事项抽查建议</el-button>
            </el-tab-pane>
            <el-tab-pane v-if="workspace.workflow_context?.can_author" label="可选验证" name="laboratory" lazy>
              <RiskLabPanel :case-id="selected.id" :assessment="assessment" :is-latest="isLatest" :context="workspace.workflow_context" @changed="refreshLatest" />
            </el-tab-pane>
            <el-tab-pane v-if="workspace.workflow_context?.can_author" label="研判报告" name="reports">
              <el-alert type="info" :closable="false" title="独立研判报告固定对象、证据、结论、限制、复核和抽查建议。不经过实验室也能生成报告。" />
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
  max-width: 1600px;
  margin: 0 auto;
  padding: 24px;
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
  grid-template-columns: minmax(300px, 0.8fr) minmax(0, 1.2fr);
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
@media (max-width: 1100px) {
  .risk-layout.detailed {
    grid-template-columns: minmax(0, 1fr);
  }
  .risk-layout.detailed .case-detail {
    grid-row: 1;
  }
}
@media (max-width: 600px) {
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
