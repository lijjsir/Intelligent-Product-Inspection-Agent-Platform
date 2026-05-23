<template>
  <div class="tool-binding">
    <section class="hero-card">
      <div>
        <h1 class="hero-title">Agent 绑定</h1>
        <p class="hero-subtitle">控制每个 Agent 可以调用哪些工具，配置自动调用和审批策略。</p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="showCreateDialog = true">新增绑定</el-button>
        <el-button @click="loadBindings">刷新</el-button>
      </div>
    </section>

    <section class="panel" v-loading="loading">
      <div class="panel-header">
        <h2 class="panel-title">绑定列表</h2>
        <el-input v-model="search" placeholder="搜索 Agent 或工具..." style="width: 280px" clearable />
      </div>

      <div v-if="bindings.length === 0 && !loading" class="empty-state">
        <p>暂无 Agent 绑定记录，点击「新增绑定」开始配置。</p>
      </div>

      <el-table v-else :data="paginatedBindings" stripe size="small">
        <el-table-column prop="agent_name" label="Agent" width="180" />
        <el-table-column prop="tool_name" label="工具" width="180" />
        <el-table-column prop="tool_version" label="版本" width="90" />
        <el-table-column label="自动调用" width="100">
          <template #default="{ row }">
            <el-tag :type="row.auto_call_enabled ? 'success' : 'info'" size="small">
              {{ row.auto_call_enabled ? '允许' : '禁止' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审批" width="100">
          <template #default="{ row }">
            <el-tag :type="row.approval_required ? 'warning' : 'info'" size="small">
              {{ row.approval_required ? '需要' : '不需要' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.binding_status === 'active' ? 'success' : 'info'" size="small">
              {{ row.binding_status === 'active' ? '活跃' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="editBinding(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="removeBinding(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="bindings.length > pageSize"
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredBindings.length"
        layout="prev, pager, next"
        size="small"
        class="pagination"
      />
    </section>

    <el-dialog v-model="showCreateDialog" title="新增 Agent 绑定" width="480px" destroy-on-close>
      <el-form :model="createForm" label-position="top">
        <el-form-item label="agent">
          <el-select v-model="createForm.agent_id" placeholder="选择 Agent" filterable>
            <el-option
              v-for="agent in agentOpsStore.agents"
              :key="agent.id"
              :label="agent.name"
              :value="agent.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="工具">
          <el-select v-model="createForm.tool_id" placeholder="选择工具" filterable>
            <el-option
              v-for="tool in store.tools"
              :key="tool.id"
              :label="`${tool.display_name} (${tool.tool_key})`"
              :value="tool.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="自动调用">
          <el-switch v-model="createForm.auto_call_enabled" />
        </el-form-item>
        <el-form-item label="需要审批">
          <el-switch v-model="createForm.approval_required" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="doCreateBinding">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑绑定" width="480px" destroy-on-close>
      <el-form :model="editForm" label-position="top">
        <el-form-item label="自动调用">
          <el-switch v-model="editForm.auto_call_enabled" />
        </el-form-item>
        <el-form-item label="需要审批">
          <el-switch v-model="editForm.approval_required" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.binding_status">
            <el-option label="活跃" value="active" />
            <el-option label="停用" value="inactive" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="doUpdateBinding">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useToolsStore } from "@/stores/tools.store";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import type { AgentToolBinding, BindingCreateRequest, BindingUpdateRequest } from "@/types/tools.types";

const store = useToolsStore();
const agentOpsStore = useAgentOpsStore();
const loading = ref(false);
const bindings = ref<AgentToolBinding[]>([]);
const search = ref("");
const currentPage = ref(1);
const pageSize = ref(15);

const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const editingBindingId = ref<string | null>(null);

const createForm = reactive<BindingCreateRequest>({
  agent_id: "",
  tool_id: "",
  tool_version_id: "",
  auto_call_enabled: true,
  approval_required: false,
});

const editForm = reactive<BindingUpdateRequest & { binding_status: string }>({
  auto_call_enabled: true,
  approval_required: false,
  binding_status: "active",
});

const filteredBindings = computed(() => {
  if (!search.value) return bindings.value;
  const q = search.value.toLowerCase();
  return bindings.value.filter(
    (b) =>
      b.agent_name.toLowerCase().includes(q) || b.tool_name.toLowerCase().includes(q)
  );
});

const paginatedBindings = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredBindings.value.slice(start, start + pageSize.value);
});

async function loadBindings() {
  loading.value = true;
  try {
    bindings.value = await store.fetchBindings();
    await store.fetchTools();
    await agentOpsStore.fetchAgents({});
  } finally {
    loading.value = false;
  }
}

async function doCreateBinding() {
  if (!createForm.agent_id || !createForm.tool_id) {
    ElMessage.warning("请选择 Agent 和工具");
    return;
  }
  try {
    await store.createBinding({ ...createForm });
    showCreateDialog.value = false;
    ElMessage.success("绑定已创建");
    await loadBindings();
  } catch {
    ElMessage.error("创建失败");
  }
}

function editBinding(row: AgentToolBinding) {
  editingBindingId.value = row.id;
  editForm.auto_call_enabled = row.auto_call_enabled;
  editForm.approval_required = row.approval_required;
  editForm.binding_status = row.binding_status;
  showEditDialog.value = true;
}

async function doUpdateBinding() {
  if (!editingBindingId.value) return;
  try {
    const { binding_status: _, ...rest } = editForm;
    await store.updateBinding(editingBindingId.value, rest);
    showEditDialog.value = false;
    ElMessage.success("绑定已更新");
    await loadBindings();
  } catch {
    ElMessage.error("更新失败");
  }
}

async function removeBinding(row: AgentToolBinding) {
  await ElMessageBox.confirm(
    `确认解除 Agent「${row.agent_name}」与工具「${row.tool_name}」的绑定？`,
    "删除绑定",
    { type: "warning" }
  );
  await store.deleteBinding(row.id);
  ElMessage.success("绑定已删除");
  await loadBindings();
}

onMounted(loadBindings);
</script>

<style scoped>
.tool-binding {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.panel {
  background: oklch(1 0 0);
  border: 1px solid oklch(0.91 0.005 260);
  border-radius: 16px;
  box-shadow: 0 4px 16px oklch(0.96 0.005 260 / 0.6);
}

.hero-card {
  padding: 24px 28px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  background: linear-gradient(
    135deg,
    oklch(0.97 0.02 260) 0%,
    oklch(1 0 0) 100%
  );
}

.hero-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
  color: oklch(0.15 0.01 260);
}

.hero-subtitle {
  margin: 0;
  font-size: 14px;
  color: oklch(0.45 0.01 260);
}

.panel {
  padding: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: oklch(0.2 0.01 260);
}

.empty-state {
  padding: 48px 0;
  text-align: center;
  color: oklch(0.55 0.01 260);
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
