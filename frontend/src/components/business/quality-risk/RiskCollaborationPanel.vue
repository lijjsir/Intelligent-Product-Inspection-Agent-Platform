<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { extractApiErrorMessage } from "@/api/http";
import { riskCollaborationApi } from "@/api/risk-collaboration.api";
import PagedReferenceSelect from '@/components/business/supervision/PagedReferenceSelect.vue';
import type { ReferenceLoader } from '@/api/supervision.api';
import { useAuthStore } from "@/stores/auth.store";
import { formatServerDateTime } from "@/utils/date-time";
import type { RiskAssessmentV4, RiskWorkflowContext } from "@/types/quality-risk.types";
import type { RiskCollaboration } from "@/types/risk-collaboration.types";
const props = defineProps<{
  caseId: string;
  assessment: RiskAssessmentV4 | null;
  isLatest: boolean;
  context?: RiskWorkflowContext | null;
}>();
const isDemo = computed(() => props.context?.execution_mode !== "business");
const basis = computed(() => isDemo.value ? props.assessment?.demo_validation?.basis_hash : props.context?.basis_hash);
const eligible = computed(() => isDemo.value ? props.assessment?.demo_validation?.is_current : props.context?.eligible && props.context.assessment_id === props.assessment?.id);
const router = useRouter(),
  auth = useAuthStore();
const rows = ref<RiskCollaboration[]>([]),
  selected = ref<RiskCollaboration | null>(null);
const loading = ref(false),
  saving = ref(false),
  error = ref(""),
  detailError = ref("");
const open = ref(false),
  showAll = ref(false);
const participantOptions:ReferenceLoader=async query=>(await riskCollaborationApi.participantPage(query)).data.data;
const form = reactive({ coordinator_id: "", participant_ids: [] as string[], purpose: "" });
let requestKey = crypto.randomUUID(),
  epoch = 0,
  detailEpoch = 0;
