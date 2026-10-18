<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, type UploadFile, type UploadFiles } from "element-plus";
import { extractApiErrorMessage } from "@/api/http";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useAuthStore } from "@/stores/auth.store";
import LocationPicker from "@/components/business/quality-risk/LocationPicker.vue";
import type { LocationRef } from "@/types/quality-risk.types";
import KnowledgeSubmitDialog from "@/components/business/KnowledgeSubmitDialog.vue";
import MaterialTaskDraftDialog from "@/components/business/MaterialTaskDraftDialog.vue";
import { formatServerDateTime } from "@/utils/date-time";
import {
  RECORD_TYPE_LABELS,
  type QualityAttachment,
  type QualityRecordType,
  type QualitySourceRecord,
  type QualityRecordContext,
  type IntakeReferenceOptions,
} from "@/types/quality-risk.types";
defineProps<{ embedded?: boolean }>();
const auth = useAuthStore();
const route = useRoute(),
  router = useRouter();
const smallScreen = ref(window.innerWidth <= 650);
const onResize = () => {
  smallScreen.value = window.innerWidth <= 650;
};
const ownOnly = computed(() => !auth.hasPermission("quality_material_read_business"));
const canCreate = computed(() => auth.hasPermission("quality_material_submit"));
const canImport = computed(() => auth.hasPermission("quality_ingestion_manage"));
const records = ref<QualitySourceRecord[]>([]);
const total = ref(0),
  page = ref(1),
  loading = ref(false),
  saving = ref(false),
  importing = ref(false);
const recordDialog = ref(false),
  importDialog = ref(false);
const selected = ref<QualitySourceRecord | null>(null);
const knowledgeSubmitOpen = ref(false),
  taskDraftOpen = ref(false);
const products = ref<IntakeReferenceOptions["products"]>([]);
const categories = ref<IntakeReferenceOptions["categories"]>([]);
const enterprises = ref<IntakeReferenceOptions["enterprises"]>([]);
const enterpriseId = ref("");
const filterProductId = ref(""),
  filterEnterpriseId = ref("");
const referencesLoading = ref(false),
  referencesError = ref("");
let referenceEpoch = 0,
  listEpoch = 0,
  contextEpoch = 0;
const context = ref<QualityRecordContext | null>(null);
const contextLoading = ref(false),
  contextError = ref(""),
  listError = ref("");
const coreTypes = [
  { key: "", label: "全部资料" },
  { key: "consumer_complaint", label: "投诉资料" },
  { key: "public_opinion", label: "舆情资料" },
  { key: "inspection_report", label: "检测资料" },
];
const objectsDialog = ref(false),
  objectsSaving = ref(false);
const bindingError = ref(""),
  recordError = ref("");
