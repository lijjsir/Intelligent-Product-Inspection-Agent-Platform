<script setup lang="ts">
import { Check, Close, Document, Paperclip, Plus, Refresh, Select } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useCollabStore } from "@/stores/collab.store";
import type {
  CollabActionRequestCreatePayload,
  CollabTarget,
  CollabWorkItem,
  CollabWorkItemType,
  CollabWorkItemView,
} from "@/types/collab.types";
import { formatServerDateTime } from "@/utils/date-time";

type CenterTab = CollabWorkItemView | "history";

const store = useCollabStore();
const route = useRoute();
const activeTab = ref<CenterTab>("pending");
const selectedWorkItemId = ref("");
const selectedHistoryThreadId = ref("");
const itemTypeFilter = ref<CollabWorkItemType | "">("");
const scopeFilter = ref("");
const roomFilter = ref("");
const createVisible = ref(false);
const decisionVisible = ref(false);
const decisionAction = ref("");
const decisionNote = ref("");
const comment = ref("");
const commentSending = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const createForm = reactive<CollabActionRequestCreatePayload>({
  target_type: "user",
  target_id: "",
  title: "",
  description: "",
  attachments: [],
  source_link: "",
  source_context: {},
  idempotency_key: "",
});

const tabs: Array<{ value: CenterTab; label: string }> = [
  { value: "pending", label: "待我处理" },
  { value: "initiated", label: "我发起的" },
  { value: "processed", label: "已处理" },
  { value: "history", label: "历史会话" },
];

const selectedWorkItem = computed(() => (
  store.workItems.find((item) => item.id === selectedWorkItemId.value) || store.workItems[0] || null
));
const selectedHistoryThread = computed(() => (
  store.threads.find((thread) => thread.id === selectedHistoryThreadId.value) || store.threads[0] || null
));
const selectedHistoryMessages = computed(() => (
  selectedHistoryThread.value ? store.messagesByThread[selectedHistoryThread.value.id] || [] : []
));
const meetingTargets = computed(() => store.targets.filter((target) => target.target_type === "meeting_room"));
const createTargets = computed(() => store.targets.filter((target) => target.target_type === createForm.target_type));
const activeCount = computed(() => {
  if (activeTab.value === "pending") return store.workItemSummary.pending_count;
  if (activeTab.value === "initiated") return store.workItemSummary.initiated_count;
  if (activeTab.value === "processed") return store.workItemSummary.processed_count;
  return store.threads.length;
});

function unwrapRouteTab(): CenterTab {
  const requested = String(route.query.view || "");
  return tabs.some((tab) => tab.value === requested) ? requested as CenterTab : "pending";
}

function formatTime(value?: string | null) {
  return formatServerDateTime(value, { compactDate: true, includeSeconds: false }) || "—";
}

function itemTypeLabel(type: string) {
  return type === "memory_share" ? "记忆共享" : "处理请求";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending_approval: "待审批",
    pending: "待处理",
    requested: "已发起",
    executed: "已批准",
    accepted: "已接受",
    done: "已完成",
    rejected: "已拒绝",
    cancelled: "已撤销",
  };
  return labels[status] || status;
}

function statusTone(status: string) {
  if (["executed", "done", "accepted"].includes(status)) return "success";
  if (status === "rejected") return "danger";
  if (status === "cancelled") return "info";
  return "warning";
}

function actionLabel(action: string) {
  const labels: Record<string, string> = {
    approve: "批准",
    reject: "拒绝",
    cancel: "撤销",
    accepted: "接受",
    rejected: "拒绝",
    done: "完成",
  };
  return labels[action] || action;
}

function actionType(action: string) {
  if (["approve", "accepted", "done"].includes(action)) return "primary";
  if (["reject", "rejected"].includes(action)) return "danger";
  return "default";
}

function targetLabel(target: CollabTarget) {
  return `${target.label}${target.description ? ` · ${target.description}` : ""}`;
}

function compactEvidence(value: Record<string, unknown>) {
  return String(value.label || value.name || value.title || value.message_id || value.id || value.type || "来源证据");
}

