<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, type UploadFile } from "element-plus";
import { ChatDotRound, DocumentAdd, RefreshRight, Right, UploadFilled } from "@element-plus/icons-vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import LocationPicker from "@/components/business/quality-risk/LocationPicker.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import type { LocationRef, QualityRecordType, QualitySourceRecord } from "@/types/quality-risk.types";

type OpinionType = "consumer_complaint" | "public_opinion";
type TypeFilter = "all" | OpinionType;

const auth = useAuthStore();
const router = useRouter();
const references = useQualityReferenceStore();
const rows = ref<QualitySourceRecord[]>([]);
const complaintTotal = ref(0);
const opinionTotal = ref(0);
const activeType = ref<TypeFilter>("all");
const keyword = ref("");
const page = ref(1);
const pageSize = 20;
const loading = ref(false);
const saving = ref(false);
const dialog = ref(false);
const attachments = ref<File[]>([]);

const canCreate = computed(() => ["admin", "user", "expert"].includes(auth.role));
const activeSources = computed(() => references.sources.filter((item) => item.status === "active"));
const filteredProducts = computed(() =>
  references.products.filter((item) => !form.category_id || item.category_id === form.category_id),
);
const filteredRows = computed(() =>
  activeType.value === "all"
    ? rows.value
    : rows.value.filter((item) => item.record_type === activeType.value),
);
const visibleRows = computed(() =>
  filteredRows.value.slice((page.value - 1) * pageSize, page.value * pageSize),
);

const form = reactive({
  source_id: "",
  external_record_id: "",
  record_type: "consumer_complaint" as OpinionType,
  occurred_at: new Date().toISOString(),
  text: "",
  enterprise_name: "",
  category_id: "",
  product_id: "",
  production_batch_ref: "",
  location: { location_method: "unknown" } as LocationRef,
});

function resetForm() {
  Object.assign(form, {
    source_id: activeSources.value[0]?.id || "",
    external_record_id: "",
    record_type: activeType.value === "public_opinion" ? "public_opinion" : "consumer_complaint",
    occurred_at: new Date().toISOString(),
    text: "",
    enterprise_name: "",
    category_id: "",
    product_id: "",
    production_batch_ref: "",
    location: { location_method: "unknown" },
  });
  attachments.value = [];
}

async function load() {
  loading.value = true;
  try {
    const params = { page: 1, size: 200, keyword: keyword.value.trim() || undefined };
    const [complaints, opinions] = await Promise.all([
      qualityRiskApi.records({ ...params, record_type: "consumer_complaint" }),
      qualityRiskApi.records({ ...params, record_type: "public_opinion" }),
      references.loadSources(),
      references.loadProducts(),
    ]);
    complaintTotal.value = complaints.data.data.total;
    opinionTotal.value = opinions.data.data.total;
    rows.value = [...complaints.data.data.items, ...opinions.data.data.items].sort(
      (left, right) => new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime(),
    );
    page.value = 1;
  } finally {
    loading.value = false;
  }
}

async function openCreate() {
  if (!references.sources.length || !references.products.length) {
    await Promise.all([references.loadSources(), references.loadProducts()]);
  }
  resetForm();
  dialog.value = true;
}

function fileChanged(file: UploadFile) {
  if (file.raw) attachments.value = [file.raw];
}

async function saveRecord() {
  if (!form.source_id || !form.text.trim()) {
    ElMessage.warning("请选择数据来源并填写投诉或舆情原文");
    return;
  }
  saving.value = true;
  try {
    const uploaded = attachments.value.length
      ? (await qualityRiskApi.uploadAttachments(attachments.value)).data.data
      : [];
    await qualityRiskApi.createEvent({
      source_id: form.source_id,
      external_record_id: form.external_record_id || null,
      record_type: form.record_type,
      occurred_at: form.occurred_at,
      content: { text: form.text },
      enterprise_ref: form.enterprise_name ? { name: form.enterprise_name } : {},
      product_ref: {
        category_id: form.category_id || null,
        product_id: form.product_id || null,
        production_batch_ref: form.production_batch_ref || null,
        unit_serial_ref: null,
      },
      location: form.location,
      attachment_ids: uploaded.map((item) => item.id),
      provenance: { channel: "public_opinion_monitoring" },
    });
    dialog.value = false;
    ElMessage.success("线索已登记，原文、附件和来源均已留痕");
    await load();
  } finally {
    saving.value = false;
  }
}

