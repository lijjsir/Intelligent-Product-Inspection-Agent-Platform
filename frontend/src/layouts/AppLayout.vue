<template>
  <div class="app-shell flex h-screen overflow-hidden bg-zinc-50" :class="{ 'user-workspace': isOrdinaryUser, 'chat-workspace': showChatControls && canChat }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside
      v-if="showSidebar"
      class="app-sidebar flex h-screen w-56 shrink-0 flex-col border-r border-zinc-200 bg-white"
      :class="{ 'mobile-nav-open': mobileNavOpen }"
    >
      <div class="app-brand border-b border-zinc-100 px-5 py-5">
        <div class="flex items-center gap-3">
          <div class="brand-mark" aria-label="PIAP 智能检测平台图标">
            <img src="/piap-icon.svg?v=3" alt="" width="40" height="40" />
          </div>
          <div class="text-[1.75rem] font-bold tracking-[0.08em] text-zinc-950">PIAP</div>
        </div>
        <div class="mt-1 text-[11px] tracking-[0.2em] text-zinc-400">智能检测平台</div>
      </div>

      <nav class="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-4">
        <template v-for="entry in navigationMenu" :key="entry.title">
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
            </RouterLink>
            <span v-else class="nav-link cursor-not-allowed text-zinc-400">
              <span>{{ entry.title }}</span>
              <span class="ml-1 text-[11px] text-zinc-300">开发中</span>
            </span>
          </template>
        </template>
        <section v-if="usesChatSidebar" class="user-conversations" aria-label="历史对话">
          <el-button class="new-conversation" plain @click="startUserConversation">＋ 新对话</el-button>
          <button class="conversation-search" aria-label="搜索历史对话" @click="searchDialogVisible=true"><Search aria-hidden="true" /><span>搜索对话</span></button>
          <div class="conversation-heading">历史对话</div>
          <div v-for="item in filteredSessions" :key="item.id" class="conversation-item" :class="{ selected: showChatControls && chatStore.session?.id === item.id }">
            <button class="conversation-select" :title="sessionDisplayLabel(item)" @click="openUserConversation(item.id)">{{ sessionDisplayLabel(item) }}</button>
            <el-dropdown trigger="click" placement="bottom-end" :show-arrow="false" popper-class="conversation-actions-menu" @command="(command: string) => handleConversationAction(command, item)">
              <button class="conversation-more" :aria-label="`对话操作：${sessionDisplayLabel(item)}`"><MoreFilled aria-hidden="true" /></button>
              <template #dropdown><el-dropdown-menu>
                <el-dropdown-item command="rename"><EditPen />修改标题</el-dropdown-item>
                <el-dropdown-item command="pin"><Top />{{ item.is_pinned ? '取消置顶' : '置顶对话' }}</el-dropdown-item>
                <el-dropdown-item command="delete" class="conversation-delete"><Delete />删除对话</el-dropdown-item>
              </el-dropdown-menu></template>
            </el-dropdown>
            <span v-if="item.is_pinned" class="conversation-pin" title="已置顶"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-label="已置顶"><path d="m16 3 5 5-4 1-3 5-4-4 5-3 1-4Z" /><path d="m2 22 7-7" /></svg></span>
          </div>
          <p v-if="!filteredSessions.length" class="conversation-empty">开始对话后会保存在这里</p>
        </section>
      </nav>
      <RouterLink v-if="usesChatSidebar" to="/app/profile" class="user-profile-link"><Setting aria-hidden="true" /><span>个人设置</span></RouterLink>
    </aside>
    <ConversationSearchDialog v-if="canChat" v-model="searchDialogVisible" @select="openSearchResult" />

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
          <span class="whitespace-nowrap text-sm font-semibold text-zinc-900">{{ showChatControls ? 'AI 对话' : 'PIAP 控制台' }}</span>

          <template v-if="showChatControls && !usesChatSidebar">
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
            aria-label="当前账号与个人设置"
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
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowRight, Menu, Search, Setting, Top, MoreFilled, EditPen, Delete } from "@element-plus/icons-vue";
import ConversationSearchDialog from '@/components/chat/ConversationSearchDialog.vue';
import { useAuthStore } from "@/stores/auth.store";
import { useChatStore } from "@/stores/chat.store";
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
import type { ChatSession, ChatSearchItem } from "@/types/chat.types";
import { parseServerDateTime } from "@/utils/date-time";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const userStore = useUserStore();
const chatStore = useChatStore();
const navigation = useNavigationStore();

