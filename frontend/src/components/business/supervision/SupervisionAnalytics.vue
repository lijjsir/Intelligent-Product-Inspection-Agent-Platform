<script setup lang="ts">
import { onMounted, ref } from "vue";
import { supervisionApi } from "@/api/supervision.api";
import { useAuthStore } from "@/stores/auth.store";
import { useRouter } from "vue-router";
const auth = useAuthStore(),
  router = useRouter();
const enabled = ref(false),
  report = ref<any>(null);
const dimensions: Record<string, string> = {
  complaint_region_id: "投诉发生地",
  sampling_region_id: "抽样地",
  enterprise_id: "企业",
  product_category: "产品类别",
};
async function load() {
  try {
    enabled.value = (await supervisionApi.settings()).data.data.enabled;
    if (enabled.value) report.value = (await supervisionApi.analytics()).data.data;
  } catch {
    report.value = null;
  }
}
onMounted(load);
</script>
<template>
  <section v-if="enabled && report" class="supervision-analytics">
    <header>
      <div>
        <p class="eyebrow">MARKET SIGNALS</p>
        <h2>态势概览</h2>
        <p>基于已确认风险案件查看地区、企业、产品和抽查覆盖变化；案件增长不等同产品失效率。</p>
      </div>
      <div class="header-actions">
        <el-button v-if="auth.role === 'expert'" @click="router.push('/app/exposures')"
          >导入市场统计基数</el-button
        >
        <el-button @click="load">刷新</el-button>
      </div>
    </header>
    <p>{{ report.summary }}</p>
    <el-tabs
      ><el-tab-pane label="地区与类别"
        ><div class="dimensions">
          <section v-for="(label, key) in dimensions" :key="key">
            <h3>{{ label }}</h3>
            <el-table
              :data="
                Object.entries(report.dimensions[key] || {}).map(([name, count]) => ({
                  name,
                  count,
                }))
              "
              ><el-table-column prop="name" label="对象" /><el-table-column
                prop="count"
                label="案件数"
                width="90"
            /></el-table>
          </section></div></el-tab-pane
      ><el-tab-pane label="抽查与检测"
        ><el-descriptions :column="3" border
          ><el-descriptions-item label="抽查计划">{{ report.plans.length }}</el-descriptions-item
          ><el-descriptions-item label="检测会话">{{ report.sessions.length }}</el-descriptions-item
          ><el-descriptions-item label="已签发">{{
            report.sessions.filter((x: any) => x.status === "signed").length
          }}</el-descriptions-item></el-descriptions
        ><el-alert
          type="info"
          :closable="false"
          :title="report.metric_status" /></el-tab-pane></el-tabs
    ><el-alert type="warning" :closable="false" :title="report.limitations.join('；')" />
  </section>
</template>
<style scoped>
.supervision-analytics {
  margin: 18px 0 0;
  padding: 22px;
  border: 1px solid #dce6f0;
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(16, 42, 67, 0.05);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h2 {
  margin: 0;
  color: #102a43;
  font-size: 24px;
  line-height: 1.2;
}
.eyebrow {
  margin: 0 0 6px;
  color: #0b63ce;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}
h3 {
  color: #334e68;
  font-size: 14px;
}
.header-actions {
  display: flex;
  gap: 10px;
}
.dimensions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.dimensions > section {
  overflow: hidden;
  border: 1px solid #e3ebf3;
  border-radius: 12px;
}
.dimensions > section h3 {
  margin: 0;
  padding: 12px 14px;
  border-bottom: 1px solid #e8eef5;
  background: #f7faff;
}
.el-alert {
  margin-top: 14px;
}
@media (max-width: 640px) {
  header {
    align-items: flex-start;
    flex-direction: column;
    gap: 16px;
  }
  .header-actions {
    width: 100%;
  }
  .header-actions :deep(.el-button) {
    min-height: 44px;
    flex: 1;
  }
  .dimensions {
    grid-template-columns: 1fr;
  }
}
</style>
