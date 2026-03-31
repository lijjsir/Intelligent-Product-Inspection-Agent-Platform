<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">PIAP</div>
      <nav class="nav">
        <template v-if="canApp">
          <div class="nav-group">应用工作台</div>
          <RouterLink to="/app/dashboard" class="nav-link" exact-active-class="router-link-active">仪表盘</RouterLink>
          <RouterLink to="/app/tasks" class="nav-link">任务列表</RouterLink>
          <RouterLink to="/app/alerts" class="nav-link">预警中心</RouterLink>
          <RouterLink to="/app/analytics" class="nav-link">分析中心</RouterLink>
          <RouterLink v-if="canUserAdmin" to="/app/users" class="nav-link">用户管理</RouterLink>
        </template>
        <template v-if="canOps">
          <div class="nav-group">运维工作台</div>
          <RouterLink to="/ops/runtime" class="nav-link">运行中心</RouterLink>
        </template>
        <template v-if="canGovernance">
          <div class="nav-group">治理工作台</div>
          <RouterLink to="/governance/admin/inspection-specs" class="nav-link">检测标准</RouterLink>
          <RouterLink to="/governance/admin/models" class="nav-link">模型配置</RouterLink>
          <RouterLink to="/governance/admin/billing" class="nav-link">Token 成本</RouterLink>
          <RouterLink to="/governance/admin/gpu" class="nav-link">GPU 监控</RouterLink>
          <RouterLink to="/governance/quality/report" class="nav-link">质量报告</RouterLink>
          <RouterLink to="/governance/quality/tracing" class="nav-link">质量追踪</RouterLink>
          <RouterLink to="/governance/quality/feedbacks" class="nav-link">反馈流水</RouterLink>
        </template>
      </nav>
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
import { useRouter } from "vue-router";
import { computed, onMounted } from "vue";
import { useAuthStore } from "@/stores/auth.store";
import { useUserStore } from "@/stores/user.store";
import {
  ROLE_ADMIN,
  WORKSPACE_GOVERNANCE,
  WORKSPACE_OPS,
  WORKSPACE_APP,
  normalizeRole,
} from "@/constants/roles";

const router = useRouter();
const auth = useAuthStore();
const userStore = useUserStore();
const currentRoles = computed(() => (auth.roles.length ? auth.roles : [auth.role]));
const normalizedRoles = computed(() => currentRoles.value.map(normalizeRole));
const canApp = computed(() => auth.isAuthed);
const canOps = computed(() => auth.workspaces.includes(WORKSPACE_OPS));
const canGovernance = computed(() => auth.workspaces.includes(WORKSPACE_GOVERNANCE));
const canUserAdmin = computed(() => normalizedRoles.value.includes(ROLE_ADMIN));
const profileName = computed(() => userStore.current?.username || auth.userId || "当前用户");

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
  min-height: 100vh;
  display: grid;
  grid-template-columns: 240px 1fr;
  background: #eef2f6;
}

.sidebar {
  background: #0f2235;
  color: #e2e8f0;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-group {
  margin-top: 12px;
  padding: 8px 12px 4px;
  color: #7dd3fc;
  font-size: 12px;
  letter-spacing: 0.08em;
}

.nav-link {
  color: inherit;
  padding: 10px 12px;
  border-radius: 10px;
  transition: background 0.2s ease, color 0.2s ease;
}

.nav-link.router-link-active {
  background: rgba(37, 99, 168, 0.4);
  color: #fff;
}

.content {
  display: flex;
  flex-direction: column;
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
}

.title {
  font-weight: 600;
  color: #1b3a5c;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.workspace-chip {
  margin-left: auto;
  margin-right: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #075985;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.profile-link {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  color: #1b3a5c;
  line-height: 1.2;
}

.profile-name {
  font-size: 13px;
  font-weight: 600;
}

.profile-role {
  font-size: 12px;
  color: #64748b;
}

.page {
  padding: 24px;
}

.ghost {
  border: 1px solid #cbd5f5;
  background: transparent;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
}

@media (max-width: 960px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .sidebar {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .nav {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
