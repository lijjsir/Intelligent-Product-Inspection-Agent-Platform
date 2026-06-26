<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { inspectionStandardApi } from "@/api/inspection-standard.api";
import { productMasterApi } from "@/api/product-master.api";
import { ragSpaceApi } from "@/api/rag-space.api";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { formatCodeName } from "@/utils/master-data-labels";
import type {
  InspectionStandardLibraryItem,
  InspectionStandardPayload,
  ProductLine,
  ProductSku,
} from "@/types/governance.types";
import type { RagSpace } from "@/types/rag-space.types";

const router = useRouter();
const inspectionSpecStore = useInspectionSpecStore();
const loading = ref(false);
const saving = ref(false);
const dialogOpen = ref(false);
const editingId = ref("");
const items = ref<InspectionStandardLibraryItem[]>([]);
const ragSpaces = ref<RagSpace[]>([]);
const productLines = ref<ProductLine[]>([]);
const productSkus = ref<ProductSku[]>([]);
const filters = reactive({
  productFamily: "",
  status: "all" as "all" | "active" | "inactive",
});
const form = reactive<InspectionStandardPayload>({
  name: "",
  product_family: "",
  inspection_spec_id: null,
  spec_code: null,
  applicable_product_line_ids: [],
  applicable_product_sku_ids: [],
  description: "",
  rag_space_ids: [],
  is_active: true,
});

const activeSpecOptions = computed(() => inspectionSpecStore.items.filter((item) => item.is_active));
const filteredItems = computed(() =>
  items.value.filter((item) => {
    const familyMatched = !filters.productFamily || item.product_family === filters.productFamily;
    const statusMatched =
      filters.status === "all" ||
      (filters.status === "active" && item.is_active) ||
      (filters.status === "inactive" && !item.is_active);
    return familyMatched && statusMatched;
  }),
);
const productFamilies = computed(() =>
  Array.from(new Set(items.value.map((item) => item.product_family).filter(Boolean))).sort(),
);
const selectedSpec = computed(() => activeSpecOptions.value.find((item) => item.id === form.inspection_spec_id) || null);
const selectedLineNames = computed(() =>
  (form.applicable_product_line_ids || [])
    .map((id) => {
      const line = productLines.value.find((item) => item.id === id);
      return line ? formatCodeName(line) : "";
    })
    .filter(Boolean)
    .join("、"),
);
const selectedSkuNames = computed(() =>
  (form.applicable_product_sku_ids || [])
    .map((id) => {
      const sku = productSkus.value.find((item) => item.id === id);
      return sku ? formatCodeName(sku) : "";
    })
    .filter(Boolean)
    .join("、"),
);

function resetForm() {
  editingId.value = "";
  Object.assign(form, {
    name: "",
    product_family: "",
    inspection_spec_id: null,
    spec_code: null,
    applicable_product_line_ids: [],
    applicable_product_sku_ids: [],
    description: "",
    rag_space_ids: [],
    is_active: true,
  });
}