const binding = reactive({
  enterprise_id: "",
  product_id: "",
  category_id: "",
  reason: "",
  expected_version: 0,
});
let bindingRecordId = "";
const bindingHistory = computed(() =>
  Array.isArray(selected.value?.provenance.object_binding_history)
    ? selected.value!.provenance.object_binding_history
    : [],
);
function openObjectBinding() {
  if (!selected.value || !context.value) return;
  bindingRecordId = selected.value.id;
  bindingError.value = "";
  const objects = context.value.objects;
  Object.assign(binding, {
    enterprise_id: objects.enterprise.id || "",
    product_id: objects.product.id || "",
    category_id: objects.category.id || "",
    reason: "",
    expected_version: Number(selected.value.provenance.object_binding_version || 0),
  });
  objectsDialog.value = true;
  void loadReferences();
}
async function saveObjectBinding() {
  if (objectsSaving.value || !binding.reason.trim()) {
    if (!binding.reason.trim()) ElMessage.warning("请填写关联依据");
    return;
  }
  objectsSaving.value = true;
  try {
    const result = (
      await qualityRiskApi.updateRecordObjects(bindingRecordId, {
        enterprise_id: binding.enterprise_id || null,
        product_id: binding.product_id || null,
        category_id: binding.category_id || null,
        reason: binding.reason,
        expected_version: binding.expected_version,
      })
    ).data.data;
    objectsDialog.value = false;
    ElMessage.success(
      Number(result.provenance.object_binding_version || 0) === binding.expected_version
        ? "关联未变化，保留原记录"
        : "关联已更新；引用本资料的旧研判需要重新核验",
    );
    if (selected.value?.id === bindingRecordId) await showRecord(result);
    await loadRecords();
  } catch (error) {
    bindingError.value = extractApiErrorMessage(error, "关联未能保存，请核对后重试");
  } finally {
    objectsSaving.value = false;
  }
}
async function reloadObjectBinding() {
  const reason = binding.reason;
  objectsDialog.value = false;
  await showRecord(bindingRecordId);
  if (context.value && selected.value) {
    openObjectBinding();
    binding.reason = reason;
    ElMessage.info("已读取最新关联，请重新核对后保存");
  }
}
const objectLabels = { enterprise: "关联企业", product: "关联产品", category: "产品类别" };
function mergeOptions<T extends { id: string }>(previous: T[], current: T[]): T[] {
  return [...new Map([...previous, ...current].map((item) => [item.id, item])).values()];
}
async function loadReferences(keyword = "") {
  const epoch = ++referenceEpoch;
  referencesLoading.value = true;
  referencesError.value = "";
  try {
    const options = (await qualityRiskApi.intakeReferences(keyword)).data.data;
    if (epoch !== referenceEpoch) return;
    products.value = mergeOptions(products.value, options.products);
    categories.value = mergeOptions(categories.value, options.categories);
    enterprises.value = mergeOptions(enterprises.value, options.enterprises);
  } catch (error) {
    if (epoch === referenceEpoch)
      referencesError.value = extractApiErrorMessage(
        error,
        "档案选项未能加载；请重试，原始描述仍可保存",
      );
  } finally {
    if (epoch === referenceEpoch) referencesLoading.value = false;
  }
}
function objectSummary(row: QualitySourceRecord) {
  const productName = products.value.find((item) => item.id === row.product_ref.product_id)?.name;
  const companyId = row.enterprise_ref.enterprise_id || row.enterprise_ref.id;
  const companyName = enterprises.value.find((item) => item.id === companyId)?.name;
  const product = row.product_ref.product_id
    ? productName || "已引用产品档案"
    : row.content.product_description
      ? `${row.content.product_description}（待确认）`
      : "产品待确认";
  const enterprise = companyId
    ? companyName || "已引用企业档案"
    : row.enterprise_ref.name
      ? `${row.enterprise_ref.name}（待确认）`
      : "企业待确认";
  return `${product} · ${enterprise}`;
}
function searchRecords() {
  page.value = 1;
  if (
    route.path === "/app/quality-data" &&
    (String(route.query.product_id || "") !== filterProductId.value ||
      String(route.query.enterprise_id || "") !== filterEnterpriseId.value ||
      String(route.query.record_type || "") !== recordType.value)
  ) {
    void router.replace({
      query: {
        ...route.query,
        product_id: filterProductId.value || undefined,
        enterprise_id: filterEnterpriseId.value || undefined,
        record_type: recordType.value || undefined,
      },
    });
    return;
  }
  void loadRecords();
}
function setRecordType(value: string) {
  recordType.value = value as QualityRecordType | "";
  searchRecords();
}
const categoryId = ref("");
const filteredProducts = computed(() =>
  products.value.filter((item) => !categoryId.value || item.category_id === categoryId.value),
);
watch(categoryId, () => {
  if (productId.value && !filteredProducts.value.some((item) => item.id === productId.value))
    productId.value = "";
});
const location = ref<LocationRef>({ location_method: "unknown" });
const productId = ref("");
watch(productId, (value) => {
  const product = products.value.find((item) => item.id === value);
  if (product) categoryId.value = product.category_id;
});
watch(
  () => binding.product_id,
  (value) => {
    if (!objectsDialog.value) return;
    const product = products.value.find((item) => item.id === value);
    if (product) binding.category_id = product.category_id;
  },
);
const selectedAttachments = ref<QualityAttachment[]>([]);
const files = ref<UploadFiles>([]),
  uploaded = ref<QualityAttachment[]>([]);
const keyword = ref(""),
  recordType = ref<QualityRecordType | "">("");
const otherRecordType = computed<QualityRecordType | "">({
  get: () => (coreTypes.some((item) => item.key === recordType.value) ? "" : recordType.value),
  set: (value) => {
    recordType.value = value;
  },
});
const importFile = ref<File | null>(null),
  importPreview = ref<any>(null),
  importRequestKey = ref("");
const importMapping = ref<Record<string, string>>({}),
  importColumns = ref<string[]>([]);
