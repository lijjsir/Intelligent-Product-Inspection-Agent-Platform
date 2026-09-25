<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, CircleCheck, RefreshRight } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { supervisionApi } from "@/api/supervision.api";
import { OP_LABELS, type BusinessTodo } from "@/types/supervision.types";

const router = useRouter();
const enabled = ref(false);
const loading = ref(false);
const items = ref<BusinessTodo[]>([]);

async function load() {
  loading.value = true;
  try {
    enabled.value = (await supervisionApi.settings()).data.data.enabled;
    if (enabled.value) items.value = (await supervisionApi.todos()).data.data;
  } catch {
    if (enabled.value) ElMessage.error("业务待办暂时不可用，请刷新");
  } finally {
    loading.value = false;
  }
}

async function decide(item: BusinessTodo, decision: string) {
  const result = await ElMessageBox.prompt(
    "记录复核依据或需要补齐的材料。",
    "处理" + OP_LABELS[item.operation],
    { inputType: "textarea", inputValidator: (v: string) => !!v?.trim() || "请填写处理意见" },
  );
  await supervisionApi.decide(item.id, decision, result.value);
  ElMessage.success("已记录处理结果");
  await load();
}

function open(item: BusinessTodo) {
  router.push({ path: `/app/${item.kind}`, query: { record: item.record_id } });
}

onMounted(load);
</script>

<template>
  <section v-if="enabled" class="todo-panel" v-loading="loading" aria-labelledby="todo-title">
    <header>
      <div>
        <span class="queue-kicker">HUMAN REVIEW QUEUE</span>
        <h2 id="todo-title">
          待我处理 <b v-if="items.length">{{ items.length }}</b>
        </h2>
        <p>补证、风险复核、抽查方案与正式结果在这里集中确认。</p>
      </div>
      <el-button :icon="RefreshRight" @click="load">刷新</el-button>
    </header>

    <el-table v-if="items.length" :data="items" class="todo-table">
      <el-table-column prop="name" label="业务记录" min-width="180" />
      <el-table-column label="处理事项" width="150">
        <template #default="{ row }">{{ OP_LABELS[row.operation] || row.operation }}</template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="70" />
      <el-table-column label="操作" min-width="300">
        <template #default="{ row }">
          <el-button size="small" text @click="open(row)">查看依据 <ArrowRight /></el-button>
          <template v-if="row.operation !== 'request_evidence'">
            <el-button size="small" type="primary" @click="decide(row, 'accept')">通过</el-button>
            <el-button size="small" @click="decide(row, 'request_evidence')">退回补证</el-button>
            <el-button size="small" @click="decide(row, 'escalate')">转人工会商</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <div v-else class="queue-empty">
      <span class="empty-icon"><CircleCheck /></span>
      <div>
        <strong>当前队列已处理完</strong>
        <p>新的复核或确认请求到达后会显示在这里。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.todo-panel {
  overflow: hidden;
  border: 1px solid #deded9;
  border-radius: 16px;
  background: #fff;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px 20px;
  border-bottom: 1px solid #ecece8;
}

.queue-kicker {
  color: #71717a;
  font:
    700 10px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
  letter-spacing: 0.14em;
}

h2 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 7px 0 4px;
  font-size: 22px;
}

h2 b {
  display: inline-grid;
  min-width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 12px;
  background: #111214;
  color: #fff;
  font:
    700 11px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

header p,
.queue-empty p {
  margin: 0;
  color: #71717a;
  font-size: 13px;
}

.todo-table {
  padding: 0 12px 12px;
}

.todo-table :deep(.el-button svg) {
  width: 13px;
  margin-left: 3px;
}

.queue-empty {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 124px;
  padding: 26px;
  background: linear-gradient(90deg, rgba(15, 118, 110, 0.04), transparent 30%), #fff;
}

.empty-icon {
  display: grid;
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  background: #e8f7f3;
  color: #0f766e;
}

.empty-icon svg {
  width: 22px;
}

.queue-empty strong {
  display: block;
  margin-bottom: 5px;
  font-size: 15px;
}

@media (max-width: 640px) {
  header {
    align-items: flex-start;
    padding: 20px 16px 16px;
  }
  .queue-empty {
    min-height: 110px;
    padding: 20px 16px;
  }
}
</style>
