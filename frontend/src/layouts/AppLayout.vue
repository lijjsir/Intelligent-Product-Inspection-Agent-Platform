<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">PIAP</div>
      <nav class="nav">
        <!-- 应用工作台 -->
        <el-collapse v-if="canApp" v-model="activeNames" class="nav-collapse">
          <el-collapse-item name="app">
            <template #title>
              <div class="collapse-title">
                <el-icon><Monitor /></el-icon>
                <span>应用工作台</span>
              </div>
            </template>
            <div class="nav-items">
              <RouterLink to="/app/dashboard" class="nav-link" exact-active-class="router-link-active">
                <el-icon><DataLine /></el-icon>
                <span>仪表盘</span>
              </RouterLink>
              <RouterLink to="/app/tasks" class="nav-link">
                <el-icon><List /></el-icon>
                <span>任务管理</span>
              </RouterLink>
              <RouterLink to="/app/stability" class="nav-link">
                <el-icon><Bell /></el-icon>
                <span>稳定性工作台</span>
              </RouterLink>
              <RouterLink to="/app/feedbacks" class="nav-link">
                <el-icon><ChatLineRound /></el-icon>
                <span>反馈流水</span>
              </RouterLink>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 运维工作台 -->
        <el-collapse v-if="canOps" v-model="activeNames" class="nav-collapse">
          <el-collapse-item name="ops">
            <template #title>
              <div class="collapse-title">
                <el-icon><Setting /></el-icon>
                <span>运维工作台</span>
              </div>
            </template>
            <div class="nav-items">
              <RouterLink to="/ops/runtime" class="nav-link">
                <el-icon><VideoPlay /></el-icon>
                <span>Agent 运行中心</span>
              </RouterLink>
              <RouterLink to="/ops/rag-analysis" class="nav-link">
                <el-icon><DataAnalysis /></el-icon>
                <span>RAG 召回分析</span>
              </RouterLink>
              <RouterLink to="/ops/analytics" class="nav-link">
                <el-icon><TrendCharts /></el-icon>
                <span>分析中心</span>
              </RouterLink>
              <RouterLink to="/ops/billing" class="nav-link">
                <el-icon><Wallet /></el-icon>
                <span>Token 成本</span>
              </RouterLink>
              <RouterLink to="/ops/gpu" class="nav-link">
                <el-icon><Histogram /></el-icon>
                <span>GPU 监控</span>
              </RouterLink>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 治理工作台 -->
        <el-collapse v-if="canGovernance" v-model="activeNames" class="nav-collapse">
          <el-collapse-item name="governance">
            <template #title>
              <div class="collapse-title">
                <el-icon><Management /></el-icon>
                <span>治理工作台</span>
              </div>
            </template>
            <div class="nav-items">
              <RouterLink to="/governance/admin/models" class="nav-link">
                <el-icon><Cpu /></el-icon>
                <span>模型配置</span>
              </RouterLink>
              <RouterLink to="/governance/data-management" class="nav-link">
                <el-icon><DataAnalysis /></el-icon>
                <span>数据管理</span>
              </RouterLink>
            </div>
          </el-collapse-item>
        </el-collapse>
      </nav>
      <div v-if="canUserAdmin" class="sidebar-bottom">
        <div class="sidebar-bottom-title">系统管理</div>
        <RouterLink to="/users" class="nav-link fixed-nav-link" exact-active-class="router-link-active">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </RouterLink>
      </div>
    </aside>
    <div class="content">
      <header class="topbar">
        <div class="title">PIAP 控制台</div>
        <div class="topbar-actions">
          <div class="workspace-chip">{{ auth.defaultWorkspace }}</div>
          <RouterLink to="/app/profile" class="profile-link">
            <span class="profile-name">{{ profileName }}</span>
            <span class="profile-role">{{ auth.role || "未识别角色" }}</span>
          </RouterLink>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </header>
      <main class="page">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { useUserStore } from "@/stores/user.store";
