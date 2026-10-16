<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { rolesOrgsApi } from "@/api/roles-orgs.api";
import { userApi } from "@/api/user.api";
import { extractApiErrorMessage } from "@/api/http";
import { ROLE_ADMIN } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import {
  groupPermissionFeatures,
  resolvePermissions,
  sameOverrides,
  samePermissions,
  groupUsersByRole,
  rolePermissionCatalog,
  personalPermissionToggle,
  permissionDifference,
  personalGrantOptions,
} from "@/utils/permissions";
import type { RoleItem, RolesPermissionMatrix } from "@/types/governance.types";
import type { PermissionAction, PermissionEffect, UserPermissions } from "@/types/permission.types";
import type { User } from "@/types/user.types";

const props = defineProps<{ mode: string }>();
const auth = useAuthStore();
const roles = ref<RoleItem[]>([]);
const matrix = ref<RolesPermissionMatrix | null>(null);
const roleDrafts = reactive<Record<string, string[]>>({});
const users = ref<User[]>([]);
const userSaved = reactive<Record<string, UserPermissions>>({});
const userDrafts = reactive<
  Record<string, { role: string; overrides: Record<string, PermissionEffect> }>
>({});
const selectedRole = ref("algorithm_engineer");
const selectedUser = ref("");
const group = ref("algorithm");
const query = ref("");
const userQuery = ref("");
const userPage = ref(1);
const userTotal = ref(0);
const userRoleFilter = ref("");
const roleCounts = ref<Record<string, number>>({});
const collapsedRoles = reactive<Record<string, boolean>>({});
const loading = ref(true);
const loadingUsers = ref(false);
const loadingUser = ref(false);
const saving = ref(false);
const loadError = ref("");
const userError = ref("");
const expanded = ref("");
const personalView = ref<"all" | "extra" | "denied">("all");
const grantDialog = ref(false);
const grantKind = ref<"extra" | "restore" | "fixed">("extra");
const grantQuery = ref("");
const grantSelection = ref<string[]>([]);
let usersRequest = 0;
let detailRequest = 0;
let searchTimer: ReturnType<typeof setTimeout> | undefined;

const isUser = computed(() => props.mode === "users");
const userGroups = computed(() =>
  groupUsersByRole(users.value, roles.value, roleCounts.value, userRoleFilter.value),
);
const directoryTotal = computed(() =>
  Object.values(roleCounts.value).reduce((sum, count) => sum + count, 0),
);
const draft = computed(() => userDrafts[selectedUser.value]);
const person = computed(() => users.value.find((item) => item.id === selectedUser.value));
const savedPerson = computed(() => userSaved[selectedUser.value]);
const locked = computed(
  () =>
    auth.primaryRole !== ROLE_ADMIN ||
    (isUser.value
      ? savedPerson.value?.role === ROLE_ADMIN || draft.value?.role === ROLE_ADMIN
      : matrix.value?.protected_roles.includes(selectedRole.value)),
);
const selectedRoleResources = computed(() => roleDrafts[selectedRole.value] || []);
const roleDefaults = computed(() => matrix.value?.matrix[draft.value?.role || ""] || []);
const dependencies = computed(() =>
  Object.fromEntries((matrix.value?.catalog || []).map((item) => [item.key, item.requires || []])),
);
const finalPermissions = computed(() =>
  resolvePermissions(roleDefaults.value, draft.value?.overrides || {}, dependencies.value),
);
const savedEffective = computed(() => savedPerson.value?.effective || []);
const effectiveChanges = computed(() =>
  permissionDifference(savedEffective.value, finalPermissions.value),
);
const permissionName = (key: string) => {
  const action =
    roleCatalog.value.find((item) => item.key === key) ||
    matrix.value?.catalog.find((item) => item.key === key);
  return action ? `${action.name}·${action.action}` : key;
};
const personalSource = (key: string) =>
  draft.value?.overrides[key] === "grant"
    ? roleDefaults.value.includes(key)
      ? "个人固定授权"
      : "额外授权"
    : draft.value?.overrides[key] === "deny"
      ? "单独撤销"
      : "跟随角色";
const changedPermission = (key: string) =>
  savedEffective.value.includes(key) !== finalPermissions.value.includes(key);
const activeRole = computed(() => (isUser.value ? draft.value?.role || "" : selectedRole.value));
const roleCapabilities = computed(() => matrix.value?.role_capabilities?.[activeRole.value] || []);
const roleCatalog = computed(() =>
  rolePermissionCatalog(matrix.value?.catalog || [], roleCapabilities.value, activeRole.value),
);
const features = computed(() => groupPermissionFeatures(roleCatalog.value));
const grantOptions = computed(() =>
  personalGrantOptions(
    roleCatalog.value,
    roleDefaults.value,
    draft.value?.overrides || {},
    dependencies.value,
  ),
);
const extraGranted = computed(() =>
  roleCatalog.value.filter(
    (action) =>
      draft.value?.overrides[action.key] === "grant" && !roleDefaults.value.includes(action.key),
  ),
);
const personallyDenied = computed(() =>
  roleCatalog.value.filter((action) => draft.value?.overrides[action.key] === "deny"),
);
const grantChoices = computed(() =>
  grantOptions.value[grantKind.value].filter((action) => {
    const text = grantQuery.value.trim().toLowerCase();
    return `${action.name} ${action.action} ${groupLabel(action.group)}`
      .toLowerCase()
      .includes(text);
  }),
);
const grantChoiceGroups = computed(() =>
  (matrix.value?.groups || [])
    .map((item) => ({
      ...item,
      actions: grantChoices.value.filter((action) => action.group === item.key),
    }))
    .filter((item) => item.actions.length),
);
const selectedGrantKeys = computed(() =>
  grantSelection.value.filter((key) =>
    grantOptions.value[grantKind.value].some((action) => action.key === key),
  ),
);
const relatedGrantKeys = computed(() =>
  [...new Set(selectedGrantKeys.value.flatMap((key) => dependencies.value[key] || []))].filter(
    (key) => !finalPermissions.value.includes(key) && !selectedGrantKeys.value.includes(key),
  ),
);
const availableGroups = computed(() =>
  (matrix.value?.groups || []).filter((item) =>
    roleCatalog.value.some((action) => action.group === item.key),
  ),
);
const visibleFeatures = computed(() =>
  features.value
    .map((item) => ({
      ...item,
      actions: item.actions.filter(
        (action) =>
          !isUser.value ||
          personalView.value === "all" ||
          (personalView.value === "extra"
            ? extraGranted.value.some((extra) => extra.key === action.key)
            : draft.value?.overrides[action.key] === "deny"),
      ),
    }))
    .filter((item) => {
      if (!item.actions.length) return false;
      const text = query.value.trim().toLowerCase();
      return text
        ? `${item.name} ${item.actions.map((action) => `${action.key} ${action.action}`).join(" ")}`
            .toLowerCase()
            .includes(text)
        : item.group === group.value;
    }),
);
const groupLabel = (key: string) =>
  matrix.value?.groups.find((item) => item.key === key)?.label || key;
