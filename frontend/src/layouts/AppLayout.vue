<template>
  <div class="app-shell flex h-screen overflow-hidden bg-zinc-50">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside
      v-if="showSidebar"
      class="app-sidebar flex h-screen w-56 shrink-0 flex-col border-r border-zinc-200 bg-white"
      :class="{ 'mobile-nav-open': mobileNavOpen }"
    >
      <div class="app-brand border-b border-zinc-100 px-5 py-5">
        <div class="flex items-center gap-3">
          <div class="brand-mark" aria-label="PIAP 智能检测平台图标">
            <img src="/piap-icon.svg?v=2" alt="" width="40" height="40" />
          </div>
          <div class="text-[1.75rem] font-bold tracking-[0.08em] text-zinc-950">PIAP</div>
        </div>
        <div class="mt-1 text-[11px] tracking-[0.2em] text-zinc-400">智能检测平台</div>
      </div>

      <nav class="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-4">
        <template v-for="entry in menu" :key="entry.title">
          <div v-if="isMenuGroup(entry)" class="nav-group">
            <button
              type="button"
              class="nav-link nav-group-link w-full"
              :aria-expanded="navigation.expandedGroups.includes(entry.title)"
              :aria-controls="`nav-group-${entry.title}`"
              @click="toggleMenuGroup(entry)"
            >
              <span>{{ entry.title }}</span>
              <ArrowRight
                class="nav-group-arrow"
                :class="{ 'is-expanded': navigation.expandedGroups.includes(entry.title) }"
              />
            </button>
            <div
              v-show="navigation.expandedGroups.includes(entry.title)"
              :id="`nav-group-${entry.title}`"
              class="flex flex-col gap-1 pb-1 pl-2"
            >
              <template v-for="item in entry.items" :key="item.path">
                <RouterLink
                  v-if="!item.placeholder"
                  :to="item.path"
                  :class="['nav-link', { 'nav-link-active': isMenuItemActive(item) }]"
                >
                  <span>{{ item.title }}</span>
                  <span
                    v-if="item.path === '/app/collab' && collabStore.pendingWorkItemCount > 0"
                    class="nav-count-badge"
                    :aria-label="`${collabStore.pendingWorkItemCount} 项待我处理`"
                  >
                    {{
                      collabStore.pendingWorkItemCount > 99
                        ? "99+"
                        : collabStore.pendingWorkItemCount
                    }}
                  </span>
                </RouterLink>
                <span v-else class="nav-link cursor-not-allowed text-zinc-400">
                  <span>{{ item.title }}</span>
                  <span class="ml-1 text-[11px] text-zinc-300">开发中</span>
                </span>
              </template>
            </div>
          </div>

          <template v-else>
            <RouterLink
              v-if="!entry.placeholder"
              :to="entry.path"
              :class="['nav-link', { 'nav-link-active': isMenuItemActive(entry) }]"
            >
              <span>{{ entry.title }}</span>
              <span
                v-if="entry.path === '/app/collab' && collabStore.pendingWorkItemCount > 0"
                class="nav-count-badge"
                :aria-label="`${collabStore.pendingWorkItemCount} 项待我处理`"
              >
                {{
                  collabStore.pendingWorkItemCount > 99 ? "99+" : collabStore.pendingWorkItemCount
                }}
              </span>
            </RouterLink>
            <span v-else class="nav-link cursor-not-allowed text-zinc-400">
              <span>{{ entry.title }}</span>
              <span class="ml-1 text-[11px] text-zinc-300">开发中</span>
            </span>
          </template>
        </template>
      </nav>
    </aside>

    <button
      v-if="showSidebar && mobileNavOpen"
      type="button"
      class="mobile-nav-backdrop"
      aria-label="关闭导航"
      @click="mobileNavOpen = false"
    />

    <div class="app-content flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
      <header
        class="app-header flex h-12 shrink-0 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-5"
      >
        <div class="flex min-w-0 flex-wrap items-center gap-4">
          <button
            v-if="showSidebar"
            type="button"
            class="mobile-menu-button"
            :aria-expanded="mobileNavOpen"
            :aria-label="mobileNavOpen ? '关闭导航' : '打开导航'"
            @click="mobileNavOpen = !mobileNavOpen"
          >
            <Menu />
          </button>
          <span class="whitespace-nowrap text-sm font-semibold text-zinc-900">PIAP 控制台</span>

          <template v-if="showChatControls">
            <el-select
              :model-value="chatStore.session?.id || ''"
              class="!w-[260px]"
              filterable
              size="small"
              placeholder="选择会话"
              @change="handleChatSessionChange"
            >
              <el-option
                v-for="item in sessionOptions"
                :key="item.id"
                :label="sessionLabel(item.id)"
                :value="item.id"
              />
            </el-select>
            <el-button size="small" @click="createChatSession">新建会话</el-button>
            <el-button size="small" type="danger" plain @click="deleteChatSession"
              >删除会话</el-button
            >
            <el-tag size="small" type="info" effect="plain"
              >会话数：{{ chatStore.sessions.length }}</el-tag
            >
          </template>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-3">
          <span
            class="topbar-workspace rounded-full bg-zinc-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-600"
          >
            {{ workspaceLabel }}
          </span>
          <RouterLink
            to="/app/profile"
            class="flex flex-col items-end leading-tight text-zinc-700 transition-colors hover:text-zinc-900"
          >
            <span class="text-[13px] font-medium">{{ profileName }}</span>
            <span class="profile-role text-[11px] text-zinc-400">{{ roleLabel }}</span>
          </RouterLink>
          <button class="ghost-btn" @click="logout">退出登录</button>
        </div>
      </header>

      <main
        id="main-content"
        class="app-main flex-1 overflow-x-hidden overflow-y-auto p-4"
        tabindex="-1"
      >
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { ArrowRight, Menu } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth.store";
import { useChatStore } from "@/stores/chat.store";
import { useCollabStore } from "@/stores/collab.store";
import { useUserStore } from "@/stores/user.store";
import { useNavigationStore } from "@/stores/navigation.store";
import {
  ROLE_ADMIN,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_EXPERT,
  ROLE_USER,
} from "@/constants/roles";
import {
  isMenuGroup,
  resolveMenuGroupLandingPath,
  useMenu,
  type MenuGroup,
  type MenuItem,
} from "@/composables/useMenu";
import type { ChatSession } from "@/types/chat.types";
import { formatServerDateTime, parseServerDateTime } from "@/utils/date-time";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const userStore = useUserStore();
const chatStore = useChatStore();
const collabStore = useCollabStore();
const navigation = useNavigationStore();

