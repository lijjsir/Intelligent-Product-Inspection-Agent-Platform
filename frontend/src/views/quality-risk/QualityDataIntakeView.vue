<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, type UploadFile } from "element-plus";
import { Connection, DocumentAdd, RefreshRight, UploadFilled } from "@element-plus/icons-vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import LocationPicker from "@/components/business/quality-risk/LocationPicker.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import {
  RECORD_TYPE_LABELS,
  type LocationRef,
  type QualityRecordType,
  type QualitySourceRecord,
} from "@/types/quality-risk.types";

const auth = useAuthStore();
const route = useRoute();
const refs = useQualityReferenceStore();
const records = ref<QualitySourceRecord[]>([]);
const total = ref(0);
const page = ref(1);
const listLoading = ref(false);
const referenceLoading = ref(false);
const saving = ref(false);
const recordDialog = ref(false);
const sourceDialog = ref(false);
const importDialog = ref(false);
const selected = ref<QualitySourceRecord | null>(null);
const attachments = ref<File[]>([]);
const importFile = ref<File | null>(null);
const importPreview = ref<any>(null);
const keyword = ref("");
const recordType = ref<QualityRecordType | "">(
  (route.query.record_type as QualityRecordType | undefined) || "",
);

const canManageSources = computed(() => auth.role === "admin");
const canCreate = computed(() => ["admin", "user", "expert"].includes(auth.role));

const sourceForm = reactive({
  code: "",
  name: "",
  source_type: "consumer_complaint",
  connector_type: "manual",
});

const form = reactive({
  source_id: "",
  external_record_id: "",
  record_type: "consumer_complaint" as QualityRecordType,
  occurred_at: new Date().toISOString(),
  text: "",
  risk_type: "",
  risk_level: "",
  category_id: "",
  product_id: "",
  production_batch_ref: "",
  unit_serial_ref: "",
  enterprise_name: "",
  location: { location_method: "unknown" } as LocationRef,
});

const recordTypes = Object.entries(RECORD_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const filteredProducts = computed(() =>
  refs.products.filter((item) => !form.category_id || item.category_id === form.category_id),
);

function resetForm() {
  Object.assign(form, {
    source_id: refs.sources.find((item) => item.status === "active")?.id || "",
    external_record_id: "",
    record_type: "consumer_complaint",
    occurred_at: new Date().toISOString(),
    text: "",
    risk_type: "",
    risk_level: "",
    category_id: "",
    product_id: "",
    production_batch_ref: "",
    unit_serial_ref: "",
    enterprise_name: "",
    location: { location_method: "unknown" },
  });
  attachments.value = [];
}

async function loadRecords() {
  listLoading.value = true;
  try {
    const response = await qualityRiskApi.records({
      page: page.value,
      size: 20,
      keyword: keyword.value || undefined,
      record_type: recordType.value || undefined,
    });
    records.value = response.data.data.items;
    total.value = response.data.data.total;
  } finally {
    listLoading.value = false;
  }
}

async function ensureReferences() {
  referenceLoading.value = true;
  try {
    await Promise.all([refs.loadSources(), refs.loadProducts()]);
  } finally {
    referenceLoading.value = false;
  }
}

async function openRecordDialog() {
  resetForm();
  recordDialog.value = true;
  await ensureReferences();
  if (!form.source_id) form.source_id = refs.sources.find((item) => item.status === "active")?.id || "";
}

function fileChanged(file: UploadFile) {
  if (file.raw) attachments.value = [file.raw];
}

async function saveRecord() {
  if (!form.source_id || !form.text.trim()) {
    ElMessage.warning("请选择来源并填写原始内容");
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
      content: {
        text: form.text,
        ...(form.risk_type ? { risk_type: form.risk_type } : {}),
        ...(form.risk_level ? { risk_level: form.risk_level } : {}),
      },
      enterprise_ref: form.enterprise_name ? { name: form.enterprise_name } : {},
      product_ref: {
        category_id: form.category_id || null,
        product_id: form.product_id || null,
        production_batch_ref: form.production_batch_ref || null,
        unit_serial_ref: form.unit_serial_ref || null,
      },
      location: form.location,
      attachment_ids: uploaded.map((item) => item.id),
      provenance: { channel: "manual_form" },
    });
    recordDialog.value = false;
    ElMessage.success("原始资料已登记并生成可追溯证据");
    await loadRecords();
  } finally {
    saving.value = false;
  }
}

