<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, DataAnalysis, Plus, RefreshRight } from "@element-plus/icons-vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useAuthStore } from "@/stores/auth.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import { RECORD_TYPE_LABELS, type QualityRecordType, type QualitySourceRecord, type RiskAssessmentV4, type RiskCaseV4 } from "@/types/quality-risk.types";

const auth = useAuthStore();
const references = useQualityReferenceStore();
const route = useRoute();
const router = useRouter();
const rows = ref<RiskCaseV4[]>([]);
const policies = ref<any[]>([]);
const policyId = ref("");
const sourceRecords = ref<QualitySourceRecord[]>([]);
const total = ref(0);
const page = ref(1);
const keyword = ref("");
const status = ref("");
const listLoading = ref(false);
const sourceLoading = ref(false);
const dialog = ref(false);
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
      new Set(sourceRecords.value.map((item) => String(item.enterprise_ref.name || "").trim()).filter(Boolean)),
    ).map((name) => ({ value: name, label: name }));
  const key = form.scope_type === "production_batch" ? "production_batch_ref" : "unit_serial_ref";
  if (["production_batch", "individual_unit"].includes(form.scope_type))
    return Array.from(
      new Set(sourceRecords.value.map((item) => String(item.product_ref[key] || "").trim()).filter(Boolean)),
    ).map((name) => ({ value: name, label: name }));
  return [];
});
const riskLabels: Record<string, string> = { low: "低", medium: "中", high: "高", critical: "严重", unknown: "待确认" };

async function load() {
  listLoading.value = true;
  try {
    const [response, policyResponse] = await Promise.all([
      qualityRiskApi.riskCases({ page: page.value, size: 20, keyword: keyword.value || undefined, status: status.value || undefined }),
      qualityRiskApi.policies(),
    ]);
    rows.value = response.data.data.items;
    total.value = response.data.data.total;
    policies.value = policyResponse.data.data.filter((item: any) => item.status === "published");
    if (!policyId.value) policyId.value = policies.value[0]?.id || "";
    const requestedCaseId = String(route.query.case_id || "");
    if (requestedCaseId) {
      selected.value = rows.value.find((item) => item.id === requestedCaseId) || selected.value;
    } else if (selected.value) {
      selected.value = rows.value.find((item) => item.id === selected.value?.id) || selected.value;
    }
  } finally {
    listLoading.value = false;
  }
}

async function openCreate() {
  Object.assign(form, { title: "", scope_type: "category", scope_value: "", source_record_ids: [] });
  dialog.value = true;
  sourceLoading.value = true;
  try {
    const [records] = await Promise.all([
      qualityRiskApi.records({ page: 1, size: 200 }),
      references.loadProducts(),
    ]);
    sourceRecords.value = records.data.data.items;
  } finally {
    sourceLoading.value = false;
  }
}

async function saveCase() {
  if (!form.title.trim() || !form.scope_value.trim() || !form.source_record_ids.length) {
    ElMessage.warning("请填写标题、研判范围并选择至少一条原始资料");
    return;
  }
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
}

async function selectCase(row: RiskCaseV4) {
  selected.value = row;
  assessment.value = null;
}

async function analyze() {
  if (!selected.value) return;
  assessment.value = (
    await qualityRiskApi.analyzeRisk(selected.value.id, policyId.value || undefined)
  ).data.data;
  expertLevel.value =
    assessment.value.risk_level === "unknown" ? "medium" : assessment.value.risk_level;
  expertRiskType.value = assessment.value.risk_type || "";
  ElMessage.success("风险研判草稿已生成，请核对缺失输入和证据范围");
  await load();
}

async function review(decision: "accept" | "request_evidence") {
  if (!selected.value) return;
  const prompt = await ElMessageBox.prompt(
    decision === "accept" ? "填写独立复核依据。" : "说明需要补充的材料。",
    decision === "accept" ? "通过风险研判" : "退回补证",
    { inputType: "textarea", inputValidator: (value: string) => !!value.trim() || "请填写意见" },
  );
  assessment.value = (
    await qualityRiskApi.reviewRisk(selected.value.id, decision, prompt.value, {
      ...(decision === "accept"
        ? { risk_level: expertLevel.value, risk_type: expertRiskType.value || null }
        : {}),
    })
  ).data.data;
  ElMessage.success(decision === "accept" ? "风险研判已确认" : "已退回补证");
  await load();
}

function sourceLabel(id: string) {
  const row = sourceRecords.value.find((item) => item.id === id);
  if (!row) return id;
  return `${RECORD_TYPE_LABELS[row.record_type as QualityRecordType]} · ${row.content.text || row.external_record_id || row.id}`;
}

onMounted(load);
</script>

