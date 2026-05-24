<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useExportStore } from "@/stores/export.store";
import { usePagination } from "@/composables/usePagination";
import type { ExportFormat, ExportJob, ExportJobStatus, ReportType } from "@/types/governance.types";

const exportStore = useExportStore();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const mainTab = ref<"create" | "history" | "templates">("create");
const step = ref(1);
const deletingId = ref<string | null>(null);

const reportTypes: { key: ReportType; label: string; desc: string }[] = [
  { key: "single_task", label: "单任务检测报告", desc: "导出某一次检测结果" },
  { key: "batch_summary", label: "批量检测汇总报告", desc: "导出一段时间内的检测统计" },
  { key: "quality_analysis", label: "质量分析报告", desc: "导出幻觉率、可信度、模型表现" },
  { key: "feedback_report", label: "异常反馈报告", desc: "导出用户反馈和处理闭环" },
  { key: "evidence_trace", label: "证据溯源报告", desc: "导出 Trace、引用和推理链" },
];

const formats: { key: ExportFormat; label: string; desc: string }[] = [
  { key: "pdf", label: "PDF", desc: "正式归档、对外提交" },
  { key: "docx", label: "DOCX", desc: "需要人工编辑" },
  { key: "xlsx", label: "XLSX", desc: "数据分析" },
  { key: "csv", label: "CSV", desc: "原始明细" },
  { key: "json", label: "JSON", desc: "系统对接" },
];

const templates = [
  { key: "standard", label: "标准报告模板", desc: "封面+目录+正文" },
  { key: "simple", label: "简洁模板", desc: "只含核心结论" },
  { key: "audit", label: "审计模板", desc: "含证据链和日志" },
];

const failureDetailVisible = ref(false);
const activeFailureJob = ref<ExportJob | null>(null);
const failedJobDeletingId = ref<string | null>(null);

const form = ref({
  report_name: "",
  report_type: "" as ReportType | "",
  format: "pdf" as ExportFormat,
  template: "standard",
  task_id: "",
  date_range: [] as string[],
  include_images: true,
  include_defects: true,
  include_reasoning: false,
  include_citations: false,
  include_feedback: false,
  include_review: false,
  only_abnormal: false,
  include_trends: true,
  include_model_comparison: false,
});

const statusMap: Record<ExportJobStatus, { label: string; type: "" | "warning" | "success" | "info" | "danger" }> = {
  pending: { label: "等待中", type: "info" },
  running: { label: "生成中", type: "warning" },
  success: { label: "成功", type: "success" },
  failed: { label: "失败", type: "danger" },
  expired: { label: "已过期", type: "info" },
};

const reportTypeLabels: Record<ReportType, string> = {
  single_task: "单任务报告",
  batch_summary: "批量汇总",
  quality_analysis: "质量分析",
  feedback_report: "异常反馈",
  evidence_trace: "证据溯源",
};

const previewSections = computed(() => {
  const sections = ["封面", "检测概览"];
  if (form.value.report_type === "single_task") {
    sections.push("结果统计", "缺陷明细");
    if (form.value.include_images) sections.push("图片标注");
    if (form.value.include_citations) sections.push("引用证据");
    if (form.value.include_reasoning) sections.push("推理链路");
    if (form.value.include_feedback) sections.push("用户反馈");
  } else if (form.value.report_type === "batch_summary") {
    sections.push("统计汇总", "异常样本");
    if (form.value.include_trends) sections.push("趋势图");
  } else if (form.value.report_type === "quality_analysis") {
    sections.push("质量指标", "模型对比");
    if (form.value.include_trends) sections.push("趋势分析");
  } else if (form.value.report_type === "feedback_report") {
    sections.push("反馈统计", "处理闭环");
  } else if (form.value.report_type === "evidence_trace") {
    sections.push("证据链路", "Trace 明细");
  }
  sections.push("附录");
  return sections;
});

const canNext = computed(() => {
  if (step.value === 1) return !!form.value.report_type;
  if (step.value === 2) {
    if (form.value.report_type === "single_task") return !!form.value.task_id.trim();
    return form.value.date_range.length === 2;
  }
  return true;
});

onMounted(() => {
  fetchHistory();
});

async function fetchHistory() {
  await exportStore.fetchJobs({ page: page.value, size: pageSize.value });
  total.value = exportStore.total;
}

function selectReportType(key: ReportType) {
  form.value.report_type = key;
  if (!form.value.report_name) {
    form.value.report_name = reportTypeLabels[key] + "报告";
  }
}

