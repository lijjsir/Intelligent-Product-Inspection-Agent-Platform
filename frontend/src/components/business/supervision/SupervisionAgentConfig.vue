<script setup lang="ts">
import { ref, onMounted } from "vue";
import { http } from "@/api/http";
import { useAuthStore } from "@/stores/auth.store";
import { ElMessage } from "element-plus";
const auth = useAuthStore(),
  rows = ref<any[]>([]);
const labels: Record<string, string> = {
  market_monitoring: "市场监控 Agent",
  public_opinion_monitoring: "舆情监测 Agent",
  supervision_sampling: "监督抽查 Agent",
  laboratory_testing: "实验室检测 Agent",
};
async function load() {
  const data = (await http.get<Record<string, any>>("/v1/quality-supervision/agent-config")).data
    .data;
  rows.value = Object.entries(data).map(([id, config]) => ({ id, ...config }));
}
async function save() {
  await http.patch("/v1/quality-supervision/agent-config", {
    agents: Object.fromEntries(rows.value.map(({ id, ...config }) => [id, config])),
  });
  ElMessage.success("配置已保存，暂停后不再受理新分析");
}
onMounted(load);
</script>
<template>
  <el-collapse class="supervision-config"
    ><el-collapse-item title="四类质监 Agent 的运行设置"
      ><el-table :data="rows"
        ><el-table-column label="业务角色"
          ><template #default="{ row }">{{ labels[row.id] }}</template></el-table-column
        ><el-table-column label="受理新分析" width="150"
          ><template #default="{ row }"
            ><el-switch
              v-model="row.enabled"
              :disabled="auth.role === 'platform_operator'" /></template></el-table-column
        ><el-table-column label="超时（秒）" width="180"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.timeout_seconds"
              :min="30"
              :max="600"
              :disabled="auth.role === 'platform_operator'" /></template></el-table-column
        ><el-table-column label="最多轮次" width="160"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.max_rounds"
              :min="1"
              :max="2"
              :disabled="
                auth.role === 'platform_operator'
              " /></template></el-table-column></el-table
      ><el-button v-if="['admin', 'app_developer'].includes(auth.role)" type="primary" @click="save"
        >保存运行设置</el-button
      ></el-collapse-item
    ></el-collapse
  >
</template>
<style scoped>
.supervision-config {
  margin: 18px 0;
}
.el-button {
  margin-top: 12px;
}
</style>
