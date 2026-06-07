<script setup lang="ts">
import { ArrowLeft, ArrowRight, ChatDotRound, Check, Close, CopyDocument, Delete, EditPen, FolderOpened, Key, MagicStick, Plus, Promotion, RefreshRight, Share, User } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type StyleValue } from "vue";
import { feedbackApi } from "@/api/feedback.api";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useMeetingStore } from "@/stores/meeting.store";
import type { MeetingDataDomain, MeetingMemory, MeetingMessage, MeetingRoom, MeetingRoomMember, MeetingRoomType } from "@/types/meeting.types";
import { normalizeAiResponseText } from "@/utils/ai-response";
import { writeTextToClipboard } from "@/utils/clipboard";

const auth = useAuthStore();
const store = useMeetingStore();

const roomTitle = ref("会议室");
const roomPassword = ref("");
const roomType = ref<MeetingRoomType>("quality_business");
const joinCode = ref("");
const joinPassword = ref("");
const hubMode = ref<"create" | "join">("create");
const input = ref("");
const actionTitle = ref("");
const actionDescription = ref("");
const actionOwnerId = ref("");
const quotedMessage = ref<MeetingMessage | null>(null);
const messageListRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);
const leftPanelWidth = ref(260);
const rightPanelWidth = ref(300);
const leftPanelCollapsed = ref(false);
const rightPanelCollapsed = ref(false);
const resizingPanel = ref<"" | "left" | "right">("");
let stopResizeListeners: (() => void) | null = null;

const PANEL_WIDTHS = {
  left: { min: 220, max: 420 },
  right: { min: 260, max: 520 },
};

const roomTypeOptions: Array<{ value: MeetingRoomType; label: string; note: string }> = [
  { value: "quality_business", label: "质检业务", note: "任务、结果、标准" },
  { value: "platform_ops", label: "平台运营", note: "Agent、模型、路由" },
  { value: "org_admin", label: "组织管理", note: "成员、角色、审计" },
  { value: "data_ops", label: "数据接入", note: "数据源、RAG、同步" },
  { value: "memory_governance", label: "记忆治理", note: "候选、共享、冲突" },
  { value: "general", label: "普通协作", note: "会议、资料、纪要" },
];

const roomTypeLabels = Object.fromEntries(roomTypeOptions.map((item) => [item.value, item.label])) as Record<string, string>;
const domainLabels: Record<string, string> = {
  quality: "质检业务",
  standard: "质检标准",
  meeting: "会议协作",
  memory: "记忆",
  platform_ops: "平台运营",
  model_billing: "模型成本",
  org_admin: "组织管理",
  data_access: "数据接入",
  security_audit: "安全审计",
  ai_conversation: "AI 会话",
};

const meetingLayoutStyle = computed<StyleValue>(() => ({
  "--left-panel-width": leftPanelCollapsed.value ? "52px" : `${leftPanelWidth.value}px`,
  "--right-panel-width": rightPanelCollapsed.value ? "52px" : `${rightPanelWidth.value}px`,
}));

const mentionTargets = computed(() => {
  const entries = [
    { id: "general_agent", agent_name: "会议Agent" },
  ];
  const seen = new Set<string>();
  return entries.filter((item) => {
    const key = item.agent_name.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
});
const activeMeetingLink = computed(() => {
  const code = store.activeRoom?.access_code;
  if (!code) return "";
  const url = new URL(window.location.href);
  url.searchParams.set("room", code);
  url.hash = "";
  return url.toString();
});
const hostMember = computed(() => {
  const creatorId = store.activeRoom?.created_by;
  return store.members.find((member) => member.role === "host")
    || store.members.find((member) => member.user_id === creatorId)
    || null;
});
const visibleMemberCount = computed(() => store.members.length || store.activeRoom?.member_count || 0);
const canManageRoom = computed(() => Boolean(store.activeRoom && store.activeRoom.created_by === auth.userId));
const canReviewMemory = computed(() => {
  if (!store.activeRoom) return false;
  if (store.activeRoom.created_by === auth.userId) return true;
  return store.members.some((member) => member.user_id === auth.userId && member.role === "host");
});
const roomTitleCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const room of store.rooms) {
    const title = room.title.trim() || "会议室";
    counts.set(title, (counts.get(title) || 0) + 1);
  }
  return counts;
});
const roomStatusLabel = computed(() => {
  const status = store.activeRoom?.status || "";
  if (status === "active") return "进行中";
  if (status === "closed") return "已关闭";
  if (status === "archived") return "已归档";
  return status || "未选择";
});
const activeRoomTypeLabel = computed(() => {
  const previewLabel = store.contextPreview?.room_type_label;
  if (previewLabel) return previewLabel;
  return roomTypeLabel(store.activeRoom?.room_type);
});
const contextAllowedDomains = computed(() => store.contextPreview?.allowed_domains || store.activeRoom?.allowed_data_domains || []);
const contextDeniedDomains = computed(() => store.contextPreview?.denied_domains || []);

function canDeleteRoom(room: MeetingRoom) {
  return room.created_by === auth.userId;
}

function roomTypeLabel(value?: string | null) {
  return roomTypeLabels[String(value || "quality_business")] || "质检业务";
}

function domainLabel(value: string) {
  return domainLabels[value] || value;
}

function roomDomainPreview(room: MeetingRoom) {
  const domains = room.allowed_data_domains || [];
  if (!domains.length) return roomTypeLabel(room.room_type);
  return domains.slice(0, 2).map(domainLabel).join("、") + (domains.length > 2 ? ` +${domains.length - 2}` : "");
}

function auditDecisionLabel(value: string) {
  if (value === "allowed") return "允许";
  if (value === "partial") return "部分";
  if (value === "denied") return "拒绝";
  return value || "未知";
}

function auditDecisionClass(value: string) {
  if (value === "allowed") return "audit-allowed";
  if (value === "partial") return "audit-partial";
  if (value === "denied") return "audit-denied";
  return "";
}

function hasMeetingAgentMention(content: string) {
  return content.replace(/\s+/g, "").toLowerCase().includes("@会议agent");
}

function memberRoleLabel(role: string) {
  return role === "host" ? "主持人" : "成员";
}

function normalizedMemberRole(role: string): "host" | "member" {
  return role === "host" ? "host" : "member";
}

function memberInitial(name: string) {
  return (name || "?").trim().slice(0, 1).toUpperCase();
}