function nextStep() {
  if (step.value < 4) step.value++;
}

function prevStep() {
  if (step.value > 1) step.value--;
}

async function handleGenerate() {
  if (!form.value.report_type) {
    ElMessage.warning("请选择报告类型");
    return;
  }
  const config: Record<string, unknown> = {};
  if (form.value.report_type === "single_task") {
    config.task_id = form.value.task_id;
    config.include_images = form.value.include_images;
    config.include_defects = form.value.include_defects;
    config.include_reasoning = form.value.include_reasoning;
    config.include_citations = form.value.include_citations;
    config.include_feedback = form.value.include_feedback;
    config.include_review = form.value.include_review;
  } else {
    config.date_range = form.value.date_range;
    config.only_abnormal = form.value.only_abnormal;
    config.include_trends = form.value.include_trends;
    config.include_model_comparison = form.value.include_model_comparison;
  }

  try {
    await exportStore.createJob({
      report_name: form.value.report_name,
      report_type: form.value.report_type as ReportType,
      format: form.value.format,
      template: form.value.template,
      config_json: config,
    });
    ElMessage.success("报告生成任务已创建");
    mainTab.value = "history";
    step.value = 1;
    form.value = {
      report_name: "", report_type: "", format: "pdf", template: "standard",
      task_id: "", date_range: [], include_images: true, include_defects: true,
      include_reasoning: false, include_citations: false, include_feedback: false, include_review: false,
      only_abnormal: false, include_trends: true, include_model_comparison: false,
    };
    fetchHistory();
  } catch {
    ElMessage.error("创建失败");
  }
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm("确认删除此导出记录？", "删除确认", { type: "warning" });
  deletingId.value = id;
  try {
    await exportStore.removeJob(id);
    ElMessage.success("已删除");
    fetchHistory();
  } finally {
    deletingId.value = null;
  }
}

function handlePageChange(val: number) {
  onPageChange(val);
  fetchHistory();
}

function handleSizeChange(val: number) {
  onSizeChange(val);
  fetchHistory();
}

function formatTime(t: string | null) {
  if (!t) return "--";
  return t.replace("T", " ").slice(0, 19);
}

