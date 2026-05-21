<template>
  <div class="flex h-screen overflow-hidden bg-zinc-50">
    <aside v-if="showSidebar" class="flex h-screen w-56 shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div class="border-b border-zinc-100 px-5 py-5">
        <div class="text-[2rem] font-bold tracking-[0.08em] text-zinc-950">PIAP</div>
        <div class="mt-1 text-[11px] tracking-[0.2em] text-zinc-400">智能检测平台</div>
      </div>

      <nav class="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-4">
        <template v-for="entry in menu" :key="entry.title">
          <el-collapse
            v-if="isMenuGroup(entry)"
            v-model="activeNames"
            class="nav-collapse"
            @change="handleGroupCollapseChange(entry, $event)"
          >
            <el-collapse-item :name="entry.title">
              <template #title>
                <div class="nav-link nav-group-link w-full">
                  <el-icon v-if="entry.icon" class="text-[15px] text-zinc-400">
                    <component :is="iconMap[entry.icon || '']" />
                  </el-icon>
                  <span>{{ entry.title }}</span>
                </div>
              </template>
              <div class="flex flex-col gap-1 pl-2">
                <template v-for="item in entry.items" :key="item.path">
                  <RouterLink
                    v-if="!item.placeholder"
                    :to="item.path"
                    class="nav-link"
                    active-class="nav-link-active"
                  >
                    <span>{{ item.title }}</span>
                  </RouterLink>
                  <span v-else class="nav-link cursor-not-allowed text-zinc-400">
                    <span>{{ item.title }}</span>
                    <span class="ml-1 text-[11px] text-zinc-300">开发中</span>
                  </span>
                </template>
              </div>
            </el-collapse-item>
          </el-collapse>

          <template v-else>
            <RouterLink
              v-if="!entry.placeholder"
              :to="entry.path"
              class="nav-link"
              active-class="nav-link-active"
            >
              <span>{{ entry.title }}</span>
            </RouterLink>
            <span v-else class="nav-link cursor-not-allowed text-zinc-400">
              <span>{{ entry.title }}</span>
              <span class="ml-1 text-[11px] text-zinc-300">开发中</span>
            </span>
          </template>
        </template>
      </nav>
    </aside>

    <div class="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
      <header
        class="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-5"
      >
        <div class="flex min-w-0 flex-wrap items-center gap-4">
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
            <el-button size="small" type="danger" plain @click="deleteChatSession">删除会话</el-button>
            <el-tag size="small" type="info" effect="plain">会话数：{{ chatStore.sessions.length }}</el-tag>
          </template>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-3">
          <span
            class="rounded-full bg-zinc-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-600"
          >
            {{ workspaceLabel }}
          </span>
          <RouterLink
            to="/app/profile"
            class="flex flex-col items-end leading-tight text-zinc-700 transition-colors hover:text-zinc-900"
          >
            <span class="text-[13px] font-medium">{{ profileName }}</span>
            <span class="text-[11px] text-zinc-400">{{ roleLabel }}</span>
          </RouterLink>
          <button class="ghost-btn" @click="logout">退出登录</button>
        </div>
      </header>

      <main class="flex-1 overflow-x-hidden overflow-y-auto p-4">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Management, Monitor, Setting } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth.store";
import { useChatStore } from "@/stores/chat.store";
import { useUserStore } from "@/stores/user.store";
import {
  ROLE_ADMIN,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_APP_DEVELOPER,
  ROLE_EXPERT,
  ROLE_USER,
} from "@/constants/roles";
import { isMenuGroup, resolveMenuGroupLandingPath, useMenu, type MenuGroup } from "@/composables/useMenu";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const userStore = useUserStore();
const chatStore = useChatStore();

const { menu, primaryRole } = useMenu();

const showSidebar = computed(() => auth.isAuthed && menu.value.length > 0);

const activeNames = ref<string[]>([]);
const chatInitialized = ref(false);

const iconMap: Record<string, unknown> = {
  Monitor,
  Setting,
  Management,
  View: Monitor,
};

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

const workspaceLabel = computed(() => {
  switch (auth.defaultWorkspace) {
    case "app":
      return "应用";
    case "ops":
      return "运维";
    case "governance":
      return "治理";
    default:
      return auth.defaultWorkspace || "工作台";
  }
});

const roleLabel = computed(() => {
  switch (primaryRole.value) {
    case ROLE_ADMIN:
      return "系统管理员";
    case ROLE_APP_DEVELOPER:
      return "应用开发者";
    case ROLE_ALGORITHM_ENGINEER:
      return "算法工程师";
    case ROLE_EXPERT:
      return "终端用户-专业";
    case ROLE_USER:
      return "终端用户-标准";
    default:
      return auth.role || "未识别角色";
  }
});

const sessionOptions = computed(() => {
  const rows = [...chatStore.sessions];
  rows.sort((a, b) => {
    const ta = new Date(a.updated_at || a.last_message_at || a.created_at || 0).getTime();
    const tb = new Date(b.updated_at || b.last_message_at || b.created_at || 0).getTime();
    return tb - ta;
  });
  return rows;
});

function formatTime(ts?: string | null) {
  if (!ts) return "-";
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(ts) ? ts : `${ts}Z`;
  const dt = new Date(normalized);
  if (Number.isNaN(dt.getTime())) return ts;
  return dt.toLocaleString("zh-CN", { hour12: false });
}

function sessionLabel(sessionId: string) {
  const found = chatStore.sessions.find((item) => item.id === sessionId);
  if (!found) return sessionId;
  const title = found.title || `会话-${found.id.slice(-6)}`;
  const ts = found.last_message_at || found.updated_at || found.created_at;
  return `${title} · ${formatTime(ts)}`;
}

function normalizeActiveNames(value: string | string[]) {
  return Array.isArray(value) ? value : [value].filter(Boolean);
}

function handleGroupCollapseChange(group: MenuGroup, value: string | string[]) {
  const nextNames = normalizeActiveNames(value);
  const landingPath = resolveMenuGroupLandingPath(group);
  if (nextNames.includes(group.title) && landingPath && route.path !== landingPath) {
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
    await chatStore.createNewSession("新会话");
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

onMounted(() => {
  if (auth.isAuthed && !userStore.current) {
    userStore.fetchCurrentUser().catch(() => undefined);
  }
});

function logout() {
  chatStore.stopStream();
  auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.nav-link,
.nav-sublink {
  @apply flex items-center gap-2 rounded-xl px-3 py-2 text-[14px] text-zinc-600 transition-colors duration-150;
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

.ghost-btn {
  @apply cursor-pointer rounded-lg border border-zinc-200 bg-transparent px-3 py-1.5 text-[13px] text-zinc-500 transition-all duration-150;
}

.ghost-btn:hover {
  @apply border-zinc-300 bg-zinc-50 text-zinc-700;
}

.nav-collapse {
  background: transparent;
  border: none;
}

.nav-collapse :deep(.el-collapse-item__header) {
  @apply h-auto border-none bg-transparent px-0 leading-normal;
}

.nav-collapse :deep(.el-collapse-item__header.is-active) {
  @apply text-zinc-900;
}

.nav-collapse :deep(.el-collapse-item__arrow) {
  @apply mr-2 text-zinc-400;
}

.nav-collapse :deep(.el-collapse-item__wrap) {
  @apply border-none bg-transparent;
}

.nav-collapse :deep(.el-collapse-item__content) {
  @apply p-0 pb-1;
}

.nav-group-link {
  @apply my-0;
}
</style>
