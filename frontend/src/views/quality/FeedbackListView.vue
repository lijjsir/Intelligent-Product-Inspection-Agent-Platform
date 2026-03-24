<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useFeedbackStore } from "@/stores/feedback.store";

const store = useFeedbackStore();

const csvContent = computed(() => {
  const header = ["created_at", "result_id", "actor_id", "feedback_type", "rating", "category", "comment"];
  const rows = store.items.map((item) => header.map((key) => JSON.stringify((item as any)[key] ?? "")).join(","));
  return [header.join(","), ...rows].join("\n");
});

function exportCsv() {
  const blob = new Blob([csvContent.value], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "feedbacks.csv";
  link.click();
  URL.revokeObjectURL(url);
}

onMounted(() => {
  store.fetchList({ page: 1, size: 100 });
});
</script>

<template>
  <div class="page-container">
    <div class="hero">
      <div>
        <h2>反馈流水</h2>
        <p>查看治理层回灌的点赞/点踩与评论。</p>
      </div>
      <el-button @click="exportCsv">导出 CSV</el-button>
    </div>
    <el-card shadow="never">
      <el-table :data="store.items" v-loading="store.loading">
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="actor_id" label="用户" min-width="180" />
        <el-table-column prop="feedback_type" label="类型" width="100" />
        <el-table-column prop="rating" label="评分" width="80" />
        <el-table-column prop="category" label="分类" width="160" />
        <el-table-column prop="comment" label="评论" min-width="240" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: grid; gap: 16px; }
.hero { display: flex; justify-content: space-between; align-items: center; }
.hero h2 { margin: 0; color: #1b3a5c; }
.hero p { margin: 6px 0 0; color: #64748b; }
</style>

