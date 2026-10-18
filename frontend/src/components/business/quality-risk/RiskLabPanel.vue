<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { extractApiErrorMessage } from "@/api/http";
import { riskCompletionApi, type LabLink } from "@/api/risk-completion.api";
import type { RiskAssessmentV4, RiskWorkflowContext } from "@/types/quality-risk.types";
import { useAuthStore } from "@/stores/auth.store";
const props = defineProps<{
  caseId: string;
  assessment: RiskAssessmentV4 | null;
  isLatest: boolean;
  context?: RiskWorkflowContext | null;
}>();
const isDemo = computed(() => props.context?.execution_mode !== "business");
const basis = computed(() => isDemo.value ? props.assessment?.demo_validation?.basis_hash : props.context?.basis_hash);
const eligible = computed(() => isDemo.value ? props.assessment?.demo_validation?.is_current : props.context?.eligible && props.context.assessment_id === props.assessment?.id);
const emit = defineEmits<{ changed: [] }>();
const router = useRouter(),
  auth = useAuthStore();
const loading = ref(false),
  saving = ref(false),
  error = ref("");
const rows = ref<LabLink[]>([]),
  options = ref<Awaited<ReturnType<typeof riskCompletionApi.labOptions>>["data"]["data"]>({
    tasks: [],
    records: [],
  });
const form = reactive({
  mode: "skip" as "skip" | "verify",
  purpose: "",
  task_id: null as string | null,
});
const returnId = ref(""),
  recordIds = ref<string[]>([]),
  note = ref("");