async function saveSource() {
  if (!sourceForm.code.trim() || !sourceForm.name.trim()) {
    ElMessage.warning("请填写来源编码和名称");
    return;
  }
  await qualityRiskApi.createSource({ ...sourceForm, config: {}, status: "active" });
  refs.invalidate("sources");
  await refs.loadSources(true);
  sourceDialog.value = false;
  ElMessage.success("数据来源已创建");
}

function importChanged(file: UploadFile) {
  importFile.value = file.raw || null;
  importPreview.value = null;
}

async function previewImport() {
  if (!form.source_id || !importFile.value) {
    ElMessage.warning("请选择来源和文件");
    return;
  }
  importPreview.value = (
    await qualityRiskApi.previewImport(
      form.source_id,
      `quality-import:${crypto.randomUUID()}`,
      importFile.value,
    )
  ).data.data;
}

async function confirmImport() {
  await qualityRiskApi.confirmImport(importPreview.value.id);
  importDialog.value = false;
  ElMessage.success(`已确认导入 ${importPreview.value.valid_count} 条资料`);
  await loadRecords();
}

async function openImportDialog() {
  importFile.value = null;
  importPreview.value = null;
  importDialog.value = true;
  await refs.loadSources();
  form.source_id = refs.sources.find((item) => item.status === "active")?.id || "";
}