function formatSize(bytes: number | null) {
  if (bytes == null) return "--";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function downloadFile(url: string) {
  window.open(url, "_blank");
}

function showFailureDetail(row: ExportJob) {
  activeFailureJob.value = row;
  failureDetailVisible.value = true;
}

async function handleRegenerate(row: ExportJob) {
  if (row.report_type) {
    form.value.report_type = row.report_type as ReportType;
    form.value.report_name = row.report_name;
    form.value.format = (row.format as ExportFormat) || "pdf";
    form.value.template = row.template || "standard";
  }
  mainTab.value = "create";
  step.value = 1;
  ElMessage.info("已加载原导出配置，请继续编辑后重新生成");
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="hero">
      <div>
        <h2>报告导出中心</h2>
        <p>选择报告类型、配置范围、预览内容并生成文件。</p>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="mainTab">
        <el-tab-pane label="新建导出" name="create" />
        <el-tab-pane label="导出历史" name="history" />
        <el-tab-pane label="报告模板" name="templates" />
      </el-tabs>

      <template v-if="mainTab === 'create'">
        <el-steps :active="step - 1" align-center class="mb-8 mt-4">
          <el-step title="报告类型" />
          <el-step title="数据范围" />
          <el-step title="格式模板" />
          <el-step title="预览生成" />
        </el-steps>

        <div class="flex gap-6">
          <div class="flex-1 min-w-0">
            <template v-if="step === 1">
              <h3 class="text-base font-semibold mb-4">选择报告类型</h3>
              <div class="grid grid-cols-3 gap-4">
                <div
                  v-for="rt in reportTypes"
                  :key="rt.key"
                  class="report-type-card"
                  :class="{ active: form.report_type === rt.key }"
                  @click="selectReportType(rt.key)"
                >
                  <div class="w-8 h-8 rounded-lg mb-3 mx-auto flex items-center justify-center"
                    :style="{ backgroundColor: form.report_type === rt.key ? '#ecf5ff' : '#f4f4f5' }">
                    <div class="w-1.5 h-1.5 rounded-full"
                      :style="{ backgroundColor: form.report_type === rt.key ? '#409eff' : '#a8abb2' }" />
                  </div>
                  <div class="font-semibold text-sm">{{ rt.label }}</div>
                  <div class="text-xs text-zinc-400 mt-1">{{ rt.desc }}</div>
                </div>
              </div>
            </template>

            <template v-if="step === 2">
              <h3 class="text-base font-semibold mb-4">配置数据范围</h3>
              <el-form label-position="top" class="max-w-lg">
                <el-form-item label="报告名称" required>
                  <el-input v-model="form.report_name" placeholder="请输入报告名称" />
                </el-form-item>

                <template v-if="form.report_type === 'single_task'">
                  <el-form-item label="任务 ID" required>
                    <el-input v-model="form.task_id" placeholder="请输入任务 ID" />
                  </el-form-item>
                  <el-collapse>
                    <el-collapse-item title="基础内容" name="basic">
                      <div class="grid grid-cols-2 gap-4">
                        <el-form-item label="包含图片">
                          <el-switch v-model="form.include_images" />
                        </el-form-item>
                        <el-form-item label="包含缺陷坐标">
                          <el-switch v-model="form.include_defects" />
                        </el-form-item>
                      </div>
                    </el-collapse-item>
                    <el-collapse-item title="证据内容" name="evidence">
                      <div class="grid grid-cols-2 gap-4">
                        <el-form-item label="包含引用证据">
                          <el-switch v-model="form.include_citations" />
                        </el-form-item>
                        <el-form-item label="包含用户反馈">
                          <el-switch v-model="form.include_feedback" />
                        </el-form-item>
                      </div>
                    </el-collapse-item>
                    <el-collapse-item title="技术内容" name="technical">
                      <div class="grid grid-cols-2 gap-4">
                        <el-form-item label="包含推理链">
                          <el-switch v-model="form.include_reasoning" />
                        </el-form-item>
                        <el-form-item label="包含人工复核">
                          <el-switch v-model="form.include_review" />
                        </el-form-item>
                      </div>
                    </el-collapse-item>
                  </el-collapse>
                </template>

                <template v-else>
                  <el-form-item label="时间范围" required>
                    <el-date-picker
                      v-model="form.date_range"
                      type="daterange"
                      range-separator="至"
                      start-placeholder="开始日期"
                      end-placeholder="结束日期"
                      value-format="YYYY-MM-DD"
                      class="!w-full"
                    />
                  </el-form-item>
                  <el-collapse>
                    <el-collapse-item title="高级选项" name="advanced">
                      <div class="grid grid-cols-2 gap-4">
                        <el-form-item v-if="form.report_type === 'batch_summary'" label="仅导出异常样本">
                          <el-switch v-model="form.only_abnormal" />
                        </el-form-item>
                        <el-form-item v-if="form.report_type !== 'feedback_report'" label="包含趋势图">
                          <el-switch v-model="form.include_trends" />
                        </el-form-item>
                        <el-form-item v-if="form.report_type === 'quality_analysis'" label="包含模型对比">
                          <el-switch v-model="form.include_model_comparison" />
                        </el-form-item>
                      </div>
                    </el-collapse-item>
                  </el-collapse>
                </template>
              </el-form>
            </template>

            <template v-if="step === 3">
              <h3 class="text-base font-semibold mb-4">选择格式和模板</h3>
              <el-form label-position="top" class="max-w-lg">
                <el-form-item label="导出格式">
                  <el-radio-group v-model="form.format">
                    <el-radio-button v-for="f in formats" :key="f.key" :value="f.key">
                      {{ f.label }}
                    </el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="报告模板">
                  <div class="grid grid-cols-3 gap-3 w-full">
                    <div
                      v-for="t in templates"
                      :key="t.key"
                      class="template-card"
                      :class="{ active: form.template === t.key }"
                      @click="form.template = t.key"
                    >
                      <div class="font-semibold text-sm">{{ t.label }}</div>
                      <div class="text-xs text-gray-400 mt-1">{{ t.desc }}</div>
                    </div>
                  </div>
                </el-form-item>
              </el-form>
            </template>

            <template v-if="step === 4">
              <h3 class="text-base font-semibold mb-4">预览并生成</h3>
              <el-descriptions :column="2" border>
                <el-descriptions-item label="报告名称">{{ form.report_name }}</el-descriptions-item>
                <el-descriptions-item label="报告类型">{{ reportTypeLabels[form.report_type as ReportType] || "--" }}</el-descriptions-item>
                <el-descriptions-item label="导出格式">{{ form.format.toUpperCase() }}</el-descriptions-item>
                <el-descriptions-item label="模板">{{ templates.find((t) => t.key === form.template)?.label || "--" }}</el-descriptions-item>
              </el-descriptions>
            </template>

            <div class="flex justify-between mt-8">
              <el-button v-if="step > 1" @click="prevStep">上一步</el-button>
              <div v-else />
              <div class="flex gap-3">
                <el-button v-if="step < 4" type="primary" :disabled="!canNext" @click="nextStep">下一步</el-button>
                <el-button v-if="step === 4" type="success" @click="handleGenerate">生成报告</el-button>
              </div>
            </div>
          </div>

          <div class="w-64 shrink-0 hidden lg:block">
            <div class="sticky top-4">
              <h4 class="text-sm font-semibold mb-3 text-gray-500">报告预览目录</h4>
              <div class="bg-gray-50 rounded-lg p-4">
                <div v-for="(section, i) in previewSections" :key="i" class="flex items-center gap-2 py-1.5 text-sm">
                  <span class="text-gray-300">{{ i + 1 }}.</span>
                  <span :class="{ 'font-semibold text-gray-700': i === 0, 'text-gray-500': i > 0 }">{{ section }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="mainTab === 'history'">
        <el-table :data="exportStore.jobs" v-loading="exportStore.loading" stripe class="mt-4">
          <el-table-column prop="report_name" label="报告名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="report_type" label="类型" width="120">
            <template #default="{ row }">{{ reportTypeLabels[row.report_type as ReportType] || row.report_type }}</template>
          </el-table-column>
          <el-table-column prop="format" label="格式" width="80">
            <template #default="{ row }">{{ row.format.toUpperCase() }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusMap[row.status as ExportJobStatus]?.type ?? 'info'">
                {{ statusMap[row.status as ExportJobStatus]?.label ?? row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_size" label="大小" width="90">
            <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.status === 'success' && row.file_url" link type="primary" size="small" @click="downloadFile(row.file_url)">下载</el-button>
              <el-button v-if="row.status === 'failed'" link type="warning" size="small" @click="showFailureDetail(row)">失败原因</el-button>
              <el-button v-if="row.status === 'failed' || row.status === 'expired'" link type="primary" size="small" @click="handleRegenerate(row)">重新生成</el-button>
              <el-button link type="danger" size="small" :loading="deletingId === row.id" @click="handleDelete(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="flex justify-end mt-4">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </template>

      <template v-if="mainTab === 'templates'">
        <div class="mt-4">
          <h3 class="text-base font-semibold mb-4">可用报告模板</h3>
          <div class="grid grid-cols-4 gap-4 mb-6">
            <div
              v-for="t in templates"
              :key="t.key"
              class="template-card cursor-default"
            >
              <div class="font-semibold text-sm">{{ t.label }}</div>
              <div class="text-xs text-zinc-400 mt-1">{{ t.desc }}</div>
              <el-tag size="small" class="mt-2" :type="t.key === 'standard' ? '' : t.key === 'audit' ? 'warning' : 'info'">
                {{ t.key === 'standard' ? '默认' : t.key === 'audit' ? '审计' : '简洁' }}
              </el-tag>
            </div>
          </div>
          <el-divider />
          <div class="text-sm text-zinc-400">
            在"新建导出"中选择模板后，报告将按模板结构生成。后期将支持自定义模板上传和管理。
          </div>
        </div>
      </template>
    </el-card>

    <el-dialog v-model="failureDetailVisible" title="导出失败详情" width="520px">
      <template v-if="activeFailureJob">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="报告名称">{{ activeFailureJob.report_name }}</el-descriptions-item>
          <el-descriptions-item label="失败原因">
            <span class="text-red-500">{{ activeFailureJob.error_message || "未知错误" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="建议">
            <div class="text-sm text-zinc-500">
              <p>1. 检查数据源是否可用（任务、结果、图片资源）。</p>
              <p>2. 尝试调整导出范围或减少包含的内容项。</p>
              <p>3. 联系管理员查看后台日志或 Celery Worker 状态。</p>
            </div>
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template #footer>
        <el-button @click="failureDetailVisible = false">关闭</el-button>
        <el-button v-if="activeFailureJob" type="primary" @click="handleRegenerate(activeFailureJob); failureDetailVisible = false">重新生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.report-type-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.report-type-card:hover {
  border-color: #409eff;
}
.report-type-card.active {
  border-color: #409eff;
  background: #f0f7ff;
}

.template-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px 12px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
}
.template-card:hover {
  border-color: #409eff;
}
.template-card.active {
  border-color: #409eff;
  background: #f0f7ff;
}
</style>
