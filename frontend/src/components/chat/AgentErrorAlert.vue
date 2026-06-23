<script setup lang="ts">
import { computed } from "vue";
import type { AgentErrorPayload } from "@/types/chat.types";
import { agentErrorBrief } from "@/views/chat-rendering";

const props = defineProps<{
  error: AgentErrorPayload;
}>();

const brief = computed(() => agentErrorBrief(props.error));
</script>

<template>
  <div class="agent-error-alert">
    <div class="agent-error-title">{{ brief.title }}</div>
    <div class="agent-error-message">{{ brief.message }}</div>
  </div>
</template>

<style scoped>
.agent-error-alert {
  display: grid;
  gap: 6px;
}

.agent-error-title {
  color: #991b1b;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}

.agent-error-message {
  color: #7f1d1d;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
