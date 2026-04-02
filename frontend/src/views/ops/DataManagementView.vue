<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();

const modules = [
  {
    title: "Agent 管理",
    description: "创建和管理业务 Agent，配置工作流绑定与启停状态",
    icon: "Monitor",
    route: "governance-agents",
    color: "#409eff",
  },
  {
    title: "Prompt 管理",
    description: "管理 Prompt 模板与版本，支持多版本对比和发布",
    icon: "EditPen",
    route: "governance-prompts",
    color: "#67c23a",
  },
  {
    title: "意图路由配置",
    description: "配置用户意图到 Agent 的路由映射规则",
    icon: "Guide",
    route: "governance-intent-routes",
    color: "#e6a23c",
  },
  {
    title: "检测标准",
    description: "维护产品检测标准与缺陷分类规范",
    icon: "DocumentChecked",
    route: "governance-inspection-specs",
    color: "#f56c6c",
  },
];

function navigateTo(routeName: string) {
  router.push({ name: routeName });
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h1>数据管理</h1>
      <p class="subtitle">管理 Agent 运维相关的核心数据资源</p>
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
          <div class="module-icon" :style="{ backgroundColor: item.color + '1a', color: item.color }">
            <el-icon :size="28"><component :is="item.icon" /></el-icon>
          </div>
          <div class="module-info">
            <h3>{{ item.title }}</h3>
            <p>{{ item.description }}</p>
          </div>
        </div>
        <div class="module-arrow">
          <el-icon :size="16" color="#c0c4cc"><ArrowRight /></el-icon>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100%;
}
.page-header {
  margin-bottom: 24px;
}
.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
}
.subtitle {
  color: #909399;
  margin: 0;
}
.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}
.module-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.module-card:hover {
  transform: translateY(-2px);
}
.module-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
}
.module-card-body {
  display: flex;
  align-items: center;
  gap: 16px;
}
.module-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.module-info h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 4px 0;
  color: #303133;
}
.module-info p {
  font-size: 13px;
  color: #909399;
  margin: 0;
  line-height: 1.5;
}
.module-arrow {
  flex-shrink: 0;
}
</style>
