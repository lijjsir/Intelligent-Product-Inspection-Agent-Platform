<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { http } from "@/api/http";
import type { MeetingRoomAgent } from "@/types/meeting.types";

interface AvailableAgent {
  id: string;
  name: string;
  description: string | null;
  group_key: string;
}

const props = defineProps<{
  modelValue: boolean;
  existingAgents: MeetingRoomAgent[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "add", agentId: string, role: string): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const allAgents = ref<AvailableAgent[]>([]);
const loading = ref(false);
const adding = ref(false);

const existingIds = computed(() => new Set(props.existingAgents.map((a) => a.agent_id)));

const availableAgents = computed(() =>
  allAgents.value.filter((a) => !existingIds.value.has(a.id))
);

onMounted(async () => {
  loading.value = true;
  try {
    const { data } = await http.get("/v1/meetings/available-agents");
    const payload = data as { data?: AvailableAgent[] };
    allAgents.value = payload.data || [];
  } catch {
    ElMessage.error("获取 Agent 列表失败");
  } finally {
    loading.value = false;
  }
});

async function handleAdd(agent: AvailableAgent) {
  adding.value = true;
  try {
    emit("add", agent.id, "participant");
    visible.value = false;
  } finally {
    adding.value = false;
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="添加 Agent 到会议室" width="480px" destroy-on-close>
    <div v-loading="loading" class="agent-picker-body">
      <p v-if="!availableAgents.length && !loading" class="empty-hint">
        暂无可添加的 Agent
      </p>
      <button
        v-for="agent in availableAgents"
        :key="agent.id"
        type="button"
        class="agent-option"
        :disabled="adding"
        @click="handleAdd(agent)"
      >
        <div class="agent-option-head">
          <span class="agent-name">{{ agent.name }}</span>
          <span class="agent-group">{{ agent.group_key }}</span>
        </div>
        <p class="agent-desc">{{ agent.description || "暂无描述" }}</p>
      </button>
    </div>
  </el-dialog>
</template>

<style scoped>
.agent-picker-body {
  max-height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty-hint {
  color: #71717a;
  text-align: center;
  padding: 24px 0;
  font-size: 14px;
}

.agent-option {
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  transition: border-color 150ms ease, background 150ms ease;
}

.agent-option:hover {
  border-color: #18181b;
  background: #fafafa;
}

.agent-option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.agent-option-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-name {
  font-weight: 600;
  color: #111827;
}

.agent-group {
  font-size: 11px;
  color: #a1a1aa;
  background: #f4f4f5;
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-desc {
  margin-top: 4px;
  font-size: 13px;
  color: #71717a;
  line-height: 1.5;
}
</style>
