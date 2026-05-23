<script setup lang="ts">
import { ChatDotRound, Delete, Key, Plus, Promotion, RefreshRight } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { feedbackApi } from "@/api/feedback.api";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useMeetingStore } from "@/stores/meeting.store";
import type { MeetingMessage } from "@/types/meeting.types";

const auth = useAuthStore();
const store = useMeetingStore();

const roomTitle = ref("会议室");
const roomPassword = ref("");
const joinCode = ref("");
const joinPassword = ref("");
const input = ref("");
const messageListRef = ref<HTMLElement | null>(null);

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
  const roomPart = store.activeRoom?.access_code ? `?room=${store.activeRoom.access_code}` : "";
  const url = `${window.location.origin}${window.location.pathname}${roomPart}#meeting-message-${message.id}`;
  copyToClipboard(url, "分享链接已复制");
}

async function scrollToBottom() {
  await nextTick();
  const el = messageListRef.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

// ── Feedback ─────────────────────────────────────────────────────

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
    ElMessage.success(feedbackType === "up" ? "已点赞" : "已点踩");
  } catch (error) {
    store.setReaction(message.id, previous || "");
    ElMessage.error("反馈提交失败，请稍后重试。");
    console.error(error);
  }
}

// ── Input ────────────────────────────────────────────────────────

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// ── Actions ──────────────────────────────────────────────────────

async function createRoom() {
  try {
    const room = await store.createRoom(roomTitle.value.trim() || "会议室", roomPassword.value.trim() || null);
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
    ElMessage.error("加入会议室失败，请检查会议码或密码。");
    console.error(error);
  }
}

async function sendMessage() {
  if (!store.canSend) return;
  const content = input.value.trim();
  await store.sendMessage(content);
  input.value = "";
  await scrollToBottom();
}

