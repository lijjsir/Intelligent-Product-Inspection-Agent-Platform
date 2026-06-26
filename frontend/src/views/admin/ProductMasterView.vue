<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { productMasterApi } from "@/api/product-master.api";
import { formatCodeName } from "@/utils/master-data-labels";
import type {
  ProductBatch,
  ProductBatchPayload,
  ProductLine,
  ProductLinePayload,
  ProductSku,
  ProductSkuPayload,
} from "@/types/governance.types";

type DialogMode = "line" | "sku" | "batch";

const loading = ref(false);
const saving = ref(false);
const dialogOpen = ref(false);
const dialogMode = ref<DialogMode>("line");
const editingId = ref("");
const productLines = ref<ProductLine[]>([]);
const productSkus = ref<ProductSku[]>([]);
const productBatches = ref<ProductBatch[]>([]);

const lineForm = reactive<ProductLinePayload>({
  code: "",
  name: "",
  description: "",
  is_active: true,
});
const skuForm = reactive<ProductSkuPayload>({
  product_line_id: "",
  code: "",
  name: "",
  description: "",
  is_active: true,
});
const batchForm = reactive<ProductBatchPayload>({
  product_sku_id: "",
  batch_no: "",
  name: "",
  production_date: null,
  description: "",
  is_active: true,
});

const activeLines = computed(() => productLines.value.filter((item) => item.is_active));
const activeSkus = computed(() => productSkus.value.filter((item) => item.is_active));
const activeBatches = computed(() => productBatches.value.filter((item) => item.is_active));
const dialogTitle = computed(() => {
  const verb = editingId.value ? "编辑" : "新增";
  const name = dialogMode.value === "line" ? "产品线" : dialogMode.value === "sku" ? "SKU" : "批次";
  return `${verb}${name}`;
});

function resetForms() {
  editingId.value = "";
  Object.assign(lineForm, { code: "", name: "", description: "", is_active: true });
  Object.assign(skuForm, { product_line_id: activeLines.value[0]?.id || "", code: "", name: "", description: "", is_active: true });
  Object.assign(batchForm, {
    product_sku_id: activeSkus.value[0]?.id || "",
    batch_no: "",
    name: "",
    production_date: null,
    description: "",
    is_active: true,
  });
}

async function loadCatalog() {
  loading.value = true;
  try {
    const { data } = await productMasterApi.catalog(true);
    productLines.value = data.data.product_lines;
    productSkus.value = data.data.product_skus;
    productBatches.value = data.data.product_batches;
  } finally {
    loading.value = false;
  }
}

function openCreate(mode: DialogMode) {
  resetForms();
  dialogMode.value = mode;
  dialogOpen.value = true;
}

function openEditLine(item: ProductLine) {
  resetForms();
  dialogMode.value = "line";
  editingId.value = item.id;
  Object.assign(lineForm, {
    code: item.code,
    name: item.name,
    description: item.description || "",
    is_active: item.is_active,
  });
  dialogOpen.value = true;
}

function openEditSku(item: ProductSku) {
  resetForms();
  dialogMode.value = "sku";
  editingId.value = item.id;
  Object.assign(skuForm, {
    product_line_id: item.product_line_id,
    code: item.code,
    name: item.name,
    description: item.description || "",
    is_active: item.is_active,
  });
  dialogOpen.value = true;
}

function openEditBatch(item: ProductBatch) {
  resetForms();
  dialogMode.value = "batch";
  editingId.value = item.id;
  Object.assign(batchForm, {
    product_sku_id: item.product_sku_id,
    batch_no: item.batch_no,
    name: item.name,
    production_date: item.production_date || null,
    description: item.description || "",
    is_active: item.is_active,
  });
  dialogOpen.value = true;
}

function validateCurrentForm() {
  if (dialogMode.value === "line" && (!lineForm.code.trim() || !lineForm.name.trim())) {
    throw new Error("请填写产品线编码和名称");
  }
  if (dialogMode.value === "sku" && (!skuForm.product_line_id || !skuForm.code.trim() || !skuForm.name.trim())) {
    throw new Error("请选择产品线，并填写 SKU 编码和名称");
  }
  if (dialogMode.value === "batch" && (!batchForm.product_sku_id || !batchForm.batch_no.trim())) {
    throw new Error("请选择 SKU，并填写批次号");
  }
}