const roleLabel = (key: string) => roles.value.find((item) => item.key === key)?.label || key;
const restricted = (key: string) =>
  (
    matrix.value?.role_restrictions?.[
      isUser.value ? draft.value?.role || "" : selectedRole.value
    ] || []
  ).includes(key);
const userDirty = (id: string) =>
  Boolean(
    userSaved[id] &&
    userDrafts[id] &&
    (userDrafts[id].role !== userSaved[id].role ||
      !sameOverrides(userDrafts[id].overrides, userSaved[id].overrides)),
  );
const roleDirty = (role: string) =>
  Boolean(
    matrix.value &&
    roleDrafts[role] &&
    !samePermissions(roleDrafts[role], matrix.value.matrix[role] || []),
  );
const dirty = computed(() =>
  isUser.value ? userDirty(selectedUser.value) : roleDirty(selectedRole.value),
);
const anyDirty = computed(
  () => Object.keys(roleDrafts).some(roleDirty) || Object.keys(userDrafts).some(userDirty),
);
const title = computed(() =>
  isUser.value
    ? `${savedPerson.value?.username || person.value?.username || "选择用户"} · 用户授权`
    : roleLabel(selectedRole.value),
);
const canSave = computed(
  () =>
    auth.primaryRole === ROLE_ADMIN &&
    dirty.value &&
    !saving.value &&
    !loadingUser.value &&
    !loadError.value &&
    (!isUser.value || !userError.value),
);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const [roleResponse, matrixResponse] = await Promise.all([
      rolesOrgsApi.listRoles(),
      rolesOrgsApi.getPermissionsMatrix(),
    ]);
    roles.value = roleResponse.data.data;
    matrix.value = matrixResponse.data.data;
    for (const [key, resources] of Object.entries(matrix.value.matrix))
      roleDrafts[key] = [...resources];
    if (!roles.value.some((item) => item.key === selectedRole.value))
      selectedRole.value = roles.value[0]?.key || "";
    if (auth.primaryRole === ROLE_ADMIN) await fetchUsers();
  } catch (error) {
    loadError.value = extractApiErrorMessage(error, "权限数据加载失败");
  } finally {
    loading.value = false;
  }
}

async function fetchUsers() {
  const request = ++usersRequest;
  loadingUsers.value = true;
  try {
    const { data } = await userApi.permissionDirectory({
      page: userPage.value,
      size: 20,
      keyword: userQuery.value.trim() || undefined,
      role: userRoleFilter.value || undefined,
    });
    if (request !== usersRequest) return;
    users.value = data.data.items;
    userTotal.value = data.data.total;
    roleCounts.value = data.data.role_counts;
    if (!users.value.some((item) => item.id === selectedUser.value))
      selectedUser.value =
        users.value.find((item) => item.role !== ROLE_ADMIN)?.id || users.value[0]?.id || "";
    if (!selectedUser.value) {
      detailRequest++;
      loadingUser.value = false;
      userError.value = "";
    }
    const selected = users.value.find((item) => item.id === selectedUser.value);
    for (const role of roles.value) {
      if (!(role.key in collapsedRoles)) collapsedRoles[role.key] = true;
    }
    if (selected) collapsedRoles[selected.role] = false;
    if (selectedUser.value && !userDrafts[selectedUser.value]) await selectUser(selectedUser.value);
  } catch (error) {
    if (request === usersRequest)
      ElMessage.error(extractApiErrorMessage(error, "用户列表加载失败"));
  } finally {
    if (request === usersRequest) loadingUsers.value = false;
  }
}

function toggleUserGroup(key: string, members: User[]) {
  if (!members.length) {
    userRoleFilter.value = key;
    collapsedRoles[key] = false;
  } else collapsedRoles[key] = !collapsedRoles[key];
}

async function selectUser(id: string) {
  selectedUser.value = id;
  const selected = users.value.find((item) => item.id === id);
  if (selected) collapsedRoles[selected.role] = false;
  expanded.value = "";
  userError.value = "";
  const request = ++detailRequest;
  if (userDrafts[id]) {
    loadingUser.value = false;
    return;
  }
  loadingUser.value = true;
  try {
    const { data } = await userApi.getPermissions(id);
    updateRoleSnapshot(data.data);
    userSaved[id] = data.data;
    userDrafts[id] = { role: data.data.role, overrides: { ...data.data.overrides } };
  } catch (error) {
    if (request === detailRequest)
      userError.value = extractApiErrorMessage(error, "用户授权加载失败");
  } finally {
    if (request === detailRequest) loadingUser.value = false;
  }
}

function updateRoleSnapshot(user: UserPermissions) {
  if (!matrix.value) return;
  const edited = roleDirty(user.role);
  matrix.value.matrix[user.role] = [...user.role_default];
  matrix.value.versions[user.role] = user.role_version;
  if (!edited) roleDrafts[user.role] = [...user.role_default];
}

function toggleRole(key: string, checked: boolean) {
  const set = new Set(selectedRoleResources.value);
  if (checked) set.add(key);
  else set.delete(key);
  if (checked) for (const required of dependencies.value[key] || []) set.add(required);
  else
    for (const [dependent, required] of Object.entries(dependencies.value))
      if (required.includes(key)) set.delete(dependent);
  roleDrafts[selectedRole.value] = [...set];
}

function setOverride(key: string, effect: string) {
  if (!draft.value || locked.value) return;
  if (effect === "inherit") delete draft.value.overrides[key];
  else draft.value.overrides[key] = effect as PermissionEffect;
}

