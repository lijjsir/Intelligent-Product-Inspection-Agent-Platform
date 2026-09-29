<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Plus, RefreshRight, Search } from "@element-plus/icons-vue";
import { http } from "@/api/http";
import { inspectionStandardApi } from "@/api/inspection-standard.api";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useAuthStore } from "@/stores/auth.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import type { StandardRetrieveHit } from "@/types/governance.types";

const auth = useAuthStore();
const references = useQualityReferenceStore();
const rows = ref<any[]>([]);
const standards = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialog = ref(false);
const searching = ref(false);
const clauseQuery = ref("");
const clauseHits = ref<StandardRetrieveHit[]>([]);
const selectedExcerpt = ref("");
const form = reactive({
  code: "",
  name: "",
  version: "v1",
  standard_id: "",
  clause_ref: "",
  page_ref: "",
  category_id: "",
  product_id: "",
  indicator: "",
  method: "",
  unit: "",
  operator: "lte",
  threshold: "",
  decision_action: "fail",
  manual_review: true,
});

const selectedStandard = computed(() => standards.value.find((item) => item.id === form.standard_id));
const filteredProducts = computed(() =>
  references.products.filter((item) => !form.category_id || item.category_id === form.category_id),
);
const operatorLabels: Record<string, string> = {
  lte: "不得高于",
  gte: "不得低于",
  eq: "必须等于",
  contains: "必须包含",
  not_contains: "不得包含",
};

