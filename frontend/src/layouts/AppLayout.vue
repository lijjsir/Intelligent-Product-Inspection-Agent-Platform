<template>
  <div class="flex h-screen overflow-hidden bg-zinc-50">
    <!-- Sidebar -->
    <aside class="flex h-screen w-52 shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div class="px-4 py-4">
        <div class="text-lg font-bold tracking-wider text-zinc-900">PIAP</div>
        <div class="text-2xs text-zinc-400 tracking-widest uppercase mt-0.5">智能检测平台</div>
      </div>

      <nav class="flex-1 flex flex-col gap-0.5 px-2 overflow-y-auto">
        <template v-for="entry in menu" :key="entry.title">
          <!-- Workspace group (admin only) -->
          <el-collapse v-if="isMenuGroup(entry) && showWorkspaceGroups" v-model="activeNames" class="nav-collapse">
            <el-collapse-item :name="entry.title">
              <template #title>
                <div class="flex items-center gap-2 px-2 text-[13px] font-medium text-zinc-600">
                  <el-icon class="text-[15px] text-zinc-400"><component :is="iconMap[entry.icon || '']" /></el-icon>
                  <span>{{ entry.title }}</span>
                </div>
              </template>
              <div class="flex flex-col gap-0.5 pl-2">
                <template v-for="item in entry.items" :key="item.path">
                  <RouterLink v-if="!item.placeholder" :to="item.path" class="nav-link" active-class="nav-link-active">
                    <span>{{ item.title }}</span>
                  </RouterLink>
                  <span v-else class="nav-link text-zinc-400 cursor-not-allowed">
                    <span>{{ item.title }}</span>
                    <span class="text-2xs text-zinc-300 ml-1">开发中</span>
                  </span>
                </template>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- Flat menu item (non-admin) -->
          <template v-else-if="isMenuItem(entry) && !isMenuGroup(entry)">
            <RouterLink v-if="!entry.placeholder" :to="entry.path" class="nav-link" active-class="nav-link-active">
              <span>{{ entry.title }}</span>
            </RouterLink>
            <span v-else class="nav-link text-zinc-400 cursor-not-allowed">
              <span>{{ entry.title }}</span>
              <span class="text-2xs text-zinc-300 ml-1">开发中</span>
            </span>
          </template>

          <!-- Flat group items (non-admin sees group items flattened) -->
          <template v-else-if="isMenuGroup(entry) && !showWorkspaceGroups">
            <template v-for="item in entry.items" :key="item.path">
              <RouterLink v-if="!item.placeholder" :to="item.path" class="nav-link" active-class="nav-link-active">
                <span>{{ item.title }}</span>
              </RouterLink>
              <span v-else class="nav-link text-zinc-400 cursor-not-allowed">
                <span>{{ item.title }}</span>
                <span class="text-2xs text-zinc-300 ml-1">开发中</span>
              </span>
            </template>
          </template>
        </template>
      </nav>
    </aside>

    <!-- Main content -->
    <div class="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
      <!-- Topbar -->
      <header class="h-12 flex items-center justify-between px-5 bg-white border-b border-zinc-200 shrink-0 gap-4">
        <div class="flex items-center gap-4 min-w-0 flex-wrap">
          <span class="text-sm font-semibold text-zinc-900 whitespace-nowrap">PIAP 控制台</span>

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

        <div class="flex items-center gap-3 flex-wrap shrink-0">
          <span class="px-2.5 py-0.5 rounded-full bg-zinc-100 text-zinc-600 text-2xs tracking-wider font-semibold uppercase">{{ workspaceLabel }}</span>
          <RouterLink to="/app/profile" class="flex flex-col items-end leading-tight text-zinc-700 hover:text-zinc-900 transition-colors">
            <span class="text-[13px] font-medium">{{ profileName }}</span>
            <span class="text-[11px] text-zinc-400">{{ roleLabel }}</span>
          </RouterLink>
          <button class="ghost-btn" @click="logout">退出登录</button>
        </div>
      </header>

      <!-- Page content -->
      <main class="flex-1 overflow-y-auto overflow-x-hidden p-4">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  Management,
  Monitor,
  Setting,
} from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth.store";
import { useChatStore } from "@/stores/chat.store";
import { useUserStore } from "@/stores/user.store";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
  ROLE_EXPERT,
} from "@/constants/roles";
import { useMenu, type MenuItem, type MenuGroup } from "@/composables/useMenu";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const userStore = useUserStore();
const chatStore = useChatStore();

