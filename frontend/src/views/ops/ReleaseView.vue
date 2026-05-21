<script setup lang="ts">
import { onMounted, ref } from "vue";
import { modelConfigApi } from "@/api/model_config.api";
import { useAnalyticsStore } from "@/stores/analytics.store";
import type { ModelConfig } from "@/types/governance.types";

const analyticsStore = useAnalyticsStore();
const models = ref<ModelConfig[]>([]);
const loading = ref(false);

async function fetchData() {
  loading.value = true;
  try {
    const [modelRes] = await Promise.all([
      modelConfigApi.list().catch(() => ({ data: { data: [] } })),
      analyticsStore.fetchOverview().catch(() => {}),
    ]);
    models.value = modelRes.data.data ?? [];
  } finally {
    loading.value = false;
  }
}

const overview = () => analyticsStore.overview;

function healthyCount() {
  return models.value.filter(m => m.health_status === "healthy" && m.is_active).length;
}

function degradedCount() {
  return models.value.filter(m => m.health_status === "degraded" && m.is_active).length;
}

function activeCount() {
  return models.value.filter(m => m.is_active).length;
}

onMounted(fetchData);
</script>

<template>
  <div class="release-shell">
    <section class="hero">
      <p class="eyebrow">Release Coordination</p>
      <h2>发布协同</h2>
      <p class="sub">跟踪 Agent 配置变更、模型版本发布和系统上线状态，协调跨团队发布流程。</p>
    </section>

    <!-- Status overview -->
    <section class="summary-row">
      <div class="sc">
        <span class="sl">活跃模型</span>
        <span class="sv">{{ activeCount() }}</span>
        <span class="sl-sub">共 {{ models.length }} 个已配置</span>
      </div>
      <div class="sc">
        <span class="sl">健康模型</span>
        <span class="sv text-green-600">{{ healthyCount() }}</span>
      </div>
      <div class="sc">
        <span class="sl">降级模型</span>
        <span class="sv text-amber-600">{{ degradedCount() }}</span>
      </div>
      <div class="sc">
        <span class="sl">近期调用量</span>
        <span class="sv">{{ overview()?.total_tasks?.toLocaleString() || '0' }}</span>
      </div>
    </section>

    <div class="info-grid">
      <el-card shadow="never" class="info-card">
        <template #header>
          <strong>发布事项看板</strong>
          <span class="card-meta">待协调的发布任务</span>
        </template>
        <el-empty description="暂无待协调的发布事项" :image-size="80" />
        <p class="info-note">
          发布协同功能对接 Agent 配置版本管理系统。当 app_developer 提交新的 Agent 配置或 Prompt 变更时，
          在此生成发布任务，platform_operator 负责协调上线时间和验证流程。
        </p>
      </el-card>

      <el-card shadow="never" class="info-card">
        <template #header>
          <strong>模型就绪状态</strong>
          <span class="card-meta">当前各模型健康概况</span>
        </template>
        <div v-if="models.length" class="model-list">
          <div v-for="m in models" :key="m.model_key" class="model-row">
            <div class="model-info">
              <span class="model-name">{{ m.display_name || m.model_key }}</span>
              <span class="model-key">{{ m.model_type }} · {{ m.provider }}</span>
            </div>
            <div class="model-badges">
              <el-tag
                :type="m.health_status === 'healthy' ? 'success' : m.health_status === 'degraded' ? 'warning' : 'danger'"
                size="small"
                effect="dark"
              >
                {{ m.health_status === 'healthy' ? '健康' : m.health_status === 'degraded' ? '降级' : '异常' }}
              </el-tag>
              <el-tag :type="m.is_active ? 'success' : 'info'" size="small" effect="plain">
                {{ m.is_active ? '已上线' : '已下线' }}
              </el-tag>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无模型配置" :image-size="60" />
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.release-shell { display: grid; gap: 18px; padding: 24px; }

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 52%, #059669 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.sc {
  padding: 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 16px rgba(15,23,42,.03);
}
.sl { display: block; font-size: 13px; color: #a1a1aa; }
.sv { display: block; margin-top: 8px; font-size: 28px; font-weight: 800; color: #18181b; }
.sl-sub { display: block; margin-top: 4px; font-size: 11px; color: #d4d4d8; }

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.info-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
}
.info-card strong { font-size: 18px; color: #172033; }
.card-meta { display: block; margin-top: 4px; font-size: 13px; color: #64748b; }
.info-note {
  margin-top: 12px;
  padding: 16px;
  background: #f4f4f5;
  border-radius: 10px;
  font-size: 13px;
  color: #71717a;
  line-height: 1.6;
}

.model-list { display: flex; flex-direction: column; gap: 8px; }
.model-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: 10px;
  background: #fafafa;
}
.model-info { display: flex; flex-direction: column; gap: 2px; }
.model-name { font-weight: 600; color: #18181b; font-size: 14px; }
.model-key { font-size: 12px; color: #a1a1aa; }
.model-badges { display: flex; gap: 6px; flex-shrink: 0; }

.text-green-600 { color: #16a34a; }
.text-amber-600 { color: #d97706; }

@media (max-width: 960px) {
  .summary-row { grid-template-columns: 1fr 1fr; }
  .info-grid { grid-template-columns: 1fr; }
}
</style>
