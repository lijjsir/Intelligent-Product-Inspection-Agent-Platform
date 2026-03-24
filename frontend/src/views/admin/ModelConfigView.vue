<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useModelConfigStore } from "@/stores/model_config.store";

const store = useModelConfigStore();
const drawerOpen = ref(false);
const editingId = ref("");
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
    await store.createOne(payload);
    ElMessage.success("模型配置已创建");
  }
  drawerOpen.value = false;
}

async function remove(id: string) {
  await store.removeOne(id);
  ElMessage.success("模型配置已删除");
}

onMounted(() => {
  store.fetchAll();
});
</script>

<template>
  <div class="page-container">
    <div class="hero">
      <div>
        <h2>模型配置</h2>
        <p>治理层维护多模型路由、优先级与健康状态。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增模型</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="store.items" v-loading="store.loading">
        <el-table-column prop="display_name" label="名称" min-width="180" />
        <el-table-column prop="model_key" label="模型标识" min-width="180" />
        <el-table-column prop="provider" label="Provider" width="120" />
        <el-table-column prop="priority" label="优先级" width="100" />
        <el-table-column label="输入单价" width="120">
          <template #default="{ row }">￥{{ Number(row.input_price_per_million || 0).toFixed(2) }}/1M</template>
        </el-table-column>
        <el-table-column label="输出单价" width="120">
          <template #default="{ row }">￥{{ Number(row.output_price_per_million || 0).toFixed(2) }}/1M</template>
        </el-table-column>
        <el-table-column label="健康状态" width="140">
          <template #default="{ row }">
            <el-tag :type="row.health_status === 'healthy' ? 'success' : row.health_status === 'degraded' ? 'warning' : 'info'">
              {{ row.health_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "是" : "否" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
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
.page-container { display: grid; gap: 16px; }
.hero { display: flex; justify-content: space-between; align-items: center; }
.hero h2 { margin: 0; color: #1b3a5c; }
.hero p { margin: 6px 0 0; color: #64748b; }
</style>