const { menu, primaryRole } = useMenu();

const showSidebar = computed(() => auth.isAuthed && menu.value.length > 0);

const chatInitialized = ref(false);
const mobileNavOpen = ref(false);

const canChat = computed(() => {
  const role = primaryRole.value;
  return role === ROLE_USER || role === ROLE_EXPERT;
});

const showChatControls = computed(
  () => auth.isAuthed && canChat.value && route.path.startsWith("/app/chat"),
);

const profileName = computed(
  () => userStore.current?.username || auth.username || auth.userId || "当前用户",
);

const workspaceLabel = "PIAP";

const roleLabel = computed(() => {
  switch (primaryRole.value) {
    case ROLE_ADMIN:
      return "系统管理员";
    case ROLE_APP_DEVELOPER:
      return "应用开发者";
    case ROLE_PLATFORM_OPERATOR:
      return "平台运营";
    case ROLE_ALGORITHM_ENGINEER:
      return "算法工程师";
    case ROLE_EXPERT:
      return "专家";
    case ROLE_USER:
      return "普通用户";
    default:
      return auth.role || "未识别角色";
  }
});

const sessionOptions = computed(() => {
  const rows = [...chatStore.sessions];
  rows.sort((a, b) => {
    const ta =
      parseServerDateTime(a.updated_at || a.last_message_at || a.created_at)?.getTime() ?? 0;
    const tb =
      parseServerDateTime(b.updated_at || b.last_message_at || b.created_at)?.getTime() ?? 0;
    return tb - ta;
  });
  return rows;
});

const AUTO_SESSION_TITLE_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

function sessionDisplayLabel(item: ChatSession) {
  const rawTitle = String(item.title || "").trim();
  if (rawTitle && !AUTO_SESSION_TITLE_RE.test(rawTitle)) return rawTitle;
  return (
    formatServerDateTime(item.created_at || item.last_message_at || item.updated_at) ||
    rawTitle ||
    "无"
  );
}

function sessionLabel(sessionId: string) {
  const found = chatStore.sessions.find((item) => item.id === sessionId);
  if (!found) {
    if (chatStore.session?.id === sessionId) return sessionDisplayLabel(chatStore.session);
    return sessionId;
  }
  return sessionDisplayLabel(found);
}

function isPathActive(targetPath: string) {
  return route.path === targetPath || route.path.startsWith(`${targetPath}/`);
}

function isMenuItemActive(item: MenuItem) {
  const matchPaths = [item.path, ...(item.activeMatchPaths || [])];
  return matchPaths.some((path) => isPathActive(path));
}

function syncActiveMenuGroups() {
  const matchingGroups = menu.value
    .filter((entry): entry is MenuGroup => isMenuGroup(entry))
    .filter((group) => group.items.some((item) => isMenuItemActive(item)))
    .map((group) => group.title);
  navigation.revealGroups(matchingGroups);
}

function toggleMenuGroup(group: MenuGroup) {
  const expanded = navigation.toggleGroup(group.title);
  const landingPath = resolveMenuGroupLandingPath(group);
  if (expanded && landingPath && !group.items.some(isMenuItemActive)) {
    router.push(landingPath);
  }
}

async function ensureChatTopbarState() {
  if (!showChatControls.value || !canChat.value || !auth.isAuthed) return;

  if (chatInitialized.value) {
    if (!chatStore.session && chatStore.sessions.length > 0) {
      await chatStore.selectSession(chatStore.sessions[0].id);
    }
    return;
  }

  await chatStore.initForChatPage();
  chatInitialized.value = true;
}