async function submit() {
  try {
    validateCurrentForm();
  } catch (error) {
    ElMessage.warning(error instanceof Error ? error.message : "请补全表单");
    return;
  }
  saving.value = true;
  try {
    if (dialogMode.value === "line") {
      if (editingId.value) await productMasterApi.updateLine(editingId.value, lineForm);
      else await productMasterApi.createLine(lineForm);
    } else if (dialogMode.value === "sku") {
      if (editingId.value) await productMasterApi.updateSku(editingId.value, skuForm);
      else await productMasterApi.createSku(skuForm);
    } else if (editingId.value) {
      await productMasterApi.updateBatch(editingId.value, batchForm);
    } else {
      await productMasterApi.createBatch(batchForm);
    }
    ElMessage.success("主数据已保存");
    dialogOpen.value = false;
    await loadCatalog();
  } finally {
    saving.value = false;
  }
}

async function removeLine(item: ProductLine) {
  await ElMessageBox.confirm(`确认删除产品线「${item.name}」？如已关联 SKU，请先处理 SKU。`, "删除产品线", { type: "warning" });
  await productMasterApi.deleteLine(item.id);
  ElMessage.success("产品线已删除");
  await loadCatalog();
}

async function removeSku(item: ProductSku) {
  await ElMessageBox.confirm(`确认删除 SKU「${item.name}」？如已关联批次，请先处理批次。`, "删除 SKU", { type: "warning" });
  await productMasterApi.deleteSku(item.id);
  ElMessage.success("SKU 已删除");
  await loadCatalog();
}

async function removeBatch(item: ProductBatch) {
  await ElMessageBox.confirm(`确认删除批次「${item.batch_no}」？`, "删除批次", { type: "warning" });
  await productMasterApi.deleteBatch(item.id);
  ElMessage.success("批次已删除");
  await loadCatalog();
}

onMounted(loadCatalog);
</script>

