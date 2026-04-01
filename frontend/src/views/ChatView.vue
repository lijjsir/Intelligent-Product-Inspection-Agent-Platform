<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { CollectionTag, Paperclip, Promotion } from "@element-plus/icons-vue";
import { chatApi } from "@/api/chat.api";
import { useChatStore } from "@/stores/chat.store";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { useTaskStore } from "@/stores/task.store";
import type { ChatAttachment, ChatCreatedTask, ChatMessage } from "@/types/chat.types";

const router = useRouter();
const chatStore = useChatStore();
const taskStore = useTaskStore();
const inspectionSpecStore = useInspectionSpecStore();

const input = ref("");
const messageListRef = ref<HTMLElement | null>(null);
const attachmentInputRef = ref<HTMLInputElement | null>(null);
const taskImageInputRef = ref<HTMLInputElement | null>(null);

const taskDialogVisible = ref(false);
const taskSubmitting = ref(false);
const taskFormRef = ref<FormInstance>();
const taskForm = ref({
  product_id: "",
  spec_code: "",
  image_urls_input: "",
  priority: 5,
});
const taskFormAttachments = ref<ChatAttachment[]>([]);

const taskRules: FormRules = {
  product_id: [{ required: true, message: "请输入产品编号", trigger: "blur" }],
  spec_code: [{ required: true, message: "请选择或输入检测标准编号", trigger: "change" }],
  image_urls_input: [
    {
      validator: (_rule, value: string, callback) => {
        const hasText = Boolean(value?.trim());
        const hasUploads = taskFormAttachments.value.length > 0;
        if (!hasText && !hasUploads) {
          callback(new Error("请至少提供一个检测图片 URL，或者上传一张图片"));
          return;
        }
        callback();
      },
      trigger: "blur",
    },
  ],
};

const activeSpecOptions = computed(() => inspectionSpecStore.items.filter((item) => item.is_active));
const canSend = computed(() => (input.value.trim().length > 0 || chatStore.pendingAttachments.length > 0) && !chatStore.loading);
const selectedRagId = computed({
  get: () => chatStore.selectedRagSpaceId,
  set: (value: string) => {
    if (!value) {
      chatStore.clearSelectedRagSpace();
      return;
    }
    chatStore.selectRagSpace(value);
  },
});

const citationList = (message: ChatMessage) => message.payload?.citations || [];
const qualityLabel = (message: ChatMessage) => message.payload?.quality?.risk_level || "";
const missingSlots = (message: ChatMessage) => message.payload?.missing_slots || [];
const attachments = (message: ChatMessage) => message.payload?.attachment_echo || [];
const taskDraft = (message: ChatMessage) => message.payload?.task_draft || message.payload?.task_form_defaults || null;
const createdTask = (message: ChatMessage) => message.payload?.created_task || null;

const slotLabel = (slot: string) => {
  if (slot === "product_id") return "产品编号";
  if (slot === "spec_code") return "检测标准编号";
  if (slot === "image_urls") return "检测图片";
  return slot;
};

const intentLabel = (message: ChatMessage) => {
  const intent = message.payload?.intent;
  if (intent === "smalltalk") return "普通对话";
  if (intent === "quality_qa") return "质量问答";
  if (intent === "task_create" || intent === "task_followup") return "任务对话";
  return "";
};

const actionStateLabel = (message: ChatMessage) => {
  const state = message.payload?.action_state;
  if (state === "awaiting_task_details") return "等待补充信息";
  if (state === "awaiting_task_confirmation") return "等待确认创建";
  if (state === "task_created") return "任务已创建";
  if (state === "task_cancelled") return "已取消";
  if (state === "task_create_failed") return "创建失败";
  return "";
};

const qualityTagType = (message: ChatMessage) => {
  const level = qualityLabel(message);
  if (level === "green") return "success";
  if (level === "yellow") return "warning";
  if (level === "red") return "danger";
  return "info";
};

const canOpenTaskForm = (message: ChatMessage) =>
  message.role === "assistant" &&
  message.payload?.task_submit_mode === "direct_create" &&
  ["awaiting_task_details", "awaiting_task_confirmation"].includes(message.payload?.action_state || "");

