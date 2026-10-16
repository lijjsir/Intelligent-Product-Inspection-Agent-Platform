<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { exportApi } from "@/api/export.api";
import { useAuthStore } from "@/stores/auth.store";
import { taskApi } from "@/api/task.api";
import {resultApi} from '@/api/result.api';
import type {TaskResultBundle} from '@/types/result.types';
import { extractApiErrorMessage } from "@/api/http";
import { formatServerDateTime } from "@/utils/date-time";
import type { ExportJob, ExportJobStatus } from "@/types/governance.types";
import type { InspectionTask } from "@/types/task.types";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const canGenerate = computed(() => auth.hasPermission("report_generate"));
const canRead = computed(() => auth.hasPermission("report_read"));
const props = defineProps<{ taskId?: string; embedded?: boolean;executionRunId?:string;legacyOnly?:boolean }>();
const bundle=ref<TaskResultBundle|null>(null);
const sourceChoice=ref(props.executionRunId||(props.legacyOnly?'legacy':''));
const sourceError=ref('');
const tasks = ref<InspectionTask[]>([]);
const reports = ref<ExportJob[]>([]);
const taskId = ref(props.taskId || String(route.query.task_id || ""));
const format = ref<"pdf" | "docx">("pdf");
const loading = ref(true);
const generating = ref(false);
const historyError = ref("");
const downloadingId = ref("");
const selectedTask = computed(() => tasks.value.find((task) => task.id === taskId.value));
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let historyRequest = 0;

const statusLabels: Record<ExportJobStatus, string> = {
  pending: "等待生成",
  running: "生成中",
  success: "可下载",
  failed: "生成失败",
  expired: "已过期",
};

function taskLabel(task: InspectionTask) {
  return `${task.product_name || task.product_line_name || task.product_id} · ${task.standard_name || task.spec_code} · ${task.id.slice(0, 8)}`;
}

async function loadHistory() {
  if (disposed || !canRead.value) return;
  const requestNumber = ++historyRequest;
  if (pollTimer) clearTimeout(pollTimer);
  try {
    const { data } = await exportApi.list({
      page: 1,
      size: 20,
      report_type: "single_task",
      task_id: taskId.value || undefined,
    });
    if (disposed || requestNumber !== historyRequest) return;
    reports.value = data.data.items;
    historyError.value = "";
  } catch (error) {
    if (disposed || requestNumber !== historyRequest) return;
    historyError.value = extractApiErrorMessage(error, "暂时无法加载导出记录，请刷新重试。");
  }
  if (!disposed && reports.value.some((report) => ["pending", "running"].includes(report.status))) {
    pollTimer = setTimeout(() => void loadHistory(), 3000);
  }
}

async function loadTasks() {
  try {
    if (props.taskId) {
      const { data } = await taskApi.get(props.taskId);
      tasks.value = [data.data];
      taskId.value = props.taskId;
      return;
    }
    const { data } = await resultApi.reportTasks();
    tasks.value = data.data;
    if (taskId.value && !tasks.value.some((task) => task.id === taskId.value)) {
      const { data: detail } = await taskApi.get(taskId.value);
      tasks.value.unshift(detail.data);
    }
    if (!taskId.value && tasks.value.length) taskId.value = tasks.value[0].id;
  } catch (error) {
    ElMessage.error(extractApiErrorMessage(error, "无法加载可导出的任务"));
  } finally {
    loading.value = false;
    if(taskId.value)await loadSummary();
  }
}

async function loadSummary(){
  if(!taskId.value)return;
  sourceError.value='';
  try{bundle.value=(await resultApi.summary(taskId.value,sourceChoice.value==='legacy'?{legacy_only:true}:
    sourceChoice.value?{execution_run_id:sourceChoice.value}:undefined)).data.data;
    sourceChoice.value=bundle.value.selection.execution_run_id||(bundle.value.auxiliary?'legacy':'');
  }catch(cause){bundle.value=null;sourceError.value=extractApiErrorMessage(cause,'当前结果依据不可读取');}
}

async function generateReport() {
  if (!selectedTask.value || generating.value || !canGenerate.value||!bundle.value?.can_export) return;
  generating.value = true;
  try {
    await exportApi.create({
      report_name: `${selectedTask.value.product_name || selectedTask.value.product_id}检测报告`,
      report_type: "single_task",
      format: format.value,
      template: "standard",
      config_json: { task_id:selectedTask.value.id,execution_run_id:bundle.value.selection.execution_run_id,
        legacy_only:bundle.value.selection.legacy_only,expected_result_token:bundle.value.result_token },
    });
    ElMessage.success("报告已开始生成，完成后可在下方下载。");
    await loadHistory();
    await loadSummary();
  } catch (error) {
    ElMessage.error(extractApiErrorMessage(error, "报告生成失败，请重试"));
  } finally {
    generating.value = false;
  }
}

