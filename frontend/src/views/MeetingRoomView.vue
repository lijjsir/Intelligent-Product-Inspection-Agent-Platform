<script setup lang="ts">
import { ChatDotRound, Key, Plus, Promotion, RefreshRight } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { feedbackApi } from "@/api/feedback.api";
import { meetingApi } from "@/api/meeting.api";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useAuthStore } from "@/stores/auth.store";
import type { MeetingMessage, MeetingRoom } from "@/types/meeting.types";

const auth = useAuthStore();

const rooms = ref<MeetingRoom[]>([]);
const messages = ref<MeetingMessage[]>([]);
const activeRoomId = ref("");
const roomTitle = ref("会议室");
const roomPassword = ref("");
const joinCode = ref("");
const joinPassword = ref("");
const input = ref("");
const loadingRooms = ref(false);
const loadingMessages = ref(false);
const sending = ref(false);
const messageListRef = ref<HTMLElement | null>(null);
const messageReactions = ref<Record<string, "up" | "down">>({});
let pollTimer: number | undefined;

const activeRoom = computed(() => rooms.value.find((item) => item.id === activeRoomId.value) || null);
const canSend = computed(() => Boolean(activeRoom.value && input.value.trim() && !sending.value));

function formatTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function copyToClipboard(text: string, successText = "已复制") {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success(successText);
  } catch {
    ElMessage.error("复制失败，请手动复制。");
  }
}

function shareMeetingMessage(message: MeetingMessage) {
  const roomPart = activeRoom.value?.access_code ? `?room=${activeRoom.value.access_code}` : "";
  const url = `${window.location.origin}${window.location.pathname}${roomPart}#meeting-message-${message.id}`;
  copyToClipboard(url, "分享链接已复制");
}

async function loadMessageReactions() {
  const ids = messages.value.map((message) => message.id).filter(Boolean);
  if (ids.length === 0) {
    messageReactions.value = {};
    return;
  }
  try {
    const { data } = await feedbackApi.listMessages({
      target_type: "meeting",
      target_ids: ids.join(","),
    });
    const next: Record<string, "up" | "down"> = {};
    for (const item of data.data) {
      next[item.target_id] = item.feedback_type;
    }
    messageReactions.value = next;
  } catch {
    // Feedback state can be refreshed later; do not block meeting messages.
  }
}

async function submitMeetingFeedback(message: MeetingMessage, feedbackType: "up" | "down") {
  const previous = messageReactions.value[message.id];
  messageReactions.value = { ...messageReactions.value, [message.id]: feedbackType };
  try {
    await feedbackApi.submitMessage("meeting", message.id, {
      feedback_type: feedbackType,
      rating: feedbackType === "up" ? 5 : 1,
      category: feedbackType === "up" ? "meeting_helpful" : "meeting_not_helpful",
      comment: `meeting_room:${message.room_id}`,
    });
    ElMessage.success(feedbackType === "up" ? "已点赞" : "已点踩");
  } catch (error) {
    if (previous) {
      messageReactions.value = { ...messageReactions.value, [message.id]: previous };
    } else {
      const next = { ...messageReactions.value };
      delete next[message.id];
      messageReactions.value = next;
    }
    ElMessage.error("反馈提交失败，请稍后重试。");
    console.error(error);
  }
}