function setPersonalAllowed(key: string, allowed: boolean) {
  if (!draft.value || locked.value || saving.value) return;
  draft.value.overrides = personalPermissionToggle(draft.value.overrides, key, allowed);
  if (allowed) {
    for (const required of dependencies.value[key] || [])
      if (!finalPermissions.value.includes(required)) draft.value.overrides[required] = "grant";
  } else {
    for (const [dependent, required] of Object.entries(dependencies.value))
      if (required.includes(key)) draft.value.overrides[dependent] = "deny";
  }
}

function openGrantDialog() {
  grantKind.value = "extra";
  grantQuery.value = "";
  grantSelection.value = [];
  grantDialog.value = true;
}

function toggleGrantSelection(key: string, checked: boolean) {
  grantSelection.value = checked
    ? [...new Set([...grantSelection.value, key])]
    : grantSelection.value.filter((item) => item !== key);
}

function applyPersonalGrants() {
  if (!draft.value || locked.value || saving.value || loadingUser.value) return;
  const keys = [...selectedGrantKeys.value];
  for (const key of keys) setPersonalAllowed(key, true);
  personalView.value = "all";
  query.value = "";
  const first = roleCatalog.value.find((action) => action.key === keys[0]);
  if (first) group.value = first.group;
  grantDialog.value = false;
}

function changeUserRole(event: Event) {
  if (!draft.value) return;
  draft.value.role = (event.target as HTMLSelectElement).value;
  if (draft.value.role === ROLE_ADMIN) draft.value.overrides = {};
  const allowed = new Set(matrix.value?.role_capabilities?.[draft.value.role] || []);
  for (const key of Object.keys(draft.value.overrides))
    if (!allowed.has(key)) delete draft.value.overrides[key];
}

function discard() {
  if (isUser.value && savedPerson.value) {
    userDrafts[selectedUser.value] = {
      role: savedPerson.value.role,
      overrides: { ...savedPerson.value.overrides },
    };
  } else if (matrix.value)
    roleDrafts[selectedRole.value] = [...matrix.value.matrix[selectedRole.value]];
}

async function save() {
  if (!canSave.value) return;
  saving.value = true;
  const userId = selectedUser.value;
  const role = selectedRole.value;
  try {
    if (isUser.value && draft.value && savedPerson.value) {
      const { data } = await userApi.updatePermissions(userId, {
        role: draft.value.role,
        expected_role: savedPerson.value.role,
        overrides: { ...draft.value.overrides },
        version: savedPerson.value.version,
      });
      updateRoleSnapshot(data.data);
      userSaved[userId] = data.data;
      userDrafts[userId] = { role: data.data.role, overrides: { ...data.data.overrides } };
      const user = users.value.find((item) => item.id === userId);
      if (user) user.role = data.data.role;
      if (userRoleFilter.value && userRoleFilter.value !== data.data.role)
        userRoleFilter.value = data.data.role;
      else await fetchUsers();
    } else if (matrix.value) {
      const edited = new Set(Object.keys(roleDrafts).filter(roleDirty));
      const { data } = await rolesOrgsApi.updateRolePermissions(
        role,
        [...roleDrafts[role]],
        matrix.value.versions[role],
      );
      matrix.value = data.data;
      for (const [key, resources] of Object.entries(data.data.matrix)) {
        if (!edited.has(key)) roleDrafts[key] = [...resources];
      }
      roleDrafts[role] = [...data.data.matrix[role]];
    }
    ElMessage.success("权限已保存，后续请求按最新授权执行");
    await auth.refreshPermissions();
  } catch (error) {
    ElMessage.error(extractApiErrorMessage(error, "保存失败，改动已保留，请重试"));
  } finally {
    saving.value = false;
  }
}

async function refreshData() {
  if (anyDirty.value) {
    try {
      await ElMessageBox.confirm("刷新将撤销所有未保存的权限改动，并获取最新授权。", "刷新权限", {
        confirmButtonText: "刷新",
        cancelButtonText: "继续编辑",
        type: "warning",
      });
    } catch {
      return;
    }
  }
  for (const key of Object.keys(userSaved)) delete userSaved[key];
  for (const key of Object.keys(userDrafts)) delete userDrafts[key];
  await load();
}

function adjustmentLabel(action: PermissionAction) {
  const effect = draft.value?.overrides[action.key];
  return effect === "grant" ? `+ ${action.action}` : effect === "deny" ? `− ${action.action}` : "";
}

async function confirmLeave() {
  if (!anyDirty.value) return true;
  try {
    await ElMessageBox.confirm("有尚未保存的权限改动，离开后这些改动将丢失。", "离开权限管理", {
      confirmButtonText: "离开",
      cancelButtonText: "继续编辑",
      type: "warning",
    });
    return true;
  } catch {
    return false;
  }
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (anyDirty.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}

watch(userQuery, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    userPage.value = 1;
    void fetchUsers();
  }, 250);
});
watch(userRoleFilter, () => {
  clearTimeout(searchTimer);
  userPage.value = 1;
  void fetchUsers();
});
watch(
  availableGroups,
  (items) => {
    if (!items.length) return;
    if (!items.some((item) => item.key === group.value)) {
      group.value = items[0]?.key || "";
      expanded.value = "";
    }
  },
  { immediate: true },
);
watch(
  () => props.mode,
  () => {
    expanded.value = "";
  },
);
watch([selectedUser, activeRole, () => props.mode], () => {
  grantDialog.value = false;
  grantSelection.value = [];
  personalView.value = "all";
});
watch(grantKind, () => {
  grantSelection.value = [];
});
onBeforeRouteLeave(confirmLeave);
onMounted(() => {
  window.addEventListener("beforeunload", beforeUnload);
  void load();
});
onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", beforeUnload);
  clearTimeout(searchTimer);
  usersRequest++;
  detailRequest++;
});
</script>

