<script setup lang="ts">
import { useRouter } from "vue-router";
import {
  ArrowRight,
  DocumentChecked,
  EditPen,
  Guide,
  Monitor,
} from "@element-plus/icons-vue";

const router = useRouter();

const modules = [
  {
    title: "Agent 管理",
    description: "自动发现当前 LangGraph Agent，查看运行状态、拓扑结构和路由控制能力。",
    icon: Monitor,
    route: "governance-agents",
    color: "#2563eb",
  },
  {
    title: "Prompt 管理",
    description: "集中管理各 Agent 与流程阶段的提示词，支持代码默认、数据库版本、差异对比与回滚。",
    icon: EditPen,
    route: "governance-prompts",
    color: "#0f766e",
  },
  {
    title: "路由策略",
    description: "查看请求如何从入口被识别、分流到目标 Agent，并核对规则优先级和命中路径。",
    icon: Guide,
    route: "governance-intent-routes",
    color: "#d97706",
  },
  {
    title: "检测标准",
    description: "维护检测标准、缺陷分类和质量阈值，作为 RAG 与判定流程的业务基线。",
    icon: DocumentChecked,
    route: "governance-inspection-specs",
    color: "#dc2626",
  },
];

function navigateTo(routeName: string) {
  router.push({ name: routeName });
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="page-header">
      <h1>治理工作台</h1>
      <p class="mt-2 text-sm text-zinc-500">
        围绕 Agent、Prompt、路由策略和检测标准的统一治理入口。
      </p>
    </div>

    <div class="module-grid">
      <el-card
        v-for="item in modules"
        :key="item.route"
        class="module-card"
        shadow="hover"
        @click="navigateTo(item.route)"
      >
        <div class="module-card-body">
          <div
            class="module-icon"
            :style="{ backgroundColor: `${item.color}18`, color: item.color }"
          >
            <el-icon :size="28"><component :is="item.icon" /></el-icon>
          </div>
          <div class="module-info">
            <h3>{{ item.title }}</h3>
            <p>{{ item.description }}</p>
          </div>
        </div>
        <div class="module-arrow">
          <el-icon :size="16" color="#94a3b8"><ArrowRight /></el-icon>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 26px;
  color: #0f172a;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.module-card {
  cursor: pointer;
  border-radius: 20px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.module-card:hover {
  transform: translateY(-2px);
}

.module-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22px 24px;
}

.module-card-body {
  display: flex;
  align-items: center;
  gap: 16px;
}

.module-icon {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.module-info h3 {
  margin: 0 0 6px;
  font-size: 17px;
  color: #0f172a;
}

.module-info p {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
}
</style>
