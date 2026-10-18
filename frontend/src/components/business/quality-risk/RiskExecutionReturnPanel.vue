<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { riskCompletionApi, type LabLink, type ExecutionCandidate, type ExecutionReturn } from "@/api/risk-completion.api";
import { extractApiErrorMessage } from "@/api/http";
import { useAuthStore } from "@/stores/auth.store";
import { formatServerDateTime } from "@/utils/date-time";

const props = defineProps<{ caseId: string; links: LabLink[] }>();
const emit = defineEmits<{ changed: [] }>();
const auth = useAuthStore(), router = useRouter();
const linkId = ref(""), runId = ref(""), note = ref(""), withdrawalNote = ref("");
const items = ref<ExecutionCandidate[]>([]), total = ref(0), page = ref(1);
const loading = ref(false), saving = ref(false), error = ref("");
const links = computed(() => props.links.filter(r => r.case_id === props.caseId && r.mode === "verify" && r.task_id));
const link = computed(() => links.value.find(r => r.id === linkId.value));
const selected = computed(() => items.value.find(r => r.id === runId.value));
const verdict = (value?: string | null) => ({pass:"所选项目通过", fail:"所选项目未通过"})[value || ""] || "待核对";
let epoch = 0, alive = true;
async function load() {
  const target = link.value, requestedCase = props.caseId, key = ++epoch;
  items.value = []; runId.value = ""; total.value = 0; error.value = "";
  if (!target) { loading.value = false; return; }
  loading.value = true;
  try {
    const data = (await riskCompletionApi.executionCandidates(target.id, page.value)).data.data;
    if (key !== epoch || requestedCase !== props.caseId || target.id !== linkId.value) return;
    items.value = data.items; total.value = data.total;
  } catch (e) {
    if (key === epoch) error.value = extractApiErrorMessage(e, "检测结果加载失败，请核对任务和权限");
  } finally { if (key === epoch) loading.value = false; }
}
async function returnResult() {
  const target = link.value, result = selected.value, requestedCase = props.caseId;
  if (!target || !result?.eligible || !result.definition_hash || !note.value.trim() || saving.value || loading.value) return;
  saving.value = true; error.value = "";
  try {
    await riskCompletionApi.returnExecution(target.id, {expected_revision:target.revision, run_id:result.id,
      expected_run_hash:result.definition_hash, note:note.value.trim()});
    if (!alive || requestedCase !== props.caseId || target.id !== linkId.value) return;
    note.value = ""; emit("changed");
    ElMessage.success("检测结果已返回原事项，请生成新版研判并独立复核");
  } catch (e) {
    if (alive && requestedCase === props.caseId && target.id === linkId.value)
      error.value = extractApiErrorMessage(e, "结果回流失败，请刷新核对版本");
  } finally { saving.value = false; }
}
async function withdraw(entry: ExecutionReturn) {
  const target = link.value, requestedCase = props.caseId;
  if (!target || !withdrawalNote.value.trim() || saving.value || loading.value) return;
  saving.value = true; error.value = "";
  try {
    await riskCompletionApi.withdrawExecution(target.id, entry.id, {expected_revision:target.revision, note:withdrawalNote.value.trim()});
    if (!alive || requestedCase !== props.caseId || target.id !== linkId.value) return;
    withdrawalNote.value = ""; emit("changed");
    ElMessage.success("已撤回本次引用，历史记录保留，请重新研判");
  } catch (e) {
    if (alive && requestedCase === props.caseId && target.id === linkId.value)
      error.value = extractApiErrorMessage(e, "撤回失败，请刷新核对版本");
  } finally { saving.value = false; }
}
watch(() => props.caseId, () => { linkId.value = ""; note.value = ""; withdrawalNote.value = ""; });
watch(() => links.value.map(r => `${r.id}:${r.revision}`).join(","), () => {
  if (links.value.length && !links.value.some(r => r.id === linkId.value)) linkId.value = links.value[0].id;
  page.value = 1; void load();
}, {immediate:true});
function changeLink() { page.value = 1; note.value = ""; withdrawalNote.value = ""; void load(); }
onBeforeUnmount(() => { alive = false; ++epoch; });
</script>