async function downloadTemplate() {
  const blob = (await qualityRiskApi.importTemplate()).data as Blob;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "质量数据导入模板.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

async function showRecord(row: QualitySourceRecord) {
  selected.value = row;
}

onMounted(loadRecords);
</script>

<template>
  <main class="intake-page">
    <header class="intake-hero">
      <div>
        <p class="kicker">QUALITY DATA INTAKE</p>
        <h1>质量数据接入</h1>
        <p class="lead">统一接收投诉、抽查、执法、企业信息、舆情、标准、报告和多媒体资料，每一条判断都能返回原始来源。</p>
      </div>
      <div class="hero-actions">
        <el-button v-if="canManageSources" :icon="Connection" @click="sourceDialog = true">登记来源</el-button>
        <el-button v-if="canCreate" :icon="UploadFilled" @click="openImportDialog">文件导入</el-button>
        <el-button v-if="canCreate" type="primary" :icon="DocumentAdd" @click="openRecordDialog">登记原始资料</el-button>
      </div>
    </header>

    <section class="source-strip">
      <article>
        <strong>13</strong><span>统一数据类型</span>
      </article>
      <article>
        <strong>{{ total }}</strong><span>已接入原始记录</span>
      </article>
      <article>
        <strong>可选</strong><span>型号、批次与序列号</span>
      </article>
      <article>
        <strong>100%</strong><span>来源与内容哈希留痕</span>
      </article>
    </section>

    <section class="records-panel">
      <div class="panel-head">
        <div>
          <p class="section-index">01 / SOURCE RECORDS</p>
          <h2>原始资料台账</h2>
        </div>
        <el-button :icon="RefreshRight" @click="loadRecords">刷新</el-button>
      </div>
      <div class="filters">
        <el-input v-model="keyword" clearable placeholder="搜索原始内容" @keyup.enter="loadRecords" />
        <el-select v-model="recordType" clearable placeholder="全部数据类型" @change="loadRecords">
          <el-option v-for="item in recordTypes" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-button type="primary" @click="loadRecords">查询</el-button>
      </div>
      <el-table :data="records" v-loading="listLoading" @row-click="showRecord">
        <el-table-column label="类型" width="140">
          <template #default="{ row }"><el-tag effect="plain">{{ RECORD_TYPE_LABELS[row.record_type as QualityRecordType] }}</el-tag></template>
        </el-table-column>
        <el-table-column label="原始内容" min-width="300">
          <template #default="{ row }"><span class="record-text">{{ row.content.text || row.content.description || row.external_record_id || "结构化记录" }}</span></template>
        </el-table-column>
        <el-table-column label="产品范围" min-width="180">
          <template #default="{ row }">{{ row.product_ref.production_batch_ref || row.product_ref.unit_serial_ref || (row.product_ref.product_id ? "具体产品" : row.product_ref.category_id ? "产品类别" : "尚未识别") }}</template>
        </el-table-column>
        <el-table-column prop="occurred_at" label="发生时间" width="190" />
        <el-table-column label="证据状态" width="110"><template #default="{ row }"><el-tag type="success">{{ row.normalization_status === "normalized" ? "已留痕" : row.normalization_status }}</el-tag></template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="loadRecords" />
    </section>

    <el-drawer :model-value="!!selected" title="来源与证据详情" size="min(560px, 94vw)" @update:model-value="($event) => { if (!$event) selected = null }">
      <template v-if="selected">
        <div class="detail-code">{{ selected.content_hash.slice(0, 16) }}</div>
        <h3>{{ RECORD_TYPE_LABELS[selected.record_type] }}</h3>
        <p class="detail-text">{{ selected.content.text || JSON.stringify(selected.content, null, 2) }}</p>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="外部记录编号">{{ selected.external_record_id || "未提供" }}</el-descriptions-item>
          <el-descriptions-item label="数据性质">{{ selected.data_nature }}</el-descriptions-item>
          <el-descriptions-item label="真实生产批次">{{ selected.product_ref.production_batch_ref || "未知" }}</el-descriptions-item>
          <el-descriptions-item label="单件序列号">{{ selected.product_ref.unit_serial_ref || "未提供" }}</el-descriptions-item>
          <el-descriptions-item label="地址">{{ selected.location.formatted_address || "未提供" }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>

    <el-dialog v-model="recordDialog" title="登记原始质量资料" width="min(900px, 95vw)" top="3vh" class="quality-record-dialog" :close-on-click-modal="false">
      <el-form label-position="top" v-loading="referenceLoading">
        <div class="form-grid">
          <el-form-item label="数据来源" required><el-select v-model="form.source_id" filterable><el-option v-for="item in refs.sources.filter(x => x.status === 'active')" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
          <el-form-item label="数据类型" required><el-select v-model="form.record_type"><el-option v-for="item in recordTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="发生时间" required><el-date-picker v-model="form.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item>
          <el-form-item label="外部记录编号（选填）"><el-input v-model="form.external_record_id" placeholder="例如投诉单号、报告号或执法案号" /></el-form-item>
        </div>
        <el-form-item label="原始内容" required><el-input v-model="form.text" type="textarea" :rows="5" placeholder="保留原始表述，不在录入时改写结论" /></el-form-item>
        <el-collapse>
          <el-collapse-item title="产品、企业与追溯范围（按来源选填）">
            <div class="form-grid">
              <el-form-item label="产品类别"><el-select v-model="form.category_id" clearable filterable @change="form.product_id = ''"><el-option v-for="item in refs.categories" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
              <el-form-item label="具体产品 / 型号"><el-select v-model="form.product_id" clearable filterable><el-option v-for="item in filteredProducts" :key="item.id" :label="[item.brand, item.name, item.model].filter(Boolean).join(' · ')" :value="item.id" /></el-select></el-form-item>
              <el-form-item label="涉及企业"><el-input v-model="form.enterprise_name" placeholder="能识别时填写" /></el-form-item>
              <el-form-item label="真实生产批次"><el-input v-model="form.production_batch_ref" placeholder="不知道时留空，系统不会生成伪批次" /></el-form-item>
              <el-form-item label="单件序列号"><el-input v-model="form.unit_serial_ref" placeholder="仅在一物一码或单件追溯时填写" /></el-form-item>
            </div>
          </el-collapse-item>
          <el-collapse-item title="地点（选填）"><LocationPicker v-model="form.location" /></el-collapse-item>
          <el-collapse-item title="附件与初始标签（选填）">
            <div class="form-grid">
              <el-form-item label="附件"><el-upload :auto-upload="false" :limit="1" accept="image/*,video/*,.pdf,.doc,.docx,.txt" :on-change="fileChanged"><el-button>选择图片、视频、PDF或文档</el-button></el-upload></el-form-item>
              <el-form-item label="来源已有风险类型"><el-input v-model="form.risk_type" placeholder="只记录来源中明确给出的标签" /></el-form-item>
              <el-form-item label="来源已有风险等级"><el-select v-model="form.risk_level" clearable><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer><el-button @click="recordDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRecord">保存并生成证据</el-button></template>
    </el-dialog>

    <el-dialog v-model="sourceDialog" title="登记质量数据来源" width="min(560px, 94vw)" top="6vh">
      <el-form label-position="top"><div class="form-grid"><el-form-item label="来源编码" required><el-input v-model="sourceForm.code" /></el-form-item><el-form-item label="来源名称" required><el-input v-model="sourceForm.name" /></el-form-item><el-form-item label="来源类型"><el-input v-model="sourceForm.source_type" /></el-form-item><el-form-item label="接入方式"><el-select v-model="sourceForm.connector_type"><el-option label="人工录入" value="manual" /><el-option label="文件导入" value="file" /><el-option label="API" value="api" /><el-option label="Webhook" value="webhook" /><el-option label="数据库同步" value="database_sync" /></el-select></el-form-item></div></el-form>
      <template #footer><el-button @click="sourceDialog = false">取消</el-button><el-button type="primary" @click="saveSource">保存来源</el-button></template>
    </el-dialog>

    <el-dialog v-model="importDialog" title="批量导入结构化资料" width="min(760px, 94vw)" top="6vh">
      <el-form label-position="top"><el-form-item label="数据来源" required><el-select v-model="form.source_id"><el-option v-for="item in refs.sources.filter(x => x.status === 'active')" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="CSV、XLSX或JSON"><el-upload :auto-upload="false" :limit="1" accept=".csv,.xlsx,.json" drag :on-change="importChanged"><el-icon><UploadFilled /></el-icon><div>拖入文件或点击选择</div></el-upload></el-form-item><div class="hero-actions"><el-button @click="downloadTemplate">下载模板</el-button><el-button :disabled="!importFile" @click="previewImport">校验并预览</el-button></div></el-form>
      <el-alert v-if="importPreview" :title="`有效 ${importPreview.valid_count} 条，错误 ${importPreview.error_count} 条；导入批次 ${importPreview.import_batch_code}`" :type="importPreview.error_count ? 'warning' : 'success'" :closable="false" />
      <template #footer><el-button @click="importDialog = false">取消</el-button><el-button type="primary" :disabled="!importPreview?.valid_count" @click="confirmImport">确认导入</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.intake-page { max-width: 1520px; margin: 0 auto; padding: 18px 20px 44px; color: #112a43; }
.intake-hero { display: flex; justify-content: space-between; gap: 28px; padding: 30px 34px; border: 1px solid #b8d7f2; border-radius: 18px; background: linear-gradient(120deg, #eef7ff 0%, #f9fcff 62%, #e8f7f2 100%); }
.kicker,.section-index { margin: 0 0 8px; color: #075fae; font: 700 11px/1.2 ui-monospace, monospace; letter-spacing: .14em; }
h1 { margin: 0; font-size: clamp(30px, 4vw, 48px); font-weight: 650; letter-spacing: -.04em; }
.lead { max-width: 760px; margin: 14px 0 0; color: #486581; line-height: 1.7; }
.hero-actions { display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
.source-strip { display: grid; grid-template-columns: repeat(4,1fr); margin: 18px 0; border: 1px solid #d9e5ef; border-radius: 14px; background: #fff; overflow: hidden; }
.source-strip article { padding: 20px 22px; border-right: 1px solid #e7eef5; }
.source-strip article:last-child { border-right: 0; }
.source-strip strong { display: block; font-size: 23px; color: #0a5d9f; }
.source-strip span { display: block; margin-top: 4px; color: #6b7f93; font-size: 12px; }
.records-panel { border: 1px solid #d9e5ef; border-radius: 16px; background: #fff; padding: 22px; box-shadow: 0 14px 36px rgba(37,76,112,.07); }
.panel-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
h2 { margin:0; font-size:24px; }
.filters { display:grid; grid-template-columns:minmax(220px,1fr) 220px auto; gap:10px; margin-bottom:14px; }
.record-text { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; line-height:1.5; }
.el-pagination { margin-top:18px; }
.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0 18px; }
.form-grid :deep(.el-select),.form-grid :deep(.el-date-editor) { width:100%; }
.detail-code { color:#087f8c; font:700 11px ui-monospace,monospace; letter-spacing:.12em; }
h3 { margin:10px 0; font-size:24px; }
.detail-text { padding:16px; border-radius:10px; background:#f4f8fb; white-space:pre-wrap; line-height:1.7; }
@media(max-width:850px){.intake-hero{flex-direction:column}.source-strip{grid-template-columns:repeat(2,1fr)}.filters{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}}
@media(max-width:520px){.intake-page{padding:12px}.intake-hero{padding:22px 18px}.source-strip{grid-template-columns:1fr}.source-strip article{border-right:0;border-bottom:1px solid #e7eef5}.hero-actions :deep(.el-button){width:100%;min-height:44px;margin-left:0}}
</style>
