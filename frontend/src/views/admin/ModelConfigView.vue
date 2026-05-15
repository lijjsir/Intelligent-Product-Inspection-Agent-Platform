<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useModelConfigStore } from "@/stores/model_config.store";

const store = useModelConfigStore();
const drawerOpen = ref(false);
const editingId = ref("");
const checkingId = ref("");
const checkingAll = ref(false);
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

function resetForm() {
  editingId.value = "";
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

async function submit() {
  const payload = {
    provider: form.provider,
    model_key: form.model_key,
    display_name: form.display_name,
    endpoint: form.endpoint,
    api_key: form.api_key || undefined,
    model_type: form.model_type,
    priority: form.priority,
    rpm_limit: form.rpm_limit,
    input_price_per_million: form.input_price_per_million,
    output_price_per_million: form.output_price_per_million,
    is_active: form.is_active,
  };
  if (editingId.value) {
    await store.updateOne(editingId.value, payload);
    ElMessage.success("模型配置已更新");
  } else {
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
    await store.checkHealth(id);
    ElMessage.success("健康检查完成");
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
    ElMessage.success(`检测完成: ${result.checked} 个模型, ${result.healthy} 健康, ${result.degraded} 降级, ${result.unhealthy} 异常`);
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
        <el-table-column prop="provider" label="Provider" width="110" />
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

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑模型配置' : '新增模型配置'" size="420px">
      <el-form label-position="top">
        <el-form-item label="Provider"><el-input v-model="form.provider" /></el-form-item>
        <el-form-item label="模型标识"><el-input v-model="form.model_key" /></el-form-item>
        <el-form-item label="展示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="Endpoint"><el-input v-model="form.endpoint" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password /></el-form-item>
        <el-form-item label="模型类型"><el-input v-model="form.model_type" /></el-form-item>
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
</style>