<template>
  <main class="risk-page">
    <header class="risk-hero">
      <div class="hero-copy">
        <p>SHARED RISK ASSESSMENT</p>
        <h1>风险研判</h1>
        <span>汇合市场与舆情证据，形成可复核的风险类型、影响范围、依据和监管建议。这是四类 Agent 共享的业务对象。</span>
      </div>
      <div class="hero-actions"><el-button v-if="isExpert" @click="router.push('/app/risk-policies')">风险政策</el-button><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate">建立风险线索</el-button></div>
    </header>

    <section class="principles">
      <div><b>01</b><strong>证据先行</strong><span>每个判断引用原始记录</span></div>
      <div><b>02</b><strong>范围明确</strong><span>类别、企业、产品、批次或单件</span></div>
      <div><b>03</b><strong>概率克制</strong><span>未经校准保持未知</span></div>
      <div><b>04</b><strong>独立复核</strong><span>提交人与复核人分离</span></div>
    </section>

    <div class="risk-layout" :class="{ detailed: selected }">
      <section class="case-list">
        <header><div><p>RISK REGISTER</p><h2>风险线索台账</h2></div><el-button :icon="RefreshRight" @click="load">刷新</el-button></header>
        <div class="filters"><el-input v-model="keyword" clearable placeholder="搜索风险标题" @keyup.enter="load" /><el-select v-model="status" clearable placeholder="全部状态" @change="load"><el-option label="收集中" value="collecting" /><el-option label="待补证" value="awaiting_evidence" /><el-option label="待复核" value="awaiting_review" /><el-option label="已确认" value="risk_assessed" /></el-select></div>
        <el-table :data="rows" v-loading="listLoading" highlight-current-row @row-click="selectCase">
          <el-table-column prop="code" label="编号" width="160" />
          <el-table-column prop="title" label="风险对象" min-width="210" />
          <el-table-column label="范围" width="120"><template #default="{ row }">{{ {category:'产品类别',enterprise:'企业',product:'具体产品',production_batch:'生产批次',individual_unit:'单件',mixed:'混合'}[row.scope_type as string] }}</template></el-table-column>
          <el-table-column label="证据" width="70"><template #default="{ row }">{{ row.evidence_ids.length }}</template></el-table-column>
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'risk_assessed' ? 'success' : row.status === 'awaiting_evidence' ? 'warning' : 'info'">{{ row.status }}</el-tag></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load" />
      </section>

      <aside v-if="selected" class="case-detail">
        <div class="detail-head"><div><small>{{ selected.code }}</small><h2>{{ selected.title }}</h2></div><el-button text @click="selected = null; assessment = null">收起</el-button></div>
        <div class="scope-card"><span>当前研判范围</span><strong>{{ selected.scope.name || selected.scope_type }}</strong><small>来源记录 {{ selected.source_record_ids.length }} 条 · 可引用证据 {{ selected.evidence_ids.length }} 项</small></div>
        <div class="action-row"><el-select v-model="policyId" clearable placeholder="选择已发布风险政策（可选）"><el-option v-for="item in policies" :key="item.id" :label="`${item.name} · ${item.version}`" :value="item.id" /></el-select><el-button type="primary" :icon="DataAnalysis" @click="analyze">生成风险研判草稿</el-button></div>
        <template v-if="assessment">
          <section class="assessment-card">
            <div class="assessment-title"><span>风险等级</span><el-tag :type="assessment.risk_level === 'high' || assessment.risk_level === 'critical' ? 'danger' : assessment.risk_level === 'unknown' ? 'info' : 'warning'">{{ riskLabels[assessment.risk_level] }}</el-tag></div>
            <dl><dt>风险类型</dt><dd>{{ assessment.risk_type || "待专家识别" }}</dd><dt>政策版本</dt><dd>{{ assessment.policy_version || "未指定" }}</dd><dt>可信状态</dt><dd>{{ assessment.trust_status }}</dd><dt>风险概率</dt><dd>{{ assessment.probability == null ? "未校准，不展示概率" : assessment.probability }}</dd></dl>
            <el-alert v-if="assessment.missing_inputs.length" type="warning" :closable="false" :title="`仍需补充：${assessment.missing_inputs.join('、')}`" />
            <div v-if="assessment.possible_causes.length"><h3>可能成因</h3><p>{{ assessment.possible_causes.join('；') }}</p></div>
            <div v-if="assessment.recommendations.length"><h3>监管建议</h3><p>{{ assessment.recommendations.join('；') }}</p></div>
            <div v-if="isExpert && assessment.status !== 'accepted'" class="expert-confirm">
              <h3>专家确认</h3>
              <el-input v-model="expertRiskType" placeholder="确认风险类型" />
              <el-select v-model="expertLevel"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select>
            </div>
          </section>
          <div v-if="isExpert && assessment.status !== 'accepted'" class="review-actions"><el-button type="primary" :icon="CircleCheck" @click="review('accept')">独立复核通过</el-button><el-button @click="review('request_evidence')">退回补证</el-button></div>
        </template>
      </aside>
    </div>

    <el-dialog v-model="dialog" title="建立风险线索" width="min(760px, 94vw)" top="5vh" :close-on-click-modal="false">
      <el-form label-position="top" v-loading="sourceLoading">
        <el-form-item label="风险线索标题" required><el-input v-model="form.title" placeholder="例如：电动自行车充电温升异常" /></el-form-item>
        <div class="form-grid"><el-form-item label="研判对象类型" required><el-select v-model="form.scope_type" @change="form.scope_value = ''"><el-option label="按产品类别研判" value="category" /><el-option label="按企业研判" value="enterprise" /><el-option label="按具体产品/型号研判" value="product" /><el-option label="按真实生产批次研判" value="production_batch" /><el-option label="按具体单件研判" value="individual_unit" /><el-option label="多个对象联合研判" value="mixed" /></el-select></el-form-item><el-form-item label="具体研判对象" required><el-select v-model="form.scope_value" filterable allow-create default-first-option placeholder="选择已有对象；来源中出现的新对象可直接输入"><el-option v-for="item in scopeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div>
        <el-form-item label="关联原始资料" required><el-select v-model="form.source_record_ids" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择投诉、报告、图片或其他原始资料"><el-option v-for="item in sourceRecords" :key="item.id" :label="sourceLabel(item.id)" :value="item.id" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="saveCase">建立线索</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.risk-page{max-width:1520px;margin:0 auto;padding:18px 20px 44px;color:#172b3a}.risk-hero{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:26px;padding:28px 32px;border:1px solid #add9d5;border-radius:18px;background:linear-gradient(125deg,#e9f8f6,#fbfdfd 65%,#fff7e9)}.hero-copy p,.case-list header p{margin:0 0 7px;color:#087f8c;font:700 11px ui-monospace,monospace;letter-spacing:.13em}.hero-copy h1{margin:0;font-size:42px;letter-spacing:-.04em}.hero-copy span{display:block;margin-top:9px;color:#52697a;line-height:1.6}.hero-actions{display:flex;gap:8px}.principles{display:grid;grid-template-columns:repeat(4,1fr);margin:18px 0;border:1px solid #dae6e5;border-radius:14px;background:#fff;overflow:hidden}.principles div{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;padding:18px 20px;border-right:1px solid #e6eeee}.principles div:last-child{border-right:0}.principles b{grid-row:1/3;color:#c16a12;font:700 12px ui-monospace,monospace}.principles strong{font-size:14px}.principles span{color:#718391;font-size:12px}.risk-layout{display:grid;gap:18px}.risk-layout.detailed{grid-template-columns:minmax(0,1.35fr) minmax(360px,.65fr)}.case-list,.case-detail{border:1px solid #dbe5ea;border-radius:16px;background:#fff;box-shadow:0 12px 32px rgba(29,62,82,.06)}.case-list{padding:20px}.case-list>header,.detail-head{display:flex;align-items:center;justify-content:space-between}.case-list h2,.detail-head h2{margin:0;font-size:22px}.filters{display:grid;grid-template-columns:1fr 190px;gap:10px;margin:16px 0}.el-pagination{margin-top:18px}.case-detail{padding:22px;border-top:4px solid #087f8c}.detail-head small{color:#758a99;font:700 11px ui-monospace,monospace}.scope-card{display:grid;gap:5px;margin:18px 0;padding:16px;border-radius:12px;background:#eef8f7}.scope-card span,.scope-card small{color:#627b7c;font-size:12px}.scope-card strong{font-size:18px}.action-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin-bottom:16px}.assessment-card{padding:18px;border:1px solid #dfE9e8;border-radius:12px}.assessment-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.assessment-title span{font-weight:700}.assessment-card dl{display:grid;grid-template-columns:90px 1fr;gap:10px;margin:0}.assessment-card dt{color:#718391}.assessment-card dd{margin:0}.assessment-card h3{margin:16px 0 5px;font-size:13px}.assessment-card p{margin:0;line-height:1.6}.expert-confirm{display:grid;grid-template-columns:1fr 130px;gap:8px;margin-top:16px;padding-top:12px;border-top:1px solid #e3eceb}.expert-confirm h3{grid-column:1/-1;margin:0}.review-actions{display:flex;gap:8px;margin-top:14px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.el-select{width:100%}@media(max-width:1000px){.risk-layout.detailed{grid-template-columns:1fr}.principles{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.risk-page{padding:12px}.risk-hero{grid-template-columns:1fr;padding:20px 16px}.risk-hero>.hero-actions{grid-column:1}.hero-copy h1{font-size:30px}.principles{grid-template-columns:1fr}.principles div{border-right:0;border-bottom:1px solid #e6eeee}.filters,.form-grid,.expert-confirm,.action-row{grid-template-columns:1fr}}
</style>
