<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useModelConfigStore } from "@/stores/model_config.store";
import type { ModelConfigPayload, ModelType } from "@/types/governance.types";

const store = useModelConfigStore();
const drawerOpen = ref(false);
const editingId = ref("");
const checkingId = ref("");
const checkingAll = ref(false);
const editingHasApiKey = ref(false);
const form = reactive({
  provider: "volcengine",
  model_key: "",
  display_name: "",
  endpoint: "",
  api_key: "",
  model_type: "chat",
  priority: 100,
  rpm_limit: 60,
  input_price_per_million: 0,
  output_price_per_million: 0,
  is_active: true,
});

const modelTypeOptions = [
  { label: "chat", value: "chat" },
  { label: "embedding", value: "embedding" },
  { label: "multimodal", value: "multimodal" },
];

function resetForm() {
  editingId.value = "";
  editingHasApiKey.value = false;
  Object.assign(form, {
    provider: "volcengine",
    model_key: "",
    display_name: "",
    endpoint: "",
    api_key: "",
    model_type: "chat",
    priority: 100,
    rpm_limit: 60,
    input_price_per_million: 0,
    output_price_per_million: 0,
    is_active: true,
  });
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  editingHasApiKey.value = Boolean(row.has_api_key);
  Object.assign(form, {
    provider: row.provider,
    model_key: row.model_key,
    display_name: row.display_name,
    endpoint: row.endpoint,
    api_key: "",
    model_type: row.model_type,
    priority: row.priority,
    rpm_limit: row.rpm_limit ?? 60,
    input_price_per_million: row.input_price_per_million ?? 0,
    output_price_per_million: row.output_price_per_million ?? 0,
    is_active: row.is_active,
  });
  drawerOpen.value = true;
}

const isEditing = computed(() => Boolean(editingId.value));
const apiKeyHint = computed(() => {
  if (!isEditing.value) return "创建后不会回显明文 API Key，请妥善保管。";
  return editingHasApiKey.value
    ? "已配置 API Key；留空表示保持不变，输入新值表示覆盖。"
    : "尚未配置 API Key；留空表示不设置。";
});

async function submit() {
  const payload: ModelConfigPayload = {
    provider: form.provider,
    model_key: form.model_key,
    display_name: form.display_name,
    endpoint: form.endpoint,
    model_type: form.model_type as ModelType,
    priority: form.priority,
    rpm_limit: form.rpm_limit,
    input_price_per_million: form.input_price_per_million,
    output_price_per_million: form.output_price_per_million,
    is_active: form.is_active,
  };
  if (editingId.value) {
    if (form.api_key) {
      payload.api_key = form.api_key;
    }
    await store.updateOne(editingId.value, payload);
    ElMessage.success("模型配置已更新");
  } else {
    payload.api_key = form.api_key || undefined;
    const created = await store.createOne(payload);
    ElMessage.success("模型配置已创建");
    try {
      await store.checkHealth(created.id);
    } catch { /* health check is best-effort */ }
  }
  drawerOpen.value = false;
}

async function remove(id: string) {
  try {
    await ElMessageBox.confirm("确定要删除此模型配置吗？", "确认删除", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.removeOne(id);
    ElMessage.success("模型配置已删除");
  } catch {
    // user cancelled
  }
}

async function checkOne(id: string) {
  checkingId.value = id;
  try {
    const result = await store.checkHealth(id);
    if (result.health_status === "healthy") {
      ElMessage.success(result.health_message || "健康检查通过");
    } else if (result.health_status === "degraded") {
      ElMessage.warning(result.health_message || "健康检查降级");
    } else {
      ElMessage.error(result.health_message || "健康检查失败");
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "健康检查失败");
  } finally {
    checkingId.value = "";
  }
}

async function checkAll() {
  checkingAll.value = true;
  try {
    const result = await store.checkHealthAll();
    const message = `检测完成: ${result.checked} 个模型, ${result.healthy} 健康, ${result.degraded} 降级, ${result.unhealthy} 异常`;
    if (result.unhealthy > 0) {
      ElMessage.warning(message);
    } else {
      ElMessage.success(message);
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "批量健康检查失败");
  } finally {
    checkingAll.value = false;
  }
}

function healthTagType(status: string) {
  if (status === "healthy") return "success";
  if (status === "degraded") return "warning";
  if (status === "unhealthy") return "danger";
  return "info";
}

onMounted(() => {
  store.fetchAll();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="hero">
      <div>
        <h2>模型配置</h2>
        <p>治理层维护多模型路由、优先级与健康状态。</p>
      </div>
      <div class="flex gap-3">
        <el-button @click="checkAll" :loading="checkingAll">全部检测</el-button>
        <el-button type="primary" @click="openCreate">新增模型</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table :data="store.items" v-loading="store.loading">
        <el-table-column prop="display_name" label="名称" min-width="150" />
        <el-table-column prop="model_key" label="模型标识" min-width="150" />
        <el-table-column prop="provider" label="提供方" width="110" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column label="输入单价" width="110">
          <template #default="{ row }">￥{{ Number(row.input_price_per_million || 0).toFixed(2) }}/1M</template>
        </el-table-column>
        <el-table-column label="输出单价" width="110">
          <template #default="{ row }">￥{{ Number(row.output_price_per_million || 0).toFixed(2) }}/1M</template>
        </el-table-column>
        <el-table-column label="健康状态" width="150">
          <template #default="{ row }">
            <el-tooltip :content="row.health_message || '暂无详情'" :disabled="!row.health_message">
              <el-tag :type="healthTagType(row.health_status)">
                {{ row.health_status }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "是" : "否" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="checkOne(row.id)" :loading="checkingId === row.id">检测</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑模型配置' : '新增模型配置'" size="500px">
      <el-form label-position="top">
        <el-form-item label="提供方">
          <el-input v-model="form.provider" :disabled="isEditing" />
        </el-form-item>
        <el-form-item label="模型标识">
          <el-input v-model="form.model_key" :disabled="isEditing" />
          <div v-if="isEditing" class="field-hint">编辑时不支持修改提供方或模型标识；如需变更请新建模型配置。</div>
        </el-form-item>
        <el-form-item label="展示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="接口地址"><el-input v-model="form.endpoint" /></el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password />
          <div class="field-hint">{{ apiKeyHint }}</div>
        </el-form-item>
        <el-form-item label="模型类型">
          <el-select v-model="form.model_type" placeholder="选择模型类型">
            <el-option v-for="item in modelTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="9999" /></el-form-item>
        <el-form-item label="RPM 限制"><el-input-number v-model="form.rpm_limit" :min="1" :max="100000" /></el-form-item>
        <el-form-item label="输入单价（元 / 1M tokens）">
          <el-input-number v-model="form.input_price_per_million" :min="0" :step="0.1" :precision="4" />
        </el-form-item>
        <el-form-item label="输出单价（元 / 1M tokens）">
          <el-input-number v-model="form.output_price_per_million" :min="0" :step="0.1" :precision="4" />
        </el-form-item>
        <el-form-item><el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerOpen = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
:deep(.el-drawer__body) {
  overflow-y: auto;
}

.field-hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}
</style>