const formatTime = (ts?: string | null) => {
  if (!ts) return "-";
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(ts) ? ts : `${ts}Z`;
  const dt = new Date(normalized);
  if (Number.isNaN(dt.getTime())) return ts;
  return dt.toLocaleString();
};

const scrollToBottom = async () => {
  await nextTick();
  const element = messageListRef.value;
  if (!element) return;
  element.scrollTop = element.scrollHeight;
};

watch(
  () => chatStore.messages.map((item) => `${item.id}:${item.content.length}:${item.message_type}:${item.seq_no}`).join("|"),
  () => {
    scrollToBottom().catch(() => undefined);
  },
);

function buildOutgoingMessage() {
  const text = input.value.trim();
  if (text) return text;
  if (chatStore.pendingAttachments.length > 0) {
    return "请查看我上传的附件。";
  }
  return "";
}

const sendMessage = async () => {
  const message = buildOutgoingMessage();
  if (!message || chatStore.loading) return;
  const previousInput = input.value;
  input.value = "";
  try {
    await chatStore.sendMessage({
      message,
      schema_version: "1.0.0",
      workspace: "app",
    });
  } catch (error) {
    input.value = previousInput;
    ElMessage.error("发送失败，请稍后重试");
    console.error(error);
  }
};

const onInputKeydown = async (event: KeyboardEvent) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendMessage();
  }
};

const jumpToTask = (taskId: string) => {
  router.push(`/app/tasks/${taskId}`);
};

const triggerAttachmentSelect = () => {
  attachmentInputRef.value?.click();
};

const triggerTaskImageSelect = () => {
  taskImageInputRef.value?.click();
};

const handleAttachmentSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try {
    await chatStore.uploadPendingAttachments(files);
  } catch (error) {
    ElMessage.error("附件上传失败，请稍后重试");
    console.error(error);
  } finally {
    inputElement.value = "";
  }
};

const handleTaskImageSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try {
    const { data } = await chatApi.uploadAttachments(files);
    taskFormAttachments.value = [...taskFormAttachments.value, ...data.data.items];
    syncTaskFormImageUrls();
  } catch (error) {
    ElMessage.error("任务图片上传失败，请稍后重试");
    console.error(error);
  } finally {
    inputElement.value = "";
  }
};

const syncTaskFormImageUrls = () => {
  const urls = Array.from(
    new Set(
      taskForm.value.image_urls_input
        .split(/[\n,，；;]+/)
        .map((item) => item.trim())
        .filter(Boolean)
        .concat(taskFormAttachments.value.map((item) => item.url)),
    ),
  );
  taskForm.value.image_urls_input = urls.join("\n");
};

const removeTaskAttachment = (attachmentId: string) => {
  taskFormAttachments.value = taskFormAttachments.value.filter((item) => item.id !== attachmentId);
  syncTaskFormImageUrls();
};

const resetTaskDialog = () => {
  taskForm.value = {
    product_id: "",
    spec_code: "",
    image_urls_input: "",
    priority: 5,
  };
  taskFormAttachments.value = [];
};

const openTaskForm = async (message: ChatMessage) => {
  const defaults = message.payload?.task_form_defaults || message.payload?.task_draft || {};
  taskForm.value = {
    product_id: String(defaults.product_id || ""),
    spec_code: String(defaults.spec_code || ""),
    image_urls_input: Array.isArray(defaults.image_urls) ? defaults.image_urls.join("\n") : "",
    priority: Number(defaults.priority || 5),
  };
  taskFormAttachments.value = [...attachments(message).filter((item) => item.kind === "image")];
  syncTaskFormImageUrls();
  taskDialogVisible.value = true;
  await nextTick();
  taskFormRef.value?.clearValidate();
};