import {
  Monitor,
  DataLine,
  List,
  Bell,
  TrendCharts,
  User,
  Setting,
  VideoPlay,
  ChatLineRound,
  DataAnalysis,
  Management,
  Cpu,
  Wallet,
  Histogram,
} from "@element-plus/icons-vue";
import {
  ROLE_ADMIN,
  WORKSPACE_GOVERNANCE,
  WORKSPACE_OPS,
  WORKSPACE_APP,
  normalizeRole,
} from "@/constants/roles";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const userStore = useUserStore();

const currentRoles = computed(() => (auth.roles.length ? auth.roles : [auth.role]));
const normalizedRoles = computed(() => currentRoles.value.map(normalizeRole));
const canApp = computed(() => auth.isAuthed);
const canOps = computed(() => auth.workspaces.includes(WORKSPACE_OPS));
const canGovernance = computed(() => auth.workspaces.includes(WORKSPACE_GOVERNANCE));
const canUserAdmin = computed(() => normalizedRoles.value.includes(ROLE_ADMIN));
const profileName = computed(() => userStore.current?.username || auth.userId || "当前用户");

// 根据当前路由自动展开对应的折叠面板
const activeNames = ref<string[]>([]);

function updateActiveNames() {
  const path = route.path;
  const names: string[] = [];
  if (path.startsWith("/app")) names.push("app");
  if (path.startsWith("/ops")) names.push("ops");
  if (path.startsWith("/governance")) names.push("governance");
  activeNames.value = names;
}

// 监听路由变化
watch(() => route.path, updateActiveNames, { immediate: true });

onMounted(() => {
  if (auth.isAuthed) {
    userStore.fetchCurrentUser().catch(() => undefined);
  }
});

const logout = () => {
  auth.logout();
  router.push("/login");
};
</script>

<style scoped>
.layout {
  height: 100vh;
  display: grid;
  grid-template-columns: 220px 1fr;
  background: #eef2f6;
  overflow: hidden;
}

.sidebar {
  background: #0f2235;
  color: #e2e8f0;
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
}

.sidebar::-webkit-scrollbar {
  width: 4px;
}

.sidebar::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
}

.sidebar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}

.logo {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 0 8px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.sidebar-bottom {
  margin-top: auto;
  padding: 12px 8px 0;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
}

.sidebar-bottom-title {
  margin-bottom: 8px;
  color: #7dd3fc;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

/* 折叠面板样式 */
.nav-collapse {
  background: transparent;
  border: none;
}

.nav-collapse :deep(.el-collapse-item__header) {
  background: transparent;
  border: none;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  padding: 0 8px;
  height: 40px;
}

.nav-collapse :deep(.el-collapse-item__header.is-active) {
  color: #7dd3fc;
}

.nav-collapse :deep(.el-collapse-item__arrow) {
  color: #7dd3fc;
}

.nav-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border: none;
}

.nav-collapse :deep(.el-collapse-item__content) {
  padding: 0;
  color: inherit;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-title .el-icon {
  font-size: 16px;
}

.nav-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 8px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  transition: all 0.2s ease;
  text-decoration: none;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.nav-link.router-link-active {
  background: rgba(37, 99, 168, 0.5);
  color: #fff;
}

.nav-link .el-icon {
  font-size: 15px;
  flex-shrink: 0;
}

.fixed-nav-link {
  background: rgba(255, 255, 255, 0.04);
}

.content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.topbar {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.title {
  font-weight: 600;
  color: #1b3a5c;
  font-size: 16px;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.workspace-chip {
  padding: 4px 10px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #075985;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 500;
}

.profile-link {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  text-decoration: none;
  color: inherit;
  line-height: 1.3;
}

.profile-name {
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
}

.profile-role {
  font-size: 11px;
  color: #64748b;
}

.ghost {
  background: transparent;
  border: 1px solid #cbd5e1;
  color: #64748b;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ghost:hover {
  border-color: #94a3b8;
  color: #475569;
  background: #f8fafc;
}

.page {
  flex: 1;
  overflow: auto;
  padding: 20px;
}
</style>