const form = reactive({
  record_type: "consumer_complaint" as QualityRecordType,
  text: "",
  origin_label: "",
  occurred_at: "",
  external_record_id: "",
  product_description: "",
  enterprise_name: "",
  production_batch_ref: "",
});
const importForm = reactive({ origin_label: "", record_type: "consumer_complaint" });
const types = Object.entries(RECORD_TYPE_LABELS);
const submissionTypes = types.filter(([type]) => type !== "standard_document");
const mappingFields = [
  ["text", "原始内容"],
  ["record_type", "资料类型"],
  ["occurred_at", "发生时间"],
  ["origin_label", "原始出处"],
  ["external_record_id", "外部编号"],
  ["enterprise_name", "原始企业描述"],
  ["enterprise_id", "关联企业ID"],
  ["product_id", "已有产品ID"],
  ["category_id", "已有类别ID"],
  ["production_batch_ref", "真实批次号"],
  ["unit_serial_ref", "单件序列号"],
];
async function loadRecords() {
  const epoch = ++listEpoch;
  loading.value = true;
  listError.value = "";
  try {
    const response = await qualityRiskApi.records({
      page: page.value,
      size: 20,
      record_type: recordType.value || undefined,
      keyword: keyword.value || undefined,
      product_id: filterProductId.value || undefined,
      enterprise_id: filterEnterpriseId.value || undefined,
    });
    if (epoch !== listEpoch) return;
    records.value = response.data.data.items;
    total.value = response.data.data.total;
  } catch (error) {
    if (epoch === listEpoch) {
      records.value = [];
      total.value = 0;
      listError.value = extractApiErrorMessage(error, "资料未能加载，请重试");
    }
  } finally {
    if (epoch === listEpoch) loading.value = false;
  }
}
function openRecord() {
  recordError.value = "";
  Object.assign(form, {
    record_type:
      recordType.value && recordType.value !== "standard_document"
        ? recordType.value
        : "consumer_complaint",
    text: "",
    origin_label: "",
    occurred_at: "",
    external_record_id: "",
    product_description: "",
    enterprise_name: "",
    production_batch_ref: "",
  });
  files.value = [];
  uploaded.value = [];
  productId.value = "";
  categoryId.value = "";
  enterpriseId.value = "";
  location.value = { location_method: "unknown" };
  recordDialog.value = true;
  void loadReferences();
}
function fileChanged(_file: UploadFile, list: UploadFiles) {
  files.value = list;
  uploaded.value = [];
}
async function saveRecord() {
  if (saving.value) return;
  if (!form.text.trim() && !files.value.length) {
    ElMessage.warning("请填写原始内容或选择附件");
    return;
  }
  saving.value = true;
  try {
    if (files.value.length && !uploaded.value.length)
      uploaded.value = (
        await qualityRiskApi.uploadAttachments(
          files.value.map((x) => x.raw).filter((x): x is NonNullable<typeof x> => !!x),
        )
      ).data.data;
    const response = await qualityRiskApi.createEvent({
      record_type: form.record_type,
      origin_label: form.origin_label || null,
      occurred_at: form.occurred_at ? new Date(form.occurred_at).toISOString() : null,
      external_record_id: form.external_record_id || null,
      content: {
        ...(form.text.trim() ? { text: form.text } : {}),
        ...(form.product_description ? { product_description: form.product_description } : {}),
      },
      enterprise_ref: {
        ...(form.enterprise_name ? { name: form.enterprise_name } : {}),
        ...(enterpriseId.value ? { enterprise_id: enterpriseId.value } : {}),
      },
      product_ref: {
        ...(categoryId.value ? { category_id: categoryId.value } : {}),
        ...(form.production_batch_ref ? { production_batch_ref: form.production_batch_ref } : {}),
        ...(productId.value
          ? {
              product_id: productId.value,
              category_id: products.value.find((item) => item.id === productId.value)?.category_id,
            }
          : {}),
      },
      location: location.value,
      attachment_ids: uploaded.value.map((x) => x.id),
      provenance: { channel: "manual_form" },
    });
    recordDialog.value = false;
    ElMessage.success(
      `${response.data.data.duplicate ? "资料已存在，复用受理记录" : "资料已受理"}：${response.data.data.display_no || response.data.data.id}`,
    );
    await loadRecords();
  } catch (error) {
    recordError.value = extractApiErrorMessage(error, "资料未能提交，请核对后重试");
  } finally {
    saving.value = false;
  }
}
function openImport() {
  importFile.value = null;
  importPreview.value = null;
  importMapping.value = {};
  importColumns.value = [];
  importRequestKey.value = crypto.randomUUID();
  importDialog.value = true;
}
function importChanged(file: UploadFile) {
  importFile.value = file.raw || null;
  importPreview.value = null;
  importMapping.value = {};
  importColumns.value = [];
  importRequestKey.value = crypto.randomUUID();
}
function mappingChanged() {
  importRequestKey.value = crypto.randomUUID();
  importPreview.value = null;
}
async function previewImport() {
  if (!importFile.value) {
    ElMessage.warning("请选择CSV、XLSX或JSON文件");
    return;
  }
  importing.value = true;
  try {
    importPreview.value = (
      await qualityRiskApi.previewImport(
        null,
        importRequestKey.value,
        importFile.value,
        importMapping.value,
        importForm.origin_label || null,
        importForm.record_type,
      )
    ).data.data;
    importMapping.value = { ...importPreview.value.mapping };
    importColumns.value = importPreview.value.source_columns;
  } finally {
    importing.value = false;
  }
}
async function confirmImport() {
  importing.value = true;
  try {
    const result = (await qualityRiskApi.confirmImport(importPreview.value.id)).data.data;
    importPreview.value = result;
    ElMessage.success(
      `导入完成：新建 ${result.created_count}，重复 ${result.duplicate_count}，失败 ${result.failed_count}`,
    );
    await loadRecords();
  } finally {
    importing.value = false;
  }
}
async function cancelImport() {
  if (importPreview.value?.status === "preview")
    await qualityRiskApi.cancelImport(importPreview.value.id);
  importDialog.value = false;
}
async function downloadTemplate() {
  const blob = (await qualityRiskApi.importTemplate()).data as unknown as Blob;
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "质量资料导入模板.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}
async function selectRecord(row: QualitySourceRecord) {
  if (route.path === "/app/quality-data" && route.query.record !== row.id) {
    await router.push({
      query: { ...route.query, record: row.id, record_type: recordType.value || undefined },
    });
  } else await showRecord(row);
}
async function showRecord(row: QualitySourceRecord | string) {
  const epoch = ++contextEpoch;
  selected.value = typeof row === "string" ? null : row;
  selectedAttachments.value = [];
  context.value = null;
  contextError.value = "";
  contextLoading.value = true;
  try {
    const value = (await qualityRiskApi.recordContext(typeof row === "string" ? row : row.id)).data
      .data;
    if (epoch !== contextEpoch) return;
    context.value = value;
    selected.value = value.record;
    selectedAttachments.value = value.attachments;
  } catch (error) {
    if (epoch === contextEpoch)
      contextError.value = extractApiErrorMessage(error, "资料关联信息未能加载，请重试");
  } finally {
    if (epoch === contextEpoch) contextLoading.value = false;
  }
}
async function downloadAttachment(file: QualityAttachment) {
  const blob = (await qualityRiskApi.downloadAttachment(file.id)).data as unknown as Blob;
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.file_name;
  anchor.click();
  URL.revokeObjectURL(url);
}
function closeDetail(value: boolean) {
  if (!value) {
    ++contextEpoch;
    selected.value = null;
    context.value = null;
    contextLoading.value = false;
    contextError.value = "";
    if (route.query.record) {
      const query = { ...route.query };
      delete query.record;
      void router.replace({ query });
    }
  }
}
async function applyRoute() {
  if (route.path !== "/app/quality-data") return;
  const type = String(route.query.record_type || "");
  filterProductId.value = String(route.query.product_id || "");
  filterEnterpriseId.value = String(route.query.enterprise_id || "");
  recordType.value = Object.prototype.hasOwnProperty.call(RECORD_TYPE_LABELS, type)
    ? (type as QualityRecordType)
    : "";
  page.value = 1;
  await loadRecords();
  if (route.query.record) await showRecord(String(route.query.record));
  if (route.query.create === "1" && canCreate.value) {
    openRecord();
    const query = { ...route.query };
    delete query.create;
    await router.replace({ query });
  }
}
watch(
  () => [
    route.query.record,
    route.query.create,
    route.query.record_type,
    route.query.product_id,
    route.query.enterprise_id,
  ],
  () => {
    void applyRoute();
  },
);
onMounted(() => {
  window.addEventListener("resize", onResize);
  void loadReferences();
  if (route.path === "/app/quality-data") void applyRoute();
  else void loadRecords();
});
onBeforeUnmount(() => window.removeEventListener("resize", onResize));
</script>
<template>
  <main class="intake-page" :class="{ embedded }">
    <header class="page-head">
      <div>
        <h1>{{ ownOnly ? "本人质量资料" : "数据采集" }}</h1>
        <p>统一接入投诉、舆情、抽检和报告等原始资料，保留出处，供监测与风险研判引用。</p>
      </div>
      <div class="actions">
        <el-button v-if="canImport" @click="openImport">文件导入</el-button
        ><el-button
          v-if="!embedded && auth.hasPermission('inspection_standard_library_read')"
          @click="router.push('/governance/admin/inspection-standards')"
          >查看标准资料</el-button
        ><el-button
          v-if="!embedded && auth.hasPermission('knowledge_read')"
          @click="router.push('/app/rag-spaces')"
          >查看知识资料</el-button
        ><el-button v-if="canCreate" type="primary" @click="openRecord">提交资料</el-button>
      </div>
    </header>
    <nav class="source-kinds" aria-label="资料分类">
      <button
        v-for="item in coreTypes"
        :key="item.key"
        type="button"
        :aria-pressed="recordType === item.key"
        :class="{ active: recordType === item.key }"
        @click="setRecordType(item.key)"
      >
        {{ item.label }}
      </button>
    </nav>
    <el-alert v-if="listError" :title="listError" type="error" :closable="false" />
    <div class="filters">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索原始内容或外部编号"
        @keyup.enter="searchRecords"
      /><el-select
        v-model="otherRecordType"
        clearable
        placeholder="其它资料类型"
        @change="searchRecords"
        ><el-option
          v-for="[value, label] in types.filter(
            ([value]) => !coreTypes.some((item) => item.key === value),
          )"
          :key="value"
          :label="label"
          :value="value" /></el-select
      ><el-select
        v-model="filterProductId"
        clearable
        filterable
        remote
        :remote-method="loadReferences"
        :loading="referencesLoading"
        placeholder="按关联产品筛选"
        @change="searchRecords"
        ><el-option
          v-for="product in products"
          :key="product.id"
          :value="product.id"
          :label="product.name" /></el-select
      ><el-select
        v-model="filterEnterpriseId"
        clearable
        filterable
        remote
        :remote-method="loadReferences"
        :loading="referencesLoading"
        placeholder="按关联企业筛选"
        @change="searchRecords"
        ><el-option
          v-for="enterprise in enterprises"
          :key="enterprise.id"
          :value="enterprise.id"
          :label="enterprise.name" /></el-select
      ><el-button @click="searchRecords">查询</el-button
      ><el-button @click="loadRecords">刷新</el-button>
    </div>
    <div v-if="smallScreen" class="mobile-records">
      <button v-for="row in records" :key="row.id" class="mobile-record" @click="selectRecord(row)">
        <strong>{{ row.content.text || row.content.description || "附件资料" }}</strong
        ><span
          >{{ RECORD_TYPE_LABELS[row.record_type] }} ·
          {{ row.provenance.origin_label || "出处未知" }}</span
        ><small>{{ row.display_no || "历史资料" }} · {{ objectSummary(row) }}</small>
      </button>
    </div>
    <el-table v-else :data="records" v-loading="loading" @row-click="selectRecord">
      <el-table-column label="受理编号" min-width="220"
        ><template #default="{ row }">{{ row.display_no || "历史资料" }}</template></el-table-column
      >
      <el-table-column label="类型" width="130"
        ><template #default="{ row }">{{
          RECORD_TYPE_LABELS[row.record_type as QualityRecordType]
        }}</template></el-table-column
      >
      <el-table-column label="原始材料" min-width="250"
        ><template #default="{ row }">{{
          row.content.text ||
          row.content.description ||
          (row.attachment_ids.length ? "附件资料" : "结构化资料")
        }}</template></el-table-column
      >
      <el-table-column label="关联对象" min-width="210"
        ><template #default="{ row }">{{ objectSummary(row) }}</template></el-table-column
      >
      <el-table-column label="原始出处" min-width="160"
        ><template #default="{ row }">{{
          row.provenance.origin_label || "未知"
        }}</template></el-table-column
      >
      <el-table-column label="发生 / 接收时间" min-width="190"
        ><template #default="{ row }"
          ><div>{{ row.occurred_at ? formatServerDateTime(row.occurred_at) : "发生时间未知" }}</div>
          <small class="muted">接收 {{ formatServerDateTime(row.received_at) }}</small></template
        ></el-table-column
      >
      <el-table-column label="状态" width="100"
        ><template #default><el-tag type="info">已受理</el-tag></template></el-table-column
      >
    </el-table>
    <el-pagination
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="loadRecords"
    />
    <el-drawer
      :model-value="!!selected || contextLoading || !!contextError"
      title="原始资料详情"
      size="min(620px,96vw)"
      append-to-body
      @update:model-value="closeDetail"
    >
      <template v-if="!selected"
        ><el-skeleton v-if="contextLoading" :rows="3" animated /><el-alert
          v-if="contextError"
          :title="contextError"
          type="error"
          :closable="false"
        /><el-button
          v-if="contextError && route.query.record"
          @click="showRecord(String(route.query.record))"
          >重试资料详情</el-button
        ></template
      >
      <template v-if="selected"
        ><h2>{{ selected.display_no || "历史资料" }}</h2>
        <p class="raw-text">
          {{ selected.content.text || JSON.stringify(selected.content, null, 2) }}
        </p>
        <el-alert
          v-if="contextError"
          :title="contextError"
          type="error"
          :closable="false"
        /><el-button v-if="contextError" @click="showRecord(selected)">重试关联信息</el-button>
        <el-skeleton v-if="contextLoading" :rows="2" animated />
        <section v-if="context" class="object-links" aria-label="关联档案">
          <div class="object-link-heading">
            <h3>关联档案</h3>
            <el-button
              v-if="
                canCreate &&
                (selected.created_by === auth.userId ||
                  auth.hasPermission('quality_material_read_business'))
              "
              link
              type="primary"
              @click="openObjectBinding"
              >确认或调整关联</el-button
            >
          </div>
          <p class="muted">档案引用与原始描述分别保存；未关联的对象保持待确认。</p>
          <dl>
            <template v-for="(label, key) in objectLabels" :key="key"
              ><dt>{{ label }}</dt>
              <dd>
                {{
                  context.objects[key].name ||
                  (context.objects[key].status === "unlinked" ? "待确认" : "档案不可用")
                }}
                <el-tag
                  v-if="context.objects[key].status === 'unavailable'"
                  type="warning"
                  size="small"
                  >已停用或不可用</el-tag
                >
              </dd></template
            >
          </dl>
        </section>
        <el-descriptions :column="1" border
          ><el-descriptions-item label="出处">{{
            selected.provenance.origin_label || "未知"
          }}</el-descriptions-item
          ><el-descriptions-item label="接入来源">{{
            context?.source.name || "来源待核对"
          }}</el-descriptions-item
          ><el-descriptions-item label="原始企业描述">{{
            selected.enterprise_ref.name || "未知"
          }}</el-descriptions-item
          ><el-descriptions-item label="原始产品描述">{{
            selected.content.product_description || "未提供"
          }}</el-descriptions-item
          ><el-descriptions-item label="发生时间">{{
            selected.occurred_at ? formatServerDateTime(selected.occurred_at) : "未知"
          }}</el-descriptions-item
          ><el-descriptions-item label="接收时间">{{
            formatServerDateTime(selected.received_at)
          }}</el-descriptions-item
          ><el-descriptions-item label="外部真实编号">{{
            selected.external_record_id || "未提供"
          }}</el-descriptions-item
          ><el-descriptions-item label="来源文件行号">{{
            selected.provenance.import_row || "不适用"
          }}</el-descriptions-item
          ><el-descriptions-item label="真实生产批次">{{
            selected.product_ref.production_batch_ref || "未知"
          }}</el-descriptions-item
          ><el-descriptions-item label="数据性质">{{
            { observed: "真实来源", inferred: "推断资料", synthetic: "模拟资料" }[
              selected.data_nature
            ] || selected.data_nature
          }}</el-descriptions-item></el-descriptions
        >
        <el-collapse v-if="selected.provenance.original_row"
          ><el-collapse-item title="查看导入原始行">
            <pre class="raw-text">{{
              JSON.stringify(selected.provenance.original_row, null, 2)
            }}</pre>
            <p class="muted">
              导入批次 {{ selected.provenance.import_batch_code || "未记录" }} · 原始行号
              {{ selected.provenance.import_row || "未记录" }}
            </p></el-collapse-item
          ></el-collapse
        >
        <section v-if="bindingHistory.length" class="binding-history">
          <h3>关联确认记录</h3>
          <article v-for="item in bindingHistory" :key="item.version">
            <strong>关联版本 {{ item.version }}</strong>
            <p>{{ item.reason }}</p>
            <template v-if="item.before_labels && item.after_labels"
              ><p
                v-for="(label, key) in objectLabels"
                :key="key"
                v-show="item.before_labels[key] !== item.after_labels[key]"
              >
                {{ label }}：{{ item.before_labels[key] || "待确认" }} →
                {{ item.after_labels[key] || "待确认" }}
              </p></template
            >
            <small
              >{{ item.actor_name || "已记录操作人" }} ·
              {{ formatServerDateTime(item.confirmed_at) }}</small
            >
          </article>
        </section>
        <el-alert
          v-if="context?.unavailable_attachment_ids.length"
          type="warning"
          :closable="false"
          :title="`${context.unavailable_attachment_ids.length} 个关联附件已撤回或不可用`"
        />
        <section v-if="context?.related_cases.length" class="related-cases">
          <h3>引用本资料的研判事项</h3>
          <el-button
            v-for="item in context.related_cases"
            :key="item.id"
            link
            type="primary"
            @click="router.push({ path: '/app/risk-assessments', query: { case_id: item.id } })"
            >{{ item.code }} · {{ item.title }}</el-button
          >
        </section>
        <div class="attachments">
          <el-button
            v-if="auth.hasPermission('knowledge_candidate_submit')"
            @click="knowledgeSubmitOpen = true"
            >从资料提出知识候选</el-button
          ><el-button
            v-if="['user', 'expert'].includes(auth.primaryRole) && auth.hasPermission('task')"
            @click="taskDraftOpen = true"
            >复用附件创建任务草稿</el-button
          ><el-button
            v-for="file in selectedAttachments"
            :key="file.id"
            @click="downloadAttachment(file)"
            >下载 {{ file.file_name }}</el-button
          >
        </div>
        <p class="muted">资料已受理；对象关联与风险结论分别核对。</p></template
      >
    </el-drawer>
    <KnowledgeSubmitDialog
      v-if="selected"
      v-model="knowledgeSubmitOpen"
      source-kind="intake_record"
      :source-id="selected.id"
    />
    <MaterialTaskDraftDialog v-if="selected" v-model="taskDraftOpen" :record-id="selected.id" />
    <el-dialog
      v-model="objectsDialog"
      title="确认资料对象关联"
      width="min(640px,94vw)"
      :close-on-click-modal="false"
      append-to-body
    >
      <p class="muted">
        仅确认档案引用，原文、原始描述、时间和附件保持不变。变更产品会取消旧批次档案关联，原始批次描述继续保留。
      </p>
      <el-alert v-if="referencesError" :title="referencesError" type="warning" :closable="false" />
      <el-alert v-if="bindingError" :title="bindingError" type="error" :closable="false" />
      <el-button v-if="bindingError" @click="reloadObjectBinding">重新核对最新关联</el-button>
      <el-form label-position="top">
        <el-form-item label="关联企业"
          ><el-select
            v-model="binding.enterprise_id"
            clearable
            filterable
            remote
            :remote-method="loadReferences"
            :loading="referencesLoading"
            placeholder="未知可留空"
            ><el-option
              v-for="item in enterprises"
              :key="item.id"
              :label="item.name"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-form-item label="关联产品"
          ><el-select
            v-model="binding.product_id"
            clearable
            filterable
            remote
            :remote-method="loadReferences"
            :loading="referencesLoading"
            placeholder="未知可留空"
            ><el-option
              v-for="item in products"
              :key="item.id"
              :label="item.name"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-form-item label="关联类别"
          ><el-select
            v-model="binding.category_id"
            clearable
            filterable
            remote
            :remote-method="loadReferences"
            :loading="referencesLoading"
            placeholder="已选产品时可从产品档案确认"
            ><el-option
              v-for="item in categories"
              :key="item.id"
              :label="item.name"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-form-item label="关联依据" required
          ><el-input
            v-model="binding.reason"
            type="textarea"
            :rows="3"
            maxlength="1000"
            placeholder="说明根据哪条原始资料确认或调整对象"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button :disabled="objectsSaving" @click="objectsDialog = false">取消</el-button
        ><el-button type="primary" :loading="objectsSaving" @click="saveObjectBinding"
          >保存关联</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="recordDialog"
      class="quality-intake-form"
      top="3vh"
      title="提交质量资料"
      width="min(700px,94vw)"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-alert v-if="recordError" :title="recordError" type="error" :closable="false" />
      <el-form label-position="top"
        ><el-form-item label="资料类型" required
          ><el-select v-model="form.record_type"
            ><el-option
              v-for="[value, label] in submissionTypes"
              :key="value"
              :label="label"
              :value="value" /></el-select></el-form-item
        ><el-form-item label="原始内容或附件（至少一种）"
          ><el-input
            v-model="form.text"
            type="textarea"
            :rows="4"
            placeholder="保留原话或原始材料内容"
          /><el-upload
            v-model:file-list="files"
            :auto-upload="false"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.xlsx,.json"
            :on-change="fileChanged"
            :on-remove="fileChanged"
            ><el-button>选择资料文件</el-button
            ><template #tip>单文件不超过50MB；文件选择后由系统保存。</template></el-upload
          ></el-form-item
        ><el-form-item label="原始出处（选填）"
          ><el-input
            v-model="form.origin_label"
            placeholder="如某单位提供的抽检资料；不知道时留空" /></el-form-item
        ><el-collapse
          ><el-collapse-item title="对象与发生时间（已有信息再填）"
            ><el-alert
              v-if="referencesError"
              :title="referencesError"
              type="warning"
              :closable="false" /><el-button v-if="referencesError" @click="loadReferences()"
              >重试档案选项</el-button
            >
            <el-form-item label="关联企业档案（选填）"
              ><el-select
                v-model="enterpriseId"
                clearable
                filterable
                remote
                :remote-method="loadReferences"
                :loading="referencesLoading"
                placeholder="已核对企业身份时选择；未知可空"
                ><el-option
                  v-for="enterprise in enterprises"
                  :key="enterprise.id"
                  :value="enterprise.id"
                  :label="enterprise.name" /></el-select
            ></el-form-item>
            <el-form-item label="产品类别（选填）"
              ><el-select
                v-model="categoryId"
                clearable
                filterable
                remote
                :remote-method="loadReferences"
                :loading="referencesLoading"
                placeholder="已确认类别时选择"
                ><el-option
                  v-for="category in categories"
                  :key="category.id"
                  :value="category.id"
                  :label="category.name" /></el-select
            ></el-form-item>
            <el-form-item label="关联已有产品（选填）"
              ><el-select
                v-model="productId"
                clearable
                filterable
                remote
                :remote-method="loadReferences"
                :loading="referencesLoading"
                placeholder="已确认对象时选择"
                ><el-option
                  v-for="product in filteredProducts"
                  :key="product.id"
                  :value="product.id"
                  :label="
                    [product.brand, product.name, product.model].filter(Boolean).join(' · ')
                  " /></el-select></el-form-item
            ><el-form-item label="产品原始描述"
              ><el-input
                v-model="form.product_description"
                placeholder="品牌、名称、型号可以直接按原资料描述"
            /></el-form-item>
            <div class="form-grid">
              <el-form-item label="原始企业描述"
                ><el-input v-model="form.enterprise_name" /></el-form-item
              ><el-form-item label="真实生产批次号"
                ><el-input v-model="form.production_batch_ref" /></el-form-item
              ><el-form-item label="实际发生时间"
                ><el-date-picker
                  v-model="form.occurred_at"
                  type="datetime"
                  value-format="YYYY-MM-DDTHH:mm:ss"
                  placeholder="未知可空" /></el-form-item
              ><el-form-item label="外部报告／投诉编号"
                ><el-input v-model="form.external_record_id"
              /></el-form-item>
            </div>
            <el-form-item label="发生地点（选填）"
              ><LocationPicker v-model="location" /></el-form-item></el-collapse-item
        ></el-collapse>
        <p class="muted">
          受理编号、提交人和接收时间自动生成。同一出处及外部编号的相同材料复用原记录。标准文件请在标准库上传，本次检测材料在新建任务中提供。
        </p></el-form
      >
      <template #footer
        ><el-button @click="recordDialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="saveRecord">提交</el-button></template
      >
    </el-dialog>
    <el-dialog
      v-model="importDialog"
      class="quality-intake-form"
      top="3vh"
      title="导入现有结构化资料"
      width="min(880px,96vw)"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-form label-position="top"
        ><div class="form-grid">
          <el-form-item label="默认资料类型"
            ><el-select v-model="importForm.record_type" @change="mappingChanged"
              ><el-option
                v-for="[value, label] in submissionTypes"
                :key="value"
                :label="label"
                :value="value" /></el-select></el-form-item
          ><el-form-item label="共同出处（选填，逐行出处优先）"
            ><el-input v-model="importForm.origin_label" @change="mappingChanged"
          /></el-form-item>
        </div>
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".csv,.xlsx,.json"
          :on-change="importChanged"
          ><el-button>选择CSV、XLSX或JSON</el-button></el-upload
        >
        <p class="muted">最多5000条、20MB。PDF和图片通过“提交资料”保存原件。</p>
        <el-button @click="downloadTemplate">下载模板</el-button
        ><el-button :loading="importing" :disabled="!importFile" @click="previewImport"
          >校验并预览</el-button
        ></el-form
      >
      <el-collapse v-if="importColumns.length"
        ><el-collapse-item title="核对列映射（中文列名会自动建议）"
          ><div class="form-grid">
            <el-form-item v-for="[field, label] in mappingFields" :key="field" :label="label"
              ><el-select v-model="importMapping[field]" clearable @change="mappingChanged"
                ><el-option
                  v-for="column in importColumns"
                  :key="column"
                  :label="column"
                  :value="column" /></el-select
            ></el-form-item></div></el-collapse-item
      ></el-collapse>
      <template v-if="importPreview"
        ><el-alert
          :closable="false"
          :type="importPreview.error_count ? 'warning' : 'success'"
          :title="`${importPreview.import_batch_code}：有效 ${importPreview.valid_count} 条，错误 ${importPreview.error_count} 条`" /><el-table
          v-if="importPreview.errors.length"
          :data="importPreview.errors"
          ><el-table-column prop="row" label="源行／条目" width="100" /><el-table-column
            prop="message"
            label="错误" /></el-table
        ><el-table v-else-if="importPreview.status === 'preview'" :data="importPreview.preview_rows"
          ><el-table-column label="内容"
            ><template #default="{ row }">{{
              row.content.text || "结构化材料"
            }}</template></el-table-column
          ><el-table-column label="出处"
            ><template #default="{ row }">{{
              row.origin_label || "未知"
            }}</template></el-table-column
          ><el-table-column label="对象"
            ><template #default="{ row }">{{
              row.product_ref.production_batch_ref ||
              row.enterprise_ref.name ||
              row.product_ref.product_id ||
              "待确认"
            }}</template></el-table-column
          ></el-table
        ><el-alert
          v-if="importPreview.status === 'confirmed'"
          :closable="false"
          type="success"
          :title="`已完成：新建 ${importPreview.created_count}，重复 ${importPreview.duplicate_count}，失败 ${importPreview.failed_count}`"
      /></template>
      <template #footer
        ><el-button @click="cancelImport">{{
          importPreview?.status === "confirmed" ? "关闭" : "取消"
        }}</el-button
        ><el-button
          type="primary"
          :loading="importing"
          :disabled="
            !importPreview ||
            importPreview.error_count > 0 ||
            !importPreview.valid_count ||
            importPreview.status !== 'preview'
          "
          @click="confirmImport"
          >确认导入</el-button
        ></template
      >
    </el-dialog>
  </main>
