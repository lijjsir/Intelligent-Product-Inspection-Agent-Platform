<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, type UploadFile } from "element-plus";
import { supervisionApi } from "@/api/supervision.api";
import SupervisionFields from "./SupervisionFields.vue";
import SupervisionAssessment from "./SupervisionAssessment.vue";
import AdaptiveInspectionPanel from "./AdaptiveInspectionPanel.vue";
import { fields, cleanFields } from "./form-fields";
import { STATUS_LABELS, type SupervisionRecord } from "@/types/supervision.types";
import { useAuthStore } from "@/stores/auth.store";

const props = defineProps<{
  taskId: string;
  productSkuId?: string | null;
  batchId?: string | null;
}>();
const auth = useAuthStore();
const enrollmentDialog = ref(false),
  enrollmentDataset = ref("");
async function enroll() {
  if (!session.value) return;
  await supervisionApi.enrollDataset(session.value.id, enrollmentDataset.value);
  enrollmentDialog.value = false;
  ElMessage.success("已授权到指定数据集，算法工程师可按候选样本接收");
}
const canWrite = computed(() => ["user", "expert"].includes(auth.role));
const enabled = ref(false),
  sessions = ref<SupervisionRecord[]>([]),
  session = ref<SupervisionRecord | null>(null),
  taskSamples = ref<SupervisionRecord[]>([]),
  measurements = ref<any[]>([]),
  loading = ref(false);
const dialog = ref(false),
  sampleDialog = ref(false),
  form = ref<Record<string, any>>({}),
  sampleCode = ref(""),
  sampleRegion = ref("");
const options = ref<Record<string, { value: string; label: string }[]>>({}),
  file = ref<File | null>(null),
  preview = ref<any>(null),
  sourceKey = ref("");