async function loadActiveWorkItems() {
  if (activeTab.value === "history") return;
  try {
    await store.loadWorkItems(activeTab.value, {
      item_type: itemTypeFilter.value || null,
      scope_type: scopeFilter.value || null,
      room_id: roomFilter.value || null,
    });
    const requestedId = String(route.query.work_item || "");
    selectedWorkItemId.value = store.workItems.some((item) => item.id === requestedId)
      ? requestedId
      : store.workItems[0]?.id || "";
  } catch {
    // The store exposes a recoverable error state in the page.
  }
}

async function loadHistory() {
  await store.loadThreads(true);
  selectedHistoryThreadId.value = store.activeThreadId || store.threads[0]?.id || "";
  if (selectedHistoryThreadId.value) await store.openThread(selectedHistoryThreadId.value);
}

async function selectHistoryThread(threadId: string) {
  selectedHistoryThreadId.value = threadId;
  await store.openThread(threadId);
}

function openDecision(action: string) {
  const item = selectedWorkItem.value;
  if (!item) return;
  if (action === "cancel") {
    void cancelItem(item);
    return;
  }
  decisionAction.value = action;
  decisionNote.value = "";
  decisionVisible.value = true;
}

async function cancelItem(item: CollabWorkItem) {
  try {
    await ElMessageBox.confirm("撤销后目标范围将不会获得这条记忆，确定继续吗？", "撤销共享请求", {
      confirmButtonText: "确认撤销",
      cancelButtonText: "保留请求",
      type: "warning",
    });
    await store.handleWorkItem(item, "cancel");
    ElMessage.success("共享请求已撤销");
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error("撤销失败，请刷新后重试");
  }
}

async function submitDecision() {
  const item = selectedWorkItem.value;
  if (!item) return;
  const isReject = ["reject", "rejected"].includes(decisionAction.value);
  if (isReject && !decisionNote.value.trim()) {
    ElMessage.warning("拒绝时必须填写理由");
    return;
  }
  try {
    await store.handleWorkItem(item, decisionAction.value, decisionNote.value.trim() || null);
    decisionVisible.value = false;
    ElMessage.success(`${actionLabel(decisionAction.value)}成功`);
  } catch {
    ElMessage.error("处理失败，可能已由其他人处理，请刷新状态");
  }
}

async function submitComment() {
  const item = selectedWorkItem.value;
  if (!item || !comment.value.trim()) return;
  commentSending.value = true;
  try {
    await store.sendWorkItemComment(item, comment.value);
    comment.value = "";
    ElMessage.success("补充留言已发送");
  } finally {
    commentSending.value = false;
  }
}

function openCreate() {
  Object.assign(createForm, {
    target_type: "user",
    target_id: "",
    title: "",
    description: "",
    attachments: [],
    source_link: "",
    source_context: {},
    idempotency_key: `action-request:${Date.now()}:${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`,
  });
  store.clearPendingAttachments();
  createVisible.value = true;
}

async function pickFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";
  if (!files.length) return;
  try {
    const items = await store.uploadAttachments(files);
    createForm.attachments = items;
  } catch {
    ElMessage.error("附件上传失败");
  }
}

async function submitCreate() {
  if (!createForm.target_id || !createForm.title.trim() || !createForm.description.trim()) {
    ElMessage.warning("请完整填写目标、标题和说明");
    return;
  }
  try {
    await store.createActionRequest({
      ...createForm,
      title: createForm.title.trim(),
      description: createForm.description.trim(),
      source_link: createForm.source_link?.trim() || null,
      attachments: store.pendingAttachments,
    });
    createVisible.value = false;
    activeTab.value = "initiated";
    await loadActiveWorkItems();
    ElMessage.success("处理请求已发起");
  } catch {
    ElMessage.error("发起失败，请检查目标权限后重试");
  }
}

watch(activeTab, async (tab) => {
  if (tab === "history") await loadHistory();
  else await loadActiveWorkItems();
});

watch(() => createForm.target_type, () => {
  createForm.target_id = "";
});