async function createRiskCase(row: QualitySourceRecord) {
  const product = references.products.find((item) => item.id === row.product_ref.product_id);
  const category = references.categories.find((item) => item.id === row.product_ref.category_id);
  const enterpriseName = String(row.enterprise_ref.name || "").trim();
  const scopeType = product ? "product" : category ? "category" : enterpriseName ? "enterprise" : "mixed";
  const scopeName = product?.name || category?.name || enterpriseName || "待识别对象";
  const original = String(row.content.text || row.external_record_id || "质量风险").trim();
  const title = `${original.slice(0, 32)}${original.length > 32 ? "…" : ""}`;
  const result = await qualityRiskApi.createRiskCase({
    title,
    scope_type: scopeType,
    scope: { name: scopeName, category_id: category?.id || null, product_id: product?.id || null },
    source_record_ids: [row.id],
  });
  ElMessage.success("已形成待研判风险线索，正在进入风险研判");
  await router.push({ path: "/app/risk-assessments", query: { case_id: result.data.data.id } });
}

function setType(value: TypeFilter) {
  activeType.value = value;
  page.value = 1;
}

function sourceName(id: string) {
  return references.sources.find((item) => item.id === id)?.name || "来源待核对";
}

function objectName(row: QualitySourceRecord) {
  const product = references.products.find((item) => item.id === row.product_ref.product_id);
  const category = references.categories.find((item) => item.id === row.product_ref.category_id);
  return product?.name || category?.name || row.enterprise_ref.name || "对象待识别";
}

function locationName(row: QualitySourceRecord) {
  return row.location.formatted_address || "地点未提供";
}

function displayTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

onMounted(load);
</script>