const mapping = ref<Record<string, string>>({});
const columns = [
  { key: "event_id", label: "来源事件编号" },
  { key: "sample_id", label: "样品编号" },
  { key: "device_id", label: "设备编号" },
  { key: "item", label: "项目" },
  { key: "measured_at", label: "采集时间" },
  { key: "value", label: "数值" },
  { key: "unit", label: "单位" },
  { key: "method", label: "方法" },
  { key: "quality_flag", label: "质量标记" },
];
const unlocked = computed(
  () => canWrite.value && session.value && session.value.status !== "signed",
);
const plannedSamples = computed(() =>
  taskSamples.value.filter((sample) => !sample.data.sampled_at),
);
async function load() {
  try {
    const settings = (await supervisionApi.settings()).data.data;
    enabled.value = settings.enabled;
    if (!enabled.value) return;
    if (canWrite.value) options.value.datasets = (await supervisionApi.datasetTargets()).data.data;
    sessions.value = (
      await supervisionApi.list("inspection-sessions", { size: 200 })
    ).data.data.items.filter((x) => x.data.task_id === props.taskId);
    if (session.value)
      session.value = sessions.value.find((x) => x.id === session.value?.id) || null;
    else session.value = sessions.value[0] || null;
    if (session.value)
      measurements.value = (await supervisionApi.measurements(session.value.id)).data.data;
    for (const kind of ["devices", "samples", "regions", "sampling-plans", "risk-cases"] as const) {
      const result = (await supervisionApi.list(kind, { size: 200 })).data.data.items;
      if (kind === "samples")
        taskSamples.value = result.filter((item) => item.data.task_id === props.taskId);
      const key = kind === "sampling-plans" ? "plans" : kind === "risk-cases" ? "cases" : kind;
      options.value[key] = result
        .filter((x) => kind !== "samples" || x.data.task_id === props.taskId)
        .filter((x) => !["inactive", "archived"].includes(x.status))
        .map((x) => ({ value: x.id, label: x.name + " · " + x.code }));
    }
  } catch {
    if (enabled.value) ElMessage.error("无法读取测量资料，请检查服务连接后刷新");
  }
}
function newSession() {
  form.value = {
    task_id: props.taskId,
    sample_ids: [],
    device_ids: [],
    required_items: [],
    candidate_items: [],
    adaptive_enabled: true,
  };
  dialog.value = true;
}
async function createSession() {
  loading.value = true;
  try {
    session.value = (
      await supervisionApi.create("inspection-sessions", {
        code: `检测-${props.taskId.slice(-6)}-${Date.now()}`,
        name: "检测会话",
        data: cleanFields(form.value, fields["inspection-sessions"]),
      })
    ).data.data;
    dialog.value = false;
    await load();
  } finally {
    loading.value = false;
  }
}
async function registerSample() {
  if (!props.productSkuId || !props.batchId) {
    ElMessage.warning("任务尚未关联产品或批次");
    return;
  }
  const created = (
    await supervisionApi.create("samples", {
      code: sampleCode.value,
      name: sampleCode.value,
      data: {
        task_id: props.taskId,
        product_sku_id: props.productSkuId,
        batch_id: props.batchId,
        sampled_at: new Date().toISOString(),
        sampling_region_id: sampleRegion.value || null,
      },
    })
  ).data.data;
  sampleDialog.value = false;
  await load();
  form.value = {
    task_id: props.taskId,
    sample_ids: [created.id],
    device_ids: [],
    required_items: [],
    candidate_items: [],
    adaptive_enabled: true,
  };
  dialog.value = true;
}
async function confirmPlannedSamples() {
  const sampledAt = new Date().toISOString();
  await Promise.all(
    plannedSamples.value.map((sample) =>
      supervisionApi.update("samples", sample.id, {
        version: sample.version,
        data: { sampled_at: sampledAt },
      }),
    ),
  );
  ElMessage.success(`已确认 ${plannedSamples.value.length} 个计划样品完成抽样`);
  await load();
}
function fileChanged(upload: UploadFile) {
  file.value = upload.raw || null;
  preview.value = null;
  sourceKey.value = upload.name;
}
async function previewFile() {
  if (!session.value || !file.value) return;
  loading.value = true;
  try {
    preview.value = (
      await supervisionApi.preview(session.value.id, file.value, mapping.value)
    ).data.data;
  } finally {
    loading.value = false;
  }
}
async function confirmFile() {
  if (!session.value || !preview.value || !sourceKey.value.trim()) return;
  loading.value = true;
  try {
    await supervisionApi.confirm(session.value.id, preview.value.preview_id, sourceKey.value);
    preview.value = null;
    file.value = null;
    ElMessage.success("测量已入库");
    await load();
  } finally {
    loading.value = false;
  }
}
async function template() {
  const blob = (await supervisionApi.template()).data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "测量导入模板.csv";
  a.click();
  URL.revokeObjectURL(url);
}
async function analyze() {
  if (!session.value) return;
  await supervisionApi.run(
    "inspection-sessions",
    session.value.id,
    session.value.version,
    "laboratory",
  );
  ElMessage.success("已提交过程分析，可刷新查看进度");
  await load();
}
async function review(operation: string) {
  if (!session.value) return;
  await supervisionApi.review(
    "inspection-sessions",
    session.value.id,
    session.value.version,
    operation,
  );
  ElMessage.success("已进入业务待办");
}
onMounted(load);
</script>
<template>
  <section v-if="enabled" class="measurement-panel" v-loading="loading">
    <header>
      <div>
        <h2>检测过程与测量</h2>
        <p>测量关联样品、设备和检测计划，提前提示与正式签发分别记录。</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <div class="controls">
      <el-select
        v-if="sessions.length > 1"
        v-model="session"
        value-key="id"
        placeholder="选择检测批次"
        @change="load"
        ><el-option
          v-for="s in sessions"
          :key="s.id"
          :label="s.name + ' · ' + (STATUS_LABELS[s.status] || s.status)"
          :value="s" /></el-select
      ><el-tag v-else-if="session" type="info"
        >{{ session.name }} · {{ STATUS_LABELS[session.status] || session.status }}</el-tag
      ><el-button v-if="canWrite && !session" type="primary" @click="sampleDialog = true"
        >开始实验室检测</el-button
      ><el-button v-if="canWrite && plannedSamples.length" @click="confirmPlannedSamples"
        >确认计划样品已抽取</el-button
      ><el-button v-if="canWrite && session" @click="newSession">新增复测</el-button>
    </div>
    <el-empty
      v-if="!session"
      description="点击“开始实验室检测”，登记实物样品后选择设备和检测项目"
    />
    <template v-else>
      <el-alert
        v-if="session.status === 'signed'"
        type="success"
        title="此会话已签发，测量与结论版本已锁定"
        :closable="false"
      />
      <AdaptiveInspectionPanel :session="session" />
      <div v-if="unlocked" class="import-box">
        <div class="controls">
          <el-upload :auto-upload="false" :limit="1" accept=".csv,.xlsx" :on-change="fileChanged"
            ><el-button>选择测量文件</el-button></el-upload
          ><el-button @click="template">下载模板</el-button
          ><el-input v-model="sourceKey" placeholder="来源批次编号" /><el-button
            :disabled="!file"
            @click="previewFile"
            >校验与预览</el-button
          >
        </div>
        <el-collapse
          ><el-collapse-item title="自定义文件列名"
            ><div class="mapping">
              <el-form-item v-for="c in columns" :key="c.key" :label="c.label"
                ><el-input v-model="mapping[c.key]" :placeholder="c.key"
              /></el-form-item></div></el-collapse-item
        ></el-collapse>
        <template v-if="preview"
          ><p>有效 {{ preview.valid_count }} 行，错误 {{ preview.errors.length }} 行</p>
          <el-table v-if="preview.errors.length" :data="preview.errors"
            ><el-table-column prop="row" label="文件行号" width="100" /><el-table-column
              prop="message"
              label="需修正内容" /></el-table
          ><el-table :data="preview.rows"
            ><el-table-column prop="item" label="项目" /><el-table-column
              prop="value"
              label="数值" /><el-table-column prop="unit" label="单位" /><el-table-column
              prop="event_id"
              label="来源事件" /></el-table
          ><el-button type="primary" :disabled="!preview.can_confirm" @click="confirmFile"
            >确认导入</el-button
          ></template
        >
      </div>
      <div v-if="unlocked" class="controls">
        <el-button type="primary" @click="analyze">分析检测过程</el-button
        ><el-button v-if="session.data.analysis" @click="review('result.review')"
          >提交专家复核</el-button
        ><el-button v-if="session.data.analysis" @click="review('result.signoff')"
          >提交正式签发</el-button
        >
      </div>
      <SupervisionAssessment
        v-if="session.data.analysis"
        :output="session.data.analysis"
        :review-status="session.status"
      />
      <el-table :data="measurements"
        ><el-table-column prop="event_id" label="来源事件" min-width="120" /><el-table-column
          prop="item"
          label="检测项目" /><el-table-column prop="value" label="值" /><el-table-column
          prop="unit"
          label="单位" /><el-table-column prop="method" label="方法" /><el-table-column
          prop="measured_at"
          label="采集时间"
          min-width="170" /><el-table-column prop="quality_flag" label="质量标记"
      /></el-table>
    </template>
    <el-dialog v-model="dialog" title="配置检测批次" width="min(850px,94vw)"
      ><el-form label-position="top"
        ><SupervisionFields
          v-model="form"
          :specs="fields['inspection-sessions'].filter((x) => x.key !== 'task_id')"
          :options="options" /></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" @click="createSession">开始检测</el-button></template
      ></el-dialog
    >
    <el-dialog v-model="sampleDialog" title="登记实物样品" width="min(480px,94vw)"
      ><el-form label-position="top"
        ><el-form-item label="样品编号" required><el-input v-model="sampleCode" /></el-form-item
        ><el-form-item label="抽样地"
          ><el-select v-model="sampleRegion" clearable
            ><el-option
              v-for="o in options.regions"
              :key="o.value"
              :value="o.value"
              :label="o.label" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button @click="sampleDialog = false">取消</el-button
        ><el-button type="primary" :disabled="!sampleCode.trim()" @click="registerSample"
          >登记</el-button
        ></template
      ></el-dialog
    >
    <el-button v-if="canWrite && session?.status === 'signed'" @click="enrollmentDialog = true"
      >授权数据集样本</el-button
    >
    <el-dialog v-model="enrollmentDialog" title="授权已签发版本到数据集" width="min(520px,94vw)"
      ><el-select v-model="enrollmentDataset" filterable placeholder="选择接收数据集"
        ><el-option
          v-for="d in options.datasets"
          :key="d.value"
          :value="d.value"
          :label="d.label" /></el-select
      ><template #footer
        ><el-button @click="enrollmentDialog = false">取消</el-button
        ><el-button type="primary" :disabled="!enrollmentDataset" @click="enroll"
          >授权候选样本</el-button
        ></template
      ></el-dialog
    >
  </section>
</template>
<style scoped>
.measurement-panel {
  border-top: 2px solid var(--el-border-color-light);
  margin-top: 24px;
  padding-top: 20px;
}
.measurement-panel header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h2 {
  font-size: 18px;
  margin: 0;
}
header p {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin: 14px 0;
}
.controls .el-input {
  max-width: 220px;
}
.controls .el-button + .el-button {
  margin-left: 0;
}
.import-box {
  border: 1px solid var(--el-border-color-light);
  padding: 14px;
  border-radius: 6px;
  margin-bottom: 16px;
}
.mapping {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.measurement-panel .el-table {
  margin-top: 14px;
}
@media (max-width: 640px) {
  .mapping {
    grid-template-columns: 1fr;
  }
  header {
    align-items: flex-start !important;
  }
}
</style>