function parseApiTime(value?: string | null) {
  if (!value) return null;
  const raw = String(value).trim();
  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(raw);
  const date = new Date(hasTimezone ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const date = parseApiTime(value);
  if (!date) return value;
  return date.toLocaleString("zh-CN", { hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function roomDisplayTitle(room: { title: string; access_code: string }) {
  const title = room.title.trim() || "会议室";
  return (roomTitleCounts.value.get(title) || 0) > 1 ? `${title} · ${room.access_code}` : title;
}

function roomRecentLabel(room: { last_message_at?: string | null; updated_at?: string | null; created_at?: string | null }) {
  const value = room.last_message_at || room.updated_at || room.created_at;
  return formatTime(value);
}

function memoryConfidence(memory: MeetingMemory) {
  if (typeof memory.confidence !== "number") return "";
  return `${Math.round(memory.confidence * 100)}%`;
}

function quotedMessageTitle(messageId?: string | null) {
  if (!messageId) return "";
  const message = store.messages.find((item) => item.id === messageId);
  if (!message) return "引用的会议消息已不可见。";
  return `${message.username}: ${displayMessageContent(message).slice(0, 80)}`;
}

function displayMessageContent(message: MeetingMessage): string {
  if (message.message_type === "agent_streaming") return "会议Agent正在整理回复...";
  return message.message_type === "agent" ? normalizeAiResponseText(message.content).content : message.content;
}

function clampPanelWidth(panel: "left" | "right", value: number) {
  const limits = PANEL_WIDTHS[panel];
  return Math.min(limits.max, Math.max(limits.min, Math.round(value)));
}

function stopPanelResize() {
  if (stopResizeListeners) {
    stopResizeListeners();
    stopResizeListeners = null;
  }
  resizingPanel.value = "";
}

function startPanelResize(panel: "left" | "right", event: PointerEvent) {
  if (event.button !== 0) return;
  event.preventDefault();
  stopPanelResize();

  const startX = event.clientX;
  const startWidth = panel === "left" ? leftPanelWidth.value : rightPanelWidth.value;
  const previousCursor = document.body.style.cursor;
  const previousUserSelect = document.body.style.userSelect;
  resizingPanel.value = panel;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";

  const onPointerMove = (moveEvent: PointerEvent) => {
    const delta = panel === "left" ? moveEvent.clientX - startX : startX - moveEvent.clientX;
    const nextWidth = clampPanelWidth(panel, startWidth + delta);
    if (panel === "left") {
      leftPanelWidth.value = nextWidth;
    } else {
      rightPanelWidth.value = nextWidth;
    }
  };
  const onPointerUp = () => {
    document.body.style.cursor = previousCursor;
    document.body.style.userSelect = previousUserSelect;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    stopResizeListeners = null;
    resizingPanel.value = "";
  };

  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
  stopResizeListeners = onPointerUp;
}

async function copyToClipboard(text: string, successText = "已复制") {
  try {
    const copied = await writeTextToClipboard(text);
    if (!copied) throw new Error("clipboard unavailable");
    ElMessage.success(successText);
  } catch {
    ElMessage.error("复制失败，请手动复制。");
  }
}

function shareMeetingMessage(message: MeetingMessage) {
  const roomPart = store.activeRoom?.access_code ? `?room=${store.activeRoom.access_code}` : "";
  const url = `${window.location.origin}${window.location.pathname}${roomPart}#meeting-message-${message.id}`;
  copyToClipboard(url, "分享链接已复制。");
}

function buildInviteText() {
  if (!store.activeRoom) return "";
  return [
    `请加入会议：${store.activeRoom.title}`,
    `会议码：${store.activeRoom.access_code}`,
    `加入链接：${activeMeetingLink.value}`,
    "如果会议设置了密码，请向邀请人获取。",
  ].join("\n");
}

function copyInvite() {
  const text = buildInviteText();
  if (!text) return;
  copyToClipboard(text, "邀请信息已复制");
}

async function scrollToBottom() {
  await nextTick();
  const el = messageListRef.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

// Feedback

async function submitMeetingFeedback(message: MeetingMessage, feedbackType: "up" | "down") {
  const previous = store.messageReactions[message.id];
  store.setReaction(message.id, feedbackType);
  try {
    await feedbackApi.submitMessage("meeting", message.id, {
      feedback_type: feedbackType,
      rating: feedbackType === "up" ? 5 : 1,
      category: (feedbackType === "up" ? "meeting_helpful" : "meeting_not_helpful") as any,
      comment: `meeting_room:${message.room_id}`,
    });
    ElMessage.success(feedbackType === "up" ? "已标记为有帮助" : "已标记为无帮助");
  } catch (error) {
    store.setReaction(message.id, previous || "");
    ElMessage.error("反馈提交失败，请稍后重试。");
    console.error(error);
  }
}

// Input

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// Actions

async function createRoom() {
  try {
    const room = await store.createRoom(roomTitle.value.trim() || "会议室", roomPassword.value.trim() || null, {
      room_type: roomType.value,
    });
    roomTitle.value = "会议室";
    roomPassword.value = "";
    ElMessage.success(`会议室已创建，会议码 ${room.access_code}`);
  } catch (error) {
    ElMessage.error("创建会议室失败，请稍后重试。");
    console.error(error);
  }
}

async function joinRoom() {
  if (!joinCode.value.trim()) return;
  try {
    await store.joinRoom(joinCode.value.trim(), joinPassword.value.trim() || null);
    joinCode.value = "";
    joinPassword.value = "";
    ElMessage.success("已加入会议室。");
  } catch (error) {
    ElMessage.error("加入失败，请检查会议码或密码。");
    console.error(error);
  }
}

async function sendMessage() {
  if (!store.canSend) return;
  const content = input.value.trim();
  if (!content) return;
  try {
    const shouldAskMeetingAgent = hasMeetingAgentMention(content);
    const message = await store.sendMessage(content, quotedMessage.value?.id || null, {
      skipAgentTrigger: shouldAskMeetingAgent,
    });
    if (!message) return;
    input.value = "";
    quotedMessage.value = null;
    await scrollToBottom();
    if (shouldAskMeetingAgent) {
      await runGeneralAgent(content);
    }
  } catch (error) {
    ElMessage.error("消息发送失败，请稍后重试。");
    console.error(error);
  }
}

async function runGeneralAgent(query = "") {
  if (!store.activeRoom) return;
  try {
    const result = await store.runGeneralAgent("auto", query);
    await scrollToBottom();
    if (result) {
      ElMessage.success("会议Agent已回复。");
    }
  } catch (error) {
    ElMessage.error("会议Agent回应失败，请稍后重试。");
    console.error(error);
  }
}

async function extractCandidateMemories() {
  if (!store.activeRoom || !canReviewMemory.value) return;
  try {
    const list = await store.extractMemories();
    ElMessage.success(list.length ? "候选记忆已提取。" : "暂无可提取的候选记忆。");
  } catch (error) {
    ElMessage.error("提取候选记忆失败，请稍后重试。");
    console.error(error);
  }
}

async function confirmCandidateMemory(memory: MeetingMemory) {
  if (!canReviewMemory.value) return;
  try {
    await store.confirmMemory(memory.memory_id, { title: memory.title, content: memory.content });
    ElMessage.success("记忆已发布为项目共享记忆");
  } catch (error) {
    ElMessage.error("确认记忆失败，请稍后重试。");
    console.error(error);
  }
}

async function rejectCandidateMemory(memory: MeetingMemory) {
  if (!canReviewMemory.value) return;
  try {
    await store.rejectMemory(memory.memory_id);
    ElMessage.success("候选记忆已拒绝");
  } catch (error) {
    ElMessage.error("拒绝记忆失败，请稍后重试。");
    console.error(error);
  }
}

async function updateMemberRole(member: MeetingRoomMember, role: "host" | "member") {
  if (!store.activeRoom || !canManageRoom.value || normalizedMemberRole(member.role) === role) return;
  try {
    await store.updateMemberRole(member.user_id, role);
    ElMessage.success(`已设为${memberRoleLabel(role)}`);
  } catch (error) {
    ElMessage.error("成员权限更新失败，请稍后重试。");
    console.error(error);
  }
}

async function createActionItem() {
  const title = actionTitle.value.trim();
  if (!title) return;
  try {
    await store.createActionItem({
      title,
      description: actionDescription.value.trim() || null,
      owner_id: actionOwnerId.value || null,
    });
    actionTitle.value = "";
    actionDescription.value = "";
    actionOwnerId.value = "";
    ElMessage.success("会议待办已新增");
  } catch (error) {
    ElMessage.error("新增会议待办失败，请稍后重试。");
    console.error(error);
  }
}

async function completeActionItem(actionItemId: string) {
  try {
    await store.completeActionItem(actionItemId);
    ElMessage.success("会议待办已完成");
  } catch (error) {
    ElMessage.error("更新会议待办失败，请稍后重试。");
    console.error(error);
  }
}

async function editRoomTitle() {
  if (!store.activeRoom) return;
  try {
    const { value } = await ElMessageBox.prompt("修改会议标题", "会议设置", {
      inputValue: store.activeRoom.title,
      inputPattern: /^.{1,120}$/,
      inputErrorMessage: "标题长度需为 1 到 120 个字符。",
      confirmButtonText: "保存",
      cancelButtonText: "取消",
    });
    await store.updateRoomTitle(String(value || "").trim());
    ElMessage.success("会议标题已更新。");
  } catch {
    // cancelled
  }
}

async function closeRoom() {
  if (!store.activeRoom) return;
  try {
    await ElMessageBox.confirm("关闭会议后将停止发送新消息，历史内容仍可查看。", "关闭会议", {
      confirmButtonText: "关闭",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.closeRoom();
    ElMessage.success("会议已关闭。");
  } catch {
    // cancelled
  }
}

async function archiveRoom() {
  if (!store.activeRoom) return;
  try {
    await ElMessageBox.confirm("归档后会议会保留为历史记录，可继续查看。", "归档会议", {
      confirmButtonText: "归档",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.archiveRoom();
    ElMessage.success("会议已归档。");
  } catch {
    // cancelled
  }
}

async function insertAgentMention(agentName: string) {
  const mention = `@${agentName} `;
  const el = inputRef.value;
  if (!el) {
    input.value = `${input.value}${mention}`;
    return;
  }
  const start = el.selectionStart ?? input.value.length;
  const end = el.selectionEnd ?? input.value.length;
  input.value = `${input.value.slice(0, start)}${mention}${input.value.slice(end)}`;
  await nextTick();
  el.focus();
  el.setSelectionRange(start + mention.length, start + mention.length);
}

async function quoteMessage(message: MeetingMessage) {
  quotedMessage.value = message;
  await nextTick();
  inputRef.value?.focus();
}

async function handleDeleteRoom(room: MeetingRoom) {
  if (!canDeleteRoom(room)) return;
  try {
    await ElMessageBox.confirm(
      `确定删除会议室「${room.title}」吗？删除后所有成员都将无法继续访问。`,
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
    await store.deleteRoom(room.id);
    ElMessage.success("会议室已删除");
  } catch {
    // cancelled or error
  }
}

// Lifecycle

async function loadActiveRoomData(newId: string) {
  if (!newId) {
    store.disconnectStream();
    await store.loadMembers();
    return;
  }

  const results = await Promise.allSettled([
    store.loadMessages(0),
    store.loadMembers(),
    store.loadMeetingContext(),
  ]);
  const failed = results.find((item) => item.status === "rejected");
  if (failed) {
    console.error("Failed to load meeting room data", failed.reason);
  }
  store.connectStream();
  await scrollToBottom();
}

watch(() => store.activeRoomId, async (newId) => {
  try {
    await loadActiveRoomData(newId);
  } catch (error) {
    console.error("Failed to switch meeting room", error);
  }
});

watch(() => store.messages.length, async () => {
  await scrollToBottom();
});

watch(() => store.messages.map((item) => `${item.id}:${item.content.length}`).join("|"), async () => {
  await scrollToBottom();
});

onMounted(async () => {
  const invitedCode = new URLSearchParams(window.location.search).get("room")?.trim().toUpperCase() || "";
  if (invitedCode) {
    joinCode.value = invitedCode;
    hubMode.value = "join";
  }
  await store.loadRooms(true);
  if (invitedCode) {
    const matchedRoom = store.rooms.find((room) => room.access_code.toUpperCase() === invitedCode);
    store.activeRoomId = matchedRoom?.id || "";
  }
});

onBeforeUnmount(() => {
  stopPanelResize();
  store.disconnectStream();
});
</script>

<template>
  <div
    class="meeting-page"
    :class="{
      'is-left-collapsed': leftPanelCollapsed,
      'is-right-collapsed': rightPanelCollapsed,
      'is-resizing-left': resizingPanel === 'left',
      'is-resizing-right': resizingPanel === 'right',
    }"
    :style="meetingLayoutStyle"
  >
    <aside class="meeting-sidebar" :class="{ 'panel-collapsed': leftPanelCollapsed }">
      <button
        type="button"
        class="panel-toggle panel-toggle-left"
        :aria-label="leftPanelCollapsed ? '展开会议入口' : '收起会议入口'"
        :title="leftPanelCollapsed ? '展开会议入口' : '收起会议入口'"
        @click="leftPanelCollapsed = !leftPanelCollapsed"
      >
        <ArrowRight v-if="leftPanelCollapsed" />
        <ArrowLeft v-else />
      </button>
      <div class="panel-collapsed-label">会议入口</div>
      <div class="panel-content">
        <section class="sidebar-section">
        <p class="section-kicker">会议入口</p>
        <h1>会议室</h1>
        <p class="section-copy">创建新会议，或使用别人发来的会议码加入。</p>

        <div class="hub-mode" role="tablist" aria-label="会议室操作">
          <button
            type="button"
            :class="{ 'hub-mode-active': hubMode === 'create' }"
            role="tab"
            :aria-selected="hubMode === 'create'"
            @click="hubMode = 'create'"
          >
            创建会议
          </button>
          <button
            type="button"
            :class="{ 'hub-mode-active': hubMode === 'join' }"
            role="tab"
            :aria-selected="hubMode === 'join'"
            @click="hubMode = 'join'"
          >
            加入会议
          </button>
        </div>

        <div v-if="hubMode === 'create'" class="form-stack">
          <label>
            <span>会议标题</span>
            <el-input v-model="roomTitle" placeholder="会议室" />
          </label>
          <label>
            <span>房间类型</span>
            <el-select v-model="roomType" placeholder="选择房间类型">
              <el-option
                v-for="item in roomTypeOptions"
                :key="item.value"
                :label="`${item.label} · ${item.note}`"
                :value="item.value"
              />
            </el-select>
          </label>
          <label>
            <span>入会密码（可选）</span>
            <el-input v-model="roomPassword" type="password" show-password placeholder="可留空" />
          </label>
          <el-button :icon="Plus" @click="createRoom">创建会议室</el-button>
        </div>

        <div v-else class="form-stack">
          <label>
            <span>会议码</span>
            <el-input v-model="joinCode" placeholder="会议码" />
          </label>
          <label>
            <span>入会密码</span>
            <el-input v-model="joinPassword" type="password" show-password placeholder="无密码可留空" @keydown.enter="joinRoom" />
          </label>
          <el-button :icon="Key" @click="joinRoom">加入会议</el-button>
        </div>
        </section>

        <section class="room-list">
        <div class="room-list-head">
          <h2>我加入过的会议</h2>
          <el-button text :icon="RefreshRight" :loading="store.loadingRooms" @click="store.loadRooms()" aria-label="刷新会议列表" />
        </div>
        <div
          v-for="room in store.rooms"
          :key="room.id"
          class="room-item"
          :class="{ 'room-item-active': room.id === store.activeRoomId }"
          role="button"
          tabindex="0"
          @click="store.activeRoomId = room.id"
          @keydown.enter="store.activeRoomId = room.id"
        >
          <span class="room-item-head">
            <span class="room-title">{{ roomDisplayTitle(room) }}</span>
            <el-button
              v-if="canDeleteRoom(room)"
              text
              type="danger"
              size="small"
              :icon="Delete"
              class="room-delete-button"
              aria-label="删除会议"
              title="删除会议"
              @click.stop="handleDeleteRoom(room)"
            />
          </span>
          <span class="room-meta">
            <span>{{ room.access_code }} · {{ room.member_count }} 人</span>
            <span>{{ roomTypeLabel(room.room_type) }} · {{ roomDomainPreview(room) }}</span>
            <span v-if="roomRecentLabel(room)">最近 {{ roomRecentLabel(room) }}</span>
          </span>
        </div>
        <p v-if="!store.rooms.length && !store.loadingRooms" class="empty-note">暂无加入过的会议</p>
        </section>
      </div>
      <div
        v-if="!leftPanelCollapsed"
        class="panel-resizer panel-resizer-left"
        role="separator"
        aria-label="调整左侧面板宽度"
        aria-orientation="vertical"
        @pointerdown="startPanelResize('left', $event)"
      />
    </aside>

    <section class="meeting-room">
      <header class="room-header">
        <div class="room-title-block">
          <p class="section-kicker">实时会议</p>
          <h2>{{ store.activeRoom?.title || "实时会议协作" }}</h2>
          <div v-if="store.activeRoom && hostMember" class="room-submeta">
            <span class="host-pill">主持人 {{ hostMember.username }}</span>
            <span class="room-type-pill">{{ activeRoomTypeLabel }}</span>
            <span class="status-pill" :class="`status-${store.activeRoom.status}`">{{ roomStatusLabel }}</span>
          </div>
        </div>
        <div v-if="store.activeRoom" class="room-header-right">
          <div class="room-toolbar-main">
            <div class="room-code">
              <span>会议码</span>
              <strong>{{ store.activeRoom.access_code }}</strong>
            </div>
          <el-popover
            placement="bottom-end"
            :width="340"
            trigger="click"
            @show="store.loadMembers()"
          >
            <template #reference>
              <el-button size="small" :icon="User">
                成员 ({{ visibleMemberCount }})
              </el-button>
            </template>
            <div class="member-panel">
              <div class="member-panel-head">
                <span>会议成员</span>
                <strong>{{ visibleMemberCount }} 人</strong>
              </div>
              <div v-if="store.members.length === 0" class="member-panel-empty">
                暂无成员信息
              </div>
              <div v-for="member in store.members" :key="member.id" class="member-item">
                <span class="member-avatar">{{ memberInitial(member.username) }}</span>
                <span class="member-main">
                  <strong>{{ member.username }}</strong>
                  <small>{{ member.user_id === auth.userId ? "当前账号" : member.user_id.slice(-8) }}</small>
                </span>
                <el-select
                  v-if="canManageRoom && member.user_id !== store.activeRoom.created_by"
                  :model-value="normalizedMemberRole(member.role)"
                  size="small"
                  class="member-role-select"
                  @change="(role) => updateMemberRole(member, role as 'host' | 'member')"
                >
                  <el-option label="主持人" value="host" />
                  <el-option label="成员" value="member" />
                </el-select>
                <span v-else class="member-role" :class="{ 'member-role-host': member.role === 'host' }">
                  {{ memberRoleLabel(member.role) }}
                </span>
              </div>
            </div>
          </el-popover>

          <el-popover
            placement="bottom-end"
            :width="360"
            trigger="click"
          >
            <template #reference>
              <el-button size="small" type="primary" plain :icon="Share">
                邀请成员
              </el-button>
            </template>
            <div class="invite-panel">
              <div class="invite-panel-head">
                <span>会议码</span>
                <strong>{{ store.activeRoom.access_code }}</strong>
              </div>
              <p class="invite-note">复制给成员后，对方打开链接会自动填入会议码。</p>
              <div class="invite-link">{{ activeMeetingLink }}</div>
              <div class="invite-actions">
                <el-button size="small" :icon="CopyDocument" @click="copyToClipboard(store.activeRoom.access_code, '会议码已复制')">
                  复制会议码
                </el-button>
                <el-button size="small" type="primary" :icon="Share" @click="copyInvite">
                  复制邀请
                </el-button>
              </div>
            </div>
          </el-popover>

          </div>
          <div v-if="canManageRoom" class="room-toolbar-admin">
            <el-button size="small" :icon="EditPen" @click="editRoomTitle">
              改标题
            </el-button>
            <el-button v-if="store.activeRoom.status === 'active'" size="small" :icon="Close" @click="closeRoom">
              关闭
            </el-button>
            <el-button v-if="store.activeRoom.status !== 'archived'" size="small" :icon="FolderOpened" @click="archiveRoom">
              归档
            </el-button>
          </div>
        </div>
        <p v-else class="room-hint">创建或加入会议后开始聊天，也可以点名 @会议Agent。</p>
      </header>

      <div ref="messageListRef" v-loading="store.loadingMessages" class="message-list">
        <div v-if="!store.activeRoom" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
          <p>发言和会议Agent回复都会沉淀在同一条时间线中。</p>
        </div>

        <div v-else-if="store.messages.length === 0 && !store.loadingMessages" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
          <p>输入会议消息后回车发送；需要会议Agent时可以直接点名 @会议Agent。</p>
        </div>

        <div v-if="store.generalAgentRunning" class="ai-thinking-bar">
          <span class="ai-thinking-dots">
            <span class="dot" /><span class="dot" /><span class="dot" />
          </span>
          会议Agent处理中...
        </div>

        <article
          v-for="message in store.messages"
          :key="message.id"
          :id="`meeting-message-${message.id}`"
          class="message-row"
          :class="{
            'message-row-own': message.user_id === auth.userId && !['agent', 'agent_streaming'].includes(message.message_type),
            'message-row-agent': ['agent', 'agent_streaming'].includes(message.message_type),
          }"
        >
          <div class="message-meta">
            <span v-if="['agent', 'agent_streaming'].includes(message.message_type)" class="agent-tag">会议Agent</span>
            <span v-else-if="message.message_type === 'system'" class="system-tag">系统</span>
            <span v-else>{{ message.username }}</span>
            <time>{{ formatTime(message.created_at) }}</time>
          </div>
          <div v-if="message.quote_message_id" class="quoted-message">
            {{ quotedMessageTitle(message.quote_message_id) }}
          </div>
          <div
            class="message-bubble"
            :class="{
              'agent-bubble': ['agent', 'agent_streaming'].includes(message.message_type),
              'agent-streaming-bubble': message.message_type === 'agent_streaming',
            }"
          >
            <span v-if="message.message_type === 'agent_streaming'" class="inline-thinking-dots">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </span>
            <span>{{ displayMessageContent(message) }}</span>
          </div>
          <div v-if="message.message_type !== 'agent_streaming'" class="message-toolbar">
            <MessageActionBar
              :reaction="store.messageReactions[message.id] || ''"
              show-feedback
              @copy="copyToClipboard(displayMessageContent(message), '消息已复制')"
              @like="submitMeetingFeedback(message, 'up')"
              @dislike="submitMeetingFeedback(message, 'down')"
              @share="shareMeetingMessage(message)"
            />
            <el-tooltip content="引用" placement="bottom">
              <el-button text size="small" @click="quoteMessage(message)">引用</el-button>
            </el-tooltip>
          </div>
        </article>
      </div>

      <footer class="composer">
        <div v-if="quotedMessage" class="composer-quote">
          <span>引用 {{ quotedMessage.username }}：{{ quotedMessage.content.slice(0, 80) }}</span>
          <el-button text size="small" :icon="Close" @click="quotedMessage = null" />
        </div>
        <div v-if="mentionTargets.length" class="mention-bar">
          <button
            v-for="agent in mentionTargets"
            :key="agent.id"
            type="button"
            class="mention-chip"
            @click="insertAgentMention(agent.agent_name)"
          >
            @{{ agent.agent_name }}
          </button>
        </div>
        <textarea
          ref="inputRef"
          v-model="input"
          class="composer-textarea"
          :disabled="!store.activeRoom || store.activeRoom.status !== 'active'"
          rows="1"
          :placeholder="store.activeRoom?.status === 'active' ? '输入消息后按回车发送，可用 @会议Agent 点名。' : '会议已关闭或归档，只能查看历史。'"
          @keydown="onInputKeydown"
        />
        <el-button type="primary" :icon="Promotion" :loading="store.sending" :disabled="!store.canSend" @click="sendMessage">
          发送
        </el-button>
      </footer>
    </section>

    <aside class="meeting-context" :class="{ 'panel-collapsed': rightPanelCollapsed }" v-loading="store.loadingContext">
      <button
        type="button"
        class="panel-toggle panel-toggle-right"
        :aria-label="rightPanelCollapsed ? '展开上下文面板' : '收起上下文面板'"
        :title="rightPanelCollapsed ? '展开上下文面板' : '收起上下文面板'"
        @click="rightPanelCollapsed = !rightPanelCollapsed"
      >
        <ArrowLeft v-if="rightPanelCollapsed" />
        <ArrowRight v-else />
      </button>
      <div class="panel-collapsed-label">上下文</div>
      <div class="panel-content context-panel-content">
        <section class="context-card boundary-card">
        <div class="context-head">
          <div>
            <p class="section-kicker">边界</p>
            <h2>可查询范围</h2>
          </div>
          <span class="count-pill">{{ contextAllowedDomains.length }}</span>
        </div>
        <div v-if="store.activeRoom" class="boundary-summary">
          <span>{{ activeRoomTypeLabel }}</span>
          <span>{{ store.contextPreview?.user_role || "user" }}</span>
          <span>{{ store.contextPreview?.room_role || "member" }}</span>
        </div>
        <div v-if="contextAllowedDomains.length" class="domain-chip-list">
          <span v-for="domain in contextAllowedDomains" :key="domain" class="domain-chip domain-chip-allowed">
            {{ domainLabel(domain) }}
          </span>
        </div>
        <div v-if="contextDeniedDomains.length" class="domain-chip-list domain-chip-list-muted">
          <span v-for="domain in contextDeniedDomains.slice(0, 6)" :key="domain" class="domain-chip domain-chip-denied">
            {{ domainLabel(domain) }}
          </span>
        </div>
        <div v-if="store.contextPreview?.agent_permissions.length" class="agent-permission-list">
          <div v-for="agent in store.contextPreview.agent_permissions" :key="agent.agent_id" class="agent-permission-item">
            <strong>{{ agent.agent_name }}</strong>
            <small>{{ agent.allowed_domains.map(domainLabel).join("、") || "未授权数据域" }}</small>
          </div>
        </div>
        <div v-if="store.contextPreview?.query_examples.length" class="query-example-list">
          <button
            v-for="example in store.contextPreview.query_examples.slice(0, 3)"
            :key="example"
            type="button"
            @click="input = `@会议Agent ${example}`"
          >
            {{ example }}
          </button>
        </div>
        </section>

        <section v-if="canReviewMemory" class="context-card audit-card">
        <div class="context-head">
          <div>
            <p class="section-kicker">审计</p>
            <h2>Agent 查询</h2>
          </div>
          <span class="count-pill">{{ store.agentQueryAudits.length }}</span>
        </div>
        <div v-if="!store.agentQueryAudits.length" class="context-empty">暂无查询记录</div>
        <article v-for="audit in store.agentQueryAudits.slice(0, 4)" :key="audit.id" class="audit-item">
          <div class="audit-item-head">
            <span :class="['audit-decision', auditDecisionClass(audit.decision)]">
              {{ auditDecisionLabel(audit.decision) }}
            </span>
            <time>{{ formatTime(audit.created_at) }}</time>
          </div>
          <p>{{ audit.question }}</p>
          <small>
            {{ audit.allowed_domains.map(domainLabel).join("、") || "无允许域" }}
            <template v-if="audit.denied_domains.length"> / 拒绝 {{ audit.denied_domains.map(domainLabel).join("、") }}</template>
          </small>
        </article>
        </section>

        <section class="context-card">
        <div class="context-head">
          <div>
            <p class="section-kicker">记忆</p>
            <h2>候选记忆</h2>
          </div>
          <div class="context-head-actions">
            <el-button
              v-if="canReviewMemory"
              text
              size="small"
              :icon="MagicStick"
              :loading="store.memoryExtracting"
              :disabled="!store.activeRoom"
              @click="extractCandidateMemories"
            >
              提取
            </el-button>
            <span class="count-pill">{{ store.candidateMemories.length }}</span>
          </div>
        </div>
        <div v-if="!store.candidateMemories.length" class="context-empty">暂无候选记忆</div>
        <article v-for="memory in store.candidateMemories" :key="memory.memory_id" class="memory-item">
          <div class="memory-title-row">
            <strong>{{ memory.title }}</strong>
            <span v-if="memoryConfidence(memory)">{{ memoryConfidence(memory) }}</span>
          </div>
          <p>{{ memory.content }}</p>
          <div v-if="canReviewMemory" class="memory-actions">
            <el-button size="small" type="primary" :icon="Check" @click="confirmCandidateMemory(memory)">确认</el-button>
            <el-button size="small" :icon="Close" @click="rejectCandidateMemory(memory)">拒绝</el-button>
          </div>
        </article>
        </section>

        <section class="context-card">
        <div class="context-head">
          <div>
            <p class="section-kicker">行动</p>
            <h2>会议待办</h2>
          </div>
          <span class="count-pill">{{ store.openActionItems.length }}</span>
        </div>
        <div class="action-create">
          <el-input v-model="actionTitle" size="small" placeholder="新待办" @keydown.enter="createActionItem" />
          <el-input v-model="actionDescription" size="small" placeholder="补充说明（可选）" />
          <el-select v-model="actionOwnerId" size="small" clearable placeholder="负责人">
            <el-option
              v-for="member in store.members"
              :key="member.user_id"
              :label="member.username"
              :value="member.user_id"
            />
          </el-select>
          <el-button size="small" type="primary" :icon="Plus" :loading="store.actionItemSaving" @click="createActionItem">
            新增
          </el-button>
        </div>
        <div v-if="!store.actionItems.length" class="context-empty">暂无会议待办</div>
        <article v-for="item in store.actionItems" :key="item.id" class="action-item" :class="{ 'action-done': item.status === 'done' }">
          <div>
            <strong>{{ item.title }}</strong>
            <p v-if="item.description">{{ item.description }}</p>
            <small>{{ item.owner_name || "未分配" }} · {{ item.status === "done" ? "已完成" : "进行中" }}</small>
          </div>
          <el-button v-if="item.status !== 'done'" text :icon="Check" @click="completeActionItem(item.id)" />
        </article>
        </section>

        <section class="context-card">
        <div class="context-head">
          <div>
            <p class="section-kicker">共享</p>
            <h2>项目共享记忆</h2>
          </div>
          <span class="count-pill">{{ store.confirmedMemories.length }}</span>
        </div>
        <div v-if="!store.confirmedMemories.length" class="context-empty">暂无已确认共享记忆</div>
        <article v-for="memory in store.confirmedMemories" :key="memory.memory_id" class="shared-memory">
          <strong>{{ memory.title }}</strong>
          <p>{{ memory.summary || memory.content }}</p>
        </article>
        </section>

        <section class="context-card">
        <div class="context-head">
          <div>
            <p class="section-kicker">房间</p>
            <h2>成员</h2>
          </div>
          <span class="count-pill">{{ visibleMemberCount }}</span>
        </div>
        <div class="compact-roster">
          <span v-for="member in store.members" :key="member.id">{{ member.username }}</span>
        </div>
        </section>
      </div>
      <div
        v-if="!rightPanelCollapsed"
        class="panel-resizer panel-resizer-right"
        role="separator"
        aria-label="调整右侧面板宽度"
        aria-orientation="vertical"
        @pointerdown="startPanelResize('right', $event)"
      />
    </aside>
  </div>
</template>

<style scoped>
.meeting-page {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: var(--left-panel-width, 260px) minmax(520px, 1fr) var(--right-panel-width, 300px);
  gap: 12px;
  transition: grid-template-columns 180ms ease;
}

.meeting-page.is-resizing-left,
.meeting-page.is-resizing-right {
  cursor: col-resize;
  user-select: none;
}

.meeting-page.is-resizing-left .meeting-room,
.meeting-page.is-resizing-right .meeting-room {
  pointer-events: none;
}

.meeting-sidebar,
.meeting-room,
.meeting-context {
  min-height: 0;
  border: 1px solid #e4e4e7;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.meeting-sidebar {
  position: relative;
  overflow: hidden;
}

.meeting-context {
  position: relative;
  overflow: visible;
}

.panel-content {
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  transition: opacity 150ms ease, visibility 150ms ease;
}

.context-panel-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 46px 12px 12px;
}

.panel-toggle {
  position: absolute;
  z-index: 8;
  top: 10px;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #52525b;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease, transform 150ms ease;
}

.panel-toggle:hover {
  border-color: #18181b;
  color: #111827;
}

.panel-toggle svg {
  width: 15px;
  height: 15px;
}

.panel-toggle-left {
  right: 8px;
}

.panel-toggle-right {
  left: 8px;
  right: auto;
}

.panel-collapsed {
  display: flex;
  align-items: center;
  justify-content: center;
}

.panel-collapsed .panel-content {
  visibility: hidden;
  opacity: 0;
  pointer-events: none;
}

.panel-collapsed .panel-toggle {
  left: 50%;
  right: auto;
  transform: translateX(-50%);
}

.panel-collapsed-label {
  display: none;
  color: #71717a;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  line-height: 1;
  writing-mode: vertical-rl;
}

.panel-collapsed .panel-collapsed-label {
  display: block;
}

.panel-resizer {
  position: absolute;
  z-index: 7;
  top: 0;
  bottom: 0;
  width: 12px;
  cursor: col-resize;
}

.panel-resizer::after {
  content: "";
  position: absolute;
  top: 14px;
  bottom: 14px;
  width: 2px;
  border-radius: 999px;
  background: transparent;
  transition: background 150ms ease;
}

.panel-resizer:hover::after,
.meeting-page.is-resizing-left .panel-resizer-left::after,
.meeting-page.is-resizing-right .panel-resizer-right::after {
  background: #18181b;
}

.panel-resizer-left {
  right: -7px;
}

.panel-resizer-left::after {
  right: 5px;
}

.panel-resizer-right {
  left: -7px;
}

.panel-resizer-right::after {
  left: 5px;
}

.sidebar-section {
  padding: 18px;
  border-bottom: 1px solid #f4f4f5;
}

.section-kicker {
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.sidebar-section h1,
.room-header h2,
.room-list h2 {
  color: #111827;
  font-weight: 700;
  letter-spacing: 0;
}

.sidebar-section h1 {
  margin-top: 8px;
  font-size: 18px;
}

.section-copy {
  margin-top: 6px;
  color: #71717a;
  font-size: 13px;
  line-height: 1.6;
}

.hub-mode {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-top: 16px;
  padding: 4px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #f8fafc;
}

.hub-mode button {
  min-height: 32px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #52525b;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease, box-shadow 150ms ease;
}

.hub-mode button:hover,
.hub-mode-active {
  background: #fff;
  color: #111827;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

label span {
  color: #3f3f46;
  font-size: 13px;
  font-weight: 500;
}

.room-list {
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
}

.room-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.room-list h2 {
  font-size: 15px;
}

.room-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: background 150ms ease, border-color 150ms ease, color 150ms ease;
}

.room-item:hover,
.room-item-active {
  border-color: #18181b;
  background: #18181b;
  color: #fff;
}

.room-item-head {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.room-title {
  min-width: 0;
  color: inherit;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.room-delete-button {
  flex: 0 0 auto;
  opacity: 0;
  margin-top: -4px;
  margin-right: -6px;
  color: #dc2626;
}

.room-item:hover .room-delete-button,
.room-item:focus-visible .room-delete-button,
.room-item-active .room-delete-button {
  opacity: 1;
}

.room-item:hover .room-delete-button,
.room-item-active .room-delete-button {
  color: #fecaca;
}

.room-meta,
.empty-note {
  color: #71717a;
  font-size: 12px;
}

.room-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.room-item-active .room-meta,
.room-item:hover .room-meta {
  color: #d4d4d8;
}

/* Main room */
.meeting-room {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
}

.room-header {
  min-height: 66px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid #e4e4e7;
  flex-wrap: wrap;
}

.room-header h2 {
  margin-top: 4px;
  font-size: 18px;
}

.room-title-block {
  flex: 1 1 240px;
  min-width: 0;
}

.room-submeta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.host-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid #d6d3d1;
  border-radius: 999px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  font-weight: 600;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 600;
}

.status-closed {
  background: #f4f4f5;
  color: #52525b;
}

.status-archived {
  background: #ecfeff;
  color: #0e7490;
}

.room-type-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
}

.room-header-right {
  display: flex;
  flex: 1 1 360px;
  flex-direction: column;
  align-items: flex-end;
  justify-content: flex-end;
  gap: 8px;
}

.room-toolbar-main,
.room-toolbar-admin {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.room-toolbar-admin {
  color: #71717a;
}

.room-toolbar-admin :deep(.el-button) {
  margin-left: 0;
}

.room-code {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 999px;
  background: #fafafa;
}

.room-code span,
.room-hint {
  color: #71717a;
  font-size: 12px;
}

.room-code strong {
  color: #18181b;
  font-size: 14px;
  font-weight: 700;
}

/* Invitation */
.invite-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.invite-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f4f4f5;
}

.invite-panel-head span {
  color: #71717a;
  font-size: 12px;
}

.invite-panel-head strong {
  color: #111827;
  font-size: 18px;
  letter-spacing: 0.04em;
}

.invite-note {
  color: #71717a;
  font-size: 13px;
  line-height: 1.6;
}

.invite-link {
  padding: 8px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
  color: #3f3f46;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}

.invite-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Members */
.member-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.member-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f4f4f5;
}

.member-panel-head span {
  color: #111827;
  font-size: 14px;
  font-weight: 700;
}

.member-panel-head strong {
  color: #71717a;
  font-size: 12px;
}

.member-panel-empty {
  padding: 18px 0;
  color: #a1a1aa;
  font-size: 13px;
  text-align: center;
}

.member-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #fafafa;
}

.member-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #18181b;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.member-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.member-main strong {
  overflow: hidden;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-main small {
  color: #a1a1aa;
  font-size: 11px;
}

.member-role {
  padding: 2px 7px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #71717a;
  font-size: 11px;
  font-weight: 600;
}

.member-role-host {
  background: #fff7ed;
  color: #9a3412;
}

.member-role-select {
  width: 86px;
}

.member-role-select :deep(.el-select__wrapper) {
  min-height: 26px;
  padding: 0 7px;
  border-radius: 999px;
  box-shadow: 0 0 0 1px #e4e4e7 inset;
}

.member-role-select :deep(.el-select__selected-item) {
  font-size: 11px;
  font-weight: 600;
}

/* Messages */
.message-list {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
}

.empty-state {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #71717a;
  text-align: center;
}

.empty-state svg {
  width: 48px;
  height: 48px;
  color: #a1a1aa;
}

.empty-state h3 {
  margin-top: 16px;
  color: #111827;
  font-size: 18px;
  font-weight: 700;
}

.empty-state p {
  max-width: 440px;
  margin-top: 8px;
  color: #71717a;
  line-height: 1.7;
}

.message-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  margin-bottom: 14px;
}

.message-row-own {
  align-items: flex-end;
}

.message-row-agent {
  align-items: flex-start;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #a1a1aa;
  font-size: 12px;
}

.message-meta span {
  color: #52525b;
  font-weight: 600;
}

.agent-tag {
  font-size: 10px;
  font-weight: 700;
  color: #2563eb;
  background: #dbeafe;
  padding: 1px 5px;
  border-radius: 4px;
}

.system-tag {
  font-size: 10px;
  font-weight: 700;
  color: #047857;
  background: #d1fae5;
  padding: 1px 5px;
  border-radius: 4px;
}

.quoted-message {
  max-width: min(640px, 80%);
  padding: 7px 10px;
  border-left: 3px solid #a3a3a3;
  border-radius: 6px;
  background: #f5f5f5;
  color: #52525b;
  font-size: 12px;
  line-height: 1.5;
}

.message-bubble {
  max-width: min(720px, 82%);
  padding: 11px 14px;
  border: 1px solid #e4e4e7;
  border-radius: 16px 16px 16px 5px;
  background: #fafafa;
  color: #111827;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-row-own .message-bubble {
  border-color: transparent;
  border-radius: 16px 16px 5px 16px;
  background: #1f2937;
  color: #fff;
}

.agent-bubble {
  border-left: 3px solid #2563eb;
  border-radius: 5px 16px 16px 16px;
  background: #eff6ff;
}

.message-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.ai-thinking-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 13px;
}

.ai-thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #2563eb;
  animation: blink 1.4s infinite both;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}

/* Composer */
.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
  padding: 12px;
  border-top: 1px solid #e4e4e7;
  background: #fff;
}

.composer-quote {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
  color: #52525b;
  font-size: 12px;
}

.composer-quote span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mention-bar {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mention-chip {
  border: 1px solid #d1d5db;
  border-radius: 999px;
  background: #fff;
  color: #374151;
  padding: 4px 10px;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
}

.mention-chip:hover {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}

.composer-textarea {
  width: 100%;
  min-height: 40px;
  max-height: 120px;
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  outline: none;
  font-family: inherit;
  transition: border-color 150ms ease;
}

.composer-textarea:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}

.composer-textarea:disabled {
  background: #f9fafb;
  color: #9ca3af;
}

/* Context panel */
.context-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fff;
}

.context-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.context-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.context-head-actions :deep(.el-button) {
  margin-left: 0;
}

.context-head h2 {
  margin-top: 3px;
  color: #111827;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0;
}

.count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.context-empty {
  padding: 14px 0;
  color: #a1a1aa;
  font-size: 13px;
  text-align: center;
}

.boundary-card {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.boundary-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.boundary-summary span {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 7px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
}

.domain-chip-list,
.query-example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.domain-chip-list-muted {
  padding-top: 8px;
  border-top: 1px dashed #d4d4d8;
}

.domain-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  min-height: 22px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.domain-chip-allowed {
  background: #dcfce7;
  color: #166534;
}

.domain-chip-denied {
  background: #f4f4f5;
  color: #71717a;
}

.agent-permission-list {
  display: grid;
  gap: 7px;
}

.agent-permission-item {
  display: grid;
  gap: 2px;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.agent-permission-item strong {
  color: #111827;
  font-size: 12px;
}

.agent-permission-item small {
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.query-example-list button {
  min-height: 26px;
  padding: 4px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  font-size: 12px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
}

.query-example-list button:hover {
  border-color: #2563eb;
  color: #1d4ed8;
}

.audit-card {
  background: #fff;
}

.audit-item {
  display: grid;
  gap: 5px;
  padding: 9px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
}

.audit-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.audit-item-head time {
  color: #a1a1aa;
  font-size: 11px;
}

.audit-decision {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 11px;
  font-weight: 700;
}

.audit-allowed {
  background: #dcfce7;
  color: #166534;
}

.audit-partial {
  background: #fef3c7;
  color: #92400e;
}

.audit-denied {
  background: #fee2e2;
  color: #991b1b;
}

.audit-item p {
  color: #111827;
  font-size: 12px;
  line-height: 1.5;
}

.audit-item small {
  color: #71717a;
  font-size: 11px;
  line-height: 1.5;
}

.memory-item,
.action-item,
.shared-memory {
  padding: 10px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
}

.memory-title-row,
.action-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.memory-title-row strong,
.action-item strong,
.shared-memory strong {
  color: #111827;
  font-size: 13px;
}

.memory-title-row span {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 700;
}

.memory-item p,
.action-item p,
.shared-memory p {
  margin-top: 6px;
  color: #52525b;
  font-size: 12px;
  line-height: 1.6;
}

.memory-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.action-create {
  display: grid;
  gap: 8px;
}

.action-item small {
  display: inline-block;
  margin-top: 6px;
  color: #71717a;
  font-size: 11px;
}

.action-done {
  opacity: 0.62;
}

.compact-roster {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.compact-roster span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 7px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #3f3f46;
  font-size: 12px;
}

/* Responsive */
@media (max-width: 920px) {
  .meeting-page {
    grid-template-columns: 1fr;
    gap: 12px;
    overflow-y: auto;
  }

  .meeting-sidebar {
    min-height: 520px;
  }

  .meeting-room {
    min-height: 620px;
  }

  .meeting-context {
    min-height: 420px;
  }

  .panel-toggle,
  .panel-resizer,
  .panel-collapsed-label {
    display: none;
  }

  .panel-collapsed {
    display: block;
  }

  .panel-collapsed .panel-content {
    visibility: visible;
    opacity: 1;
    pointer-events: auto;
  }

  .context-panel-content {
    padding: 12px;
  }
}

@media (max-width: 640px) {
  .meeting-page {
    padding: 10px;
  }

  .composer {
    grid-template-columns: 1fr;
  }
}
</style>