const { menu, primaryRole } = useMenu();
const isOrdinaryUser = computed(() => primaryRole.value === ROLE_USER);
const isExpertChat = computed(() => primaryRole.value===ROLE_EXPERT && showChatControls.value);
const usesChatSidebar = computed(() => canChat.value && (isOrdinaryUser.value || isExpertChat.value));
const navigationMenu = computed(() => {
  const entries = usesChatSidebar.value ? menu.value.filter((entry) => isMenuGroup(entry) || entry.path !== '/app/profile') : menu.value;
  return entries;
});
const searchDialogVisible = ref(false);

const showSidebar = computed(() => auth.isAuthed && menu.value.length > 0);

const chatInitialized = ref(false);
const mobileNavOpen = ref(false);

const canChat = computed(() => {
  const role = primaryRole.value;
  return (role === ROLE_USER || role === ROLE_EXPERT) && auth.hasPermission('chat');
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
    if (Boolean(a.is_pinned) !== Boolean(b.is_pinned)) return a.is_pinned ? -1 : 1;
    const ta =
      parseServerDateTime(a.updated_at || a.last_message_at || a.created_at)?.getTime() ?? 0;
    const tb =
      parseServerDateTime(b.updated_at || b.last_message_at || b.created_at)?.getTime() ?? 0;
    return tb - ta;
  });
  return rows;
});
const filteredSessions = sessionOptions;

const AUTO_SESSION_TITLE_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

function sessionDisplayLabel(item: ChatSession) {
  const rawTitle = String(item.title || "").trim();
  if (rawTitle && item.title_source === 'manual') return rawTitle;
  if (rawTitle && !AUTO_SESSION_TITLE_RE.test(rawTitle) && !/^[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}$/i.test(rawTitle)) return rawTitle;
  return (
    "新对话"
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
  navigation.revealGroups(matchingGroups, primaryRole.value === ROLE_EXPERT);
}

function toggleMenuGroup(group: MenuGroup) {
  const exclusive = primaryRole.value === ROLE_EXPERT;
  const expanded = navigation.toggleGroup(group.title, exclusive);
  const landingPath = resolveMenuGroupLandingPath(group);
  if (!exclusive && expanded && landingPath && !group.items.some(isMenuItemActive)) {
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

async function startUserConversation() {
  await router.push('/app/chat');
  await ensureChatTopbarState();
  if (chatStore.messages.length || !chatStore.session) await createChatSession();
}

async function openUserConversation(id: string) {
  await router.push('/app/chat');
  await ensureChatTopbarState();
  if (chatStore.session?.id === id) await chatStore.reloadCurrentSessionMessages();
  else await handleChatSessionChange(id);
}

async function openSearchResult(item: ChatSearchItem) {
  try {
    await router.push('/app/chat');
    await ensureChatTopbarState();
    if (!chatStore.sessions.some(row => row.id===item.id)) chatStore.sessions.push(item);
    await chatStore.selectSession(item.id, item.message_seq || undefined);
    if (!item.message_seq && (chatStore.searchFocusSeq || chatStore.hasNewerMessages)) await chatStore.reloadCurrentSessionMessages();
  } catch { ElMessage.error('无法打开这段对话，请重试'); }
}

async function removeUserConversation(id: string) {
  try { await ElMessageBox.confirm('删除后将无法从历史对话中恢复，确认删除此对话？', '删除对话', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }); } catch { return; }
  try { await chatStore.deleteSession(id); } catch { ElMessage.error('删除对话失败，请稍后重试'); }
}

async function handleConversationAction(command: string, item: ChatSession) {
  if (command === 'delete') return removeUserConversation(item.id);
  try {
    if (command === 'pin') await chatStore.updateSession(item.id, { is_pinned: !item.is_pinned });
    if (command === 'rename') {
      const { value } = await ElMessageBox.prompt('为这段对话设置一个标题', '修改标题', { inputValue: sessionDisplayLabel(item), inputValidator: (value: string) => value.trim().length > 0 && value.trim().length <= 80 || '请输入1至80字标题', confirmButtonText: '保存', cancelButtonText: '取消' });
      await chatStore.updateSession(item.id, { title: value.trim() });
    }
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error('更新对话失败，请重试'); }
}

let titlePoll: ReturnType<typeof setTimeout> | undefined;
let titlePolls = 0;
function pollTitles() {
  if (titlePoll) clearTimeout(titlePoll);
  if (!canChat.value || (!isOrdinaryUser.value && !showChatControls.value) || !chatStore.sessions.some((item) => item.title_source === 'auto' || item.title_source === 'fallback') || titlePolls >= 15) return;
  titlePoll = setTimeout(async () => {
    titlePolls++;
    try { await chatStore.fetchSessions(); } catch { /* Retry while the title job is running. */ }
    pollTitles();
  }, 3000);
}
watch(() => chatStore.sessions.map((item) => `${item.id}:${item.title_source}`).join('|'), () => { titlePolls = 0; pollTitles(); });
watch(() => [...chatStore.messages].reverse().find((item) => item.role === 'assistant' && item.message_type !== 'streaming')?.id, async () => {
  if (!canChat.value) return;
  titlePolls = 0;
  await chatStore.fetchSessions().catch(() => undefined);
  pollTitles();
});
onBeforeUnmount(() => { if (titlePoll) clearTimeout(titlePoll); });

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
  if (auth.isAuthed && canChat.value && isOrdinaryUser.value && !showChatControls.value) void chatStore.fetchSessions().catch(() => undefined);
});