<template>
  <div class="product-master-page">
    <section class="hero">
      <div>
        <p class="eyebrow">Product Master Data</p>
        <h2>产品、SKU 与批次</h2>
        <p>维护正式主数据。任务创建只允许选择这里启用的产品线、SKU 和批次，避免产品概念继续散落在任务字段里。</p>
      </div>
      <div class="hero-actions">
        <el-button @click="loadCatalog">刷新</el-button>
        <el-button type="primary" @click="openCreate('line')">新增产品线</el-button>
      </div>
    </section>

    <section class="metrics">
      <el-card shadow="never"><span>产品线</span><strong>{{ activeLines.length }}</strong></el-card>
      <el-card shadow="never"><span>SKU</span><strong>{{ activeSkus.length }}</strong></el-card>
      <el-card shadow="never"><span>批次</span><strong>{{ activeBatches.length }}</strong></el-card>
    </section>

    <el-card shadow="never" class="table-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <h3>产品线</h3>
            <p>按组织隔离的一级产品分类，可停用但不建议随意删除已使用主数据。</p>
          </div>
          <el-button type="primary" plain @click="openCreate('line')">新增产品线</el-button>
        </div>
      </template>
      <el-table :data="productLines" size="small">
        <el-table-column prop="code" label="编码" width="160" />
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditLine(row)">编辑</el-button>
            <el-button link type="danger" @click="removeLine(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="table-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <h3>SKU</h3>
            <p>SKU 绑定到产品线，是新质检任务中的正式产品对象。</p>
          </div>
          <el-button type="primary" plain @click="openCreate('sku')">新增 SKU</el-button>
        </div>
      </template>
      <el-table :data="productSkus" size="small">
        <el-table-column prop="code" label="SKU 编码" width="160" />
        <el-table-column prop="name" label="SKU 名称" min-width="180" />
        <el-table-column label="产品线" width="200">
          <template #default="{ row }">{{ formatCodeName({ code: row.product_line_code, name: row.product_line_name }) }}</template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditSku(row)">编辑</el-button>
            <el-button link type="danger" @click="removeSku(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="table-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <h3>批次</h3>
            <p>批次绑定到 SKU，新任务必选。历史数据会自动归入“未指定批次”。</p>
          </div>
          <el-button type="primary" plain @click="openCreate('batch')">新增批次</el-button>
        </div>
      </template>
      <el-table :data="productBatches" size="small">
        <el-table-column prop="batch_no" label="批次号" width="160" />
        <el-table-column prop="name" label="批次名称" min-width="160" />
        <el-table-column label="SKU" min-width="180">
          <template #default="{ row }">{{ formatCodeName({ code: row.product_sku_code, name: row.product_sku_name }) }}</template>
        </el-table-column>
        <el-table-column label="产品线" width="200">
          <template #default="{ row }">{{ formatCodeName({ code: row.product_line_code, name: row.product_line_name }) }}</template>
        </el-table-column>
        <el-table-column prop="production_date" label="生产日期" width="130" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditBatch(row)">编辑</el-button>
            <el-button link type="danger" @click="removeBatch(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="dialogOpen" :title="dialogTitle" size="520px">
      <el-form v-if="dialogMode === 'line'" label-position="top">
        <el-form-item label="产品线编码">
          <el-input v-model="lineForm.code" placeholder="如 line-a" />
        </el-form-item>
        <el-form-item label="产品线名称">
          <el-input v-model="lineForm.name" placeholder="如 电子装配线 A" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="lineForm.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="lineForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>

      <el-form v-else-if="dialogMode === 'sku'" label-position="top">
        <el-form-item label="产品线">
          <el-select v-model="skuForm.product_line_id" filterable placeholder="选择产品线" class="!w-full">
            <el-option v-for="line in productLines" :key="line.id" :label="formatCodeName(line)" :value="line.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="SKU 编码">
          <el-input v-model="skuForm.code" placeholder="如 SKU-A-001" />
        </el-form-item>
        <el-form-item label="SKU 名称">
          <el-input v-model="skuForm.name" placeholder="如 螺丝组件 A 款" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="skuForm.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="skuForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>

      <el-form v-else label-position="top">
        <el-form-item label="SKU">
          <el-select v-model="batchForm.product_sku_id" filterable placeholder="选择 SKU" class="!w-full">
            <el-option v-for="sku in productSkus" :key="sku.id" :label="formatCodeName(sku)" :value="sku.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="批次号">
          <el-input v-model="batchForm.batch_no" placeholder="如 BATCH-20260619-01" />
        </el-form-item>
        <el-form-item label="批次名称">
          <el-input v-model="batchForm.name" placeholder="默认可与批次号一致" />
        </el-form-item>
        <el-form-item label="生产日期">
          <el-date-picker v-model="batchForm.production_date" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="batchForm.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="batchForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.product-master-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(14, 116, 144, 0.14), transparent 26%),
    linear-gradient(180deg, #ecfeff 0%, #f8fafc 100%);
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 24px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 86% 16%, rgba(103, 232, 249, 0.24), transparent 30%),
    linear-gradient(135deg, #083344 0%, #155e75 54%, #0e7490 100%);
  color: #f8fafc;
  box-shadow: 0 24px 60px rgba(8, 51, 68, 0.16);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(207, 250, 254, 0.86);
}

.hero h2 {
  margin: 0;
  font-size: 30px;
}

.hero p:last-child {
  max-width: 760px;
  margin: 10px 0 0;
  color: rgba(236, 254, 255, 0.88);
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  gap: 10px;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.metrics :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.metrics span {
  color: #64748b;
}

.metrics strong {
  color: #155e75;
  font-size: 30px;
}

.table-card {
  border-radius: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-header h3 {
  margin: 0;
  color: #155e75;
}

.card-header p {
  margin: 6px 0 0;
  color: #64748b;
}

@media (max-width: 820px) {
  .product-master-page {
    padding: 14px;
  }

  .hero,
  .card-header {
    flex-direction: column;
    align-items: start;
  }

  .metrics {
    grid-template-columns: 1fr;
  }
}
</style>