async function scrollToBottom() {
  await nextTick();
  const el = messageListRef.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

async function loadRooms(selectLatest = false) {
  loadingRooms.value = true;
  try {
    const { data } = await meetingApi.listRooms();
    rooms.value = data.data;
    if (selectLatest && rooms.value.length > 0) {
      activeRoomId.value = rooms.value[0].id;
    } else if (!activeRoomId.value && rooms.value.length > 0) {
      activeRoomId.value = rooms.value[0].id;
    } else if (activeRoomId.value && !rooms.value.some((item) => item.id === activeRoomId.value)) {
      activeRoomId.value = rooms.value[0]?.id || "";
    }
  } finally {
    loadingRooms.value = false;
  }
}

async function loadMessages(afterSeq = 0) {
  if (!activeRoom.value) {
    messages.value = [];
    return;
  }
  loadingMessages.value = afterSeq === 0;
  try {
    const { data } = await meetingApi.listMessages(activeRoom.value.id, afterSeq);
    if (afterSeq > 0) {
      const seen = new Set(messages.value.map((item) => item.id));
      messages.value = [...messages.value, ...data.data.filter((item) => !seen.has(item.id))];
    } else {
      messages.value = data.data;
    }
    await scrollToBottom();
    await loadMessageReactions();
  } finally {
    loadingMessages.value = false;
  }
}

async function createRoom() {
  try {
    const { data } = await meetingApi.createRoom({
      title: roomTitle.value.trim() || "会议室",
      password: roomPassword.value.trim() || null,
    });
    rooms.value = [data.data, ...rooms.value.filter((item) => item.id !== data.data.id)];
    activeRoomId.value = data.data.id;
    roomTitle.value = "会议室";
    roomPassword.value = "";
    ElMessage.success(`会议室已创建，会议码 ${data.data.access_code}`);
  } catch (error) {
    ElMessage.error("创建会议室失败，请稍后重试。");
    console.error(error);
  }
}

async function joinRoom() {
  if (!joinCode.value.trim()) return;
  try {
    const { data } = await meetingApi.joinRoom({
      access_code: joinCode.value.trim(),
      password: joinPassword.value.trim() || null,
    });
    rooms.value = [data.data, ...rooms.value.filter((item) => item.id !== data.data.id)];
    activeRoomId.value = data.data.id;
    joinCode.value = "";
    joinPassword.value = "";
    ElMessage.success("已加入会议室。");
  } catch (error) {
    ElMessage.error("加入会议室失败，请检查会议码或密码。");
    console.error(error);
  }
}

async function sendMessage() {
  if (!canSend.value || !activeRoom.value) return;
  const content = input.value.trim();
  sending.value = true;
  try {
    const { data } = await meetingApi.sendMessage(activeRoom.value.id, content);
    messages.value = [...messages.value, data.data];
    input.value = "";
    await loadRooms();
    await scrollToBottom();
  } catch (error) {
    ElMessage.error("发送失败，请稍后重试。");
    console.error(error);
  } finally {
    sending.value = false;
  }
}

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function startPolling() {
  window.clearInterval(pollTimer);
  pollTimer = window.setInterval(async () => {
    if (!activeRoom.value) return;
    const latest = messages.value[messages.value.length - 1];
    const latestSeq = latest?.seq_no || 0;
    try {
      await loadMessages(latestSeq);
      await loadRooms();
    } catch {
      // polling should stay quiet; direct actions show errors.
    }
  }, 3500);
}

watch(activeRoomId, async () => {
  await loadMessages(0);
});

onMounted(async () => {
  await loadRooms(true);
  startPolling();
});

onBeforeUnmount(() => {
  window.clearInterval(pollTimer);
});
</script>

<template>
  <div class="meeting-page">
    <aside class="meeting-sidebar">
      <section class="sidebar-section">
        <p class="section-kicker">MEETING HUB</p>
        <h1>进入会议</h1>
        <p class="section-copy">创建会议邀请成员，或加入已有会议室。</p>

        <div class="form-stack">
          <label>
            <span>会议标题</span>
            <el-input v-model="roomTitle" placeholder="会议室" />
          </label>
          <label>
            <span>会议密码</span>
            <el-input v-model="roomPassword" type="password" show-password placeholder="可留空" />
          </label>
          <el-button :icon="Plus" @click="createRoom">创建会议室</el-button>
        </div>

        <div class="form-stack join-stack">
          <label>
            <span>会议码</span>
            <el-input v-model="joinCode" placeholder="输入会议码" />
          </label>
          <label>
            <span>会议密码</span>
            <el-input v-model="joinPassword" type="password" show-password placeholder="无密码可留空" @keydown.enter="joinRoom" />
          </label>
          <el-button :icon="Key" @click="joinRoom">加入会议</el-button>
        </div>
      </section>

      <section class="room-list">
        <div class="room-list-head">
          <h2>我加入过的会议</h2>
          <el-button text :icon="RefreshRight" :loading="loadingRooms" @click="loadRooms()" aria-label="刷新会议列表" />
        </div>
        <button
          v-for="room in rooms"
          :key="room.id"
          type="button"
          class="room-item"
          :class="{ 'room-item-active': room.id === activeRoomId }"
          @click="activeRoomId = room.id"
        >
          <span class="room-title">{{ room.title }}</span>
          <span class="room-meta">{{ room.access_code }} · {{ room.member_count }} 人</span>
        </button>
        <p v-if="!rooms.length && !loadingRooms" class="empty-note">暂无加入过的会议</p>
      </section>
    </aside>

    <section class="meeting-room">
      <header class="room-header">
        <div>
          <p class="section-kicker">LIVE ROOM</p>
          <h2>{{ activeRoom?.title || "实时会议协作" }}</h2>
        </div>
        <div v-if="activeRoom" class="room-code">
          <span>会议码</span>
          <strong>{{ activeRoom.access_code }}</strong>
        </div>
        <p v-else class="room-hint">创建或加入会议后开始多人聊天</p>
      </header>

      <div ref="messageListRef" v-loading="loadingMessages" class="message-list">
        <div v-if="!activeRoom" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
          <p>发言、资料上传、AI 阶段总结和会议结果都会沉淀在同一条时间线中。</p>
        </div>

        <div v-else-if="messages.length === 0" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
          <p>输入会议消息后回车发送。</p>
        </div>

        <article
          v-for="message in messages"
          :key="message.id"
          :id="`meeting-message-${message.id}`"
          class="message-row"
          :class="{ 'message-row-own': message.user_id === auth.userId }"
        >
          <div class="message-meta">
            <span>{{ message.username }}</span>
            <time>{{ formatTime(message.created_at) }}</time>
          </div>
          <div class="message-bubble">{{ message.content }}</div>
          <MessageActionBar
            :reaction="messageReactions[message.id] || ''"
            show-feedback
            @copy="copyToClipboard(message.content, '消息已复制')"
            @like="submitMeetingFeedback(message, 'up')"
            @dislike="submitMeetingFeedback(message, 'down')"
            @share="shareMeetingMessage(message)"
          />
        </article>
      </div>

      <footer class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :rows="1"
          resize="none"
          :disabled="!activeRoom"
          placeholder="输入会议消息后回车发送"
          @keydown="onInputKeydown"
        />
        <el-button type="primary" :icon="Promotion" :loading="sending" :disabled="!canSend" @click="sendMessage">
          发送
        </el-button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.meeting-page {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
}

.meeting-sidebar,
.meeting-room {
  min-height: 0;
  border: 1px solid #e4e4e7;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.meeting-sidebar {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
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

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.join-stack {
  padding-top: 16px;
  border-top: 1px solid #f4f4f5;
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

.room-title {
  color: inherit;
  font-weight: 600;
}

.room-meta,
.empty-note {
  color: #71717a;
  font-size: 12px;
}

.room-item-active .room-meta,
.room-item:hover .room-meta {
  color: #d4d4d8;
}

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
  gap: 16px;
  padding: 14px 16px;
  border-bottom: 1px solid #e4e4e7;
}

.room-header h2 {
  margin-top: 4px;
  font-size: 18px;
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

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
  padding: 12px;
  border-top: 1px solid #e4e4e7;
  background: #fff;
}

@media (max-width: 920px) {
  .meeting-page {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .meeting-sidebar {
    min-height: 520px;
  }

  .meeting-room {
    min-height: 620px;
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