const { menu, primaryRole, showWorkspaceGroups } = useMenu();

const activeNames = ref<string[]>([]);
const chatInitialized = ref(false);

const isMenuGroup = (entry: MenuItem | MenuGroup): entry is MenuGroup => "items" in entry;
const isMenuItem = (entry: MenuItem | MenuGroup): entry is MenuItem => !("items" in entry);

const iconMap: Record<string, any> = {
  Monitor,
  Setting,
  Management,
};

const canChat = computed(() => {
  const r = primaryRole.value;
  return r === ROLE_USER || r === ROLE_EXPERT;
});

const showChatControls = computed(() => auth.isAuthed && canChat.value && route.path.startsWith("/app/chat"));

const profileName = computed(() => userStore.current?.username || auth.username || auth.userId || "当前用户");

const workspaceLabel = computed(() => {
  switch (auth.defaultWorkspace) {
    case "app": return "应用";
    case "ops": return "运维";
    case "governance": return "治理";
    default: return auth.defaultWorkspace || "工作台";
  }
});

const roleLabel = computed(() => {
  switch (primaryRole.value) {
    case ROLE_ADMIN: return "系统管理员";
    case ROLE_APP_DEVELOPER: return "应用开发者";
    case ROLE_PLATFORM_OPERATOR: return "平台运维员";
    case ROLE_ALGORITHM_ENGINEER: return "算法工程师";
    case ROLE_USER: return "终端用户-标准";
    case ROLE_EXPERT: return "终端用户-专业";
    default: return auth.role || "未识别角色";
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

function updateActiveNames() {
  const path = route.path;
  const names: string[] = [];
  if (path.startsWith("/app")) names.push("应用工作台");
  if (path.startsWith("/ops")) names.push("运维工作台");
  if (path.startsWith("/governance")) names.push("治理工作台");
  activeNames.value = names;
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

watch(() => route.path, updateActiveNames, { immediate: true });
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

const logout = () => {
  chatStore.stopStream();
  auth.logout();
  router.push("/login");
};
</script>

<style scoped>
/* Navigation link */
.nav-link {
  @apply flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] text-zinc-600 transition-colors duration-150;
}
.nav-link:hover {
  @apply bg-zinc-100 text-zinc-900;
}
.nav-link-active {
  @apply bg-zinc-900 text-white;
}
.nav-link-active:hover {
  @apply bg-zinc-800 text-white;
}

/* Ghost button */
.ghost-btn {
  @apply px-3 py-1.5 text-[13px] text-zinc-500 border border-zinc-200 rounded-lg cursor-pointer bg-transparent transition-all duration-150;
}
.ghost-btn:hover {
  @apply border-zinc-300 text-zinc-700 bg-zinc-50;
}

/* Element Plus collapse overrides */
.nav-collapse {
  background: transparent;
  border: none;
}
.nav-collapse :deep(.el-collapse-item__header) {
  @apply bg-transparent border-none h-9 px-0;
}
.nav-collapse :deep(.el-collapse-item__header.is-active) {
  @apply text-zinc-900;
}
.nav-collapse :deep(.el-collapse-item__arrow) {
  @apply text-zinc-400;
}
.nav-collapse :deep(.el-collapse-item__wrap) {
  @apply bg-transparent border-none;
}
.nav-collapse :deep(.el-collapse-item__content) {
  @apply p-0 pb-1;
}
</style>