</template>
<style scoped>
.object-link-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.binding-history {
  margin: 18px 0;
}
.binding-history h3 {
  font-size: 15px;
}
.binding-history article {
  border-left: 2px solid #dce4ec;
  padding: 8px 12px;
  margin: 8px 0;
  font-size: 13px;
}
.binding-history article p {
  margin: 6px 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.binding-history small {
  color: #607386;
}

.source-kinds {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  border-bottom: 1px solid #dce4ec;
  margin-bottom: 16px;
}
.source-kinds button {
  padding: 10px 16px;
  min-height: 44px;
  border-bottom: 2px solid transparent;
  color: #607386;
}
.source-kinds button.active {
  border-bottom-color: #087f8c;
  color: #087f8c;
  font-weight: 600;
}
.source-kinds button:focus-visible {
  outline: 2px solid #087f8c;
  outline-offset: 2px;
}
.object-links,
.related-cases {
  margin: 18px 0;
  padding: 14px;
  border: 1px solid #dce4ec;
  border-radius: 6px;
}
.object-links h3,
.related-cases h3 {
  font-size: 15px;
  margin: 0 0 10px;
}
.object-links dl {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 10px;
  font-size: 13px;
}
.object-links dt {
  color: #607386;
}
.object-links dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.related-cases .el-button {
  display: flex;
  white-space: normal;
  text-align: left;
  height: auto;
  line-height: 1.6;
  margin: 10px 0;
}

.intake-page {
  padding: 24px;
  color: #20364a;
}
.embedded {
  padding: 0;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 22px;
}
h1 {
  font-size: 24px;
  margin: 0;
}
h2 {
  font-size: 18px;
}
.page-head p,
.muted {
  color: #607386;
  font-size: 13px;
}
.actions,
.filters,
.attachments {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.filters {
  margin-bottom: 16px;
}
.filters .el-input {
  max-width: 360px;
}
.filters .el-select {
  width: 180px;
}
.el-pagination {
  margin-top: 16px;
}
.el-select,
.el-date-editor {
  width: 100%;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 18px;
}
.raw-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.attachments {
  margin: 20px 0;
}
.el-alert,
.el-collapse,
.el-table {
  margin-top: 14px;
}
.el-form-item {
  margin-top: 12px;
}
@media (max-width: 650px) {
  .intake-page {
    padding: 14px;
  }
  .embedded {
    padding: 0;
  }
  .page-head {
    flex-direction: column;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .filters .el-input,
  .filters .el-select {
    max-width: none;
    width: 100%;
  }
}
</style>

<style>
.quality-intake-form.el-dialog {
  background: #fff !important;
  max-height: 94dvh;
  overflow: hidden;
}
.quality-intake-form .el-dialog__body {
  max-height: calc(94dvh - 150px);
  overflow: auto;
}
.mobile-records {
  display: grid;
  gap: 8px;
}
.mobile-record {
  display: grid;
  gap: 5px;
  text-align: left;
  border: 1px solid #dce4ec;
  padding: 12px;
  background: white;
  border-radius: 5px;
  color: #20364a;
  cursor: pointer;
}
.mobile-record strong {
  font-weight: 500;
  overflow-wrap: anywhere;
}
.mobile-record span,
.mobile-record small {
  color: #607386;
  font-size: 12px;
}
</style>
