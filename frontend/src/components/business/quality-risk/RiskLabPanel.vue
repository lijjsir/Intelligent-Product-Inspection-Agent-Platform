<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute,useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { extractApiErrorMessage } from "@/api/http";
import { riskCompletionApi, type LabLink } from "@/api/risk-completion.api";
import type { RiskAssessmentV4, RiskWorkflowContext } from "@/types/quality-risk.types";
import { useAuthStore } from "@/stores/auth.store";
import RiskExecutionReturnPanel from "./RiskExecutionReturnPanel.vue";
import LabResourcePicker from "./LabResourcePicker.vue";
import LabTaskCreateDialog from './LabTaskCreateDialog.vue';
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
const route=useRoute(),taskDialog=ref(false);
type VerificationPath='skip'|'report'|'task';
const pathOf=(row:LabLink):VerificationPath=>row.verification_path || (row.mode==='skip'?'skip':row.task_id?'task':'report');
const loading = ref(false),
  saving = ref(false),
  error = ref("");
const rows = ref<LabLink[]>([]);
const form = reactive({
  path: 'skip' as VerificationPath,
  purpose: "",
  task_id: null as string | null,
});
const returnId = ref(""),
  recordIds = ref<string[]>([]),
  note = ref("");
const current = computed(() => rows.value.find((r) => r.assessment_id === props.assessment?.id));
const target = computed(() => rows.value.find((r) => r.id === returnId.value));
const actionsTarget=computed(()=>{
  const row=target.value;if(!row)return null;
  if(row.assessment_id===props.assessment?.id && (pathOf(row)!==form.path || row.purpose.trim()!==form.purpose.trim() || (form.path==='task'&&(row.task_id||null)!==form.task_id)))return null;
  return row;
});
const canDecide = computed(
  () =>
    props.isLatest &&
    auth.role==='expert' && !!props.assessment && !!basis.value &&
    (!current.value ||
      (current.value.created_by === auth.userId && !current.value.record_ids.length && !current.value.execution_returns?.length && !current.value.task_creation)),
);
const statuses: Record<string, string> = {
  skipped: "已跳过", requested: "待验证资料", returned: "资料已回流",
  reference_withdrawn: "检测结果引用已撤回",
  demo_skipped: "演示已跳过",
  demo_requested: "演示待验证资料",
  demo_returned: "演示资料已回流",
  validation_planned:'待补证的验证申请',demo_validation_planned:'演示验证申请',
};
let epoch = 0;
let alive = true;
async function executionChanged() { await load(); emit("changed"); }
async function load() {
  const key = ++epoch;
  const requestedCase = props.caseId;
  loading.value = true;
  error.value = "";
  rows.value = [];
  returnId.value = "";
  recordIds.value = [];
  note.value = "";
  form.path = 'skip';
  form.purpose = "";
  form.task_id = null;
  try {
    const list = await riskCompletionApi.labs(requestedCase);
    if (key !== epoch) return;
    rows.value = list.data.data;
    const row = current.value;
    form.path = row?pathOf(row):'skip';
    form.purpose = row?.purpose || "";
    form.task_id = row?.task_id || null;
    const requested=typeof route.query.validation_id==='string'?route.query.validation_id:'';
    returnId.value=rows.value.some(r=>r.id===requested)?requested:row?.id||'';
  } catch (e) {
    if (key === epoch) error.value = extractApiErrorMessage(e, "验证资料加载失败");
  } finally {
    if (key === epoch) loading.value = false;
  }
}
async function decide() {
  const a = props.assessment;
  const requestedCase = props.caseId;
  if (!a || !basis.value || loading.value || saving.value || !canDecide.value) return;
  saving.value = true;
  error.value = "";
  try {
    await riskCompletionApi.decide(requestedCase, {
      assessment_id: a.id,
      expected_basis_hash: basis.value,
      expected_revision: current.value?.revision || null,
      mode: form.path==='skip'?'skip':'verify',
      verification_path:form.path,
      purpose: form.purpose,
      task_id: form.path === 'task' ? form.task_id : null,
    });
    if (!alive || props.caseId !== requestedCase) return;
    await load();
    ElMessage.success("验证安排已记录，未改变研判复核状态");
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
watch(()=>form.path,path=>{if(path!=='task')form.task_id=null;});
watch(() => [props.caseId, props.assessment?.id,route.query.validation_id],()=>{taskDialog.value=false;void load();});
onMounted(load);
onBeforeUnmount(() => {
  alive = false;
  ++epoch;
});
</script>
<template>
  <section class="risk-lab-panel" v-loading="loading">
    <h2>实验室验证（可选）</h2>
    <p>先选择需要哪一种验证。验证资料始终返回原事项；没有检测需求时可以直接继续分析。</p>
    <el-alert v-if="isDemo" title="演示环境：模拟资料与人工研判，不创建实际检测任务，不调用设备或模型。" type="warning" :closable="false" />
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-alert v-if="assessment && !eligible" type="info" :closable="false" title="可以先记录待补证的验证申请。申请不代表风险确认；抽查建议和正式报告仍须完成独立复核。" />
    <el-form label-position="top" :disabled="!canDecide || saving || loading" @submit.prevent>
      <el-form-item label="本版验证路径">
        <el-radio-group v-model="form.path" class="verification-paths">
          <el-radio value="skip">暂不验证</el-radio>
          <el-radio value="report">引用已有报告</el-radio>
          <el-radio value="task" :disabled="isDemo">组织新的检测</el-radio>
        </el-radio-group>
      </el-form-item>
      <p v-if="form.path==='skip'">现有资料可以继续分析时，记录暂不验证的理由即可，无需检测任务。</p>
      <p v-else-if="form.path==='report'">已有外部报告请先统一接入，再核对对象、出处和授权后回流；不需要补建检测任务。</p>
      <p v-else>本平台组织检测须有具体任务。可以关联同一产品的已有任务，也可以保存申请后创建待执行任务。</p>
      <el-form-item label="验证目的或跳过理由"><el-input v-model="form.purpose" type="textarea" :rows="3" :maxlength="2000" /></el-form-item>
      <el-form-item v-if="form.path==='task'" label="关联已有检测任务（或保存后创建）">
        <LabResourcePicker :case-id="caseId" kind="tasks" :model-value="form.task_id" label="关联既有检测任务" :disabled="!canDecide||saving||loading" @update:model-value="form.task_id=typeof $event==='string'?$event:null" />
      </el-form-item>
      <el-button v-if="canDecide" type="primary" :disabled="!form.purpose.trim()||saving||loading" @click="decide">保存本版验证选择</el-button>
    </el-form>
    <p v-if="!assessment">请先创建研判草稿，即可记录验证申请，无需先确认最终结论。</p>
    <p v-else-if="!canDecide">历史版本、已创建任务或已有回流的验证安排保留原关联。可以继续处理原验证，新的安排请在最新草稿中记录。</p>
    <el-alert v-if="target&&!actionsTarget" title="当前选择尚未保存，请先保存或刷新，后续操作将使用已保存的验证安排。" type="info" :closable="false" />
    <section v-if="actionsTarget && pathOf(actionsTarget)==='report' && !actionsTarget.record_ids.length" class="lab-return">
      <h3>引用已有报告并返回原事项</h3>
      <p>关联原研判第 {{ actionsTarget.assessment_version }} 版。新增证据会使旧研判与建议待重评，不另建风险事项。</p>
      <p>只显示已授权且对象匹配的资料；事项限定批次或单件时也须一致。未匹配资料请先在数据采集中整理对象。</p>
      <el-form label-position="top" :disabled="saving" @submit.prevent>
        <el-form-item label="已接入且确认同一对象的检测资料"><LabResourcePicker :case-id="caseId" kind="records" :model-value="recordIds" label="选择已接入的检测资料" :disabled="saving||loading" @update:model-value="recordIds=Array.isArray($event)?$event:[]" /></el-form-item>
        <el-form-item label="回流说明"><el-input v-model="note" type="textarea" :rows="3" :maxlength="2000" /></el-form-item>
        <el-button type="primary" :disabled="!recordIds.length||!note.trim()||saving||loading" @click="returnRecords">关联资料并返回原事项</el-button>
      </el-form>
      <el-button @click="router.push({path:'/app/quality-data',query:{record_type:'inspection_report',create:'1',validation_id:actionsTarget.id}})">接入新的检测资料</el-button>
    </section>
    <section v-if="actionsTarget && pathOf(actionsTarget)==='task'" class="lab-return">
      <h3>组织平台检测</h3>
      <template v-if="!actionsTarget.task_id">
        <p>申请已保存。请关联已有任务，或确认对象和检测标准配置后创建待执行任务。</p>
        <el-button type="primary" :disabled="!canDecide||isDemo||saving||loading" @click="taskDialog=true">从事项创建验证任务</el-button>
      </template>
      <el-button v-else @click="router.push({path:'/app/tasks/'+actionsTarget.task_id,query:{validation_id:actionsTarget.id}})">查看关联检测任务</el-button>
      <RiskExecutionReturnPanel v-if="!isDemo&&actionsTarget.task_id" :case-id="caseId" :links="[actionsTarget]" @changed="executionChanged" />
    </section>
    <div class="lab-links"><el-button @click="load">刷新关联与资料</el-button><el-button @click="router.push({path:'/app/risk-reports',query:{case_id:caseId}})">查看研判报告</el-button></div>
    <article v-for="row in rows" :key="row.id" class="lab-history">
      <h3>原研判第 {{ row.assessment_version }} 版 · {{ statuses[row.status]||row.status }}</h3>
      <p>验证路径：{{ {skip:'暂不验证',report:'引用已有报告',task:'组织新的检测'}[pathOf(row)] }}</p>
      <p v-if="row.request_stage==='preliminary'">此记录是补证申请，不是风险结论或复核通过记录。</p>
      <p class="preserve">{{ row.purpose }}</p>
      <p v-if="pathOf(row)==='task'">关联任务：{{ row.task_id||'尚未创建或关联' }}</p>
      <el-alert v-for="issue in row.issues" :key="issue" type="warning" :closable="false" :title="issue" />
      <p v-if="row.return_note" class="preserve">回流说明：{{ row.return_note }}</p>
      <p v-if="['demo_returned','returned'].includes(row.status)">{{ row.added_new_evidence ? '已增加原事项证据，请创建新版研判并独立复核。' : '已保留回流关联，请在原事项核对当前依据。' }}</p>
      <el-button v-for="(id,index) in row.record_ids" :key="id" link @click="router.push({path:'/app/quality-data',query:{record:id}})">查看回流资料 {{ index+1 }}</el-button>
      <el-button v-if="row.mode==='verify'" @click="returnId=row.id">继续处理此验证</el-button>
      <el-button v-if="row.task_id" link @click="router.push({path:'/app/tasks/'+row.task_id,query:{validation_id:row.id}})">查看关联检测任务</el-button>
      <details><summary>验证选择与回流记录</summary><p v-for="(event,i) in row.events" :key="i">{{ event.actor_name }} · {{ event.action }} · {{ event.at }}</p></details>
    </article>
    <LabTaskCreateDialog v-if="target" v-model="taskDialog" :link-id="target.id" @created="executionChanged" />
  </section>
</template>
<style scoped>
.verification-paths { display:flex; gap:12px; flex-wrap:wrap; }
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