const submitTaskForm = async () => {
  if (!taskFormRef.value || !chatStore.session) return;
  const valid = await taskFormRef.value.validate().catch(() => false);
  if (!valid) return;
  taskSubmitting.value = true;
  try {
    const imageUrls = Array.from(
      new Set(
        taskForm.value.image_urls_input
          .split(/[\n,，；;]+/)
          .map((item) => item.trim())
          .filter(Boolean),
      ),
    );
    const created = await taskStore.createTask({
      product_id: taskForm.value.product_id.trim(),
      spec_code: taskForm.value.spec_code.trim(),
      image_urls: imageUrls,
      priority: Number(taskForm.value.priority || 5),
    });
    const task: ChatCreatedTask = {
      id: created.id,
      status: created.status,
      product_id: created.product_id,
      spec_code: created.spec_code,
      priority: created.priority,
      image_count: created.image_urls.length,
    };
    await chatStore.appendTaskResult(task);
    taskDialogVisible.value = false;
    resetTaskDialog();
    ElMessage.success("任务已创建并回写到当前会话");
  } catch (error) {
    ElMessage.error("任务创建失败，请检查表单后重试");
    console.error(error);
  } finally {
    taskSubmitting.value = false;
  }
};

onMounted(async () => {
  await Promise.allSettled([
    inspectionSpecStore.fetchAll(),
    chatStore.initForChatPage(),
  ]);
  await scrollToBottom();
});

</script>