<template>
  <section class="permission-matrix" v-loading="loading" aria-label="权限矩阵">
    <div v-if="loadError" class="load-error" role="alert">
      <span>{{ loadError }}</span
      ><el-button @click="load">重新加载</el-button>
    </div>
    <template v-else-if="matrix">
      <div class="permission-intro">
        {{
          isUser
            ? "选择用户后直接授予或撤销具体操作；对照保存前、保存后的权限，确认变化后点击保存授权。仅影响此用户。"
            : "仅显示该角色可拥有的功能。勾选授权，取消勾选撤销；角色职责之外的权限不开放。"
        }}
      </div>
      <div class="permission-workspace">
        <aside class="entity-panel" aria-label="选择角色或用户">
          <h3>{{ isUser ? "按身份选择用户" : "选择角色" }}</h3>
          <el-input
            v-if="isUser"
            v-model="userQuery"
            aria-label="搜索用户"
            placeholder="搜索用户"
            clearable
            size="small"
            class="entity-search"
          />
          <div v-if="isUser" class="identity-filter">
            <label for="directory-role-filter">身份筛选</label>
            <select
              id="directory-role-filter"
              v-model="userRoleFilter"
              :disabled="saving || loadingUsers"
            >
              <option value="">全部身份</option>
              <option v-for="role in roles" :key="role.key" :value="role.key">
                {{ role.label }} · {{ roleCounts[role.key] || 0 }} 人
              </option>
            </select>
            <span class="directory-summary" role="status"
              >共 {{ directoryTotal }} 人 ·
              {{ Object.values(roleCounts).filter(Boolean).length }} 类身份</span
            >
          </div>
          <div v-if="!isUser" class="entity-list">
            <button
              v-for="role in roles"
              :key="role.key"
              class="entity-button"
              :aria-pressed="selectedRole === role.key"
              :disabled="saving"
              @click="
                selectedRole = role.key;
                expanded = '';
              "
            >
              <strong
                >{{ role.label
                }}<span
                  v-if="roleDirty(role.key)"
                  class="dirty-dot"
                  aria-label="有未保存改动"
                ></span
              ></strong>
              <small>{{ (matrix.matrix[role.key] || []).length }} 项角色默认权限</small>
            </button>
          </div>
          <div v-else class="user-directory" v-loading="loadingUsers" aria-label="按身份分组的用户">
            <section
              v-for="identity in userGroups"
              :key="identity.key"
              class="identity-group"
              :aria-label="`${identity.label}用户组`"
            >
              <button
                class="identity-heading"
                :disabled="saving || loadingUsers"
                :aria-expanded="!collapsedRoles[identity.key] && identity.users.length > 0"
                :aria-controls="`identity-${identity.key}`"
                @click="toggleUserGroup(identity.key, identity.users)"
              >
                <span
                  class="identity-chevron"
                  :class="{ expanded: !collapsedRoles[identity.key] && identity.users.length }"
                  aria-hidden="true"
                  >›</span
                ><strong>{{ identity.label }}</strong
                ><span class="identity-count">{{ identity.count }}</span>
              </button>
              <div
                v-show="!collapsedRoles[identity.key]"
                :id="`identity-${identity.key}`"
                class="identity-members"
              >
                <button
                  v-for="user in identity.users"
                  :key="user.id"
                  class="entity-button user-entity"
                  :aria-pressed="selectedUser === user.id"
                  :disabled="saving"
                  @click="selectUser(user.id)"
                >
                  <strong
                    >{{ user.username
                    }}<span
                      v-if="userDirty(user.id)"
                      class="dirty-dot"
                      aria-label="有未保存改动"
                    ></span
                    ><span v-if="!user.is_active" class="user-inactive">已停用</span></strong
                  >
                  <small v-if="userDrafts[user.id]?.role && userDrafts[user.id].role !== user.role"
                    >待改为：{{ roleLabel(userDrafts[user.id].role) }}</small
                  >
                </button>
                <button
                  v-if="!identity.users.length"
                  class="group-more"
                  :disabled="saving || loadingUsers"
                  @click="userRoleFilter = identity.key"
                >
                  查看该身份用户
                </button>
              </div>
            </section>
            <p v-if="!userGroups.length" class="muted empty-users">没有找到用户</p>
          </div>
          <div v-if="isUser && userTotal > 20" class="user-pagination">
            <el-button
              size="small"
              :disabled="userPage === 1 || loadingUsers || saving"
              aria-label="上一页用户"
              @click="
                userPage--;
                fetchUsers();
              "
              >上一页</el-button
            >
            <span>{{ userPage }} / {{ Math.ceil(userTotal / 20) }}</span>
            <el-button
              size="small"
              :disabled="userPage * 20 >= userTotal || loadingUsers || saving"
              aria-label="下一页用户"
              @click="
                userPage++;
                fetchUsers();
              "
              >下一页</el-button
            >
          </div>
        </aside>
        <div class="permission-content" v-loading="loadingUser">
          <header class="permission-header">
            <div>
              <h3>{{ title }}</h3>
              <p>
                {{
                  isUser
                    ? `当前角色：${roleLabel(draft?.role || "")} · 个人授权与角色默认分开显示`
                    : "定义该角色可以执行的功能与操作。"
                }}
              </p>
            </div>
            <div class="save-tools">
              <span class="save-state" :class="{ pending: dirty }" role="status">{{
                dirty ? "有未保存改动" : "已保存"
              }}</span>
              <el-button text :disabled="!dirty || saving" @click="discard"
                >撤销未保存改动</el-button
              >
              <el-button text :disabled="saving" @click="refreshData">刷新权限</el-button>
              <el-button type="primary" :loading="saving" :disabled="!canSave" @click="save">{{
                isUser ? "保存授权" : "保存权限"
              }}</el-button>
            </div>
          </header>
          <div v-if="userError && isUser" class="load-error" role="alert">
            <span>{{ userError }}</span
            ><el-button @click="selectUser(selectedUser)">重新加载</el-button>
          </div>
          <template v-else-if="!isUser || draft">
            <div class="permission-toolbar">
              <div class="permission-search-tools">
                <el-input
                  v-model="query"
                  aria-label="搜索功能"
                  placeholder="搜索功能，例如：模型配置"
                  clearable
                  class="feature-search"
                />
                <el-button
                  v-if="isUser"
                  type="primary"
                  plain
                  :disabled="locked || saving || loadingUser || !!userError"
                  @click="openGrantDialog"
                  >额外授权</el-button
                >
              </div>
              <div v-if="isUser && draft" class="user-role-select">
                <label for="permission-user-role">用户角色</label>
                <select
                  id="permission-user-role"
                  :value="draft.role"
                  :disabled="savedPerson?.role === ROLE_ADMIN || saving"
                  @change="changeUserRole"
                >
                  <option v-for="role in roles" :key="role.key" :value="role.key">
                    {{ role.label }}
                  </option>
                </select>
              </div>
              <span v-else class="muted">勾选授权 · 取消勾选撤销</span>
            </div>
            <p v-if="locked" class="protected-note">
              {{
                auth.primaryRole !== ROLE_ADMIN
                  ? "当前账号仅可查看权限，修改授权需要管理员账号。"
                  : "管理员拥有全部功能权限，个人调整不可修改。"
              }}{{
                draft?.role === ROLE_ADMIN && savedPerson?.role !== ROLE_ADMIN
                  ? "保存后该用户将成为管理员。"
                  : ""
              }}
            </p>
            <div v-if="isUser" class="personal-instruction">
              额外授权可直接授予角色默认未开放的操作，无需先撤销。取消勾选仅对此用户禁止；恢复默认后重新跟随角色。
              <nav class="personal-source-filters" aria-label="个人权限筛选">
                <button :aria-pressed="personalView === 'all'" @click="personalView = 'all'">
                  全部权限
                </button>
                <button :aria-pressed="personalView === 'extra'" @click="personalView = 'extra'">
                  已额外授权 · {{ extraGranted.length }}
                </button>
                <button :aria-pressed="personalView === 'denied'" @click="personalView = 'denied'">
                  个人撤销 · {{ personallyDenied.length }}
                </button>
                <span>可额外授予 {{ grantOptions.extra.length }} 项</span>
              </nav>
            </div>
            <div v-if="isUser && dirty" class="personal-save-preview" role="status">
              <strong>保存将生效：</strong>
              <span v-if="draft?.role !== savedPerson?.role"
                >角色 {{ roleLabel(savedPerson?.role || "") }} →
                {{ roleLabel(draft?.role || "") }}。</span
              >
              <span v-if="effectiveChanges.granted.length"
                >授予 {{ effectiveChanges.granted.map(permissionName).join("、") }}。</span
              >
              <span v-if="effectiveChanges.revoked.length"
                >撤销 {{ effectiveChanges.revoked.map(permissionName).join("、") }}。</span
              >
              <span v-if="!effectiveChanges.granted.length && !effectiveChanges.revoked.length">{{
                draft?.role !== savedPerson?.role
                  ? "数据与业务范围将按新角色重新判断。"
                  : "当前可执行权限不变，仅修改跟随角色或个人设置方式。"
              }}</span>
            </div>
            <nav class="permission-groups" aria-label="业务模块">
              <button
                v-for="item in availableGroups"
                :key="item.key"
                :aria-pressed="!query.trim() && group === item.key"
                @click="
                  group = item.key;
                  query = '';
                  expanded = '';
                "
              >
                {{ item.label }}
              </button>
            </nav>
            <div class="permission-table-wrap">
              <table class="permission-table" :class="{ 'user-permission-table': isUser }">
                <thead>
                  <tr>
                    <th scope="col">功能</th>
                    <template v-if="isUser"
                      ><th scope="col">角色默认</th>
                      <th scope="col">个人授权 · 勾选允许</th>
                      <th scope="col">保存前 · 当前生效</th>
                      <th scope="col">保存后 · 预览</th>
                      <th scope="col">恢复角色默认</th></template
                    >
                    <th v-else scope="col">允许执行的操作</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="feature in visibleFeatures" :key="feature.id">
                    <tr>
                      <td>
                        <strong
                          :title="
                            feature.actions
                              .map((action) => action.description || '')
                              .filter(Boolean)
                              .join('；')
                          "
                          >{{ feature.name }}</strong
                        >
                        <small>{{ groupLabel(feature.group) }}</small>
                      </td>
                      <td v-if="!isUser">
                        <div class="role-actions">
                          <label
                            v-for="action in feature.actions"
                            :key="action.key"
                            :title="action.key"
                            ><input
                              type="checkbox"
                              :checked="selectedRoleResources.includes(action.key)"
                              :disabled="locked || saving || restricted(action.key)"
                              :aria-label="`${roleLabel(selectedRole)} ${feature.name} ${action.action}`"
                              @change="
                                toggleRole(action.key, ($event.target as HTMLInputElement).checked)
                              "
                            />{{ action.action }}</label
                          >
                        </div>
                      </td>
                      <template v-else>
                        <td>
                          <div
                            v-for="action in feature.actions"
                            :key="action.key"
                            class="permission-state-line"
                          >
                            <span>{{ action.action }}</span
                            ><span class="permission-tag inherited">{{
                              roleDefaults.includes(action.key) ? "允许" : "未授予"
                            }}</span>
                          </div>
                        </td>
                        <td>
                          <div
                            v-for="action in feature.actions"
                            :key="action.key"
                            class="personal-operation"
                          >
                            <label
                              ><input
                                type="checkbox"
                                :checked="finalPermissions.includes(action.key)"
                                :disabled="locked || saving"
                                :aria-label="`允许${feature.name}${action.action}`"
                                @change="
                                  setPersonalAllowed(
                                    action.key,
                                    ($event.target as HTMLInputElement).checked,
                                  )
                                "
                              />{{ action.action }}</label
                            >
                            <small
                              :class="{
                                'source-denied': draft?.overrides[action.key] === 'deny',
                                'source-granted': draft?.overrides[action.key] === 'grant',
                              }"
                              >{{ personalSource(action.key) }}</small
                            >
                          </div>
                        </td>
                        <td>
                          <div
                            v-for="action in feature.actions"
                            :key="action.key"
                            class="permission-state-line"
                          >
                            <span>{{ action.action }}</span
                            ><strong
                              :class="
                                savedEffective.includes(action.key)
                                  ? 'state-allowed'
                                  : 'state-forbidden'
                              "
                              >{{ savedEffective.includes(action.key) ? "允许" : "禁止" }}</strong
                            >
                          </div>
                        </td>
                        <td>
                          <div
                            v-for="action in feature.actions"
                            :key="action.key"
                            class="permission-state-line"
                          >
                            <span>{{ action.action }}</span
                            ><strong
                              :class="
                                finalPermissions.includes(action.key)
                                  ? 'state-allowed'
                                  : 'state-forbidden'
                              "
                              >{{ finalPermissions.includes(action.key) ? "允许" : "禁止" }}</strong
                            ><span
                              v-if="changedPermission(action.key)"
                              class="permission-tag"
                              :class="finalPermissions.includes(action.key) ? 'extra' : 'denied'"
                              >{{
                                finalPermissions.includes(action.key)
                                  ? "禁止 → 允许"
                                  : "允许 → 禁止"
                              }}</span
                            >
                          </div>
                        </td>
                        <td>
                          <el-button
                            text
                            size="small"
                            :disabled="
                              locked ||
                              saving ||
                              !feature.actions.some((action) => draft?.overrides[action.key])
                            "
                            :aria-label="`恢复${feature.name}角色默认`"
                            @click="
                              feature.actions.forEach((action) =>
                                setOverride(action.key, 'inherit'),
                              )
                            "
                            >恢复默认</el-button
                          >
                        </td>
                      </template>
                    </tr>
                  </template>
                </tbody>
              </table>
              <div v-if="!visibleFeatures.length" class="permission-empty">
                {{
                  isUser && personalView !== "all"
                    ? `当前模块没有${personalView === "extra" ? "额外授权" : "个人撤销"}，可切换模块或搜索功能。`
                    : "没有找到对应功能，请更换关键词。"
                }}
              </div>
            </div>
            <footer class="permission-footer">
              <span
                >当前 {{ visibleFeatures.length }} 个功能 ·
                {{ isUser ? savedPerson?.username : roleLabel(selectedRole) }}</span
              ><span>{{
                isUser
                  ? "“保存后 · 预览”展示当前编辑结果，点击保存授权后生效。"
                  : "角色调整影响当前组织内该角色的所有用户，保存后生效。"
              }}</span>
            </footer>
          </template>
          <div v-else-if="!loadingUser" class="permission-empty">请选择一个用户查看授权。</div>
        </div>
      </div>
      <div v-if="isUser" class="permission-legend">
        <span><i class="permission-tag inherited">角色默认</i>继承角色权限</span
        ><span><i class="permission-tag extra">额外授权</i>单独增加</span
        ><span><i class="permission-tag inherited">个人固定授权</i>固定保留已有权限</span
        ><span><i class="permission-tag denied">已撤销</i>单独禁止</span>
      </div>
      <el-dialog
        v-model="grantDialog"
        title="额外授权"
        width="min(680px, calc(100vw - 32px))"
        class="personal-grant-dialog"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <div class="grant-dialog-body">
          <p class="grant-dialog-intro">
            为 {{ savedPerson?.username }} 单独授权，只影响该用户。可选操作来自{{
              roleLabel(activeRole)
            }}的职责范围。
          </p>
          <nav class="grant-kind-tabs" aria-label="授权类型">
            <button :aria-pressed="grantKind === 'extra'" @click="grantKind = 'extra'">
              可额外授予 · {{ grantOptions.extra.length }}
            </button>
            <button :aria-pressed="grantKind === 'restore'" @click="grantKind = 'restore'">
              恢复已撤销 · {{ grantOptions.restore.length }}
            </button>
            <button :aria-pressed="grantKind === 'fixed'" @click="grantKind = 'fixed'">
              固定保留已有权限 · {{ grantOptions.fixed.length }}
            </button>
          </nav>
          <p class="grant-kind-help">
            {{
              grantKind === "extra"
                ? "以下操作角色默认未授予，可直接为此用户增加，无需取消任何已有权限。"
                : grantKind === "restore"
                  ? "以下操作原本属于角色默认，但当前被禁止。选中后将为此用户单独恢复允许。"
                  : "以下操作已经允许。固定授权只改变权限来源，当前可执行权限不增加；以后角色默认调整时仍保留。"
            }}
          </p>
          <el-input
            v-if="grantOptions[grantKind].length"
            v-model="grantQuery"
            aria-label="搜索可授权操作"
            placeholder="搜索功能或操作"
            clearable
          />
          <div v-if="grantChoices.length" class="grant-choice-list">
            <fieldset v-for="item in grantChoiceGroups" :key="item.key" class="grant-choice-group">
              <legend>{{ item.label }}</legend>
              <label v-for="action in item.actions" :key="action.key" class="grant-choice">
                <input
                  type="checkbox"
                  :checked="grantSelection.includes(action.key)"
                  :aria-label="`单独授予${action.name}${action.action}`"
                  @change="
                    toggleGrantSelection(action.key, ($event.target as HTMLInputElement).checked)
                  "
                />
                <span
                  ><strong>{{ action.name }} · {{ action.action }}</strong>
                  <small v-if="action.description">{{ action.description }}</small></span
                >
                <span class="grant-choice-state">{{
                  finalPermissions.includes(action.key) ? "允许 → 允许" : "禁止 → 允许"
                }}</span>
              </label>
            </fieldset>
          </div>
          <div v-else class="grant-empty" role="status">
            <template v-if="grantQuery.trim() && grantOptions[grantKind].length"
              >没有匹配的操作，请更换关键词。</template
            >
            <template v-else-if="grantKind === 'extra'">
              <strong>当前没有可新增的额外权限</strong>
              <p>
                该角色范围内的操作已由角色默认允许，或已为此用户额外授予。已有权限可切换到“固定保留已有权限”；被禁止的默认权限可在“恢复已撤销”中授予。
              </p>
            </template>
            <template v-else-if="grantKind === 'restore'">没有需要恢复的角色默认权限。</template>
            <template v-else>已有权限均已单独固定授权。</template>
          </div>
          <div v-if="selectedGrantKeys.length" class="grant-selection-preview" role="status">
            <span>已选择 {{ selectedGrantKeys.length }} 项，仅添加到当前用户的待保存改动。</span>
            <span v-if="relatedGrantKeys.length"
              >同时授予依赖操作：{{ relatedGrantKeys.map(permissionName).join("、") }}。</span
            >
          </div>
        </div>
        <template #footer>
          <el-button @click="grantDialog = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!selectedGrantKeys.length || locked || saving || loadingUser"
            @click="applyPersonalGrants"
            >添加到待保存授权</el-button
          >
        </template>
      </el-dialog>
    </template>
  </section>