async function loadAll() {
  loading.value = true;
  try {
    const [{ data: standards }, { data: spaces }, { data: catalog }] = await Promise.all([
      inspectionStandardApi.list(),
      ragSpaceApi.list(500),
      productMasterApi.catalog(false),
      inspectionSpecStore.fetchAll({ suppressErrorToast: true }),
    ]);
    items.value = standards.data;
    ragSpaces.value = spaces.data;
    productLines.value = catalog.data.product_lines;
    productSkus.value = catalog.data.product_skus;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  dialogOpen.value = true;
}

function openEdit(item: InspectionStandardLibraryItem) {
  editingId.value = item.id;
  Object.assign(form, {
    name: item.name,
    product_family: item.product_family,
    inspection_spec_id: item.inspection_spec_id || null,
    spec_code: item.spec_code || null,
    applicable_product_line_ids: [...(item.applicable_product_line_ids || [])],
    applicable_product_sku_ids: [...(item.applicable_product_sku_ids || [])],
    description: item.description || "",
    rag_space_ids: [...item.rag_space_ids],
    is_active: item.is_active,
  });
  dialogOpen.value = true;
}

function handleSpecChange(specId: string) {
  const spec = activeSpecOptions.value.find((item) => item.id === specId);
  if (!spec) return;
  form.spec_code = spec.spec_code;
  if (!form.name) form.name = spec.name;
  if (!form.product_family) form.product_family = spec.product_family || spec.product_id || spec.spec_code;
}

function validateForm() {
  if (!form.name.trim()) throw new Error("请填写标准名称");
  if (!form.product_family.trim()) throw new Error("请填写标准品类/产品族");
  if (!form.inspection_spec_id && !form.spec_code) throw new Error("请选择检测规则/门槛配置");
  if (form.rag_space_ids.length === 0) throw new Error("请至少绑定一个 RAG 空间");
}

async function submit() {
  try {
    validateForm();
  } catch (error) {
    ElMessage.warning(error instanceof Error ? error.message : "请补全检测标准配置");
    return;
  }
  saving.value = true;
  try {
    const payload: InspectionStandardPayload = {
      ...form,
      name: form.name.trim(),
      product_family: form.product_family.trim(),
      description: form.description?.trim() || null,
      spec_code: selectedSpec.value?.spec_code || form.spec_code || null,
    };
    if (editingId.value) {
      await inspectionStandardApi.update(editingId.value, payload);
      ElMessage.success("检测标准已更新");
    } else {
      await inspectionStandardApi.create(payload);
      ElMessage.success("检测标准已创建");
    }
    dialogOpen.value = false;
    await loadAll();
  } finally {
    saving.value = false;
  }
}

async function removeItem(item: InspectionStandardLibraryItem) {
  await ElMessageBox.confirm(`将删除“${item.name}”的检测标准，是否继续？`, "删除检测标准", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await inspectionStandardApi.remove(item.id);
  ElMessage.success("检测标准已删除");
  await loadAll();
}

function goKnowledgeSpace(item: InspectionStandardLibraryItem) {
  const targetId = item.rag_space_ids[0];
  if (!targetId) return;
  router.push({ path: "/app/rag-spaces", query: { spaceId: targetId, source: "inspection-standard" } });
}

onMounted(loadAll);
</script>

<template>
  <div class="flex flex-col gap-5">
    <section class="hero">
      <div>
        <p class="eyebrow">Standards Library</p>
        <h2>检测标准</h2>
        <p>检测标准是唯一入口：在这里绑定适用产品、RAG 标准库和判定规则门槛，任务创建页只负责选择已启用标准。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增检测标准</el-button>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div>
            <h3>检测标准列表</h3>
            <p>原“质检门槛”已收束为标准内的规则配置，RAG 空间和自动放行策略也在同一入口查看。</p>
          </div>
        </div>
      </template>

      <div class="filters">
        <el-select v-model="filters.productFamily" clearable placeholder="按品类筛选" style="width: 220px">
          <el-option v-for="family in productFamilies" :key="family" :label="family" :value="family" />
        </el-select>
        <el-segmented
          v-model="filters.status"
          :options="[
            { label: '全部', value: 'all' },
            { label: '启用', value: 'active' },
            { label: '停用', value: 'inactive' },
          ]"
        />
        <el-button @click="loadAll">刷新</el-button>
      </div>

      <el-table :data="filteredItems" v-loading="loading">
        <el-table-column prop="name" label="标准名称" min-width="180" />
        <el-table-column prop="product_family" label="品类/产品族" width="140" />
        <el-table-column label="规则门槛" min-width="180">
          <template #default="{ row }">
            <div class="rule-cell">
              <strong>{{ row.spec_code || "未绑定" }}</strong>
              <span>{{ row.spec_name || "规则配置缺失" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="适用范围" min-width="180">
          <template #default="{ row }">
            <span v-if="row.applicable_product_sku_ids?.length">SKU {{ row.applicable_product_sku_ids.length }} 个</span>
            <span v-else-if="row.applicable_product_line_ids?.length">产品线 {{ row.applicable_product_line_ids.length }} 个</span>
            <span v-else>全部产品</span>
          </template>
        </el-table-column>
        <el-table-column label="绑定空间" min-width="220">
          <template #default="{ row }">
            <div class="space-list">
              <el-tag v-for="space in row.rag_spaces" :key="space.id" effect="plain">{{ space.name }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="门槛" width="150">
          <template #default="{ row }">
            <span>{{ row.required_image_count || "-" }} 图 / {{ row.auto_pass_enabled ? "自动放行" : "人工兜底" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link @click="goKnowledgeSpace(row)">查看知识库</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="removeItem(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="dialogOpen" :title="editingId ? '编辑检测标准' : '新增检测标准'" size="720px">
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="标准名称">
          <el-input v-model="form.name" placeholder="如：螺丝组件 A 款外观检测标准" />
        </el-form-item>
        <el-form-item label="品类/产品族">
          <el-input v-model="form.product_family" placeholder="如：screw、food、electronics" />
        </el-form-item>
        <el-form-item label="判定规则/门槛">
          <el-select v-model="form.inspection_spec_id" filterable clearable placeholder="选择 inspection_specs 规则配置" class="!w-full" @change="handleSpecChange">
            <el-option v-for="spec in activeSpecOptions" :key="spec.id" :label="formatCodeName({ code: spec.spec_code, name: spec.name })" :value="spec.id" />
          </el-select>
          <div v-if="selectedSpec" class="standard-preview">
            <span>必需图片 {{ selectedSpec.required_image_count }}</span>
            <span>自动放行 {{ selectedSpec.auto_pass_enabled ? "开启" : "关闭" }}</span>
            <span>置信度 {{ selectedSpec.ai_gate_confidence_threshold.toFixed(2) }}</span>
          </div>
        </el-form-item>
        <el-form-item label="适用产品线">
          <el-select v-model="form.applicable_product_line_ids" multiple filterable clearable placeholder="不选表示不按产品线限制" class="!w-full">
            <el-option v-for="line in productLines" :key="line.id" :label="formatCodeName(line)" :value="line.id" />
          </el-select>
          <div v-if="selectedLineNames" class="field-hint">已选：{{ selectedLineNames }}</div>
        </el-form-item>
        <el-form-item label="适用 SKU">
          <el-select v-model="form.applicable_product_sku_ids" multiple filterable clearable placeholder="不选表示继承产品线范围或适用全部 SKU" class="!w-full">
            <el-option v-for="sku in productSkus" :key="sku.id" :label="formatCodeName(sku)" :value="sku.id" />
          </el-select>
          <div v-if="selectedSkuNames" class="field-hint">已选：{{ selectedSkuNames }}</div>
        </el-form-item>
        <el-form-item label="关联 RAG 标准库空间">
          <el-select v-model="form.rag_space_ids" multiple filterable placeholder="选择一个或多个知识库空间" class="!w-full">
            <el-option v-for="space in ragSpaces" :key="space.id" :label="space.name" :value="space.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="记录标准来源、适用边界或版本说明" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
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
.hero {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 20px 24px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(22, 163, 74, 0.18), transparent 34%),
    linear-gradient(135deg, #16351f 0%, #1f5130 54%, #2f855a 100%);
  color: #f8fafc;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(220, 252, 231, 0.86);
}

.hero h2 {
  margin: 0;
  font-size: 28px;
}

.hero p:last-child {
  margin: 8px 0 0;
  max-width: 760px;
  color: rgba(220, 252, 231, 0.9);
  line-height: 1.7;
}

.filters {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.space-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.rule-cell {
  display: grid;
  gap: 2px;
}

.rule-cell strong {
  color: #14532d;
}

.rule-cell span,
.field-hint {
  color: #64748b;
  font-size: 12px;
}

.drawer-form {
  padding: 8px 4px 0;
}

.standard-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.standard-preview span {
  padding: 5px 9px;
  border-radius: 999px;
  background: #dcfce7;
  color: #166534;
  font-size: 12px;
}
</style>
