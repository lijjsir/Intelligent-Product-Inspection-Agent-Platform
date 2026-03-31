<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown } from "@element-plus/icons-vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { usePagination } from "@/composables/usePagination";
import type { PromptVersion, PromptVersionCreate } from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();

const loading = computed(() => store.loading);
const filters = ref({ name: "", status: "" });
const showCreateDialog = ref(false);
const createFormRef = ref();
const createForm = ref<PromptVersionCreate>({
  name: "",
  content: "",
  version: 1,
  status: "draft",
});

const rules = {
  name: [{ required: true, message: "请输入 Prompt 名称", trigger: "blur" }],
  content: [{ required: true, message: "请输入 Prompt 内容", trigger: "blur" }],
};

const statusOptions = [
  { label: "草稿", value: "draft" },
  { label: "审核中", value: "review" },
  { label: "已发布", value: "approved" },
  { label: "已废弃", value: "deprecated" },
];

const statusTagType: Record<string, string> = {
  draft: "info",
  review: "warning",
  approved: "success",
  deprecated: "danger",
};

onMounted(() => fetchData());

async function fetchData() {
  await store.fetchPrompts({
    page: page.value,
    size: pageSize.value,
    name: filters.value.name || undefined,
    status: filters.value.status || undefined,
  });
  total.value = store.promptsTotal;
}

async function handleCreate() {
  await createFormRef.value?.validate();
  try {
    await store.createPrompt(createForm.value);
    ElMessage.success("创建成功");
    showCreateDialog.value = false;
    createForm.value = { name: "", content: "", version: 1, status: "draft" };
    fetchData();
  } catch (e) {
    ElMessage.error("创建失败");
  }
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm("确定要删除该 Prompt 吗？", "确认删除", { type: "warning" });
  try {
    await store.deletePrompt(id);
    ElMessage.success("删除成功");
    fetchData();
  } catch (e) {
    ElMessage.error("删除失败");
  }
}

async function handleStatusChange(row: PromptVersion, status: string) {
  try {
    await store.updatePrompt(row.id, { status });
    ElMessage.success("状态更新成功");
  } catch (e) {
    ElMessage.error("状态更新失败");
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Prompt 版本管理</h1>
      <p class="subtitle">管理和维护 Agent 使用的 Prompt 模板版本</p>
    </div>

    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="名称">
          <el-input v-model="filters.name" placeholder="搜索 Prompt 名称" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable>
            <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData">查询</el-button>
          <el-button @click="filters = { name: '', status: '' }">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>Prompt 列表</span>
          <el-button type="primary" @click="showCreateDialog = true">+ 新建 Prompt</el-button>
        </div>
      </template>

      <el-table :data="store.prompts" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType[row.status]">{{ statusOptions.find(s => s.value === row.status)?.label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="内容预览" min-width="250" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-dropdown trigger="click">
              <el-button link type="primary">
                状态变更 <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="opt in statusOptions" :key="opt.value" @click="handleStatusChange(row, opt.value)">
                    {{ opt.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="新建 Prompt" width="600px">
      <el-form ref="createFormRef" :model="createForm" :rules="rules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入 Prompt 名称" />
        </el-form-item>
        <el-form-item label="版本号">
          <el-input-number v-model="createForm.version" :min="1" :max="999" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="createForm.status">
            <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="createForm.content" type="textarea" :rows="8" placeholder="请输入 Prompt 内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>



<style scoped>
.page-container {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100%;
}
.page-header {
  margin-bottom: 24px;
}
.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
}
.subtitle {
  color: #909399;
  margin: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.mb-4 {
  margin-bottom: 16px;
}
</style>