<template>
  <main class="opinion-page">
    <header class="opinion-hero">
      <div class="hero-copy">
        <p class="kicker">PUBLIC OPINION MONITORING</p>
        <h1>舆情监测</h1>
        <p class="lead">汇集消费投诉与公开舆情，保留原文、附件和来源，识别值得进一步研判的质量风险线索。</p>
        <div class="boundary-note"><ChatDotRound />舆情强烈不等于产品不合格；这里只形成证据化线索，不直接作质量终判。</div>
      </div>
      <div class="hero-actions">
        <el-button :icon="UploadFilled" @click="router.push('/app/quality-data')">查看全部数据</el-button>
        <el-button v-if="canCreate" type="primary" :icon="DocumentAdd" @click="openCreate">登记投诉或舆情</el-button>
      </div>
    </header>

    <section class="signal-overview" aria-label="舆情线索概览">
      <button :class="{ active: activeType === 'all' }" @click="setType('all')"><strong>{{ complaintTotal + opinionTotal }}</strong><span>全部舆情线索</span></button>
      <button :class="{ active: activeType === 'consumer_complaint' }" @click="setType('consumer_complaint')"><strong>{{ complaintTotal }}</strong><span>消费投诉</span></button>
      <button :class="{ active: activeType === 'public_opinion' }" @click="setType('public_opinion')"><strong>{{ opinionTotal }}</strong><span>公开舆情</span></button>
      <div><strong>{{ references.sources.length }}</strong><span>已登记数据来源</span></div>
    </section>

    <section class="signals-panel">
      <div class="panel-head">
        <div><p class="section-index">01 / VERIFIED SIGNALS</p><h2>投诉与舆情线索</h2></div>
        <el-button :icon="RefreshRight" :loading="loading" @click="load">刷新</el-button>
      </div>
      <div class="filters">
        <el-input v-model="keyword" clearable placeholder="搜索投诉、舆情原文或外部编号" @keyup.enter="load" />
        <el-button type="primary" @click="load">查询</el-button>
      </div>

      <el-skeleton v-if="loading && !rows.length" :rows="5" animated />
      <el-empty v-else-if="!visibleRows.length" description="暂无投诉或舆情线索">
        <el-button v-if="canCreate" type="primary" @click="openCreate">登记第一条线索</el-button>
      </el-empty>
      <div v-else class="signal-list" aria-live="polite">
        <article v-for="row in visibleRows" :key="row.id" class="signal-card">
          <div class="signal-type" :class="row.record_type"><span>{{ row.record_type === 'consumer_complaint' ? '消费投诉' : '公开舆情' }}</span><small>{{ sourceName(row.source_id) }}</small></div>
          <div class="signal-content">
            <p>{{ row.content.text || "原文内容待补充" }}</p>
            <dl><div><dt>关联对象</dt><dd>{{ objectName(row) }}</dd></div><div><dt>发生地点</dt><dd>{{ locationName(row) }}</dd></div><div><dt>发生时间</dt><dd>{{ displayTime(row.occurred_at) }}</dd></div><div><dt>证据状态</dt><dd>{{ row.normalization_status === 'normalized' ? '已标准化' : '待整理' }}</dd></div></dl>
          </div>
          <div class="signal-action"><el-button v-if="canCreate" :icon="Right" @click="createRiskCase(row)">形成风险线索</el-button></div>
        </article>
      </div>
      <el-pagination v-if="filteredRows.length > pageSize" v-model:current-page="page" :page-size="pageSize" :total="filteredRows.length" layout="prev, pager, next" />
    </section>

    <el-dialog v-model="dialog" title="登记投诉或舆情" width="min(820px, 94vw)" top="3vh" :close-on-click-modal="false">
      <el-alert v-if="!activeSources.length" type="warning" :closable="false" title="当前没有启用的数据来源，请先在质量数据接入页登记来源。" class="source-alert" />
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="资料类型" required><el-radio-group v-model="form.record_type"><el-radio-button value="consumer_complaint">消费投诉</el-radio-button><el-radio-button value="public_opinion">公开舆情</el-radio-button></el-radio-group></el-form-item>
          <el-form-item label="数据来源" required><el-select v-model="form.source_id" filterable placeholder="选择来源"><el-option v-for="item in activeSources" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
          <el-form-item label="外部记录编号"><el-input v-model="form.external_record_id" placeholder="可选；用于来源系统幂等去重" /></el-form-item>
          <el-form-item label="发生时间" required><el-date-picker v-model="form.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item>
        </div>
        <el-form-item label="投诉或舆情原文" required><el-input v-model="form.text" type="textarea" :rows="5" placeholder="填写原始表述，不要先改写成风险结论" /></el-form-item>
        <div class="form-grid">
          <el-form-item label="涉及企业"><el-input v-model="form.enterprise_name" placeholder="来源能够确认时填写" /></el-form-item>
          <el-form-item label="产品类别"><el-select v-model="form.category_id" clearable filterable placeholder="可选"><el-option v-for="item in references.categories" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
          <el-form-item label="具体产品/型号"><el-select v-model="form.product_id" clearable filterable placeholder="无法确认时保持为空"><el-option v-for="item in filteredProducts" :key="item.id" :label="`${item.name}${item.model ? ` · ${item.model}` : ''}`" :value="item.id" /></el-select></el-form-item>
          <el-form-item label="真实生产批次"><el-input v-model="form.production_batch_ref" placeholder="来源明确提供时填写" /></el-form-item>
        </div>
        <el-form-item label="发生地点"><LocationPicker v-model="form.location" /></el-form-item>
        <el-form-item label="图片或附件"><el-upload :auto-upload="false" :limit="1" :on-change="fileChanged"><el-button>选择附件</el-button></el-upload></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button v-if="!activeSources.length" @click="router.push('/app/quality-data'); dialog = false">前往登记来源</el-button><el-button type="primary" :loading="saving" :disabled="!activeSources.length" @click="saveRecord">保存线索</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.opinion-page{--opinion-ink:#132a38;--opinion-muted:#607482;--opinion-accent:#087b72;--opinion-warm:#bd6415;max-width:1520px;margin:0 auto;padding:18px 20px 44px;color:var(--opinion-ink)}.opinion-hero{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:28px;padding:30px 34px;border:1px solid #b9dcd7;border-radius:18px;background:linear-gradient(120deg,#edf9f6 0%,#fbfdfc 62%,#fff5e7 100%)}.kicker,.section-index{margin:0 0 8px;color:var(--opinion-accent);font:700 11px ui-monospace,monospace;letter-spacing:.14em}.opinion-hero h1{margin:0;font-size:42px;letter-spacing:-.04em}.lead{max-width:760px;margin:10px 0 0;color:#4d6675;line-height:1.65}.boundary-note{display:flex;align-items:center;gap:8px;margin-top:16px;color:#355e63;font-size:13px}.boundary-note :deep(svg){width:18px;color:var(--opinion-accent)}.hero-actions{display:flex;gap:10px}.hero-actions :deep(.el-button){min-height:44px}.signal-overview{display:grid;grid-template-columns:repeat(4,1fr);margin:18px 0;border:1px solid #dbe6e4;border-radius:15px;background:#fff;overflow:hidden}.signal-overview>button,.signal-overview>div{display:grid;gap:5px;padding:18px 22px;border:0;border-right:1px solid #e3ecea;background:transparent;text-align:left;color:inherit}.signal-overview>button{cursor:pointer;transition:background-color .2s ease,box-shadow .2s ease}.signal-overview>button:hover,.signal-overview>button:focus-visible{background:#f1faf8;outline:2px solid transparent}.signal-overview>button.active{background:#e9f7f4;box-shadow:inset 0 -3px var(--opinion-accent)}.signal-overview>*:last-child{border-right:0}.signal-overview strong{font-size:24px;font-variant-numeric:tabular-nums}.signal-overview span{color:var(--opinion-muted);font-size:12px}.signals-panel{padding:22px;border:1px solid #dce6e8;border-radius:17px;background:#fff;box-shadow:0 12px 34px rgba(34,65,76,.06)}.panel-head{display:flex;align-items:center;justify-content:space-between}.panel-head h2{margin:0;font-size:24px}.filters{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;margin:18px 0}.filters :deep(.el-button){min-width:88px}.signal-list{display:grid;gap:10px}.signal-card{display:grid;grid-template-columns:150px minmax(0,1fr) auto;gap:20px;align-items:center;padding:18px;border:1px solid #e0e9e8;border-radius:13px;background:#fff;transition:border-color .2s ease,box-shadow .2s ease}.signal-card:hover{border-color:#a8d3ce;box-shadow:0 8px 22px rgba(28,81,81,.07)}.signal-type{display:grid;gap:6px;align-self:stretch;padding:12px;border-radius:10px;background:#edf7f6}.signal-type.public_opinion{background:#fff4e8}.signal-type span{font-weight:700}.signal-type small{color:var(--opinion-muted);line-height:1.45}.signal-content>p{margin:0 0 13px;font-size:15px;font-weight:600;line-height:1.65}.signal-content dl{display:flex;flex-wrap:wrap;gap:8px 22px;margin:0}.signal-content dl div{display:flex;gap:6px}.signal-content dt{color:#7a8c96}.signal-content dd{margin:0;color:#405866}.signal-action :deep(.el-button){min-height:44px}.el-pagination{margin-top:20px}.source-alert{margin-bottom:16px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}.el-select,.el-date-editor{width:100%}@media(max-width:900px){.opinion-hero{grid-template-columns:1fr}.hero-actions{justify-content:flex-start}.signal-overview{grid-template-columns:repeat(2,1fr)}.signal-card{grid-template-columns:130px minmax(0,1fr)}.signal-action{grid-column:2}}@media(max-width:600px){.opinion-page{padding:12px}.opinion-hero{padding:22px 18px}.opinion-hero h1{font-size:32px}.hero-actions{display:grid;grid-template-columns:1fr}.signal-overview{grid-template-columns:1fr 1fr}.signal-overview>*{border-bottom:1px solid #e3ecea}.signals-panel{padding:16px}.filters,.form-grid{grid-template-columns:1fr}.filters :deep(.el-button){min-height:44px}.signal-card{grid-template-columns:1fr;gap:12px}.signal-type{align-self:auto}.signal-action{grid-column:1}.signal-action :deep(.el-button){width:100%}.signal-content dl{display:grid;gap:7px}.signal-overview>button,.signal-overview>div{padding:16px}.hero-actions :deep(.el-button){width:100%;margin:0}}
@media(prefers-reduced-motion:reduce){.signal-card,.signal-overview>button{transition:none}}
</style>
