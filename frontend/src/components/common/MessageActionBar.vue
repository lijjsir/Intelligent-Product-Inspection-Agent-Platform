<script setup lang="ts">
import { CopyDocument, Edit, RefreshRight, Share } from "@element-plus/icons-vue";

withDefaults(
  defineProps<{
    reaction?: "up" | "down" | "";
    showEdit?: boolean;
    showFeedback?: boolean;
    showRetry?: boolean;
    retryDisabled?: boolean;
  }>(),
  {
    reaction: "",
    showEdit: false,
    showFeedback: false,
    showRetry: false,
    retryDisabled: false,
  },
);

defineEmits<{
  copy: [];
  edit: [];
  like: [];
  dislike: [];
  share: [];
  retry: [];
}>();
</script>

<template>
  <div class="message-actions" aria-label="消息操作">
    <el-tooltip content="复制" placement="bottom">
      <el-button text :icon="CopyDocument" aria-label="复制" @click="$emit('copy')" />
    </el-tooltip>
    <el-tooltip v-if="showEdit" content="编辑" placement="bottom">
      <el-button text :icon="Edit" aria-label="编辑" @click="$emit('edit')" />
    </el-tooltip>
    <el-tooltip v-if="showFeedback" content="喜欢" placement="bottom">
      <el-button
        text
        aria-label="喜欢"
        :class="{ 'is-active': reaction === 'up' }"
        @click="$emit('like')"
      >
        <svg class="thumb-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
          <path d="M7 11l4.5-8a2.2 2.2 0 0 1 3.9 1.8L14.5 9H20a2 2 0 0 1 2 2.3l-1.1 7a4 4 0 0 1-4 3.7H7z" />
        </svg>
      </el-button>
    </el-tooltip>
    <el-tooltip v-if="showFeedback" content="不喜欢" placement="bottom">
      <el-button
        text
        aria-label="不喜欢"
        :class="{ 'is-active': reaction === 'down' }"
        @click="$emit('dislike')"
      >
        <svg class="thumb-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3" />
          <path d="M17 13l-4.5 8a2.2 2.2 0 0 1-3.9-1.8L9.5 15H4a2 2 0 0 1-2-2.3l1.1-7a4 4 0 0 1 4-3.7H17z" />
        </svg>
      </el-button>
    </el-tooltip>
    <el-tooltip content="分享" placement="bottom">
      <el-button text :icon="Share" aria-label="分享" @click="$emit('share')" />
    </el-tooltip>
    <el-tooltip v-if="showRetry" content="重试" placement="bottom">
      <el-button text :icon="RefreshRight" aria-label="重试" :disabled="retryDisabled" @click="$emit('retry')" />
    </el-tooltip>
  </div>
</template>

<style scoped>
.message-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-height: 28px;
  margin-top: 4px;
}

.message-actions :deep(.el-button) {
  width: 28px;
  height: 28px;
  padding: 0;
  color: #6b7280;
  border-radius: 7px;
}

.message-actions :deep(.el-button:hover),
.message-actions :deep(.el-button.is-active) {
  color: #111827;
  background: #f3f4f6;
}

.message-actions :deep(.el-button.is-disabled) {
  background: transparent;
}

.thumb-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