async function handleDeleteRoom() {
  if (!store.activeRoom) return;
  try {
    await ElMessageBox.confirm(
      `确定要删除会议室「${store.activeRoom.title}」吗？所有成员将无法继续访问。`,
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
    await store.deleteRoom();
    ElMessage.success("会议室已删除");
  } catch {
    // cancelled or error
  }
}

// ── Lifecycle ────────────────────────────────────────────────────

watch(() => store.activeRoomId, async (newId) => {
  if (newId) {
    await store.loadMessages(0);
    await store.loadAgents();
    await store.loadAvailableAgentDefs();
    store.connectStream();
    await scrollToBottom();
  } else {
    store.disconnectStream();
  }
});

onMounted(async () => {
  await store.loadRooms(true);
  if (store.activeRoomId) {
    store.connectStream();
  }
});

onBeforeUnmount(() => {
  store.disconnectStream();
});
</script>

<template>
  <div class="meeting-page">
    <aside class="meeting-sidebar">
      <section class="sidebar-section">
        <p class="section-kicker">MEETING HUB</p>
        <h1>进入会议</h1>
        <p class="section-copy">创建会议邀请成员，开启 AI 助手协作。</p>

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
          <el-button text :icon="RefreshRight" :loading="store.loadingRooms" @click="store.loadRooms()" aria-label="刷新会议列表" />
        </div>
        <button
          v-for="room in store.rooms"
          :key="room.id"
          type="button"
          class="room-item"
          :class="{ 'room-item-active': room.id === store.activeRoomId }"
          @click="store.activeRoomId = room.id"
        >
          <span class="room-title">{{ room.title }}</span>
          <span class="room-meta">{{ room.access_code }} · {{ room.member_count }} 人</span>
        </button>
        <p v-if="!store.rooms.length && !store.loadingRooms" class="empty-note">暂无加入过的会议</p>
      </section>
    </aside>

    <section class="meeting-room">
      <header class="room-header">
        <div>
          <p class="section-kicker">LIVE ROOM</p>
          <h2>{{ store.activeRoom?.title || "实时会议协作" }}</h2>
        </div>
        <div class="room-header-right">
          <!-- Agent Management -->
          <el-popover
            v-if="store.activeRoom"
            placement="bottom-end"
            :width="320"
            trigger="click"
          >
            <template #reference>
              <el-button size="small">
                管理 Agent ({{ store.agents.length }})
              </el-button>
            </template>
            <div class="agent-panel">
              <div class="agent-panel-head">
                <span>会议室 Agent</span>
                <el-dropdown @command="(id: string) => store.addAgentToRoom(id)">
                  <el-button size="small" text type="primary">
                    + 添加
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="ad in store.availableAgentDefs"
                        :key="ad.id"
                        :command="ad.id"
                        :disabled="store.agents.some(a => a.agent_id === ad.id)"
                      >
                        {{ ad.name }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div v-if="store.agents.length === 0" class="agent-panel-empty">
                暂未添加 Agent，点击"+ 添加"选择
              </div>
              <div v-for="agent in store.agents" :key="agent.id" class="agent-item">
                <span class="agent-item-name">{{ agent.agent_name }}</span>
                <span class="agent-item-role">{{ agent.role === 'observer' ? '观察者' : '参与者' }}</span>
                <el-button
                  size="small"
                  type="danger"
                  text
                  @click="store.removeAgentFromRoom(agent.agent_id)"
                >
                  移除
                </el-button>
              </div>
            </div>
          </el-popover>

          <div v-if="store.activeRoom" class="room-code">
            <span>会议码</span>
            <strong>{{ store.activeRoom.access_code }}</strong>
          </div>
          <el-button v-if="store.activeRoom && store.activeRoom.created_by === auth.userId" text type="danger" :icon="Delete" @click="handleDeleteRoom">
            删除
          </el-button>
        </div>
        <p v-if="!store.activeRoom" class="room-hint">创建或加入会议后开始聊天 · 开启 AI 助手获取智能回复</p>
      </header>

      <div ref="messageListRef" v-loading="store.loadingMessages" class="message-list">
        <div v-if="!store.activeRoom" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
          <p>发言和 AI 回复都会沉淀在同一条时间线中。</p>
        </div>

        <div v-else-if="store.messages.length === 0 && !store.loadingMessages" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
          <p>输入会议消息后回车发送，开启 AI 助手后自动获得智能回复。</p>
        </div>

        <article
          v-for="message in store.messages"
          :key="message.id"
          :id="`meeting-message-${message.id}`"
          class="message-row"
          :class="{
            'message-row-own': message.user_id === auth.userId && message.message_type !== 'agent',
            'message-row-agent': message.message_type === 'agent',
          }"
        >
          <div class="message-meta">
            <span v-if="message.message_type === 'agent'" class="agent-tag">AI</span>
            <span>{{ message.username }}</span>
            <time>{{ formatTime(message.created_at) }}</time>
          </div>
          <div class="message-bubble" :class="{ 'agent-bubble': message.message_type === 'agent' }">
            {{ message.content }}
          </div>
          <MessageActionBar
            :reaction="store.messageReactions[message.id] || ''"
            show-feedback
            @copy="copyToClipboard(message.content, '消息已复制')"
            @like="submitMeetingFeedback(message, 'up')"
            @dislike="submitMeetingFeedback(message, 'down')"
            @share="shareMeetingMessage(message)"
          />
        </article>
      </div>

      <footer class="composer">
        <textarea
          v-model="input"
          class="composer-textarea"
          :disabled="!store.activeRoom"
          rows="1"
          placeholder="输入消息后回车发送"
          @keydown="onInputKeydown"
        />
        <el-button type="primary" :icon="Promotion" :loading="store.sending" :disabled="!store.canSend" @click="sendMessage">
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

.room-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
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

/* Agent Panel */
.agent-panel {
  max-height: 360px;
  overflow-y: auto;
}

.agent-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f4f4f5;
}

.agent-panel-head span {
  font-weight: 700;
  font-size: 14px;
  color: #111827;
}

.agent-panel-empty {
  padding: 20px 0;
  color: #a1a1aa;
  font-size: 13px;
  text-align: center;
}

.agent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #fafafa;
}

.agent-item-name {
  flex: 1;
  font-weight: 600;
  font-size: 13px;
  color: #111827;
}

.agent-item-role {
  font-size: 11px;
  color: #71717a;
  background: #f4f4f5;
  padding: 1px 6px;
  border-radius: 4px;
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

/* Responsive */
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