async function handleChatSessionChange(sessionId: string) {
  if (!sessionId || chatStore.session?.id === sessionId) return;
  try {
    await chatStore.selectSession(sessionId);
  } catch (error) {
    ElMessage.error("切换会话失败，请稍后重试。");
    console.error(error);
  }
}

async function createChatSession() {
  try {
    await chatStore.createNewSession();
  } catch (error) {
    ElMessage.error("新建会话失败，请稍后重试。");
    console.error(error);
  }
}

async function deleteChatSession() {
  if (!chatStore.session?.id) return;
  try {
    await chatStore.deleteSession(chatStore.session.id);
  } catch (error) {
    ElMessage.error("删除会话失败，请稍后重试。");
    console.error(error);
  }
}

watch(
  () => route.path,
  () => {
    mobileNavOpen.value = false;
    syncActiveMenuGroups();
    if (!showChatControls.value) {
      chatStore.stopStream();
      return;
    }

    ensureChatTopbarState().catch((error) => {
      console.error(error);
    });
  },
  { immediate: true },
);

watch(
  menu,
  () => {
    syncActiveMenuGroups();
  },
  { immediate: true },
);

onMounted(() => {
  if (auth.isAuthed && !userStore.current) {
    userStore.fetchCurrentUser().catch(() => undefined);
  }
  if (auth.isAuthed) {
    void collabStore.loadSummary();
    collabStore.connectStream();
  }
});

function logout() {
  chatStore.stopStream();
  collabStore.disconnectStream();
  auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.skip-link {
  position: fixed;
  z-index: 1000;
  top: 8px;
  left: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #0f172a;
  color: #fff;
  font-size: 13px;
  font-weight: 650;
  transform: translateY(-160%);
  transition: transform 150ms ease;
}

.skip-link:focus {
  transform: translateY(0);
}

.nav-link,
.nav-sublink {
  @apply flex items-center gap-2 rounded-xl px-3 py-2 text-[14px] text-zinc-600 transition-colors duration-150;
}

.brand-mark {
  width: 40px;
  height: 40px;
  flex: none;
  overflow: hidden;
  border-radius: 10px;
  background: #18181b;
}

.brand-mark img {
  display: block;
  width: 100%;
  height: 100%;
}

.mobile-menu-button,
.mobile-nav-backdrop {
  display: none;
}

.mobile-menu-button {
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid #e4e4e7;
  border-radius: 7px;
  background: #fff;
  color: #27272a;
  cursor: pointer;
}

.mobile-menu-button svg {
  width: 17px;
  height: 17px;
}

.nav-link:hover,
.nav-sublink:hover {
  @apply bg-zinc-100 text-zinc-900;
}

.nav-link-active {
  @apply bg-zinc-900 text-white;
}

.nav-link-active:hover {
  @apply bg-zinc-800 text-white;
}

.nav-count-badge {
  margin-left: auto;
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  border-radius: 999px;
  background: #18181b;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}

.nav-link-active .nav-count-badge {
  background: #fff;
  color: #18181b;
}

.ghost-btn {
  @apply cursor-pointer rounded-lg border border-zinc-200 bg-transparent px-3 py-1.5 text-[13px] text-zinc-500 transition-all duration-150;
}

.ghost-btn:hover {
  @apply border-zinc-300 bg-zinc-50 text-zinc-700;
}

.nav-group-link {
  @apply my-0 cursor-pointer border-0 bg-transparent text-left;
  font: inherit;
  font-size: 14px;
}

.nav-group-link:focus-visible {
  outline: 2px solid #a1a1aa;
  outline-offset: -2px;
}

.nav-group-arrow {
  width: 14px;
  height: 14px;
  margin-left: auto;
  flex: none;
  color: #a1a1aa;
  transition: transform 150ms ease;
}

.nav-group-arrow.is-expanded {
  transform: rotate(90deg);
}

@media (max-width: 700px) {
  .app-sidebar {
    position: fixed;
    z-index: 50;
    inset: 48px auto 0 0;
    height: calc(100vh - 48px);
    width: min(84vw, 300px);
    max-width: 300px;
    transform: translateX(-100%);
    transition: transform 180ms ease;
    box-shadow: 12px 0 32px rgba(24, 24, 27, 0.16);
  }

  .app-sidebar.mobile-nav-open {
    transform: translateX(0);
  }

  .mobile-nav-backdrop {
    position: fixed;
    z-index: 40;
    inset: 48px 0 0;
    display: block;
    border: 0;
    background: rgba(24, 24, 27, 0.35);
    cursor: pointer;
  }

  .mobile-menu-button {
    display: inline-grid;
  }

  .app-header {
    position: relative;
    z-index: 60;
    height: auto;
    min-height: 48px;
    gap: 8px;
    padding: 7px 10px;
  }

  .app-header > div {
    gap: 8px;
  }

  .topbar-workspace,
  .profile-role {
    display: none;
  }

  .ghost-btn {
    padding: 5px 8px;
    font-size: 12px;
  }

  .app-main {
    padding: 8px;
  }
}
</style>
