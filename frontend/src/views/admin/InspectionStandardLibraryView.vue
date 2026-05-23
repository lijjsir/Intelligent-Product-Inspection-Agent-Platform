<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { inspectionStandardApi } from "@/api/inspection-standard.api";
import { ragSpaceApi } from "@/api/rag-space.api";
import type { InspectionStandardLibraryItem, InspectionStandardPayload } from "@/types/governance.types";
import type { RagSpace } from "@/types/rag-space.types";

const router = useRouter();
const loading = ref(false);
const saving = ref(false);
const dialogOpen = ref(false);
const editingId = ref("");
const items = ref<InspectionStandardLibraryItem[]>([]);
const ragSpaces = ref<RagSpace[]>([]);
const filters = reactive({
  productFamily: "",
  status: "all" as "all" | "active" | "inactive",
});
const form = reactive<InspectionStandardPayload>({
  name: "",
  product_family: "",
  description: "",
  rag_space_ids: [],
  is_active: true,
});

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

function resetForm() {
  editingId.value = "";
  Object.assign(form, {
    name: "",
    product_family: "",
    description: "",
    rag_space_ids: [],
    is_active: true,
  });
}

async function loadAll() {
  loading.value = true;
  try {
    const [{ data: standards }, { data: spaces }] = await Promise.all([
      inspectionStandardApi.list(),
      ragSpaceApi.list(500),
    ]);
    items.value = standards.data;
    ragSpaces.value = spaces.data;
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
    description: item.description || "",
    rag_space_ids: [...item.rag_space_ids],
    is_active: item.is_active,
  });
  dialogOpen.value = true;
}

async function submit() {
  saving.value = true;
  try {
    if (editingId.value) {
      await inspectionStandardApi.update(editingId.value, form);
      ElMessage.success("检测标准绑定已更新");
    } else {
      await inspectionStandardApi.create(form);
      ElMessage.success("检测标准绑定已创建");
    }
    dialogOpen.value = false;
    await loadAll();
  } finally {
    saving.value = false;
  }
}

async function removeItem(item: InspectionStandardLibraryItem) {
  await ElMessageBox.confirm(`将删除“${item.name}”的标准绑定，是否继续？`, "删除检测标准", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await inspectionStandardApi.remove(item.id);
  ElMessage.success("检测标准绑定已删除");
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
        <p>绑定国家标准知识库，让系统 RAG 在聊天质检和正式任务中自动参与检索。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增标准绑定</el-button>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div>
            <h3>标准库绑定列表</h3>
            <p>本页不上传文件，只绑定现有 RAG 空间。</p>
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
        <el-table-column prop="product_family" label="食品品类" width="140" />
        <el-table-column label="绑定空间" min-width="220">
          <template #default="{ row }">
            <div class="space-list">
              <el-tag v-for="space in row.rag_spaces" :key="space.id" type="primary" effect="plain">{{ space.name }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="文档数" width="100">
          <template #default="{ row }">{{ row.total_document_count }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="220">
          <template #default="{ row }">{{ row.description || "未填写" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link @click="goKnowledgeSpace(row)">查看绑定空间</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="removeItem(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="dialogOpen" :title="editingId ? '编辑检测标准' : '新增检测标准'" size="620px">
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="标准名称">
          <el-input v-model="form.name" placeholder="如：食品国家标准基础库" />
        </el-form-item>
        <el-form-item label="食品品类">
          <el-input v-model="form.product_family" placeholder="如：food、beverage、dairy" />
        </el-form-item>
        <el-form-item label="关联 RAG 空间">
          <el-select v-model="form.rag_space_ids" multiple filterable placeholder="选择一个或多个知识库空间" class="!w-full">
            <el-option v-for="space in ragSpaces" :key="space.id" :label="space.name" :value="space.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="记录该品类下所使用的国家标准范围" />
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
  max-width: 720px;
  color: rgba(220, 252, 231, 0.9);
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

.drawer-form {
  padding: 8px 4px 0;
}
</style>
