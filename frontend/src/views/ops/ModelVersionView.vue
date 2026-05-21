<script setup lang="ts">
import { onMounted, ref } from "vue";
import { modelConfigApi } from "@/api/model_config.api";
import type { ModelConfig } from "@/types/governance.types";

const items = ref<ModelConfig[]>([]);
const loading = ref(false);
const error = ref("");

const modelTypeLabels: Record<string, string> = {
  chat: "对话",
  embedding: "嵌入",
  multimodal: "多模态",
  vision: "视觉",
  llm: "LLM",
  vlm: "VLM",
};

const healthLabels: Record<string, { label: string; tag: string }> = {
  healthy: { label: "健康", tag: "success" },
  degraded: { label: "降级", tag: "warning" },
  unhealthy: { label: "异常", tag: "danger" },
  unknown: { label: "未知", tag: "info" },
};

async function fetchModels() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await modelConfigApi.list();
    items.value = data.data ?? [];
  } catch (e: any) {
    error.value = e?.response?.data?.message || "获取模型列表失败";
  } finally {
    loading.value = false;
  }
}

function formatPrice(val: number | null | undefined) {
  if (val == null) return "-";
  return `¥${val.toFixed(2)}/M`;
}

onMounted(fetchModels);
</script>

<template>
  <div class="mv-shell">
    <section class="hero">
      <p class="eyebrow">Model Versions</p>
      <h2>模型版本查看</h2>
      <p class="sub">查看平台已配置的模型及其运行状态，只读视角，不对模型做任何修改。</p>
    </section>

    <el-alert v-if="error" :title="error" type="warning" :closable="false" />

    <el-card shadow="never" class="table-card">
      <div class="table-toolbar">
        <span class="count-label">共 {{ items.length }} 个模型</span>
        <el-button size="small" :loading="loading" @click="fetchModels">刷新</el-button>
      </div>
      <el-table :data="items" :loading="loading" size="small" empty-text="暂无模型配置">
        <el-table-column prop="display_name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="model_key" label="模型 Key" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <span class="text-[13px]">{{ modelTypeLabels[row.model_type] || row.model_type }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="供应商" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              :type="healthLabels[row.health_status]?.tag || 'info'"
              size="small"
              effect="dark"
            >
              {{ healthLabels[row.health_status]?.label || row.health_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="激活" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="输入价格" width="110">
          <template #default="{ row }">
            {{ formatPrice(row.input_price_per_million) }}
          </template>
        </el-table-column>
        <el-table-column label="输出价格" width="110">
          <template #default="{ row }">
            {{ formatPrice(row.output_price_per_million) }}
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="70">
          <template #default="{ row }">{{ row.priority }}</template>
        </el-table-column>
        <el-table-column label="RPM 限制" width="90">
          <template #default="{ row }">{{ row.rpm_limit ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="API Key" width="90">
          <template #default="{ row }">
            <el-tag :type="row.has_api_key ? 'success' : 'danger'" size="small" effect="plain">
              {{ row.has_api_key ? '已配置' : '未配置' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.mv-shell { display: grid; gap: 18px; padding: 24px; }

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 52%, #6366f1 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 18px 40px rgba(15,23,42,.05);
}
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.count-label { font-size: 13px; color: #71717a; }
</style>
