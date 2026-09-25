<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { supervisionApi } from "@/api/supervision.api";
import { taskApi } from "@/api/task.api";
import type { SupervisionRecord } from "@/types/supervision.types";
const rows = ref<SupervisionRecord[]>([]),
  busy = ref(false);
async function load() {
  rows.value = (await supervisionApi.enrollments()).data.data;
}
async function ingest(row: SupervisionRecord) {
  busy.value = true;
  try {
    const result = (
      await taskApi.ingest(row.data.task_id, {
        target: "dataset",
        dataset_id: row.data.dataset_id,
        mode: "candidate",
      })
    ).data.data;
    ElMessage.success(
      `新增${result.created_sample_count}个候选，跳过${result.skipped_count}个重复样本`,
    );
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <main style="padding: 24px" v-loading="busy">
    <h1 style="font-size: 24px">已授权业务样本</h1>
    <p>仅接收业务人员明确授权到你的数据集的签发版本，导入后仍需数据集审核。</p>
    <el-button @click="load">刷新</el-button
    ><el-table :data="rows"
      ><el-table-column prop="name" label="业务来源与接收数据集" /><el-table-column
        label="授权版本"
        width="120"
        ><template #default="{ row }">{{ row.data.session_version }}</template></el-table-column
      ><el-table-column label="接收" width="160"
        ><template #default="{ row }"
          ><el-button
            :disabled="row.data.knowledge_status === 'needs_reassessment'"
            type="primary"
            size="small"
            @click="ingest(row)"
            >导入候选样本</el-button
          ></template
        ></el-table-column
      ></el-table
    >
  </main>
</template>