onMounted(async () => {
  activeTab.value = unwrapRouteTab();
  await Promise.all([store.loadSummary(), store.loadTargets()]);
  if (activeTab.value === "history") await loadHistory();
  else await loadActiveWorkItems();
});
</script>

<template>
  <section class="collab-center" aria-labelledby="collab-title">
    <header class="center-header">
      <div>
        <p class="eyebrow">跨模块协作</p>
        <h1 id="collab-title">协作中心</h1>
        <p class="subtitle">统一处理记忆共享审批和轻量处理请求；旧协作会话仅作历史查阅。</p>
      </div>
      <el-button class="touch-button" type="primary" :icon="Plus" @click="openCreate">发起处理请求</el-button>
    </header>

    <nav class="center-tabs" aria-label="协作中心视图">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        class="center-tab"
        :class="{ active: activeTab === tab.value }"
        :aria-current="activeTab === tab.value ? 'page' : undefined"
        @click="activeTab = tab.value"
      >
        {{ tab.label }}
        <span v-if="tab.value === 'pending' && store.workItemSummary.pending_count" class="tab-count">{{ store.workItemSummary.pending_count }}</span>
      </button>
    </nav>

    <template v-if="activeTab !== 'history'">
      <div class="filter-bar">
        <el-select v-model="itemTypeFilter" clearable placeholder="全部类型" @change="loadActiveWorkItems">
          <el-option label="记忆共享" value="memory_share" /><el-option label="处理请求" value="action_request" />
        </el-select>
        <el-select v-model="scopeFilter" clearable placeholder="全部作用域" @change="loadActiveWorkItems">
          <el-option label="会议室" value="meeting_room" /><el-option label="成员个人" value="user" /><el-option label="组织空间" value="org_space" />
        </el-select>
        <el-select v-model="roomFilter" clearable filterable placeholder="全部会议室" @change="loadActiveWorkItems">
          <el-option v-for="target in meetingTargets" :key="target.target_id" :label="target.label" :value="target.target_id" />
        </el-select>
        <span class="result-count">{{ activeCount }} 项</span>
        <el-button class="touch-button" :icon="Refresh" :loading="store.loadingWorkItems" @click="loadActiveWorkItems">刷新</el-button>
      </div>

      <div v-if="store.workItemError" class="error-state" role="alert">
        <span>{{ store.workItemError }}</span><button type="button" @click="loadActiveWorkItems">重新加载</button>
      </div>

      <div class="workbench">
        <aside class="work-list" aria-label="协作工作项列表">
          <el-skeleton v-if="store.loadingWorkItems" :rows="6" animated class="p-5" />
          <el-empty v-else-if="!store.workItems.length" description="当前视图暂无工作项" />
          <button
            v-for="item in store.workItems"
            v-else
            :key="item.id"
            type="button"
            class="work-card"
            :class="{ selected: selectedWorkItem?.id === item.id }"
            @click="selectedWorkItemId = item.id"
          >
            <span class="card-topline"><span class="type-label">{{ itemTypeLabel(item.item_type) }}</span><el-tag size="small" :type="statusTone(item.status)" effect="plain">{{ statusLabel(item.status) }}</el-tag></span>
            <strong>{{ item.title }}</strong>
            <span class="scope-line">{{ item.source.label || "未知来源" }} → {{ item.target.label || "未知目标" }}</span>
            <span class="card-meta">{{ item.requester_label || "未知发起人" }} · {{ formatTime(item.updated_at || item.created_at) }}</span>
          </button>
        </aside>

        <main class="work-detail" aria-live="polite">
          <el-empty v-if="!selectedWorkItem" description="选择一个工作项查看详情" />
          <template v-else>
            <div class="detail-heading">
              <div><span class="type-label">{{ itemTypeLabel(selectedWorkItem.item_type) }}</span><h2>{{ selectedWorkItem.title }}</h2></div>
              <el-tag :type="statusTone(selectedWorkItem.status)" effect="plain">{{ statusLabel(selectedWorkItem.status) }}</el-tag>
            </div>
            <p class="detail-description">{{ selectedWorkItem.description || "暂无补充说明" }}</p>
            <dl class="metadata-grid">
              <div><dt>来源</dt><dd>{{ selectedWorkItem.source.label || "—" }}</dd></div>
              <div><dt>目标</dt><dd>{{ selectedWorkItem.target.label || "—" }}</dd></div>
              <div><dt>发起人</dt><dd>{{ selectedWorkItem.requester_label || "—" }}</dd></div>
              <div><dt>发起时间</dt><dd>{{ formatTime(selectedWorkItem.created_at) }}</dd></div>
            </dl>

            <section class="detail-section">
              <div class="section-title">
                <h3>来源证据</h3>
                <RouterLink v-if="selectedWorkItem.source_link?.startsWith('/')" :to="selectedWorkItem.source_link">查看来源</RouterLink>
                <a v-else-if="selectedWorkItem.source_link" :href="selectedWorkItem.source_link" target="_blank" rel="noreferrer">查看来源</a>
              </div>
              <div v-if="selectedWorkItem.evidence.length" class="evidence-list">
                <div v-for="(evidence, index) in selectedWorkItem.evidence" :key="index" class="evidence-row">
                  <Document /><a v-if="typeof evidence.url === 'string'" :href="evidence.url" target="_blank" rel="noreferrer">{{ compactEvidence(evidence) }}</a><span v-else>{{ compactEvidence(evidence) }}</span>
                </div>
              </div>
              <p v-else class="muted">未附加独立证据，可从来源页面核对完整上下文。</p>
            </section>

            <section class="detail-section">
              <h3>处理记录</h3>
              <ol class="history-list">
                <li v-for="(entry, index) in selectedWorkItem.history" :key="index">
                  <span class="history-dot" /><div><strong>{{ statusLabel(String(entry.action || "")) }}</strong><p>{{ entry.actor_label || entry.actor_id || "系统" }} · {{ formatTime(entry.at as string) }}</p><p v-if="entry.note" class="history-note">{{ entry.note }}</p></div>
                </li>
              </ol>
            </section>

            <section v-if="selectedWorkItem.item_type === 'action_request'" class="comment-box">
              <label for="work-item-comment">补充留言</label>
              <el-input id="work-item-comment" v-model="comment" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="补充与该工作项相关的信息" />
              <el-button class="touch-button" :loading="commentSending" :disabled="!comment.trim()" @click="submitComment">发送留言</el-button>
            </section>

            <footer v-if="selectedWorkItem.allowed_actions.length" class="detail-actions">
              <el-button
                v-for="action in selectedWorkItem.allowed_actions"
                :key="action"
                class="touch-button"
                :type="actionType(action)"
                :plain="!['approve', 'accepted', 'done'].includes(action)"
                :icon="['reject', 'rejected'].includes(action) ? Close : ['approve', 'accepted', 'done'].includes(action) ? Check : Select"
                :loading="store.handlingWorkItem"
                @click="openDecision(action)"
              >{{ actionLabel(action) }}</el-button>
            </footer>
          </template>
        </main>
      </div>
    </template>

    <div v-else class="history-workbench">
      <aside class="history-list-panel" aria-label="历史会话列表">
        <div class="readonly-callout">历史会话为只读记录，不支持回复、创建或删除。</div>
        <el-skeleton v-if="store.loadingThreads" :rows="5" animated class="p-5" />
        <el-empty v-else-if="!store.threads.length" description="暂无历史会话" />
        <button v-for="thread in store.threads" v-else :key="thread.id" type="button" class="history-thread" :class="{ selected: selectedHistoryThread?.id === thread.id }" @click="selectHistoryThread(thread.id)">
          <strong>{{ thread.title || "历史协作会话" }}</strong><span>{{ formatTime(thread.last_message_at || thread.updated_at) }}</span>
        </button>
      </aside>
      <main class="history-detail">
        <el-empty v-if="!selectedHistoryThread" description="选择一条历史会话" />
        <template v-else>
          <header><div><h2>{{ selectedHistoryThread.title }}</h2><p>只读历史 · {{ selectedHistoryMessages.length }} 条记录</p></div><el-tag type="info" effect="plain">只读</el-tag></header>
          <el-skeleton v-if="store.loadingMessages" :rows="6" animated />
          <div v-else class="message-history">
            <article v-for="message in selectedHistoryMessages" :key="message.id" class="history-message">
              <div><strong>{{ message.sender_type === 'system' ? '系统' : message.sender_id }}</strong><time>{{ formatTime(message.created_at) }}</time></div>
              <p>{{ message.content || "（无文字内容）" }}</p>
              <div v-if="message.attachments.length" class="attachment-links"><a v-for="file in message.attachments" :key="file.id" :href="file.url" target="_blank" rel="noreferrer"><Paperclip />{{ file.file_name }}</a></div>
            </article>
          </div>
        </template>
      </main>
    </div>

    <el-dialog v-model="decisionVisible" :title="`${actionLabel(decisionAction)}工作项`" width="min(520px, 92vw)" destroy-on-close>
      <label class="dialog-label" for="decision-note">{{ ['reject', 'rejected'].includes(decisionAction) ? '拒绝理由（必填）' : '处理说明（选填）' }}</label>
      <el-input id="decision-note" v-model="decisionNote" type="textarea" :rows="4" maxlength="1000" show-word-limit autofocus />
      <template #footer><el-button class="touch-button" @click="decisionVisible = false">取消</el-button><el-button class="touch-button" :type="actionType(decisionAction)" :loading="store.handlingWorkItem" @click="submitDecision">确认{{ actionLabel(decisionAction) }}</el-button></template>
    </el-dialog>

    <el-dialog v-model="createVisible" title="发起结构化处理请求" width="min(620px, 94vw)" destroy-on-close>
      <el-form label-position="top" class="request-form" @submit.prevent="submitCreate">
        <div class="form-grid">
          <el-form-item label="目标类型" required><el-segmented v-model="createForm.target_type" :options="[{ label: '成员', value: 'user' }, { label: '会议室', value: 'meeting_room' }]" /></el-form-item>
          <el-form-item label="协作目标" required><el-select v-model="createForm.target_id" filterable placeholder="选择目标"><el-option v-for="target in createTargets" :key="target.target_id" :label="targetLabel(target)" :value="target.target_id" /></el-select></el-form-item>
        </div>
        <el-form-item label="标题" required><el-input v-model="createForm.title" maxlength="200" show-word-limit placeholder="用一句话说明需要处理的事项" /></el-form-item>
        <el-form-item label="说明" required><el-input v-model="createForm.description" type="textarea" :rows="5" maxlength="4000" show-word-limit placeholder="补充背景、期望结果和必要证据" /></el-form-item>
        <el-form-item label="来源链接"><el-input v-model="createForm.source_link" placeholder="可填写会议室、检测结果或其他内部页面链接" /></el-form-item>
        <el-form-item label="附件">
          <input ref="fileInput" class="sr-only" type="file" multiple @change="pickFiles" /><el-button class="touch-button" :icon="Paperclip" :loading="store.uploading" @click="fileInput?.click()">选择附件</el-button>
          <div v-if="store.pendingAttachments.length" class="pending-files"><span v-for="file in store.pendingAttachments" :key="file.id">{{ file.name }}<button type="button" :aria-label="`移除 ${file.name}`" @click="store.removePendingAttachment(file.id)">×</button></span></div>
        </el-form-item>
      </el-form>
      <template #footer><el-button class="touch-button" @click="createVisible = false">取消</el-button><el-button class="touch-button" type="primary" :loading="store.sending" @click="submitCreate">发起请求</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.collab-center { min-height: calc(100vh - 80px); color: #18181b; }
