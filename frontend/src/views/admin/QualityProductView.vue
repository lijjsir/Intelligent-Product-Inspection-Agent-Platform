<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { supervisionApi } from "@/api/supervision.api";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import { RECORD_TYPE_LABELS, type ProductCategoryV4, type QualityProduct,
  type QualityProductionBatch, type QualityProductLinks, type QualityProductCandidate } from "@/types/quality-risk.types";
import { formatServerDateTime } from "@/utils/date-time";
import { taskStatusLabel } from "@/utils/task-status";

const refs = useQualityReferenceStore();
const tab = ref("products"), keyword = ref(""), categoryFilter = ref("");
const loading = ref(false), saving = ref(false), formDrawer = ref(false);
const mode = ref<"category" | "product">("product"), editingId = ref("");
const categoryForm = reactive({ name: "", classification_basis: "" });
const productForm = reactive({ category_id: "", name: "", model: "", brand: "", manufacturer_enterprise_id: "" });
const initialBatchForm = reactive({ original_batch_no: "", production_date: "" });
const categoryEntryMethod = ref<"manual" | "file">("manual");
const importBusy = ref(false), importFile = ref<File | null>(null), commonBasis = ref("");
const importFiles = ref<UploadFile[]>([]);
const importPreview = ref<{ rows: Array<{ name: string; classification_basis: string | null }>; errors: Array<{ row: number; message: string }>; valid_count: number; can_confirm: boolean } | null>(null);
const basisExample = '《城口县2026年产品质量监督抽查实施细则》公告，附件7《城口县电线电缆产品质量监督抽查实施细则（2026年版）》，产品项：电线电缆。';
const basisExampleUrl = 'https://www.cqck.gov.cn/bm/scjgj/zwgk_70831/fdzdgknr_70834/cpzl/jcyj/202605/t20260526_15703868.html';
const candidates = ref<QualityProductCandidate[]>([]), candidatesLoading = ref(false), supplementingId = ref('');
let candidateTimer: ReturnType<typeof setTimeout> | undefined;
let candidateRequest = 0;
async function checkCandidates() {
  const request = ++candidateRequest;
  if (mode.value !== 'product' || editingId.value || !formDrawer.value || !productForm.category_id || productForm.name.trim().length < 2) {
    candidates.value = []; candidatesLoading.value = false; return [];
  }
  candidatesLoading.value = true;
  const snapshot = JSON.stringify(productForm);
  try {
    const rows = (await qualityRiskApi.productCandidates({ category_id: productForm.category_id, name: productForm.name.trim(),
      brand: productForm.brand.trim() || undefined, model: productForm.model.trim() || undefined,
      manufacturer_enterprise_id: productForm.manufacturer_enterprise_id || undefined })).data.data;
    if (request === candidateRequest && snapshot === JSON.stringify(productForm)) candidates.value = rows;
    return rows;
  } finally { if (request === candidateRequest) candidatesLoading.value = false; }
}
async function supplement(candidate: QualityProductCandidate) {
  const incoming = { ...productForm }, incomingIdentifiers = identifiers.value.map(item => ({ ...item }));
  const batchEntered = Boolean(initialBatchForm.original_batch_no.trim() || initialBatchForm.production_date);
  supplementingId.value = candidate.id;
  try {
    await refs.loadProducts(true);
    const existing = refs.products.find(item => item.id === candidate.id);
    if (!existing) { ElMessage.warning('档案已变更，请刷新后核对'); return; }
    editProduct(existing);
    if (!productForm.brand) productForm.brand = incoming.brand;
    if (!productForm.model) productForm.model = incoming.model;
    if (!productForm.manufacturer_enterprise_id) productForm.manufacturer_enterprise_id = incoming.manufacturer_enterprise_id;
    for (const item of incomingIdentifiers) {
      if (item.identifier_value.trim() && !identifiers.value.some(old => old.identifier_type === item.identifier_type && old.identifier_value === item.identifier_value)) identifiers.value.push(item);
    }
    ElMessage.success(batchEntered ? '已打开已有产品档案，请核对后保存；已填写的批次请在该产品详情中添加' : '已打开已有档案并补入缺失信息，请核对后保存；已有信息不会自动覆盖');
  } finally { supplementingId.value = ''; }
}
function fileChanged(file: UploadFile) { importFile.value = file.raw || null; importPreview.value = null; }
function resetImport() { importFiles.value = []; importFile.value = null; commonBasis.value = ""; importPreview.value = null; }
async function previewImport() {
  if (!importFile.value) return;
  importBusy.value = true;
  try { importPreview.value = (await qualityRiskApi.previewCategoryImport(importFile.value, commonBasis.value)).data.data; }
  finally { importBusy.value = false; }
}
async function confirmImport() {
  if (!importPreview.value?.can_confirm) return;
  importBusy.value = true;
  try {
    const result = (await qualityRiskApi.confirmCategoryImport(importPreview.value.rows)).data.data;
    formDrawer.value = false; importPreview.value = null;
    ElMessage.success(`新增 ${result.created_count} 个类别，复用 ${result.reused_count} 条已有类别`);
    refs.invalidate("products"); await load();
  } finally { importBusy.value = false; }
}
function downloadCategoryTemplate() {
  const url = URL.createObjectURL(new Blob(["\ufeff类别名称,分类依据\n"], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = "产品类别目录模板.csv"; anchor.click(); URL.revokeObjectURL(url);
}
const identifiers = ref<Array<{ identifier_type: string; identifier_value: string; source_id?: string | null }>>([]);
const enterprises = ref<Array<{ id: string; name: string }>>([]);
const enterprisesLoading = ref(false);
const title = computed(() => `${editingId.value ? "编辑" : "新增"}${mode.value === "category" ? "产品类别" : "具体产品"}`);
function containsKeyword(values: Array<string | null | undefined>, search: string) {
  const query = search.trim().toLocaleLowerCase();
  return !query || values.some(value => value?.toLocaleLowerCase().includes(query));
}
const filteredProducts = computed(() => refs.products.filter(item =>
  (!categoryFilter.value || item.category_id === categoryFilter.value) &&
  containsKeyword([item.name, item.brand, item.model,
    ...(item.batches || []).flatMap(batch => [batch.original_batch_no, batch.display_no])], keyword.value)));
const filteredCategories = computed(() => refs.categories.filter(item => item.name.includes(keyword.value.trim())));
const enterpriseName = (id?: string | null) => refs.products.find(item => item.manufacturer_enterprise_id === id)?.manufacturer_enterprise_name || enterprises.value.find(item => item.id === id)?.name || "未提供";
const detailDrawer = ref(false), detailProduct = ref<QualityProduct | null>(null), detailTab = ref("basic");
const detailLoading = ref(false), batches = ref<QualityProductionBatch[]>([]);
const batchKeyword = ref("");
const filteredBatches = computed(() => batches.value.filter(batch =>
  containsKeyword([batch.original_batch_no, batch.display_no], batchKeyword.value)));
const links = ref<QualityProductLinks>({ records: [], tasks: [] }), batchFilter = ref("");
const batchDialog = ref(false), batchSaving = ref(false), editingBatch = ref<QualityProductionBatch | null>(null);
const batchForm = reactive({ original_batch_no: "", production_date: "" });
const deletingId = ref("");
async function remove(kind: "category" | "product" | "batch", row: ProductCategoryV4 | QualityProduct | QualityProductionBatch) {
  const label = { category: "类别", product: "产品", batch: "批次" }[kind];
  const name = "name" in row ? row.name : row.original_batch_no || row.display_no || "原始批次号未知";
  try { await ElMessageBox.confirm(`删除${label}“${name}”？已被业务记录引用的记录不能删除。`, `删除${label}`, { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }); }
  catch { return; }
  deletingId.value = row.id;
  try {
    if (kind === "category") {
      await qualityRiskApi.deleteCategory(row.id);
      if (categoryFilter.value === row.id) categoryFilter.value = "";
    } else if (kind === "product") {
      await qualityRiskApi.deleteProduct(row.id);
      if (detailProduct.value?.id === row.id) { detailDrawer.value = false; detailProduct.value = null; }
    } else if (detailProduct.value) {
      await qualityRiskApi.deleteProductionBatch(detailProduct.value.id, row.id);
      batches.value = (await qualityRiskApi.productBatches(detailProduct.value.id)).data.data;
      if (batchFilter.value === row.id) await filterLinks();
    }
    refs.invalidate("products"); ElMessage.success(`${label}已删除`); await load();
  } catch { return; }
  finally { deletingId.value = ""; }
}

async function load() {
  loading.value = true;
  try {
    await refs.loadProducts(true);
    if (detailProduct.value) detailProduct.value = refs.products.find(item => item.id === detailProduct.value?.id) || detailProduct.value;
  } finally { loading.value = false; }
}
async function loadEnterprises(keyword = "") {
  enterprisesLoading.value = true;
  try {
    const data = (await supervisionApi.list("enterprises", { page: 1, size: 50, keyword: keyword || undefined, status: "active" })).data.data;
    const selected = enterprises.value.find(item => item.id === productForm.manufacturer_enterprise_id);
    enterprises.value = data.items.map(item => ({ id: item.id, name: item.name }));
    if (selected && !enterprises.value.some(item => item.id === selected.id)) enterprises.value.unshift(selected);
  } finally { enterprisesLoading.value = false; }
}
function reset() {
  candidates.value = []; candidateRequest += 1; candidatesLoading.value = false;
  categoryEntryMethod.value = "manual"; resetImport();
  editingId.value = ""; identifiers.value = [];
  Object.assign(categoryForm, { name: "", classification_basis: "" });
  Object.assign(productForm, { category_id: categoryFilter.value, name: "", model: "", brand: "", manufacturer_enterprise_id: "" });
  Object.assign(initialBatchForm, { original_batch_no: "", production_date: "" });
}
function create(kind: "category" | "product") { reset(); mode.value = kind; formDrawer.value = true; }
function editCategory(row: ProductCategoryV4) {
  reset(); mode.value = "category"; editingId.value = row.id;
  Object.assign(categoryForm, { name: row.name, classification_basis: row.classification_basis || "" });
  formDrawer.value = true;
}
function editProduct(row: QualityProduct) {
  reset(); mode.value = "product"; editingId.value = row.id;
  identifiers.value = row.identifiers.map(item => ({ identifier_type: item.identifier_type, identifier_value: item.identifier_value, source_id: item.source_id }));
  Object.assign(productForm, { category_id: row.category_id, name: row.name, model: row.model || "", brand: row.brand || "", manufacturer_enterprise_id: row.manufacturer_enterprise_id || "" });
  if (row.manufacturer_enterprise_id && row.manufacturer_enterprise_name && !enterprises.value.some(item => item.id === row.manufacturer_enterprise_id))
    enterprises.value.unshift({ id: row.manufacturer_enterprise_id, name: row.manufacturer_enterprise_name });
  formDrawer.value = true;
}
async function save() {
  if (mode.value === "category" && !categoryForm.name.trim()) { ElMessage.warning("请填写类别名称"); return; }
  if (mode.value === "product" && (!productForm.category_id || !productForm.name.trim())) { ElMessage.warning("请选择已有类别并填写具体产品名称"); return; }
  saving.value = true;
  try {
    if (mode.value === "category") {
      const payload = { name: categoryForm.name.trim(), classification_basis: categoryForm.classification_basis.trim() };
      if (editingId.value) await qualityRiskApi.updateCategory(editingId.value, payload);
      else await qualityRiskApi.createCategory(payload);
    } else {
      if (!editingId.value) {
        const possible = await checkCandidates();
        if (possible.length) {
          try { await ElMessageBox.confirm('已有名称相同或接近的产品。若是同一产品，请取消并点击“补充此档案”；确实不同才继续新建。', '核对疑似重复产品', { type: 'warning', confirmButtonText: '确认不同，继续新建', cancelButtonText: '返回核对' }); }
          catch { return; }
        }
      }
      const payload = { category_id: productForm.category_id, name: productForm.name.trim(),
        brand: productForm.brand.trim() || null, model: productForm.model.trim() || null,
        manufacturer_enterprise_id: productForm.manufacturer_enterprise_id || null,
        identifiers: identifiers.value.filter(item => item.identifier_value.trim()).map(item => ({ ...item, identifier_value: item.identifier_value.trim() })) };
      if (editingId.value) await qualityRiskApi.updateProduct(editingId.value, payload);
      else {
        const originalBatchNo = initialBatchForm.original_batch_no.trim();
        await qualityRiskApi.createProduct({ ...payload,
          ...(originalBatchNo || initialBatchForm.production_date ? { initial_batch: {
            original_batch_no: originalBatchNo || null, production_date: initialBatchForm.production_date || null,
          } } : {}),
        });
      }
    }
    refs.invalidate("products"); formDrawer.value = false; ElMessage.success("已保存"); await load();
  } finally { saving.value = false; }
}
async function showDetail(row: QualityProduct, initialTab = "basic") {
  detailProduct.value = row; detailTab.value = initialTab; batchFilter.value = ""; batchKeyword.value = "";
  batches.value = []; links.value = { records: [], tasks: [] }; detailDrawer.value = true;
  detailLoading.value = true;
  try {
    const [batchData, linkData] = await Promise.all([qualityRiskApi.productBatches(row.id), qualityRiskApi.productLinks(row.id)]);
    if (detailProduct.value?.id === row.id) { batches.value = batchData.data.data; links.value = linkData.data.data; }
  } finally { detailLoading.value = false; }
}
function openBatch(row?: QualityProductionBatch) {
  editingBatch.value = row || null;
  Object.assign(batchForm, { original_batch_no: row?.original_batch_no || "", production_date: row?.production_date || "" });
  batchDialog.value = true;
}
async function saveBatch() {
  if (!detailProduct.value) return;
  batchSaving.value = true;
  try {
    const payload = { original_batch_no: batchForm.original_batch_no.trim() || null, production_date: batchForm.production_date || null };
    if (editingBatch.value) await qualityRiskApi.updateProductionBatch(detailProduct.value.id, editingBatch.value.id, payload);
    else await qualityRiskApi.createProductionBatch(detailProduct.value.id, payload);
    batches.value = (await qualityRiskApi.productBatches(detailProduct.value.id)).data.data;
    refs.invalidate("products"); await load();
    batchDialog.value = false; ElMessage.success("批次已保存");
  } finally { batchSaving.value = false; }
}
async function filterLinks(id = "") {
  if (!detailProduct.value) return;
  batchFilter.value = id; detailTab.value = "links"; detailLoading.value = true;
  try { links.value = (await qualityRiskApi.productLinks(detailProduct.value.id, id)).data.data; }
  finally { detailLoading.value = false; }
}
watch(() => [mode.value, editingId.value, formDrawer.value, productForm.category_id, productForm.name, productForm.brand, productForm.model, productForm.manufacturer_enterprise_id], () => {
  if (candidateTimer) clearTimeout(candidateTimer);
  candidateTimer = setTimeout(() => { void checkCandidates().catch(() => { candidates.value = []; }); }, 350);
});
onUnmounted(() => { if (candidateTimer) clearTimeout(candidateTimer); candidateRequest += 1; });
onMounted(() => { void load(); void loadEnterprises(); });
</script>

<template>
  <main class="product-page">
    <header class="page-heading"><div><h1>产品目录</h1><p>维护产品与类别，在产品详情中查看批次及关联记录。</p></div>
      <div class="actions"><el-button @click="load">刷新</el-button><el-button type="primary" @click="create(tab === 'categories' ? 'category' : 'product')">{{ tab === 'categories' ? '新增类别' : '新增具体产品' }}</el-button></div>
    </header>
    <section class="catalog-card">
      <el-tabs v-model="tab" @tab-change="keyword = ''"><el-tab-pane label="产品列表" name="products" /><el-tab-pane label="类别管理" name="categories" /></el-tabs>
      <div class="filter-bar"><el-input v-model="keyword" clearable :placeholder="tab === 'products' ? '搜索产品、品牌、型号或批次号' : '搜索类别名称'" :aria-label="tab === 'products' ? '搜索产品' : '搜索类别'" />
        <el-select v-if="tab === 'products'" v-model="categoryFilter" clearable placeholder="全部类别" aria-label="筛选产品类别"><el-option v-for="item in refs.categories" :key="item.id" :label="item.name" :value="item.id" /></el-select>
      </div>
      <el-table v-if="tab === 'products'" v-loading="loading" :data="filteredProducts" empty-text="暂无具体产品；有具体产品资料时再建立档案">
        <el-table-column label="产品 / 类别" min-width="230"><template #default="{ row }"><div class="product-name">{{ row.name }}</div><div class="cell-secondary">{{ row.category_name }}</div></template></el-table-column>
        <el-table-column label="品牌 / 型号" min-width="150"><template #default="{ row }"><div>{{ row.brand || '品牌未提供' }}</div><div class="cell-secondary">{{ row.model || '型号未提供' }}</div></template></el-table-column>
        <el-table-column label="生产企业" min-width="150" show-overflow-tooltip><template #default="{ row }">{{ row.manufacturer_enterprise_name || enterpriseName(row.manufacturer_enterprise_id) }}</template></el-table-column>
        <el-table-column label="批次" min-width="145"><template #default="{ row }">
          <template v-if="row.batches?.length"><el-button link type="primary" @click="showDetail(row, 'batches')">{{ row.batches.length }} 个批次</el-button><el-tooltip :content="row.batches[0].original_batch_no || '原始批次号未提供'" placement="top"><div class="batch-preview">{{ row.batches[0].original_batch_no || '原始批次号未提供' }}</div></el-tooltip></template>
          <span v-else class="cell-secondary">暂无批次</span>
        </template></el-table-column>
        <el-table-column label="操作" width="195" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="showDetail(row)">详情</el-button><el-button link @click="editProduct(row)">编辑</el-button><el-button link type="danger" :loading="deletingId === row.id" :disabled="!!deletingId && deletingId !== row.id" @click="remove('product', row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-table v-else v-loading="loading" :data="filteredCategories" empty-text="暂无类别，可新增类别或导入已有类别目录">
        <el-table-column prop="name" label="类别名称" min-width="200" />
        <el-table-column label="分类依据" min-width="260" show-overflow-tooltip><template #default="{ row }"><span v-if="row.classification_basis">{{ row.classification_basis }}</span><el-tag v-else type="warning" size="small">依据待补充</el-tag></template></el-table-column>
        <el-table-column label="系统编号" min-width="220"><template #default="{ row }">{{ row.display_no || row.code }}</template></el-table-column>
        <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link type="primary" @click="editCategory(row)">编辑</el-button><el-button link type="danger" :loading="deletingId === row.id" :disabled="!!deletingId && deletingId !== row.id" @click="remove('category', row)">删除</el-button></template></el-table-column>
      </el-table>
    </section>

    <el-drawer v-model="detailDrawer" title="产品详情" size="min(920px,96vw)">
      <div v-if="detailProduct" v-loading="detailLoading" class="detail-content">
        <h2>{{ detailProduct.name }}</h2>
        <el-tabs v-model="detailTab">
          <el-tab-pane label="基本信息" name="basic">
            <el-descriptions :column="1" border><el-descriptions-item label="系统编号">{{ detailProduct.display_no || '未生成' }}</el-descriptions-item><el-descriptions-item label="产品类别">{{ detailProduct.category_name }}</el-descriptions-item><el-descriptions-item label="品牌">{{ detailProduct.brand || '未提供' }}</el-descriptions-item><el-descriptions-item label="型号 / 规格">{{ detailProduct.model || '未提供' }}</el-descriptions-item><el-descriptions-item label="生产企业">{{ enterpriseName(detailProduct.manufacturer_enterprise_id) }}</el-descriptions-item><el-descriptions-item label="外部标识">{{ detailProduct.identifiers.map(item => item.identifier_value).join('、') || '未提供' }}</el-descriptions-item></el-descriptions>
          </el-tab-pane>
          <el-tab-pane label="批次" name="batches">
            <div class="section-heading"><p>原始批次号与系统编号分别保存，未知信息可留空。</p><el-button type="primary" @click="openBatch()">新增批次</el-button></div>
            <el-input v-model="batchKeyword" class="batch-search" clearable placeholder="搜索原始批次号或系统编号" aria-label="搜索批次" />
            <el-table :data="filteredBatches" :empty-text="batchKeyword.trim() ? '没有匹配的批次' : '暂无已登记批次'">
              <el-table-column label="批次编号" min-width="235"><template #default="{ row }"><div class="batch-number">{{ row.original_batch_no || '原始批次号未提供' }}</div><div class="cell-secondary batch-number">系统编号：<span>{{ row.display_no || '未生成' }}</span></div></template></el-table-column>
              <el-table-column label="生产日期" min-width="120"><template #default="{ row }">{{ row.production_date || '未提供' }}</template></el-table-column>
              <el-table-column label="操作" width="195"><template #default="{ row }"><el-button link @click="openBatch(row)">编辑</el-button><el-button link type="primary" @click="filterLinks(row.id)">关联记录</el-button><el-button link type="danger" :loading="deletingId === row.id" :disabled="!!deletingId && deletingId !== row.id" @click="remove('batch', row)">删除</el-button></template></el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="关联记录" name="links">
            <div class="section-heading"><span>{{ batchFilter ? '所选批次的关联记录' : '该产品的关联记录' }}</span><el-button v-if="batchFilter" link @click="filterLinks()">查看全部批次</el-button></div>
            <h3>业务资料</h3><el-table :data="links.records" empty-text="暂无已关联的业务资料"><el-table-column prop="display_no" label="资料编号" min-width="220" /><el-table-column label="类型" min-width="110"><template #default="{ row }">{{ RECORD_TYPE_LABELS[row.record_type as keyof typeof RECORD_TYPE_LABELS] || row.record_type }}</template></el-table-column><el-table-column label="出处" min-width="120"><template #default="{ row }">{{ row.origin_label || '未提供' }}</template></el-table-column><el-table-column label="接收时间" min-width="170"><template #default="{ row }">{{ formatServerDateTime(row.received_at) }}</template></el-table-column></el-table>
            <h3>检测任务与结果</h3><el-table :data="links.tasks" empty-text="暂无已关联的检测任务"><el-table-column prop="display_no" label="任务编号" min-width="220" /><el-table-column label="状态" min-width="110"><template #default="{ row }">{{ taskStatusLabel(row.status) }}</template></el-table-column><el-table-column label="检测结果" min-width="120"><template #default="{ row }">{{ row.has_result ? '已生成' : '尚未生成' }}</template></el-table-column><el-table-column label="创建时间" min-width="170"><template #default="{ row }">{{ formatServerDateTime(row.created_at) }}</template></el-table-column></el-table>
            <p class="muted">显示最近 100 条关联资料和任务。</p>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>

    <el-drawer v-model="formDrawer" :title="title" size="min(600px,96vw)" :close-on-click-modal="false">
      <template v-if="mode === 'category'">
        <el-radio-group v-if="!editingId" v-model="categoryEntryMethod" class="category-entry-method" :disabled="saving || importBusy" aria-label="类别录入方式">
          <el-radio-button value="manual">手工填写</el-radio-button><el-radio-button value="file">文件批量导入</el-radio-button>
        </el-radio-group>
        <el-form v-if="editingId || categoryEntryMethod === 'manual'" label-position="top"><el-form-item label="类别名称" required><el-input v-model="categoryForm.name" maxlength="128" placeholder="填写项目采用的工业产品类别名称" /></el-form-item><el-form-item label="分类依据（选填，可后补）"><el-input v-model="categoryForm.classification_basis" type="textarea" :rows="4" maxlength="2000" placeholder="填写采用的目录/标准名称、版本和产品条目；不知道可先留空" /></el-form-item><details class="basis-example"><summary>查看一条填写示例</summary><p><strong>类别名称：</strong>电线电缆</p><p><strong>分类依据：</strong>{{ basisExample }}</p><el-link :href="basisExampleUrl" target="_blank" rel="noopener noreferrer" type="primary">查看示例出处</el-link></details><p class="muted">空着保存会标注“依据待补充”。依据记录类别出处，由管理员核对；检测判定仍使用检测标准。编号自动生成。</p></el-form>
        <div v-else>
          <p class="muted">从CSV / XLSX批量添加类别，最多1000行。列名：类别名称、分类依据；每行依据优先于共同依据。</p>
          <el-form label-position="top"><el-form-item label="共同分类依据（文件内未填写时使用）"><el-input v-model="commonBasis" type="textarea" :rows="2" @input="importPreview = null" /></el-form-item></el-form>
          <div class="actions import-actions"><el-upload v-model:file-list="importFiles" :auto-upload="false" :limit="1" accept=".csv,.xlsx" :on-change="fileChanged" :on-remove="() => { importFile = null; importPreview = null; }"><el-button>选择目录文件</el-button></el-upload><el-button @click="downloadCategoryTemplate">下载模板</el-button><el-button :loading="importBusy" :disabled="!importFile" @click="previewImport">校验与预览</el-button></div>
          <template v-if="importPreview"><p class="muted">有效 {{ importPreview.valid_count }} 行；错误 {{ importPreview.errors.length }} 行。同名类别复用，不覆盖已有依据。</p><el-table v-if="importPreview.errors.length" :data="importPreview.errors"><el-table-column prop="row" label="行号" width="70" /><el-table-column prop="message" label="需要修正" /></el-table><el-table :data="importPreview.rows" max-height="350"><el-table-column prop="name" label="类别名称" min-width="160" /><el-table-column prop="classification_basis" label="分类依据" min-width="240" /></el-table></template>
        </div>
      </template>
      <el-form v-else label-position="top">
        <el-form-item label="具体产品名称" required><el-input v-model="productForm.name" maxlength="255" placeholder="填写资料中的具体产品名称" /></el-form-item>
        <el-form-item label="所属类别" required><el-select v-model="productForm.category_id" filterable placeholder="选择已维护的类别"><el-option v-for="item in refs.categories" :key="item.id" :label="item.name" :value="item.id" /></el-select><p v-if="!refs.categories.length" class="muted">还没有类别，请先维护类别。</p><el-button v-if="!refs.categories.length" link type="primary" @click="formDrawer = false; tab = 'categories'">前往类别管理</el-button></el-form-item>
        <div class="form-grid"><el-form-item label="品牌（选填）"><el-input v-model="productForm.brand" maxlength="128" /></el-form-item><el-form-item label="型号 / 规格（选填）"><el-input v-model="productForm.model" maxlength="128" /></el-form-item></div>
        <el-form-item label="生产企业（选填）"><el-select v-model="productForm.manufacturer_enterprise_id" filterable remote :remote-method="loadEnterprises" :loading="enterprisesLoading" clearable placeholder="输入名称搜索企业档案"><el-option v-for="item in enterprises" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
        <p class="muted">未知的品牌、型号和企业可留空，确认后再补充已有档案。</p>
        <section v-if="!editingId" class="initial-batch" aria-labelledby="initial-batch-title">
          <h3 id="initial-batch-title">批次信息（选填）</h3>
          <div class="form-grid">
            <el-form-item label="原始批次号（选填）"><el-input v-model="initialBatchForm.original_batch_no" maxlength="128" placeholder="填写包装或原资料上的批次号" /></el-form-item>
            <el-form-item label="生产日期（选填）"><el-date-picker v-model="initialBatchForm.production_date" type="date" value-format="YYYY-MM-DD" placeholder="未知可留空" clearable /></el-form-item>
          </div>
          <p class="muted">填写后与产品一起保存，系统批次编号自动生成；两项都留空时不创建批次。后续批次可在产品详情中继续添加。</p>
        </section>
        <section v-if="!editingId && (candidatesLoading || candidates.length)" class="duplicate-candidates" aria-label="疑似已有产品档案">
          <strong>疑似已有档案，请先核对</strong><p v-if="candidatesLoading" class="muted">正在查找相同或接近的名称…</p>
          <div v-for="candidate in candidates" :key="candidate.id" class="candidate-row"><div><b>{{ candidate.name }}</b><p>{{ [candidate.brand || '品牌未知', candidate.model || '型号未知', candidate.manufacturer_enterprise_name || '企业未知'].join(' · ') }}</p><p>{{ candidate.reason }}{{ candidate.missing_fields.length ? `；可补充：${candidate.missing_fields.join('、')}` : '' }}</p></div><el-button size="small" type="primary" plain :loading="supplementingId === candidate.id" @click="supplement(candidate)">补充此档案</el-button></div>
          <p class="muted">提示供核对，不会自动合并。选择补充后请检查并保存，已有信息不会自动覆盖。</p>
        </section>
        <el-collapse><el-collapse-item title="补充信息：条码、来源产品编号" name="extra">
          <div class="section-heading"><span>外部标识（选填）</span><el-button size="small" @click="identifiers.push({ identifier_type: 'barcode', identifier_value: '' })">添加标识</el-button></div>
          <div v-for="(item, index) in identifiers" :key="index" class="identifier-row"><el-select v-model="item.identifier_type"><el-option label="条码" value="barcode" /><el-option label="来源产品编号" value="source_product_id" /><el-option label="来源SKU" value="sku" /><el-option label="型号代码" value="model_code" /></el-select><el-input v-model="item.identifier_value" maxlength="255" placeholder="填写原始资料中的标识" /><el-button text type="danger" @click="identifiers.splice(index, 1)">移除</el-button></div>
          <p class="muted">系统编号：{{ refs.products.find(item => item.id === editingId)?.display_no || '保存后自动生成' }}</p>
        </el-collapse-item></el-collapse>
      </el-form>
      <p v-if="mode === 'product'" class="muted">只有类别信息时，在类别管理中记录即可，不必建立同名产品档案。</p>
      <template #footer><el-button @click="formDrawer = false">取消</el-button><el-button v-if="mode === 'category' && !editingId && categoryEntryMethod === 'file'" type="primary" :disabled="!importPreview?.can_confirm" :loading="importBusy" @click="confirmImport">确认导入</el-button><el-button v-else type="primary" :loading="saving" @click="save">{{ mode === 'category' ? '保存类别' : '保存产品' }}</el-button></template>
    </el-drawer>
    <el-dialog v-model="batchDialog" :title="editingBatch ? '编辑批次' : '新增批次'" width="min(520px,94vw)" append-to-body :close-on-click-modal="false">
      <el-form label-position="top"><el-form-item label="所属产品"><el-input :model-value="detailProduct?.name" disabled /></el-form-item><el-form-item label="原始批次号（选填）"><el-input v-model="batchForm.original_batch_no" maxlength="128" placeholder="企业资料中有批次号时填写" /></el-form-item><el-form-item label="生产日期（选填）"><el-date-picker v-model="batchForm.production_date" type="date" value-format="YYYY-MM-DD" placeholder="未知可留空" /></el-form-item><p class="muted">系统编号：{{ editingBatch?.display_no || '保存后自动生成' }}</p></el-form>
      <template #footer><el-button @click="batchDialog = false">取消</el-button><el-button type="primary" :loading="batchSaving" @click="saveBatch">保存</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.product-name{font-weight:500;line-height:1.5;overflow-wrap:anywhere}.cell-secondary{font-size:12px;color:#748498;line-height:1.5;margin-top:4px}.batch-preview{font-size:12px;color:#748498;line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px}.batch-number{white-space:normal;overflow-wrap:anywhere}.batch-search{max-width:360px;margin-bottom:16px}
.initial-batch{margin:20px 0;padding:18px 18px 4px;border:1px solid #dce5ef;border-radius:10px;background:#f8fafc}.initial-batch h3{margin:0 0 16px;font-size:15px;font-weight:600}.initial-batch .el-form-item{margin-bottom:8px}.initial-batch .muted{margin:12px 0 14px}
.basis-example{padding:12px;border:1px solid #dce5ef;border-radius:8px;font-size:13px;line-height:1.7}.basis-example summary{cursor:pointer;color:#376492}.basis-example p{margin:8px 0}.duplicate-candidates{border:1px solid #e8cc94;background:#fffaf0;border-radius:10px;padding:14px;margin:14px 0}.candidate-row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #eadfcb}.candidate-row p{font-size:12px;color:#687b90;margin:4px 0;line-height:1.5}
.category-entry-method{margin-bottom:22px}.import-actions{flex-wrap:wrap;align-items:flex-start;margin-bottom:16px}
.product-page{max-width:1440px;margin:auto;padding:28px;color:#172d44}.page-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:24px}h1{margin:0;font-size:28px;font-weight:650}.page-heading p{margin:8px 0 0;color:#687b90;font-size:14px}.actions{display:flex;gap:8px}.catalog-card{border:1px solid #dce5ef;border-radius:12px;background:white;padding:12px 20px 24px}.filter-bar{display:flex;gap:12px;margin:12px 0 20px}.filter-bar .el-input{max-width:360px}.filter-bar .el-select{max-width:220px}.el-select,.el-date-editor{width:100%}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:14px 0}.section-heading p,.muted{color:#748498;font-size:13px;line-height:1.6}.identifier-row{display:grid;grid-template-columns:135px 1fr auto;gap:8px;margin-bottom:10px}.detail-content h2{font-size:22px;margin:0 0 18px}.detail-content h3{font-size:15px;margin:24px 0 12px}@media(max-width:640px){.product-page{padding:16px}.page-heading{align-items:flex-start;flex-direction:column}.filter-bar{flex-direction:column}.catalog-card{padding:10px 12px 20px}.filter-bar .el-select{max-width:none}.form-grid{grid-template-columns:1fr}.identifier-row{grid-template-columns:1fr}.section-heading{flex-wrap:wrap}}
</style>
