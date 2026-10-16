<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { standardAdmissionApi } from "@/api/standard-admission.api";
import { admissionLabel } from "@/utils/standard-admission";

const router = useRouter();
const rows = ref<Awaited<ReturnType<typeof standardAdmissionApi.requirements>>["data"]["data"]>([]);
const loading = ref(false);
const keyword = ref("");
const filtered = computed(() => rows.value.filter((row) => !keyword.value || [row.indicator, row.standard_no, row.clause_no, row.library_name].some((value) => value?.includes(keyword.value))));

async function load() {
  loading.value = true;
  try { rows.value = (await standardAdmissionApi.requirements()).data.data; }
  finally { loading.value = false; }
}

function open(row: typeof rows.value[number]) {
  router.push({ path: `/governance/admin/inspection-standards/${row.document_id}`, query: { revision: row.revision_id, from: "requirements" } });
}

function evidenceLabel(row: any) {
  if (row.execution_mode === "numeric") return "实测值 / 报告转录";
  if (row.candidate_type === "method_condition") return "方法条件核对";
  if (row.execution_mode === "manual") return "人工核对";
  return "待补充执行方式";
}

onMounted(load);
</script>

<template>
  <section class="requirements-overview">
    <header><div><p class="eyebrow">标准管理 / 已发布要求</p><h2>检测要求总览</h2><p>这里展示已确认、已发布、可进入任务执行的检测要求；详情页保留原文和核对依据。</p></div><el-button @click="load">刷新</el-button></header>
    <el-alert type="info" :closable="false" title="检测要求总览来自标准文档库的发布版本。它只展示标准内容，不承担输入完整性、AI 采信或失败复核策略。" />
    <div class="filters"><el-input v-model="keyword" placeholder="检索标准编号、条款或指标" clearable/><span class="formal-filter">仅展示：专家已确认 · 标准修订已发布</span></div>
    <el-table :data="filtered" v-loading="loading" row-key="id" empty-text="暂无已发布检测要求">
      <el-table-column prop="standard_no" label="标准编号" min-width="180" />
      <el-table-column prop="clause_no" label="条款" width="110" />
      <el-table-column label="类型" width="130"><template #default="{ row }"><el-tag effect="plain">{{ row.candidate_type === "method_condition" ? "方法条件" : row.candidate_type === "body_clause" ? "正文条款" : "检测要求" }}</el-tag></template></el-table-column>
      <el-table-column prop="indicator" label="检测指标 / 项目" min-width="200" show-overflow-tooltip />
      <el-table-column label="执行证据" min-width="155"><template #default="{ row }"><el-tag effect="plain" :type="row.execution_mode === 'numeric' ? 'success' : row.execution_mode === 'manual' ? 'warning' : 'info'">{{ evidenceLabel(row) }}</el-tag><small v-if="row.execution_mode === 'numeric'" class="evidence-note">图片不能替代数值证据</small></template></el-table-column>
      <el-table-column prop="page_number" label="PDF页" width="90" />
      <el-table-column label="核对状态" width="120"><template #default="{ row }">{{ admissionLabel(row.status) }}</template></el-table-column>
      <el-table-column label="发布状态" width="130"><template #default="{ row }">{{ admissionLabel(row.publication_status) }}</template></el-table-column>
      <el-table-column label="操作" width="170"><template #default="{ row }"><el-button link type="primary" @click="open(row)">打开标准详情</el-button></template></el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.requirements-overview { display: flex; flex-direction: column; gap: 18px; }
.requirements-overview header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--piap-line, #dbe5f2); padding-bottom: 16px; }
.requirements-overview h2 { margin: 2px 0 6px; font-size: 24px; }
.requirements-overview p:not(.eyebrow) { margin: 0; color: var(--el-text-color-secondary); line-height: 1.7; }
.eyebrow { margin: 0; color: #2563eb; font-size: 11px; font-weight: 700; letter-spacing: .14em; }
.filters { display: flex; gap: 12px; align-items: center; }
.filters .el-input { max-width: 420px; }
.formal-filter { color: var(--el-text-color-secondary); font-size: 13px; }
.evidence-note { display: block; margin-top: 4px; color: #64748b; font-size: 11px; line-height: 1.4; }
@media (max-width: 600px) { .requirements-overview header, .filters { align-items: stretch; flex-direction: column; } .filters .el-input { max-width: none; } }
</style>
