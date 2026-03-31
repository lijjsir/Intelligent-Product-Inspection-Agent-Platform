<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { usePagination } from "@/composables/usePagination";
import type { AgentDefinition, AgentDefinitionCreate } from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();

const loading = computed(() => store.loading);
const filters = ref({ name: "", is_active: "" });
const showCreateDialog = ref(false);
const createFormRef = ref();
const createForm = ref<AgentDefinitionCreate>({
  name: "",
  description: "",
  prompt_version_id: "",
  workflow_binding: "",
  intent_config_id: "",
  is_active: true,
});

const rules = {
  name: [{ required: true, message: "请输入 Agent 名称", trigger: "blur" }],
};

onMounted(() => fetchData());

async function fetchData() {
  await store.fetchAgents({
    page: page.value,
    size: pageSize.value,
    name: filters.value.name || undefined,
    is_active: filters.value.is_active === "" ? undefined : filters.value.is_active === "true",
  });
  total.value = store.agentsTotal;
}

async function handleCreate() {
  await createFormRef.value?.validate();
  try {
    await store.createAgent(createForm.value);
    ElMessage.success("创建成功");
    showCreateDialog.value = false;
    createForm.value = {
      name: "",
      description: "",
      prompt_version_id: "",
      workflow_binding: "",
      intent_config_id: "",
      is_active: true,
    };
    fetchData();
  } catch (e) {
    ElMessage.error("创建失败");
  }
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm("确定要删除该 Agent 吗？", "确认删除", { type: "warning" });
  try {
    await store.deleteAgent(id);
    ElMessage.success("删除成功");
    fetchData();
  } catch (e) {
    ElMessage.error("删除失败");
  }
}

async function handleToggleActive(row: AgentDefinition) {
  try {
    await store.updateAgent(row.id, { is_active: !row.is_active });
    ElMessage.success(row.is_active ? "已停用" : "已启用");
  } catch (e) {
    ElMessage.error("操作失败");
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Agent 管理</h1>
      <p class="subtitle">创建和管理业务 Agent，配置工作流绑定</p>
    </div>

    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="名称">
          <el-input v-model="filters.name" placeholder="搜索 Agent 名称" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.is_active" placeholder="全部" clearable>
            <el-option label="启用" value="true" />
            <el-option label="停用" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData">查询</el-button>
          <el-button @click="filters = { name: '', is_active: '' }">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>Agent 列表</span>
          <el-button type="primary" @click="showCreateDialog = true">+ 新建 Agent</el-button>
        </div>
      </template>

      <el-table :data="store.agents" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="workflow_binding" label="工作流绑定" width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleToggleActive(row)">
              {{ row.is_active ? "停用" : "启用" }}
            </el-button>
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

    <el-dialog v-model="showCreateDialog" title="新建 Agent" width="500px">
      <el-form ref="createFormRef" :model="createForm" :rules="rules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入 Agent 名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="请输入描述" />
        </el-form-item>
        <el-form-item label="工作流绑定">
          <el-input v-model="createForm.workflow_binding" placeholder="请输入工作流绑定" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="createForm.is_active" />
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
