<script setup lang="ts">
import type { AgentErrorPayload } from "@/types/chat.types";

defineProps<{
  error: AgentErrorPayload;
}>();
</script>

<template>
  <div class="agent-error-alert">
    <div class="agent-error-main">
      <div class="agent-error-title-row">
        <span class="agent-error-title">{{ error.title || "执行失败" }}</span>
        <el-tag size="small" type="danger" effect="plain">{{ error.code }}</el-tag>
        <el-tag v-if="error.status === 'blocked'" size="small" type="warning" effect="plain">需补充信息</el-tag>
        <el-tag v-else-if="error.retryable" size="small" type="info" effect="plain">可重试</el-tag>
      </div>
      <div class="agent-error-message">{{ error.message }}</div>
      <div v-if="error.user_action" class="agent-error-action">
        <span>建议</span>
        <strong>{{ error.user_action }}</strong>
      </div>
    </div>
    <div class="agent-error-meta">
      <div v-if="error.category" class="agent-error-meta-item">
        <span>Category</span>
        <strong>{{ error.category }}</strong>
      </div>
      <div v-if="error.source" class="agent-error-meta-item">
        <span>Source</span>
        <strong>{{ error.source }}</strong>
      </div>
      <div v-if="error.owner_agent" class="agent-error-meta-item">
        <span>Agent</span>
        <strong>{{ error.owner_agent }}</strong>
      </div>
      <div v-if="error.capability" class="agent-error-meta-item">
        <span>Capability</span>
        <strong>{{ error.capability }}</strong>
      </div>
      <div v-if="error.trace_id" class="agent-error-meta-item agent-error-meta-wide">
        <span>Trace ID</span>
        <strong>{{ error.trace_id }}</strong>
      </div>
      <div v-if="error.workflow_run_id" class="agent-error-meta-item agent-error-meta-wide">
        <span>Workflow</span>
        <strong>{{ error.workflow_run_id }}</strong>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-error-alert {
  display: grid;
  gap: 12px;
}

.agent-error-main {
  display: grid;
  gap: 8px;
}

.agent-error-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-error-title {
  min-width: 0;
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

.agent-error-action {
  display: grid;
  gap: 3px;
  color: #7f1d1d;
  font-size: 13px;
  line-height: 1.5;
}

.agent-error-action span,
.agent-error-meta-item span {
  color: #b91c1c;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.agent-error-action strong {
  font-weight: 500;
}

.agent-error-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.agent-error-meta-item {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fee2e2;
}

.agent-error-meta-item strong {
  min-width: 0;
  color: #7f1d1d;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.agent-error-meta-wide {
  grid-column: 1 / -1;
}

@media (max-width: 640px) {
  .agent-error-meta {
    grid-template-columns: 1fr;
  }
}
</style>
