<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { usePagination } from "@/composables/usePagination";
import type { IntentRoute, IntentRouteCreate } from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();

const loading = computed(() => store.loading);
const filters = ref({ intent_name: "", is_active: "" });
const showCreateDialog = ref(false);
const createFormRef = ref();
const createForm = ref<IntentRouteCreate>({
  intent_name: "",
  agent_id: "",
  priority: 100,
  sample_count: 0,
  is_active: true,
});

const rules = {
  intent_name: [{ required: true, message: "请输入意图名称", trigger: "blur" }],
};

onMounted(() => fetchData());

async function fetchData() {
  await store.fetchRoutes({
    page: page.value,
    size: pageSize.value,
    intent_name: filters.value.intent_name || undefined,
    is_active: filters.value.is_active === "" ? undefined : filters.value.is_active === "true",
  });
  total.value = store.routesTotal;
}

async function handleCreate() {
  await createFormRef.value?.validate();
  try {
    await store.createRoute(createForm.value);
    ElMessage.success("创建成功");
    showCreateDialog.value = false;
    createForm.value = { intent_name: "", agent_id: "", priority: 100, sample_count: 0, is_active: true };
    fetchData();
  } catch (e) {
    ElMessage.error("创建失败");
  }
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm("确定要删除该意图路由吗？", "确认删除", { type: "warning" });
  try {
    await store.deleteRoute(id);
    ElMessage.success("删除成功");
    fetchData();
  } catch (e) {
    ElMessage.error("删除失败");
  }
}

async function handleToggleActive(row: IntentRoute) {
  try {
    await store.updateRoute(row.id, { is_active: !row.is_active });
    ElMessage.success(row.is_active ? "已停用" : "已启用");
  } catch (e) {
    ElMessage.error("操作失败");
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h1>意图路由配置</h1>
      <p class="subtitle">配置用户意图到 Agent 的映射规则，实现智能路由分发</p>
    </div>

    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="意图名称">
          <el-input v-model="filters.intent_name" placeholder="搜索意图名称" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.is_active" placeholder="全部" clearable>
            <el-option label="启用" value="true" />
            <el-option label="停用" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData">查询</el-button>
          <el-button @click="filters = { intent_name: '', is_active: '' }">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>意图路由列表</span>
          <el-button type="primary" @click="showCreateDialog = true">+ 新建路由</el-button>
        </div>
      </template>

      <el-table :data="store.routes" v-loading="loading" stripe>
        <el-table-column prop="intent_name" label="意图名称" min-width="180" />
        <el-table-column prop="agent_id" label="绑定 Agent" width="200">
          <template #default="{ row }">
            <span v-if="row.agent_id">{{ row.agent_id }}</span>
            <span v-else class="text-gray-400">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="100" sortable />
        <el-table-column prop="sample_count" label="样本数" width="100" />
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

    <el-dialog v-model="showCreateDialog" title="新建意图路由" width="500px">
      <el-form ref="createFormRef" :model="createForm" :rules="rules" label-width="100px">
        <el-form-item label="意图名称" prop="intent_name">
          <el-input v-model="createForm.intent_name" placeholder="请输入意图名称，如 product_inquiry" />
        </el-form-item>
        <el-form-item label="绑定 Agent">
          <el-select v-model="createForm.agent_id" placeholder="选择绑定的 Agent" clearable filterable>
            <el-option v-for="agent in store.agents" :key="agent.id" :label="agent.name" :value="agent.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="createForm.priority" :min="1" :max="999" />
          <span class="ml-2 text-gray-400 text-sm">数值越小优先级越高</span>
        </el-form-item>
        <el-form-item label="样本数">
          <el-input-number v-model="createForm.sample_count" :min="0" />
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
.text-gray-400 {
  color: #9ca3af;
}
.ml-2 {
  margin-left: 8px;
}
.text-sm {
  font-size: 12px;
}
</style>