const draftTarget = ref<{ caseId: string; id: string; basis: string; version: number } | null>(
  null,
);
let alive = true;
const visibleRows = computed(() =>
  rows.value.filter((r) => showAll.value || r.assessment_id === props.assessment?.id),
);
const currentExists=ref(false),page=ref(1),nextCursor=ref<string|null>(null),cursors=ref<Array<string|undefined>>([undefined]);
function resetPages(){page.value=1;cursors.value=[undefined];nextCursor.value=null;}
function movePage(direction:number){if(loading.value||saving.value)return;if(direction>0){if(!nextCursor.value)return;cursors.value[page.value]=nextCursor.value;}else if(page.value<=1)return;page.value+=direction;void load();}
const canCreate = computed(
  () =>
    auth.role === "expert" &&
    props.isLatest &&
    (isDemo.value ? props.assessment?.demo_workflow && props.assessment.status !== "demo_draft" : props.assessment?.status === "accepted") &&
    eligible.value &&
    !currentExists.value,
);
const messages = computed(() =>
  [...(selected.value?.discussion || []), ...(selected.value?.comments || [])].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  ),
);
const statuses: Record<string, string> = {
  pending: "协同待接收",
  accepted: "已接收协同",
  done: "协同已完成",
  rejected: "协同已退回",
};
async function load() {
  const token = ++epoch;
  loading.value = true;
  error.value = "";
  rows.value = [];
  try {
    const result = await riskCollaborationApi.page(props.caseId,{assessment_id:showAll.value?undefined:props.assessment?.id,cursor:cursors.value[page.value-1]});
    const currentPage=showAll.value||page.value>1?await riskCollaborationApi.page(props.caseId,{assessment_id:props.assessment?.id}):result;
    if (token === epoch){ rows.value = result.data.data.items;nextCursor.value=result.data.data.next_cursor;currentExists.value=!!currentPage.data.data.items.length; }
  } catch (e) {
    if (token === epoch) {
      selected.value = null;
      ++detailEpoch;
      error.value = extractApiErrorMessage(e);
    }
  } finally {
    if (token === epoch) loading.value = false;
  }
}
async function detail(id: string) {
  const token = ++detailEpoch,
    caseId = props.caseId;
  detailError.value = "";
  try {
    const value = (await riskCollaborationApi.get(id)).data.data;
    if (token === detailEpoch && value.case_id === caseId && caseId === props.caseId)
      selected.value = value;
  } catch (e) {
    if (token === detailEpoch) {
      selected.value = null;
      detailError.value = extractApiErrorMessage(e);
    }
  }
}
async function refresh() {
  await load();
  if (selected.value) await detail(selected.value.id);
}
async function start() {
  if (!props.assessment || !basis.value) return;
  draftTarget.value = {
    caseId: props.caseId,
    id: props.assessment.id,
    basis: basis.value,
    version: props.assessment.version,
  };
  error.value = "";
  const target = draftTarget.value;
  try {
    if (!alive || props.caseId !== target.caseId || props.assessment?.id !== target.id) return;
    Object.assign(form, { coordinator_id: "", participant_ids: [], purpose: "" });
    requestKey = crypto.randomUUID();
    open.value = true;
  } catch (e) {
    error.value = extractApiErrorMessage(e);
  }
}
async function create() {
  if (!draftTarget.value || !form.coordinator_id || !form.purpose.trim()) {
    error.value = "请选择同单位协同负责人并填写协同问题";
    return;
  }
  saving.value = true;
  error.value = "";
  const target = draftTarget.value;
  try {
    const result = (
      await riskCollaborationApi.create(target.caseId, {
        ...form,
        purpose: form.purpose.trim(),
        assessment_id: target.id,
        expected_basis_hash: target.basis,
        request_key: requestKey,
      })
    ).data.data;
    if (!alive || props.caseId !== target.caseId || props.assessment?.id !== target.id) return;
    open.value = false;
    await load();
    await detail(result.id);
    ElMessage.success(result.reused ? "已返回本版本的原协同" : "已创建固定版本的同单位协同");
  } catch (e) {
    error.value = extractApiErrorMessage(e);
  } finally {
    saving.value = false;
  }
}
function meeting(item: RiskCollaboration) {
  void router.push({ path: "/app/meetings", query: { room_id: item.room_id } });
}
function workItem(item: RiskCollaboration) {
  void router.push({
    path: "/app/collab",
    query: {
      view:
        item.created_by === auth.userId
          ? "initiated"
          : item.status === "pending"
            ? "pending"
            : "processed",
      work_item: "action_request:" + item.message_id,
    },
  });
}
watch(
  () => [props.caseId, props.assessment?.id],
  () => {
    ++detailEpoch;
    open.value = false;
    selected.value = null;
    resetPages();currentExists.value=false;
    void load();
  },
);
onMounted(load);
watch(showAll,()=>{resetPages();void load();});
onBeforeUnmount(() => {
  alive = false;
  ++epoch;
  ++detailEpoch;
});
</script>
<template>
  <section class="risk-collaboration-panel" aria-label="同单位研判协同" v-loading="loading">
    <header>
      <div>
        <el-tag type="warning" effect="plain">{{ isDemo ? "演示 · 同单位" : "同单位" }}</el-tag>
        <h3>协同讨论与意见</h3>
        <p>固定事项及研判版本，邀请本单位专家讨论。公开意见保留在原会议和工作项中。</p>
      </div>
      <div class="panel-actions">
        <el-button @click="refresh">刷新协同意见</el-button
        ><el-button v-if="canCreate" type="primary" @click="start">发起本版同单位协同</el-button>
      </div>
    </header>
    <el-alert v-if="error && !open" :title="error" type="error" :closable="false" />
    <p v-if="assessment?.status === 'demo_draft'" class="hint">
      请先提交本版研判，再发起基于锁定内容的协同。
    </p>
    <p v-if="!isLatest" class="hint">当前查看历史版本，可继续查阅该版本已有协同。</p>
    <div class="scope-filter"><el-switch v-model="showAll" active-text="查看全部版本协同" /></div>
    <el-empty
      v-if="!visibleRows.length && !loading"
      description="本版本尚无你参与的协同"
      :image-size="65"
    />
    <article
      v-for="item in visibleRows"
      :key="item.id"
      class="collaboration-card"
      :class="{ selected: selected?.id === item.id }"
    >
      <div class="card-title">
        <strong>第 {{ item.assessment_version }} 版 · {{ item.case_code }}</strong
        ><el-tag>{{ statuses[item.status] || item.status }}</el-tag
        ><el-tag v-if="!item.basis_current" type="warning">原版依据待重评</el-tag
        ><el-tag v-if="!item.is_latest" type="info">历史研判版本</el-tag>
      </div>
      <p>{{ item.purpose }}</p>
      <p v-if="item.decision_note" class="hint">协同处理说明：{{ item.decision_note }}</p>
      <small
        >参与专家：{{ item.participants.map((p) => p.name).join("、") }} ·
        {{ formatServerDateTime(item.created_at) }}</small
      >
      <div class="panel-actions">
        <el-button type="primary" plain @click="meeting(item)">进入会议讨论</el-button
        ><el-button
          v-if="[item.created_by, item.coordinator_id].includes(auth.userId)"
          @click="workItem(item)"
          >查看协同请求</el-button
        ><el-button @click="detail(item.id)">查看返回意见</el-button>
      </div>
    </article>
    <div class="panel-actions"><el-button :disabled="loading||saving||page<=1" @click="movePage(-1)">上一页协同</el-button><span>第 {{ page }} 页 · 本页 {{ rows.length }} 条</span><el-button :disabled="loading||saving||!nextCursor" @click="movePage(1)">下一页协同</el-button><el-button v-if="page>1||error" :disabled="loading||saving" @click="resetPages();load()">回到协同首页</el-button></div>
    <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
    <section v-if="selected" class="collaboration-feedback">
      <h4>第 {{ selected.assessment_version }} 版返回的协同意见</h4>
      <p class="hint">
        展示最近的公开讨论和工作项评论；讨论意见与独立复核分别记录。私聊内容不进入此处。
      </p>
      <el-empty
        v-if="!messages.length"
        description="暂无公开意见，可进入会议讨论"
        :image-size="55"
      />
      <article
        v-for="message in messages"
        :key="message.origin + message.id"
        class="feedback-message"
      >
        <small
          >{{ message.author }} ·
          {{ message.origin === "meeting" ? "会议公开讨论" : "协同请求评论" }} ·
          {{ formatServerDateTime(message.created_at) }}</small
        >
        <p>{{ message.content }}</p>
      </article>
    </section>
    <el-dialog
      v-model="open"
      title="发起同单位研判协同"
      width="min(620px, 94vw)"
      :close-on-click-modal="false"
      ><p>固定为本事项第 {{ assessment?.version }} 版。所有参与人均从本单位有效专家中选择。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" /><el-form
        label-position="top"
        ><el-form-item label="协同负责人"
          ><PagedReferenceSelect v-model="form.coordinator_id" label="协同负责人" :loader="participantOptions" :disabled="saving" /></el-form-item
        ><el-form-item label="其他参与专家（可选）"
          ><PagedReferenceSelect v-model="form.participant_ids" label="其他参与专家" multiple :selection-limit="8" :loader="participantOptions" :disabled="saving" /></el-form-item
        ><el-form-item label="协同问题"
          ><el-input
            v-model="form.purpose"
            type="textarea"
            :rows="4"
            maxlength="2000"
            placeholder="说明需要一起核对的资料、依据或不确定性" /></el-form-item></el-form
      ><template #footer
        ><el-button :disabled="saving" @click="open = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="create"
          >创建协同并关联本版</el-button
        ></template
      ></el-dialog
    >
  </section>
</template>
<style scoped>
.risk-collaboration-panel {
  padding-top: 18px;
  min-width: 0;
}
.risk-collaboration-panel > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
h3 {
  font-size: 18px;
  margin: 12px 0 6px;
}
header p,
.hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.panel-actions,
.card-title {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.panel-actions {
  margin-top: 16px;
}
.panel-actions .el-button + .el-button {
  margin-left: 0;
}
.scope-filter {
  margin: 18px 0;
}
.collaboration-card {
  padding: 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  margin-bottom: 14px;
}
.collaboration-card.selected {
  border-color: var(--el-color-primary);
}
.collaboration-card p,
.feedback-message p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.8;
  font-size: 14px;
}
.collaboration-card small,
.feedback-message small {
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.collaboration-feedback {
  margin-top: 24px;
  border-top: 1px solid var(--el-border-color-light);
}
.collaboration-feedback h4 {
  font-size: 16px;
}
.feedback-message {
  padding: 14px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.feedback-message p {
  margin: 8px 0;
}
@media (max-width: 650px) {
  .panel-actions .el-button {
    min-height: 44px;
  }
  .collaboration-card {
    padding: 14px;
  }
  :deep(textarea) {
    font-size: 16px;
  }
}
</style>