<template>
  <div class="chat-page">
    <section class="chat-shell">
      <div ref="messageListRef" class="chat-body">
        <el-alert
          v-if="chatStore.ragSpacesError"
          class="rag-warning"
          type="warning"
          :closable="false"
          show-icon
          :title="chatStore.ragSpacesError"
          description="聊天功能仍可继续使用；如果需要启用 RAG 空间，请先完成数据库迁移并重启后端。"
        />
        <el-empty v-if="chatStore.messages.length === 0" description="从这里开始提问吧" />
        <div v-else class="message-list">
          <div
            v-for="message in chatStore.messages"
            :key="message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-meta">
              <span class="message-role">{{ message.role === "user" ? "你" : "智能体" }}</span>
              <span class="message-time">{{ formatTime(message.created_at) }}</span>
            </div>

            <div class="message-bubble" :class="message.role">
              <div class="message-content">{{ message.content || "..." }}</div>

              <div v-if="intentLabel(message) || actionStateLabel(message) || message.payload?.selected_rag_space?.name" class="signal-row">
                <el-tag v-if="intentLabel(message)" size="small" effect="plain">{{ intentLabel(message) }}</el-tag>
                <el-tag v-if="actionStateLabel(message)" type="warning" size="small" effect="plain">
                  {{ actionStateLabel(message) }}
                </el-tag>
                <el-tag v-if="message.payload?.selected_rag_space?.name" type="success" size="small" effect="plain">
                  RAG：{{ message.payload.selected_rag_space.name }}
                </el-tag>
              </div>

              <div v-if="qualityLabel(message)" class="message-quality">
                <el-tag :type="qualityTagType(message)" size="small">风险等级：{{ qualityLabel(message) }}</el-tag>
              </div>

              <div v-if="attachments(message).length" class="attachment-list">
                <div class="section-title">消息附件</div>
                <div class="chip-row">
                  <el-tag v-for="attachment in attachments(message)" :key="attachment.id" size="small" effect="plain">
                    {{ attachment.name }}
                  </el-tag>
                </div>
              </div>

              <div v-if="taskDraft(message)" class="task-card">
                <div class="section-title">任务草稿</div>
                <div class="task-grid">
                  <span>产品编号</span>
                  <strong>{{ taskDraft(message)?.product_id || "未提供" }}</strong>
                  <span>检测标准</span>
                  <strong>{{ taskDraft(message)?.spec_code || "未提供" }}</strong>
                  <span>图片数量</span>
                  <strong>{{ taskDraft(message)?.image_urls?.length || 0 }}</strong>
                  <span>优先级</span>
                  <strong>{{ taskDraft(message)?.priority || 5 }}</strong>
                </div>
              </div>

              <div v-if="missingSlots(message).length" class="task-card warning-card">
                <div class="section-title">待补充字段</div>
                <div class="chip-row">
                  <el-tag
                    v-for="slot in missingSlots(message)"
                    :key="slot"
                    type="warning"
                    effect="plain"
                    size="small"
                  >
                    {{ slotLabel(slot) }}
                  </el-tag>
                </div>
                <div v-if="canOpenTaskForm(message)" class="task-actions">
                  <el-button type="primary" plain @click="openTaskForm(message)">补充信息</el-button>
                </div>
              </div>

              <div v-if="createdTask(message)" class="task-card success-card">
                <div class="section-title">已创建任务</div>
                <div class="task-grid">
                  <span>任务 ID</span>
                  <strong>{{ createdTask(message)?.id }}</strong>
                  <span>状态</span>
                  <strong>{{ createdTask(message)?.status }}</strong>
                  <span>产品编号</span>
                  <strong>{{ createdTask(message)?.product_id }}</strong>
                  <span>检测标准</span>
                  <strong>{{ createdTask(message)?.spec_code }}</strong>
                </div>
                <div class="task-actions">
                  <el-button type="primary" link @click="jumpToTask(createdTask(message)!.id)">查看任务</el-button>
                </div>
              </div>

              <div v-if="citationList(message).length" class="citation-list">
                <div class="section-title">引用依据</div>
                <div v-for="(citation, index) in citationList(message)" :key="index" class="citation-item">
                  <div class="citation-name">{{ citation.title || `依据 ${index + 1}` }}</div>
                  <div class="citation-quote">{{ citation.quote || citation.source || "" }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-footer">
        <div v-if="chatStore.pendingAttachments.length || chatStore.selectedRagSpace" class="composer-meta">
          <div v-if="chatStore.pendingAttachments.length" class="chip-row">
            <el-tag
              v-for="attachment in chatStore.pendingAttachments"
              :key="attachment.id"
              closable
              effect="plain"
              @close="chatStore.removePendingAttachment(attachment.id)"
            >
              {{ attachment.name }}
            </el-tag>
          </div>

          <el-tag v-if="chatStore.selectedRagSpace" type="success" effect="plain">
            当前 RAG：{{ chatStore.selectedRagSpace.name }}
          </el-tag>
        </div>

        <el-input
          v-model="input"
          type="textarea"
          :rows="4"
          resize="none"
          placeholder="输入质量检测问题，或直接描述你想创建的检测任务。Enter 发送，Shift+Enter 换行。"
          @keydown="onInputKeydown"
        />

        <div class="footer-actions">
          <div class="footer-left">
            <input ref="attachmentInputRef" type="file" multiple class="hidden-input" @change="handleAttachmentSelected" />
            <el-button circle plain :icon="Paperclip" title="上传图片或文件" @click="triggerAttachmentSelect" />

            <el-popover placement="top-start" trigger="click" width="340">
              <template #reference>
                <el-button circle plain :icon="CollectionTag" title="选择 RAG 空间" />
              </template>

              <div class="rag-popover">
                <div class="popover-title">选择当前会话使用的 RAG 空间</div>
                <el-alert
                  v-if="chatStore.ragSpacesError"
                  type="warning"
                  :closable="false"
                  show-icon
                  :title="chatStore.ragSpacesError"
                />
                <el-radio-group v-model="selectedRagId" class="rag-choice-group" :disabled="Boolean(chatStore.ragSpacesError)">
                  <el-radio label="">不使用额外 RAG</el-radio>
                  <el-tooltip
                    v-for="space in chatStore.ragSpaces"
                    :key="space.id"
                    :content="space.description || '暂无描述'"
                    placement="left"
                  >
                    <el-radio :label="space.id">{{ space.name }}</el-radio>
                  </el-tooltip>
                </el-radio-group>
              </div>
            </el-popover>
          </div>

          <el-button type="primary" :icon="Promotion" :loading="chatStore.loading" :disabled="!canSend" @click="sendMessage">
            发送
          </el-button>
        </div>
      </div>
    </section>

    <el-dialog v-model="taskDialogVisible" title="补充任务信息" width="560px" @closed="resetTaskDialog">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="110px">
        <el-form-item label="产品编号" prop="product_id">
          <el-input v-model="taskForm.product_id" placeholder="例如：PROD-123456" />
        </el-form-item>

        <el-form-item label="检测标准" prop="spec_code">
          <el-select
            v-model="taskForm.spec_code"
            filterable
            clearable
            allow-create
            default-first-option
            placeholder="请选择或输入检测标准编号"
            style="width: 100%"
          >
            <el-option
              v-for="spec in activeSpecOptions"
              :key="spec.id"
              :label="`${spec.spec_code} · ${spec.name}`"
              :value="spec.spec_code"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="检测图片" prop="image_urls_input">
          <el-input
            v-model="taskForm.image_urls_input"
            type="textarea"
            :rows="4"
            placeholder="可以粘贴图片 URL，多条可使用换行、逗号或分号分隔"
          />
          <div class="dialog-upload">
            <input ref="taskImageInputRef" type="file" multiple accept="image/*" class="hidden-input" @change="handleTaskImageSelected" />
            <el-button plain size="small" :icon="Paperclip" @click="triggerTaskImageSelect">上传图片</el-button>
          </div>
          <div v-if="taskFormAttachments.length" class="chip-row top-gap">
            <el-tag
              v-for="attachment in taskFormAttachments"
              :key="attachment.id"
              closable
              effect="plain"
              @close="removeTaskAttachment(attachment.id)"
            >
              {{ attachment.name }}
            </el-tag>
          </div>
        </el-form-item>

        <el-form-item label="优先级">
          <el-input-number v-model="taskForm.priority" :min="1" :max="10" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="taskSubmitting" @click="submitTaskForm">确认并提交任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.chat-page {
  display: grid;
  width: 100%;
}

.chat-shell {
  display: grid;
  grid-template-rows: minmax(calc(100vh - 250px), 1fr) auto;
  gap: 14px;
}

.chat-body {
  min-height: 0;
  overflow-y: auto;
  border: 1px solid #d9efe5;
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(16, 185, 129, 0.12), transparent 32%),
    radial-gradient(circle at bottom left, rgba(14, 165, 233, 0.1), transparent 26%),
    linear-gradient(180deg, #fbfffd 0%, #eff8f4 100%);
  padding: 22px;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rag-warning {
  margin-bottom: 16px;
}

.message-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-row.user {
  align-items: flex-end;
}

.message-row.assistant,
.message-row.system {
  align-items: flex-start;
}

.message-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}

.message-bubble {
  max-width: min(820px, 92%);
  padding: 14px 16px;
  border-radius: 20px;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
}

.message-bubble.user {
  background: linear-gradient(135deg, #0f766e 0%, #115e59 100%);
  color: #fff;
}

.message-bubble.assistant,
.message-bubble.system {
  background: rgba(255, 255, 255, 0.96);
  color: #0f172a;
  border: 1px solid #d7f3e8;
}

.message-content {
  white-space: pre-wrap;
  line-height: 1.75;
}

.chat-footer,
.composer-meta,
.rag-popover {
  display: grid;
  gap: 10px;
}

.signal-row,
.chip-row,
.task-actions,
.footer-left {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.signal-row,
.message-quality,
.attachment-list,
.task-card,
.citation-list {
  margin-top: 12px;
}

.task-card {
  padding: 12px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.warning-card {
  background: #fff7ed;
  border-color: #fdba74;
}

.success-card {
  background: #ecfdf5;
  border-color: #86efac;
}

.section-title,
.popover-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f766e;
}

.citation-quote {
  font-size: 12px;
  color: #475569;
  line-height: 1.6;
}

.task-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 6px 10px;
  align-items: center;
  font-size: 13px;
}

.citation-list {
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
  display: grid;
  gap: 8px;
}

.citation-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
}

.citation-name {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.footer-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.rag-choice-group {
  display: grid;
  gap: 8px;
}

.dialog-upload,
.top-gap {
  margin-top: 10px;
}

.hidden-input {
  display: none;
}

@media (max-width: 960px) {
  .chat-shell {
    grid-template-rows: minmax(60vh, 1fr) auto;
  }

  .message-bubble {
    width: 100%;
    max-width: 100%;
  }

  .task-grid {
    grid-template-columns: 1fr;
  }

  .footer-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