function logout() {
  chatStore.stopStream();
  auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.user-conversations { margin-top: 20px; border-top: 1px solid #29435e; padding-top: 17px; }
.new-conversation { width: 100%; justify-content: flex-start; margin-bottom: 14px; background: transparent !important; border-color: #2c4866 !important; color: #dbe9fb !important; }
.conversation-search { display: flex; align-items: center; gap: 8px; color: #8eabc9; padding: 9px; border:0; background:transparent; font:inherit; font-size:12px; cursor:pointer; width:100%; border-radius:8px; }
.conversation-search:hover { background:#183654; color:#c9dbf0; }
.conversation-search svg { width: 16px; flex: none; }
.conversation-search input { width: 100%; min-width: 0; background: transparent; color: #dceafd; border: 0; outline: none; font-size: 12px; }
.conversation-search input::placeholder { color: #87a0bf; }
.conversation-heading { font-size: 11px; color: #718aa9; padding: 20px 10px 10px; }
.conversation-item { display: flex; align-items: center; gap: 2px; border-radius: 8px; min-height: 36px; }
.conversation-item.selected, .conversation-item:hover { background: #183654; }
.conversation-select { min-width: 0; flex: 1; padding: 9px 10px; border: 0; background: transparent; color: #a6bfdd; font-size: 12px; text-align: left; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; cursor: pointer; }
.conversation-remove { background: transparent; border: 0; padding: 5px 7px; color: #8da7c7; cursor: pointer; opacity: 0; }
.conversation-item:hover .conversation-remove, .conversation-item:focus-within .conversation-remove { opacity: 1; }
.conversation-empty { color: #7e97b7; font-size: 11px; line-height: 1.8; padding: 0 10px; }
.conversation-more { display:grid; place-items:center; width:28px; height:28px; padding:0; border:0; border-radius:6px; background:transparent; color:#a2b7d0; cursor:pointer; opacity:0; }
.conversation-more svg { width:16px; height:16px; }
.conversation-more:hover { background:#254966; color:#e1edfa; }
.conversation-item:hover .conversation-more, .conversation-item.selected .conversation-more, .conversation-item:focus-within .conversation-more { opacity: 1; }
.conversation-pin { display:grid; place-items:center; color:#8cb4e3; margin:0 7px 0 2px; }
@media(max-width:700px) { .conversation-more { opacity:1; } }
.user-profile-link { display: flex; align-items: center; gap: 10px; margin: 0 14px; padding: 18px 12px; color: #a7bedb; border-top: 1px solid #28425d; font-size: 13px; text-decoration: none; }
.user-profile-link svg { width: 18px; }
.chat-workspace .app-main { padding: 0 !important; background: white; overflow: hidden; }
.chat-workspace .app-header { box-shadow: none; }
.conversation-select:focus-visible, .conversation-more:focus-visible, .conversation-search:focus-visible, .user-profile-link:focus-visible { outline: 2px solid #62a6ef; outline-offset: 1px; }
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

/* Shared shell skin: the navigation is the dark anchor, content stays bright and calm. */
.app-shell { background: #f3f7fc !important; }
.app-sidebar {
  width: 248px !important;
  border-right: 1px solid rgba(125, 159, 202, 0.18) !important;
  background: linear-gradient(180deg, #0b1930 0%, #0d2442 100%) !important;
  color: #d8e6fb;
  box-shadow: 14px 0 36px rgba(13, 36, 66, 0.08);
}
.app-brand { border-bottom-color: rgba(159, 190, 229, 0.14) !important; }
.app-brand .text-zinc-950 { color: #f4f8ff !important; }
.app-brand .text-zinc-400 { color: #8ea8c8 !important; }
.brand-mark { background: rgba(14, 51, 85, 0.9); border: 1px solid rgba(93, 206, 230, 0.24); }
.app-sidebar nav { padding: 18px 14px; }
.nav-link, .nav-sublink { color: #9db1cf; border-radius: 10px; min-height: 42px; }
.nav-link:hover, .nav-sublink:hover { background: rgba(113, 165, 237, 0.13); color: #eef6ff; }
.nav-link-active { background: linear-gradient(100deg, #1d67d8, #2787e8) !important; color: #fff !important; box-shadow: 0 8px 20px rgba(19, 103, 216, 0.24); }
.nav-link-active:hover { background: linear-gradient(100deg, #1d67d8, #2787e8) !important; }
.nav-group-link { color: #afc2de; }
.nav-group-arrow { color: #7894b9; }
.nav-count-badge { background: #35c9d3; color: #08223b; }
.nav-link-active .nav-count-badge { background: #fff; color: #1d67d8; }
.app-header {
  height: 64px !important;
  border-bottom-color: #dbe5f2 !important;
  background: rgba(255, 255, 255, 0.92) !important;
  padding-inline: 28px !important;
  box-shadow: 0 4px 18px rgba(40, 75, 122, 0.04);
}
.app-header .text-zinc-900 { color: #13213a !important; font-size: 15px; }
.app-main { padding: 24px !important; background: #f3f7fc; }
.topbar-workspace { background: #eaf2ff !important; color: #2b5eae !important; }
.ghost-btn { border-color: #dbe5f2; color: #56708f; }
.ghost-btn:hover { border-color: #a8c1e1; background: #f3f7ff; color: #1e4f93; }

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
    inset: 64px auto 0 0;
    height: calc(100vh - 64px);
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
    inset: 64px 0 0;
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
    height: auto !important;
    min-height: 64px;
    gap: 8px;
    padding: 7px 10px !important;
  }

  .app-header .el-select { max-width: 100%; }

  .app-header > div {
    gap: 8px;
  }

  .profile-role {
    display: none;
  }
  .topbar-workspace { font-size:10px !important; padding:2px 7px !important; }

  .ghost-btn {
    padding: 5px 8px;
    font-size: 12px;
  }

  .app-main {
    padding: 8px !important;
  }
}
</style>
<style>
.conversation-actions-menu.el-popper { border:1px solid #e3e8ef; border-radius:11px; box-shadow:0 8px 26px #13264020; min-width:164px; }
.conversation-actions-menu .el-dropdown-menu { padding:5px; }
.conversation-actions-menu .el-dropdown-menu__item { display:flex; align-items:center; gap:9px; height:36px; min-height:36px; box-sizing:border-box; padding:8px 12px; margin:0; border:0; border-radius:6px; font-size:13px; line-height:20px; color:#4c607b; }
.conversation-actions-menu .el-dropdown-menu__item svg { width:16px; height:16px; margin:0; flex:none; }
.conversation-actions-menu .el-dropdown-menu__item:hover { background:#f0f5fc; color:#426da4; }
.conversation-actions-menu .conversation-delete { color:#bd5760; }
.conversation-actions-menu .conversation-delete:hover { color:#b3434f; background:#fff1f2; }
</style>