async function downloadReport(report: ExportJob) {
  downloadingId.value = report.id;
  let url = "";
  try {
    const current=(await exportApi.detail(report.id)).data.data;
    if(current.source_issues?.length)ElMessage.warning('正在下载生成时的历史快照；当前来源需重新核验。');
    const { data } = await exportApi.download(report.id);
    url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.report_name}.${report.format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    ElMessage.error(extractApiErrorMessage(error, "报告下载失败，请重试"));
  } finally {
    if (url) URL.revokeObjectURL(url);
    downloadingId.value = "";
  }
}

onMounted(() => {
  void loadTasks();
  void loadHistory();
});
watch(taskId, () => {
  sourceChoice.value=props.executionRunId||(props.legacyOnly?'legacy':'');void loadSummary();
  void loadHistory();
});
onBeforeUnmount(() => {
  disposed = true;
  if (pollTimer) clearTimeout(pollTimer);
});
</script>

<template>
  <section class="task-reports">
    <el-button
      v-if="!embedded"
      link
      @click="router.push(taskId ? `/app/tasks/${taskId}` : '/app/tasks')"
      >← 返回我的任务</el-button
    >
    <header>
      <h2>{{ embedded ? "当前任务的检测报告" : "导出检测报告" }}</h2>
      <p>报告保存所选版本的样品、项目、来源和复核快照，明确记录产品整体未评定。</p>
    </header>
    <el-card shadow="never" v-loading="loading">
      <el-empty
        v-if="!loading && !tasks.length"
        description="还没有可导出报告的任务。完成检测后再来下载。"
      >
        <el-button type="primary" @click="router.push('/app/tasks')">查看我的任务</el-button>
      </el-empty>
      <el-form v-else label-position="top" class="report-form" @submit.prevent="generateReport">
        <el-form-item label="检测任务">
          <el-select
            v-model="taskId"
            :disabled="Boolean(props.taskId)"
            filterable
            placeholder="选择已有检测结果的任务"
            class="report-task-select"
          >
            <el-option
              v-for="task in tasks"
              :key="task.id"
              :label="taskLabel(task)"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="报告格式">
          <el-radio-group v-model="format">
            <el-radio-button value="pdf">PDF · 便于分享</el-radio-button>
            <el-radio-button value="docx">Word · 可编辑</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="bundle" label="报告依据版本"><el-select v-model="sourceChoice" style="width:100%" @change="loadSummary"><el-option v-for="(run,index) in bundle.execution_versions" :key="run.id" :value="run.id" :label="`执行 ${bundle.execution_versions.length-index} · 版本 ${run.row_version} · ${run.status==='accepted'?'历史已复核':'待复核记录'}`"/><el-option v-if="bundle.auxiliary" value="legacy" label="仅图片 / 历史辅助记录"/></el-select></el-form-item>
        <el-alert v-if="sourceError" :title="sourceError" type="warning" :closable="false"/>
        <el-alert v-if="bundle" :title="`${bundle.scope.label}。${bundle.scope.boundary}`" type="info" :closable="false"/>
        <el-button
          v-if="canGenerate"
          type="primary"
          :loading="generating"
          :disabled="!selectedTask||!bundle?.can_export"
          @click="generateReport"
          >生成报告</el-button
        >
        <p v-if="!canGenerate" class="report-error">未获报告生成权限；可查看和下载已有报告。</p>
      </el-form>
    </el-card>
    <el-card v-if="canRead" shadow="never">
      <template #header
        ><div class="report-history-header">
          <span>{{ taskId ? "当前任务的导出记录" : "最近导出" }}</span
          ><el-button link @click="loadHistory">刷新</el-button>
        </div></template
      >
      <el-alert
        v-if="historyError"
        :title="historyError"
        type="warning"
        :closable="false"
        show-icon
        class="mb-3"
      />
      <el-table :data="reports" empty-text="还没有导出记录">
        <el-table-column prop="report_name" label="报告" min-width="180" />
        <el-table-column label="格式" width="85"
          ><template #default="{ row }">{{ row.format.toUpperCase() }}</template></el-table-column
        >
        <el-table-column label="状态" width="110"
          ><template #default="{ row }">{{
            statusLabels[row.status as ExportJobStatus]
          }}</template></el-table-column
        >
        <el-table-column label="创建时间" min-width="150"
          ><template #default="{ row }">{{
            formatServerDateTime(row.created_at)
          }}</template></el-table-column
        >
        <el-table-column label="下载" min-width="140">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'success'"
              link
              type="primary"
              :loading="downloadingId === row.id"
              @click="downloadReport(row)"
              >下载报告</el-button
            >
            <span v-else-if="row.status === 'failed'" class="report-error">{{
              row.error_message || "生成失败，请重新生成"
            }}</span>
            <span v-else-if="row.status === 'expired'">请重新生成</span>
            <span v-else>生成完成后可下载</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<style scoped>
.task-reports {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.task-reports > .el-button {
  align-self: flex-start;
}
header h2 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: #18181b;
}
header p {
  margin: 0;
  color: #71717a;
  font-size: 14px;
}
.report-form {
  max-width: 680px;
}
.report-task-select {
  width: 100%;
}
.report-history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.report-error {
  color: #b91c1c;
  font-size: 12px;
}
</style>