<template>
  <section class="execution-return" aria-label="已复核检测结果回流" v-loading="loading">
    <h3>从检测任务返回已复核结果</h3>
    <p>选择已独立复核且依据有效的结果。回流后仍需新版研判和独立复核，项目判定只适用于原任务选定的样品与项目。</p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-empty v-if="!links.length" description="请先在验证分支关联同一产品的已有检测任务" :image-size="55" />
    <template v-else>
      <label for="execution-return-task">关联的验证任务</label>
      <select id="execution-return-task" v-model="linkId" :disabled="saving" @change="changeLink">
        <option v-for="row in links" :key="row.id" :value="row.id">原研判第 {{ row.assessment_version }} 版 · {{ row.purpose }}</option>
      </select>
      <el-empty v-if="!items.length && !loading && !error" description="暂无已独立复核的检测结果" :image-size="50" />
      <fieldset v-if="items.length" :disabled="saving || loading">
        <legend>选择检测结果</legend>
        <label v-for="item in items" :key="item.id" class="result-option">
          <input v-model="runId" type="radio" name="execution-return-result" :value="item.id" :disabled="!item.eligible || item.already_returned" />
          <span>检测执行 {{ item.id }} · 第 {{ item.row_version }} 版<span v-if="item.already_returned"> · 已回流</span>
            <small v-if="item.summary">{{ verdict(item.summary.item_verdict) }} · {{ formatServerDateTime(item.reviewed_at) }}</small>
            <small v-for="issue in item.issues" :key="issue">{{ issue }}</small>
          </span>
        </label>
      </fieldset>
      <div class="return-actions">
        <el-button :disabled="saving || page <= 1" @click="page--; load()">上一页</el-button>
        <span>第 {{ page }} 页 · 共 {{ total }} 条</span>
        <el-button :disabled="saving || page * 20 >= total" @click="page++; load()">下一页</el-button>
        <el-button :disabled="saving" @click="load">刷新检测结果</el-button>
      </div>
      <el-form label-position="top" :disabled="saving || loading" @submit.prevent>
        <el-form-item label="检测结果回流说明"><el-input v-model="note" type="textarea" :rows="2" :maxlength="2000" /></el-form-item>
        <el-button type="primary" :disabled="saving || loading || !selected?.eligible || selected.already_returned || !note.trim()" @click="returnResult">将已复核结果返回原事项</el-button>
      </el-form>
      <section v-if="link?.execution_returns?.length" class="return-history">
        <h4>检测结果回流记录</h4>
        <p>创建新版研判会自动带入全部仍有效的回流结果，原版本继续保留。</p>
        <el-button @click="router.push({path:'/app/risk-assessments', query:{case_id:caseId, tab:'assessment'}})">返回事项创建新版研判</el-button>
        <el-form label-position="top" @submit.prevent><el-form-item label="撤回引用说明（需要撤回时填写）"><el-input v-model="withdrawalNote" type="textarea" :rows="2" :maxlength="2000" :disabled="saving" /></el-form-item></el-form>
        <article v-for="entry in link.execution_returns" :key="entry.id">
          <strong>{{ entry.withdrawn_at ? '本次引用已撤回' : '检测结果已返回' }} · 检测执行 {{ entry.ref.run_id }}</strong>
          <p v-if="entry.summary">{{ verdict(entry.summary.item_verdict) }}；产品整体状态：未在此流程评定。</p>
          <p>{{ entry.note }}</p>
          <p v-if="entry.withdrawal_note">撤回说明：{{ entry.withdrawal_note }}</p>
          <el-alert v-for="issue in entry.issues" :key="issue" type="warning" :title="issue" :closable="false" />
          <div class="return-actions">
            <el-button @click="router.push('/app/tasks/' + entry.ref.task_id)">查看原检测任务与结果</el-button>
            <template v-if="entry.summary"><el-button v-for="origin in entry.ref.report_sources" :key="origin.attachment_id" @click="router.push({path:'/app/quality-data',query:{record:origin.record_id}})">查看原检测资料</el-button></template>
            <el-button v-if="!entry.withdrawn_at && [entry.returned_by, link.created_by].includes(auth.userId)" type="warning" :disabled="saving || loading || !withdrawalNote.trim()" @click="withdraw(entry)">撤回本次结果引用</el-button>
          </div>
        </article>
      </section>
    </template>
  </section>
</template>

<style scoped>
.execution-return { display:grid; gap:16px; min-width:0; border:1px solid var(--el-border-color); border-radius:7px; padding:18px; }
h3, h4 { margin:0; }
p { line-height:1.8; white-space:pre-wrap; overflow-wrap:anywhere; margin:6px 0; color:var(--el-text-color-regular); }
select { min-height:44px; padding:8px; max-width:100%; width:100%; color:inherit; background:var(--el-bg-color); border:1px solid var(--el-border-color); border-radius:5px; }
fieldset { min-width:0; border:1px solid var(--el-border-color); border-radius:5px; }
.result-option { display:flex; gap:12px; align-items:flex-start; padding:12px 4px; min-height:44px; overflow-wrap:anywhere; }
.result-option span { min-width:0; } .result-option input { margin-top:5px; } small { display:block; margin-top:8px; }
.return-actions { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
.return-actions :deep(.el-button) { margin-left:0; }
.return-history { display:grid; gap:16px; } article { border-top:1px solid var(--el-border-color); padding-top:16px; overflow-wrap:anywhere; }
:deep(.el-button) { min-height:44px; }
@media (max-width:700px) { .execution-return { padding:14px; } }
</style>