function generatedCode() {
  const date = new Date();
  const stamp = [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("");
  const suffix = String(rows.value.length + 1).padStart(3, "0");
  return `STD-RULE-${stamp}-${suffix}`;
}

async function load() {
  loading.value = true;
  try {
    const [rules, standardResult] = await Promise.all([
      qualityRiskApi.standardRules(),
      http.get<any>("/v1/inspection-standards", { params: { size: 200 } }),
      references.loadProducts(),
    ]);
    rows.value = rules.data.data;
    standards.value = standardResult.data.data.items || [];
  } finally {
    loading.value = false;
  }
}

function open() {
  Object.assign(form, {
    code: generatedCode(),
    name: "",
    version: "v1",
    standard_id: standards.value[0]?.id || "",
    clause_ref: "",
    page_ref: "",
    category_id: "",
    product_id: "",
    indicator: "",
    method: "",
    unit: "",
    operator: "lte",
    threshold: "",
    decision_action: "fail",
    manual_review: true,
  });
  clauseQuery.value = "";
  clauseHits.value = [];
  selectedExcerpt.value = "";
  dialog.value = true;
}

async function searchClauses() {
  if (!form.standard_id || !clauseQuery.value.trim()) {
    ElMessage.warning("请先选择检测标准并输入指标或条款关键词");
    return;
  }
  searching.value = true;
  try {
    const standard = selectedStandard.value;
    const response = await inspectionStandardApi.retrieve({
      query: `${standard?.name || ""} ${clauseQuery.value.trim()}`,
      domain: standard?.domain || null,
      top_k: 6,
      only_active: true,
    });
    clauseHits.value = response.data.data.hits;
    if (!clauseHits.value.length) ElMessage.info("没有检索到匹配条款，请换一个指标关键词");
  } finally {
    searching.value = false;
  }
}

function inferCondition(quote: string) {
  const operator = /不得超过|不应大于|小于等于|≤/.test(quote)
    ? "lte"
    : /不得低于|不应小于|大于等于|≥/.test(quote)
      ? "gte"
      : form.operator;
  const match = quote.match(/(-?\d+(?:\.\d+)?)\s*(%|℃|°C|V|A|mA|Ω|kΩ|MPa|kPa|mm|cm|m|g|kg|s|min|h)?/i);
  form.operator = operator;
  if (match) {
    form.threshold = match[1];
    if (match[2]) form.unit = match[2];
  }
}

function useClause(hit: StandardRetrieveHit) {
  form.clause_ref = hit.title || `${hit.standard_no || "标准"}相关条款`;
  form.page_ref = hit.page_number ? String(hit.page_number) : "";
  selectedExcerpt.value = hit.quote;
  inferCondition(hit.quote);
  if (!form.name && form.indicator) form.name = `${form.indicator}判定条件`;
  ElMessage.success("已带入条款出处并生成限值建议，请由专家核对");
}

async function save() {
  if (!form.name.trim() || !form.standard_id || !form.clause_ref.trim() || !form.indicator.trim() || !form.threshold.trim()) {
    ElMessage.warning("请补全规则名称、检测标准、条款、指标和判定值");
    return;
  }
  const numeric = Number(form.threshold);
  const threshold = Number.isFinite(numeric) && form.threshold.trim() !== "" ? numeric : form.threshold.trim();
  saving.value = true;
  try {
    await qualityRiskApi.createStandardRule({
      code: form.code,
      name: form.name,
      version: form.version,
      standard_id: form.standard_id,
      clause_ref: form.clause_ref,
      page_ref: form.page_ref || null,
      category_id: form.category_id || null,
      product_id: form.product_id || null,
      indicator: form.indicator,
      method: form.method || null,
      unit: form.unit || null,
      condition: { operator: form.operator, threshold, source_excerpt: selectedExcerpt.value || null },
      decision_action: form.decision_action,
      review_policy: { manual_review: form.manual_review },
    });
    dialog.value = false;
    ElMessage.success("标准判定条件草稿已创建，发布后可供抽查和检测方案引用");
    await load();
  } finally {
    saving.value = false;
  }
}

async function publish(row: any) {
  await qualityRiskApi.publishStandardRule(row.id);
  ElMessage.success("标准判定条件已发布");
  await load();
}

function conditionLabel(row: any) {
  return `${operatorLabels[row.condition?.operator] || row.condition?.operator || "条件"} ${row.condition?.threshold ?? "-"} ${row.unit || ""}`;
}

onMounted(load);
</script>

<template>
  <main class="rule-page">
    <header class="rule-hero"><div><p>STANDARD CLAUSE TO DECISION</p><h1>标准条款判定条件</h1><span>检测标准保存权威原文；这里把需要用于检测方案的具体条款整理成“指标、方法、单位、限值和处置动作”。</span></div><div class="hero-actions"><el-button :icon="RefreshRight" @click="load">刷新</el-button><el-button v-if="['admin','expert'].includes(auth.role)" type="primary" :icon="Plus" @click="open">从标准建立判定条件</el-button></div></header>

    <section class="relationship"><div><strong>检测标准</strong><span>国家、行业、地方、团体或企业标准原文</span></div><i>选择具体条款</i><div><strong>标准判定条件</strong><span>结构化的指标、方法、单位和限值</span></div><i>供方案引用</i><div><strong>人工复核</strong><span>检测执行链接入后给出核对结果，正式结论仍受复核策略约束</span></div></section>
    <el-alert class="gate-note" type="info" :closable="false" title="原有质检门槛仍作为 AI 结果复核门槛保留，用于控制模型置信度、证据充分度和可追溯性；它不代替检测标准中的产品限值。" />

    <section class="rule-table"><el-table :data="rows" v-loading="loading"><el-table-column label="判定条件" min-width="210"><template #default="{ row }"><div class="primary-cell"><strong>{{ row.name }}</strong><span>{{ row.code }} · {{ row.version }}</span></div></template></el-table-column><el-table-column prop="clause_ref" label="标准条款" min-width="190"/><el-table-column prop="indicator" label="核对指标" width="150"/><el-table-column label="合规条件" min-width="180"><template #default="{ row }">{{ conditionLabel(row) }}</template></el-table-column><el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'published' ? 'success' : 'info'">{{ row.status === 'published' ? '已发布' : row.status === 'superseded' ? '已替代' : '草稿' }}</el-tag></template></el-table-column><el-table-column label="操作" width="90"><template #default="{ row }"><el-button v-if="auth.role === 'admin' && row.status === 'draft'" link @click="publish(row)">发布</el-button></template></el-table-column></el-table></section>

    <el-dialog v-model="dialog" title="从检测标准建立判定条件" width="min(940px, 96vw)" top="2vh" :close-on-click-modal="false">
      <el-form label-position="top">
        <section class="form-section"><div class="section-title"><h3>1. 选择检测标准和条款</h3><span>系统负责检索与带入出处，专家负责确认</span></div><div class="form-grid three"><el-form-item label="检测标准" required><el-select v-model="form.standard_id" filterable @change="clauseHits = []; selectedExcerpt = ''"><el-option v-for="item in standards" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="条款或指标关键词" class="wide"><el-input v-model="clauseQuery" placeholder="如：温升限值、绝缘厚度、制动距离" @keyup.enter="searchClauses"><template #append><el-button :icon="Search" :loading="searching" @click="searchClauses">检索条款</el-button></template></el-input></el-form-item></div><div v-if="clauseHits.length" class="clause-results"><button v-for="hit in clauseHits" :key="hit.id" type="button" @click="useClause(hit)"><strong>{{ hit.standard_no || hit.standard_name || '标准条款' }} · 第{{ hit.page_number || '-' }}页</strong><span>{{ hit.quote }}</span><small>采用此条款</small></button></div><el-alert v-if="selectedExcerpt" type="success" :closable="false"><template #title>已选择标准原文</template><p>{{ selectedExcerpt }}</p></el-alert></section>

        <section class="form-section"><div class="section-title"><h3>2. 确认适用对象</h3><span>不选择具体产品时，条件适用于所选产品类别</span></div><div class="form-grid three"><el-form-item label="产品类别"><el-select v-model="form.category_id" clearable filterable @change="form.product_id = ''"><el-option v-for="item in references.categories" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="具体产品/型号"><el-select v-model="form.product_id" clearable filterable><el-option v-for="item in filteredProducts" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="系统编号"><el-input v-model="form.code" disabled /></el-form-item></div></section>

        <section class="form-section"><div class="section-title"><h3>3. 确认机器判定字段</h3><span>检索只能给出建议，不会把任意文字直接当成正式规则</span></div><div class="form-grid three"><el-form-item label="规则名称" required><el-input v-model="form.name" placeholder="如：充电状态温升上限" /></el-form-item><el-form-item label="标准条款号" required><el-input v-model="form.clause_ref" /></el-form-item><el-form-item label="页码"><el-input v-model="form.page_ref" /></el-form-item><el-form-item label="检测/风险指标" required><el-input v-model="form.indicator" placeholder="如：外壳温升" @blur="!form.name && form.indicator && (form.name = `${form.indicator}判定条件`)" /></el-form-item><el-form-item label="检测方法"><el-input v-model="form.method" placeholder="从标准方法条款确认" /></el-form-item><el-form-item label="单位"><el-input v-model="form.unit" placeholder="如：℃、mm、MPa" /></el-form-item><el-form-item label="合规关系"><el-select v-model="form.operator"><el-option v-for="(label, value) in operatorLabels" :key="value" :label="label" :value="value" /></el-select></el-form-item><el-form-item label="标准限值或要求" required><el-input v-model="form.threshold" placeholder="数值或明确文字条件" /></el-form-item><el-form-item label="不满足时"><el-select v-model="form.decision_action"><el-option label="判定不通过" value="fail"/><el-option label="生成预警" value="warn"/><el-option label="转人工复核" value="manual_review"/></el-select></el-form-item></div><el-switch v-model="form.manual_review" active-text="执行结果必须进入人工复核" /></section>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存草稿</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.rule-page{max-width:1440px;margin:0 auto;padding:24px;color:#172b3a}.rule-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;padding:28px;border:1px solid #e2d8c8;border-radius:16px;background:linear-gradient(120deg,#fff8ec,#fff 65%,#eef8f7)}.rule-hero p{margin:0 0 8px;color:#a9580d;font:700 11px ui-monospace,monospace;letter-spacing:.14em}.rule-hero h1{margin:0;font-size:36px}.rule-hero span{display:block;max-width:760px;margin-top:9px;color:#667a86;line-height:1.6}.hero-actions{display:flex;gap:8px}.relationship{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;align-items:center;gap:14px;margin:16px 0 10px;padding:16px;border:1px solid #e2e8eb;border-radius:13px;background:#fff}.relationship div{display:grid;gap:4px}.relationship span,.relationship i{color:#718391;font-size:12px}.relationship i{font-style:normal}.gate-note{margin-bottom:14px}.rule-table{overflow:hidden;border:1px solid #e3e8eb;border-radius:14px;background:#fff}.primary-cell{display:grid;gap:4px}.primary-cell span{color:#718391;font-size:12px}.form-section{padding:4px 0 18px}.form-section+.form-section{padding-top:18px;border-top:1px solid #e4eaed}.section-title{display:flex;align-items:baseline;justify-content:space-between;gap:18px}.section-title h3{margin:0 0 14px;font-size:16px}.section-title span{color:#718391;font-size:12px}.form-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 16px}.form-grid .wide{grid-column:span 2}.el-select{width:100%}.clause-results{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0 0 14px}.clause-results button{display:grid;gap:6px;padding:13px;border:1px solid #dbe5e8;border-radius:10px;background:#fff;text-align:left;cursor:pointer;transition:border-color .2s ease,box-shadow .2s ease}.clause-results button:hover,.clause-results button:focus-visible{border-color:#1a8177;box-shadow:0 6px 18px rgba(26,129,119,.1);outline:none}.clause-results span{display:-webkit-box;overflow:hidden;color:#526975;line-height:1.55;-webkit-line-clamp:3;-webkit-box-orient:vertical}.clause-results small{color:#0b746c;font-weight:700}.el-alert p{margin:6px 0 0;line-height:1.6}@media(max-width:850px){.rule-hero{align-items:flex-start;flex-direction:column}.relationship{grid-template-columns:1fr}.relationship i{display:none}.form-grid{grid-template-columns:1fr 1fr}.form-grid .wide{grid-column:span 1}.clause-results{grid-template-columns:1fr}}@media(max-width:560px){.rule-page{padding:12px}.form-grid{grid-template-columns:1fr}.hero-actions{width:100%}.hero-actions :deep(.el-button){min-height:44px;flex:1}}
</style>