.center-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 18px 20px 20px; border: 1px solid #e4e4e7; border-radius: 16px 16px 0 0; background: #fff; }
.eyebrow { margin: 0 0 6px; color: #3f7663; font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 0; font-size: 26px; line-height: 1.2; }
.subtitle { margin: 8px 0 0; color: #71717a; font-size: 14px; }
.center-tabs { display: flex; min-height: 52px; overflow-x: auto; border: 1px solid #e4e4e7; border-top: 0; background: #fff; }
.center-tab { position: relative; min-width: 112px; min-height: 52px; padding: 0 18px; border: 0; border-bottom: 3px solid transparent; background: transparent; color: #71717a; font-size: 14px; font-weight: 600; cursor: pointer; }
.center-tab:hover, .center-tab:focus-visible { color: #18181b; background: #fafafa; }
.center-tab.active { border-bottom-color: #18181b; color: #18181b; }
.tab-count { display: inline-flex; min-width: 20px; height: 20px; align-items: center; justify-content: center; margin-left: 6px; padding: 0 5px; border-radius: 999px; background: #18181b; color: #fff; font-size: 11px; }
.filter-bar { display: grid; grid-template-columns: minmax(140px, 190px) minmax(140px, 190px) minmax(160px, 240px) 1fr auto; align-items: center; gap: 10px; padding: 12px 16px; border: 1px solid #e4e4e7; border-top: 0; background: #fafafa; }
.result-count { justify-self: end; color: #71717a; font-size: 13px; }
.touch-button { min-height: 44px; }
.error-state { display: flex; justify-content: space-between; gap: 12px; padding: 12px 16px; border: 1px solid #fecaca; border-top: 0; background: #fef2f2; color: #991b1b; font-size: 13px; }
.error-state button { min-height: 44px; border: 0; background: transparent; color: inherit; font-weight: 700; cursor: pointer; }
.workbench, .history-workbench { display: grid; grid-template-columns: minmax(280px, 36%) minmax(0, 1fr); min-height: 610px; border: 1px solid #e4e4e7; border-top: 0; border-radius: 0 0 16px 16px; overflow: hidden; background: #fff; }
.work-list, .history-list-panel { max-height: calc(100vh - 260px); overflow-y: auto; border-right: 1px solid #e4e4e7; background: #fafafa; }
.work-card, .history-thread { width: 100%; min-height: 118px; display: flex; flex-direction: column; align-items: stretch; gap: 7px; padding: 16px 18px; border: 0; border-bottom: 1px solid #e4e4e7; background: transparent; text-align: left; cursor: pointer; }
.work-card:hover, .work-card:focus-visible, .history-thread:hover, .history-thread:focus-visible { background: #f4f4f5; outline: 2px solid transparent; }
.work-card.selected, .history-thread.selected { box-shadow: inset 4px 0 #18181b; background: #fff; }
.card-topline { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.type-label { color: #3f7663; font-size: 12px; font-weight: 700; }
.work-card strong { overflow: hidden; color: #27272a; font-size: 15px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.scope-line, .card-meta { overflow: hidden; color: #71717a; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.work-detail, .history-detail { min-width: 0; max-height: calc(100vh - 260px); overflow-y: auto; padding: 26px 28px; }
.detail-heading, .section-title, .history-detail > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.detail-heading h2, .history-detail h2 { margin: 6px 0 0; font-size: 22px; line-height: 1.35; }
.detail-description { margin: 18px 0; color: #3f3f46; line-height: 1.75; white-space: pre-wrap; }
.metadata-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; border: 1px solid #e4e4e7; border-radius: 12px; overflow: hidden; }
.metadata-grid div { min-height: 78px; padding: 14px 16px; border-right: 1px solid #e4e4e7; border-bottom: 1px solid #e4e4e7; }
.metadata-grid div:nth-child(2n) { border-right: 0; }.metadata-grid div:nth-last-child(-n+2) { border-bottom: 0; }
.metadata-grid dt { color: #a1a1aa; font-size: 12px; }.metadata-grid dd { margin: 7px 0 0; color: #27272a; font-size: 14px; font-weight: 600; }
.detail-section { padding: 22px 0; border-bottom: 1px solid #e4e4e7; }.detail-section h3 { margin: 0 0 12px; font-size: 15px; }.section-title a { color: #3f7663; font-size: 13px; font-weight: 600; }
.evidence-list { display: grid; gap: 8px; }.evidence-row { min-height: 44px; display: flex; align-items: center; gap: 9px; padding: 8px 12px; border: 1px solid #e4e4e7; border-radius: 9px; color: #52525b; font-size: 13px; }.evidence-row svg, .attachment-links svg { width: 16px; flex: none; }.evidence-row a { color: #3f7663; }.muted { color: #a1a1aa; font-size: 13px; }
.history-list { margin: 0; padding: 0; list-style: none; }.history-list li { display: grid; grid-template-columns: 12px 1fr; gap: 10px; padding: 8px 0; }.history-dot { width: 8px; height: 8px; margin-top: 6px; border-radius: 50%; background: #3f7663; }.history-list strong { font-size: 13px; }.history-list p { margin: 3px 0 0; color: #71717a; font-size: 12px; }.history-note { color: #3f3f46 !important; }
.comment-box { display: grid; gap: 10px; margin-top: 20px; padding: 16px; border-radius: 12px; background: #f4f7f5; }.comment-box label, .dialog-label { color: #3f3f46; font-size: 13px; font-weight: 700; }.comment-box .touch-button { justify-self: end; }
.detail-actions { position: sticky; bottom: -26px; display: flex; justify-content: flex-end; gap: 10px; margin: 24px -28px -26px; padding: 16px 28px; border-top: 1px solid #e4e4e7; background: rgba(255,255,255,.96); backdrop-filter: blur(8px); }
.readonly-callout { margin: 14px; padding: 12px; border: 1px solid #d4d4d8; border-radius: 10px; background: #fff; color: #71717a; font-size: 12px; line-height: 1.55; }.history-thread { min-height: 78px; }.history-thread span { color: #a1a1aa; font-size: 12px; }
.history-detail > header { padding-bottom: 18px; border-bottom: 1px solid #e4e4e7; }.history-detail header p { margin: 5px 0 0; color: #71717a; font-size: 12px; }.message-history { display: grid; gap: 12px; padding-top: 18px; }.history-message { padding: 14px 16px; border: 1px solid #e4e4e7; border-radius: 10px; }.history-message > div:first-child { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }.history-message time { color: #a1a1aa; }.history-message p { margin: 10px 0 0; color: #3f3f46; line-height: 1.65; white-space: pre-wrap; }.attachment-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }.attachment-links a { display: inline-flex; min-height: 36px; align-items: center; gap: 6px; padding: 6px 9px; border-radius: 7px; background: #f4f4f5; color: #3f7663; font-size: 12px; }
.request-form { padding-top: 4px; }.form-grid { display: grid; grid-template-columns: 1fr 1.35fr; gap: 14px; }.pending-files { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }.pending-files span { display: inline-flex; min-height: 36px; align-items: center; gap: 6px; padding: 5px 8px; border-radius: 7px; background: #f4f4f5; font-size: 12px; }.pending-files button { width: 28px; height: 28px; border: 0; border-radius: 5px; background: transparent; cursor: pointer; }.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
:deep(.el-select) { width: 100%; }:deep(.el-input__wrapper), :deep(.el-select__wrapper) { min-height: 44px; }:deep(.el-dialog__footer .el-button) { min-width: 96px; }
@media (max-width: 900px) { .filter-bar { grid-template-columns: 1fr 1fr; }.result-count { justify-self: start; }.workbench, .history-workbench { grid-template-columns: 1fr; }.work-list, .history-list-panel { max-height: 320px; border-right: 0; border-bottom: 1px solid #e4e4e7; }.work-detail, .history-detail { max-height: none; padding: 20px; }.detail-actions { bottom: -20px; margin: 20px -20px -20px; padding: 12px 20px; } }
@media (max-width: 620px) { .center-header { align-items: stretch; flex-direction: column; }.center-tabs { display: grid; grid-template-columns: repeat(2, 1fr); }.center-tab { width: 100%; }.filter-bar, .form-grid, .metadata-grid { grid-template-columns: 1fr; }.metadata-grid div, .metadata-grid div:nth-child(2n), .metadata-grid div:nth-last-child(-n+2) { border-right: 0; border-bottom: 1px solid #e4e4e7; }.metadata-grid div:last-child { border-bottom: 0; }.detail-actions { flex-wrap: wrap; }.detail-actions .el-button { flex: 1 1 120px; margin: 0; } }
</style>