const current = computed(() => rows.value.find((r) => r.assessment_id === props.assessment?.id));
const target = computed(() => rows.value.find((r) => r.id === returnId.value));
const canDecide = computed(
  () =>
    props.isLatest &&
    (isDemo.value ? props.assessment?.status === "demo_reviewed" : props.assessment?.status === "accepted") &&
    eligible.value &&
    (!current.value ||
      (current.value.created_by === auth.userId && !current.value.record_ids.length)),
);
const statuses: Record<string, string> = {
  skipped: "已跳过", requested: "待验证资料", returned: "资料已回流",
  demo_skipped: "演示已跳过",
  demo_requested: "演示待验证资料",
  demo_returned: "演示资料已回流",
};
let epoch = 0;
let alive = true;
async function load() {
  const key = ++epoch;
  const requestedCase = props.caseId;
  loading.value = true;
  error.value = "";
  rows.value = [];
  options.value = { tasks: [], records: [] };
  returnId.value = "";
  recordIds.value = [];
  note.value = "";
  form.mode = "skip";
  form.purpose = "";
  form.task_id = null;
  try {
    const [list, result] = await Promise.all([
      riskCompletionApi.labs(requestedCase),
      riskCompletionApi.labOptions(requestedCase),
    ]);
    if (key !== epoch) return;
    rows.value = list.data.data;
    options.value = result.data.data;
    const row = current.value;
    form.mode = row?.mode || "skip";
    form.purpose = row?.purpose || "";
    form.task_id = row?.task_id || null;
    returnId.value = rows.value.find((r) => r.mode === "verify" && !r.record_ids.length)?.id || "";
  } catch (e) {
    if (key === epoch) error.value = extractApiErrorMessage(e, "验证资料加载失败");
  } finally {
    if (key === epoch) loading.value = false;
  }
}
async function decide() {
  const a = props.assessment;
  const requestedCase = props.caseId;
  if (!a || !basis.value || loading.value) return;
  saving.value = true;
  error.value = "";
  try {
    await riskCompletionApi.decide(requestedCase, {
      assessment_id: a.id,
      expected_basis_hash: basis.value,
      expected_revision: current.value?.revision || null,
      mode: form.mode,
      purpose: form.purpose,
      task_id: form.mode === "verify" ? form.task_id : null,
    });
    if (!alive || props.caseId !== requestedCase) return;
    await load();
    ElMessage.success("验证选择已记录");
  } catch (e) {
    if (alive && props.caseId === requestedCase)
      error.value = extractApiErrorMessage(e, "保存失败，请刷新核对版本");
  } finally {
    saving.value = false;
  }
}
async function returnRecords() {
  const row = target.value;
  const requestedCase = props.caseId;
  if (!row || loading.value || row.case_id !== requestedCase) return;
  saving.value = true;
  error.value = "";
  try {
    await riskCompletionApi.returnRecords(row.id, {
      expected_revision: row.revision,
      record_ids: recordIds.value,
      note: note.value,
    });
    if (!alive || props.caseId !== requestedCase) return;
    recordIds.value = [];
    note.value = "";
    await load();
    emit("changed");
    ElMessage.success("资料已关联原事项，请在新版研判中核对");
  } catch (e) {
    if (alive && props.caseId === requestedCase)
      error.value = extractApiErrorMessage(e, "回流失败，请核对资料与对象");
  } finally {
    saving.value = false;
  }
}
watch(() => [props.caseId, props.assessment?.id], load);
onMounted(load);
onBeforeUnmount(() => {
  alive = false;
  ++epoch;
});
</script>
<template>
  <section class="risk-lab-panel" v-loading="loading">
    <h2>实验室验证（可选）</h2>
    <el-alert
      type="info"
      :closable="false"
      :title="isDemo ? '可以跳过验证完成分析。验证分支只关联已有任务或统一接入的模拟检测资料，不自动启动检测、设备或模型。' : '验证只关联同一产品的已有任务和检测资料，结果返回原事项，不自动执行检测。'"
    />
    <el-alert v-if="error" type="error" :closable="false" :title="error" />
    <el-form label-position="top" :disabled="!canDecide || saving || loading" @submit.prevent>
      <el-form-item label="本版是否需要实验室验证"
        ><el-radio-group v-model="form.mode"
          ><el-radio value="skip">暂不验证</el-radio
          ><el-radio value="verify">需要验证资料</el-radio></el-radio-group
        ></el-form-item
      >
      <el-form-item label="验证目的或跳过理由"
        ><el-input v-model="form.purpose" type="textarea" :rows="3" :maxlength="2000"
      /></el-form-item>
      <el-form-item v-if="form.mode === 'verify'" label="关联既有检测任务（可选）"
        ><el-select v-model="form.task_id" clearable placeholder="可直接接入报告，无需虚构任务"
          ><el-option
            v-for="task in options.tasks"
            :key="task.id"
            :label="task.label"
            :value="task.id" /></el-select
      ></el-form-item>
      <el-button
        v-if="canDecide"
        type="primary"
        :disabled="!form.purpose.trim() || saving || loading"
        @click="decide"
        >保存本版验证选择</el-button
      >
    </el-form>
    <p v-if="!canDecide">请先完成最新版本的独立复核；已有回流记录保持原版本关联。</p>
    <section v-if="target" class="lab-return">
      <h3>把验证资料返回原事项</h3>
      <p>
        当前关联第
        {{ target.assessment_version }} 版。新增证据会使旧研判与建议待重评，不另建风险事项。
      </p>
      <el-form label-position="top" :disabled="saving" @submit.prevent>
        <el-form-item label="待回流验证"
          ><el-select v-model="returnId"
            ><el-option
              v-for="row in rows.filter((r) => r.mode === 'verify' && !r.record_ids.length)"
              :key="row.id"
              :label="`原研判第 ${row.assessment_version} 版 · ${row.purpose}`"
              :value="row.id" /></el-select
        ></el-form-item>
        <el-form-item label="已接入且确认同一对象的检测资料"
          ><el-select v-model="recordIds" multiple placeholder="选择原受理记录"
            ><el-option
              v-for="record in options.records"
              :key="record.id"
              :label="`${record.already_linked ? '【已在事项中】' : ''}${record.label}`"
              :value="record.id" /></el-select
        ></el-form-item>
        <el-form-item label="回流说明"
          ><el-input v-model="note" type="textarea" :rows="3" :maxlength="2000"
        /></el-form-item>
        <el-button
          type="primary"
          :disabled="!recordIds.length || !note.trim() || saving"
          @click="returnRecords"
          >关联资料并返回原事项</el-button
        >
      </el-form>
    </section>
    <div class="lab-links">
      <el-button @click="router.push('/app/quality-data')">接入新的检测资料</el-button
      ><el-button @click="load">刷新关联与资料</el-button
      ><el-button @click="router.push({ path: '/app/risk-reports', query: { case_id: caseId } })"
        >查看研判报告</el-button
      >
    </div>
    <article v-for="row in rows" :key="row.id" class="lab-history">
      <h3>原研判第 {{ row.assessment_version }} 版 · {{ statuses[row.status] }}</h3>
      <p class="preserve">{{ row.purpose }}</p>
      <p>关联任务：{{ row.task_id || "未关联，无需虚构任务" }}</p>
      <el-alert
        v-for="issue in row.issues"
        :key="issue"
        type="warning"
        :closable="false"
        :title="issue"
      />
      <p v-if="row.return_note" class="preserve">回流说明：{{ row.return_note }}</p>
      <p v-if="['demo_returned', 'returned'].includes(row.status)">
        {{
          row.added_new_evidence
            ? "已增加原事项证据，请创建新版研判并独立复核。"
            : "仅关联事项已有资料，未增加新证据。"
        }}
      </p>
      <el-button
        v-for="(id, index) in row.record_ids"
        :key="id"
        link
        @click="router.push({ path: '/app/quality-data', query: { record: id } })"
        >查看回流资料 {{ index + 1 }}</el-button
      >
      <el-button v-if="row.task_id" link @click="router.push('/app/tasks/' + row.task_id)"
        >查看关联检测任务</el-button
      >
      <details>
        <summary>验证选择与回流记录</summary>
        <p v-for="(event, i) in row.events" :key="i">
          {{ event.actor_name }} · {{ event.action }} · {{ event.at }}
        </p>
      </details>
    </article>
  </section>
</template>
<style scoped>
.risk-lab-panel {
  display: grid;
  gap: 18px;
  min-width: 0;
}
h2 {
  font-size: 19px;
  margin: 0;
}
h3 {
  font-size: 16px;
  margin: 0 0 12px;
}
p {
  color: var(--el-text-color-regular);
  line-height: 1.7;
  margin: 8px 0;
}
.lab-return,
.lab-history {
  border: 1px solid var(--el-border-color);
  border-radius: 7px;
  padding: 18px;
  min-width: 0;
}
.lab-links {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.lab-links :deep(.el-button) {
  margin-left: 0;
  min-height: 44px;
}
.preserve {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
summary {
  cursor: pointer;
  min-height: 44px;
  line-height: 44px;
}
:deep(.el-select) {
  width: 100%;
}
:deep(.el-button) {
  min-height: 44px;
}
details {
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  .lab-return,
  .lab-history {
    padding: 14px;
  }
  .lab-links {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
