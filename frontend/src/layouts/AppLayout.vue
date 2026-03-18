<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">PIAP</div>
      <nav class="nav">
        <RouterLink to="/" class="nav-link">仪表盘</RouterLink>
        <RouterLink to="/tasks" class="nav-link">任务列表</RouterLink>
        <RouterLink to="/alerts" class="nav-link">预警中心</RouterLink>
        <RouterLink to="/analytics" class="nav-link">分析中心</RouterLink>
        <RouterLink to="/users" class="nav-link">用户管理</RouterLink>
      </nav>
    </aside>
    <div class="content">
      <header class="topbar">
        <div class="title">PIAP 控制台</div>
        <button class="ghost" @click="logout">退出</button>
      </header>
      <main class="page">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";

const router = useRouter();
const auth = useAuthStore();

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