</template>

<style scoped>
.permission-matrix {
  --line: #e1e8f2;
  --muted: #687e99;
  --blue: #2563eb;
  color: #23374f;
  min-height: 360px;
}
.permission-intro {
  padding: 16px 18px;
  margin-bottom: 20px;
  border: 1px solid #d7e5ff;
  background: #eff5ff;
  border-radius: 7px;
  color: #4b6a95;
  font-size: 13px;
  line-height: 1.7;
}
.permission-workspace {
  display: grid;
  grid-template-columns: 228px minmax(0, 1fr);
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
  background: #fff;
}
.entity-panel {
  background: #fafcff;
  padding: 20px 12px;
  border-right: 1px solid var(--line);
}
.entity-panel h3 {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
  margin: 0 12px 14px;
}
.entity-search {
  margin-bottom: 12px;
}
.identity-filter {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-bottom: 13px;
}
.identity-filter label {
  font-size: 11px;
  color: var(--muted);
}
.identity-filter select {
  width: 100%;
  font-size: 12px;
}
.directory-summary {
  font-size: 11px;
  color: var(--muted);
}
.user-directory {
  max-height: 420px;
  overflow-y: auto;
  padding-right: 3px;
  scrollbar-width: thin;
}
.identity-group + .identity-group {
  margin-top: 11px;
}
.identity-heading {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  min-height: 35px;
  padding: 6px 7px;
  border: 0;
  border-radius: 5px;
  background: #edf2f9;
  color: #4e6683;
  cursor: pointer;
  text-align: left;
}
.identity-heading strong {
  flex: 1;
  font-weight: 600;
  font-size: 12px;
}
.identity-chevron {
  font-size: 19px;
  line-height: 1;
  transform: rotate(0deg);
}
.identity-chevron.expanded {
  transform: rotate(90deg);
}
.identity-count {
  min-width: 21px;
  padding: 1px 5px;
  background: #fff;
  border-radius: 4px;
  font-size: 11px;
  text-align: center;
}
.identity-members {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 5px 0 0 10px;
}
.entity-button.user-entity {
  min-height: 38px;
  padding: 8px 10px;
  width: 100%;
}
.user-entity strong {
  font-size: 13px;
}
.user-inactive {
  margin-left: auto;
  font-size: 10px;
  color: var(--muted);
}
.group-more {
  border: 0;
  background: transparent;
  color: var(--blue);
  font-size: 11px;
  padding: 8px;
  text-align: left;
  cursor: pointer;
}
.entity-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.entity-button {
  text-align: left;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  padding: 13px 12px;
  min-height: 62px;
  color: #263c57;
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.entity-button:hover {
  background: #f0f5fd;
}
.entity-button[aria-pressed="true"] {
  background: #eaf1ff;
  border-color: #d1e0ff;
  color: var(--blue);
}
.entity-button strong {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.entity-button small {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
}
.dirty-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #bc7b14;
  flex-shrink: 0;
}
.permission-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.personal-instruction {
  padding: 13px 24px;
  font-size: 12px;
  color: #547093;
  background: #f7faff;
  border-bottom: 1px solid var(--line);
  line-height: 1.7;
}
.permission-search-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}
.permission-search-tools .el-button {
  flex-shrink: 0;
}
.personal-source-filters,
.grant-kind-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.personal-source-filters button,
.grant-kind-tabs button {
  border: 1px solid #dbe5f2;
  background: #fff;
  color: #4e6683;
  border-radius: 5px;
  font: inherit;
  padding: 7px 10px;
  cursor: pointer;
  min-height: 34px;
}
.personal-source-filters button[aria-pressed="true"],
.grant-kind-tabs button[aria-pressed="true"] {
  border-color: #bdceef;
  background: #edf3ff;
  color: #245bd0;
}
.personal-source-filters > span {
  margin-left: auto;
}
.grant-dialog-body {
  --blue: #2563eb;
  font-size: 13px;
  color: #2b4a72;
}
.grant-dialog-intro {
  margin: 0 0 16px;
  line-height: 1.8;
}
.grant-kind-tabs {
  margin-top: 0;
}
.grant-kind-help {
  padding: 12px 14px;
  background: #f4f7fc;
  border-radius: 5px;
  line-height: 1.8;
  color: #547093;
}
.grant-choice-list {
  max-height: 340px;
  overflow-y: auto;
  margin-top: 18px;
  padding-right: 4px;
}
.grant-choice-group {
  padding: 0;
  border: 0;
  margin: 0 0 18px;
  min-width: 0;
}
.grant-choice-group legend {
  color: #687e99;
  font-size: 12px;
  padding: 0 0 8px;
}
.grant-choice {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  align-items: start;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e1e8f2;
  border-radius: 6px;
  cursor: pointer;
  margin-top: 6px;
}
.grant-choice:has(input:checked) {
  border-color: #bdceef;
  background: #f7faff;
}
.grant-choice input {
  margin: 2px 0 0;
}
.grant-choice strong {
  font-weight: 500;
  line-height: 1.6;
}
.grant-choice small {
  display: block;
  color: #687e99;
  line-height: 1.7;
  margin-top: 4px;
}
.grant-choice-state {
  color: #16746a;
  font-size: 12px;
  white-space: nowrap;
}
.grant-empty {
  padding: 24px 16px;
  background: #fafcff;
  border: 1px dashed #d6e2f2;
  border-radius: 6px;
  line-height: 1.8;
}
.grant-empty p {
  margin: 8px 0 0;
  color: #687e99;
}
.grant-selection-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  margin-top: 16px;
  color: #815e1e;
  background: #fff9ed;
  border-radius: 5px;
  line-height: 1.8;
}
.personal-save-preview {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  padding: 13px 24px;
  background: #fff9ed;
  color: #815e1e;
  border-bottom: 1px solid #efe3c9;
  font-size: 12px;
  line-height: 1.8;
}
.permission-state-line {
  display: flex;
  gap: 7px;
  align-items: center;
  flex-wrap: wrap;
  margin: 5px 0;
  font-size: 12px;
}
.permission-state-line strong {
  font-size: 12px;
}
.state-allowed,
.source-granted {
  color: #16746a !important;
}
.state-forbidden,
.source-denied {
  color: #b63b3c !important;
}
.personal-operation {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 8px 0;
}
.personal-operation label {
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 28px;
  cursor: pointer;
}
.personal-operation small {
  padding-left: 23px;
}
.permission-header {
  padding: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.permission-header h3 {
  font-size: 20px;
  font-weight: 650;
  margin: 0;
}
.permission-header p {
  font-size: 12px;
  color: var(--muted);
  margin: 7px 0 0;
}
.save-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.save-tools :deep(.el-button + .el-button) {
  margin-left: 0;
}
.save-state {
  font-size: 12px;
  color: var(--muted);
}
.save-state.pending {
  color: #98640b;
}
.permission-toolbar {
  padding: 18px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--line);
}
.feature-search {
  max-width: 300px;
}
.user-role-select {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  flex-shrink: 0;
  color: var(--muted);
}
select {
  border: 1px solid #d6e2f2;
  padding: 8px 10px;
  border-radius: 5px;
  background: #fff;
  color: #2b4a72;
  font: inherit;
  min-height: 36px;
  cursor: pointer;
}
.protected-note {
  margin: 0;
  padding: 12px 24px;
  background: #fffaf0;
  color: #8c671a;
  font-size: 12px;
}
.permission-groups {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  padding: 16px 24px;
  border-bottom: 1px solid var(--line);
}
.permission-groups button {
  border: 1px solid transparent;
  border-radius: 5px;
  background: #f3f6fa;
  color: #627790;
  padding: 8px 11px;
  font-size: 12px;
  cursor: pointer;
}
.permission-groups button[aria-pressed="true"] {
  border-color: #cfddff;
  color: var(--blue);
  background: #edf3ff;
}
.permission-table-wrap {
  overflow-x: auto;
}
.permission-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  text-align: left;
}
.permission-table th {
  color: var(--muted);
  background: #f7faff;
  font-size: 12px;
  font-weight: 500;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
}
.permission-table td {
  padding: 20px 18px;
  border-bottom: 1px solid #eaf0f7;
  height: 72px;
}
.permission-table th:first-child {
  width: 30%;
}
.user-permission-table {
  min-width: 860px;
}
.user-permission-table th:first-child {
  width: 18%;
}
.user-permission-table th:nth-child(2) {
  width: 14%;
}
.user-permission-table th:nth-child(3) {
  width: 19%;
}
.user-permission-table th:nth-child(4) {
  width: 14%;
}
.user-permission-table th:nth-child(5) {
  width: 25%;
}
.user-permission-table th:nth-child(6) {
  width: 10%;
}
.permission-table td strong {
  display: block;
  font-weight: 500;
}
.permission-table td small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-top: 5px;
}
.role-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}
.role-actions label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  min-height: 32px;
}
input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--blue);
  cursor: pointer;
}
.permission-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.permission-tag {
  display: inline-block;
  font-size: 11px;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 4px 7px;
  font-style: normal;
  white-space: nowrap;
}
.permission-tag.inherited {
  color: #13736c;
  background: #eaf5f1;
  border-color: #d0eae1;
}
.permission-tag.extra,
.permission-tag.effective {
  color: #245bd0;
  background: #edf3ff;
  border-color: #d5e3ff;
}
.permission-tag.denied {
  color: #b93836;
  background: #fff1ef;
  border-color: #f6dcd8;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
.adjustment-row td {
  background: #f7faff;
  height: auto;
}
.adjustment-row fieldset {
  border: 0;
  padding: 0;
  min-width: 0;
}
.adjustment-row legend {
  color: #3b577d;
  font-size: 12px;
  margin-bottom: 8px;
}
.adjustment-control {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 10px 0;
  flex-wrap: wrap;
}
.adjustment-control label {
  min-width: 50px;
}
.adjustment-control select {
  min-width: 155px;
}
.permission-footer {
  background: #fcfdff;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 24px;
  margin-top: auto;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
  flex-wrap: wrap;
}
.permission-legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 16px;
  color: var(--muted);
  font-size: 12px;
}
.permission-legend i {
  margin-right: 5px;
}
.permission-empty {
  text-align: center;
  padding: 48px 20px;
  color: var(--muted);
  font-size: 13px;
}
.empty-users {
  padding: 16px 10px;
}
.load-error {
  padding: 24px;
  display: flex;
  gap: 18px;
  align-items: center;
  color: #b93836;
}
.user-pagination {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  font-size: 11px;
  color: var(--muted);
}
button:focus-visible,
select:focus-visible,
input:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 3px;
}
button:disabled,
select:disabled {
  cursor: not-allowed;
}
@media (max-width: 1000px) {
  .permission-workspace {
    grid-template-columns: 200px minmax(0, 1fr);
  }
  .permission-header {
    padding: 20px;
  }
  .permission-toolbar {
    flex-wrap: wrap;
  }
}
@media (max-width: 640px) {
  .permission-search-tools {
    width: 100%;
    flex-basis: 100%;
  }
  .personal-source-filters > span {
    margin-left: 0;
  }
  .grant-choice {
    grid-template-columns: 16px minmax(0, 1fr);
  }
  .grant-choice-state {
    grid-column: 2;
  }
  .permission-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .entity-panel {
    border-right: 0;
    border-bottom: 1px solid var(--line);
    padding: 12px;
  }
  .entity-panel h3 {
    margin-left: 0;
  }
  .entity-list {
    flex-direction: row;
    overflow-x: auto;
  }
  .entity-button {
    min-width: 128px;
  }
  .user-directory {
    display: flex;
    gap: 9px;
    overflow-x: auto;
    max-height: 240px;
  }
  .identity-group {
    min-width: 156px;
    margin-top: 0 !important;
    flex-shrink: 0;
  }
  .identity-members {
    padding-left: 0;
  }
  .identity-filter {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
  }
  .identity-filter select {
    width: auto;
    flex: 1;
    min-width: 120px;
  }
  .directory-summary {
    width: 100%;
  }
  .permission-header,
  .permission-toolbar,
  .permission-groups {
    padding: 16px;
  }
  .feature-search {
    max-width: none;
  }
  .permission-table th,
  .permission-table td {
    padding: 14px;
  }
  .permission-header h3 {
    font-size: 18px;
  }
  .save-tools {
    gap: 4px;
  }
  .permission-intro {
    font-size: 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .entity-button {
    transition: none;
  }
}
</style>
