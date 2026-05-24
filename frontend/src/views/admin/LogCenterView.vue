<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { logCenterApi } from "@/api/log-center.api";
import { ROLE_ADMIN } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import type { AuditLog, AuthLog } from "@/types/governance.types";

const auth = useAuthStore();

const authLogs = ref<AuthLog[]>([]);
const auditLogs = ref<AuditLog[]>([]);
const authLoading = ref(false);
const auditLoading = ref(false);
const authTotal = ref(0);
const auditTotal = ref(0);
const authPage = ref(1);
const auditPage = ref(1);
const pageSize = ref(20);
const activeTab = ref("auth");

const authFilters = reactive({
  user_id: "",
  event_type: "",
  ip_address: "",
  start_date: "",
  end_date: "",
});
const auditFilters = reactive({
  actor_id: "",
  resource_type: "",
  action: "",
  start_date: "",
  end_date: "",
});

const roles = computed(() => [...auth.roles, auth.role].filter(Boolean));
const canViewAuditLogs = computed(() => roles.value.includes(ROLE_ADMIN));
const canViewAuthLogs = computed(() => roles.value.includes(ROLE_ADMIN));

onMounted(async () => {
  if (canViewAuthLogs.value) {
    await fetchAuthLogs();
  }
  if (canViewAuditLogs.value) {
    await fetchAuditLogs();
  }
});

async function fetchAuthLogs() {
  authLoading.value = true;
  try {
    const { data } = await logCenterApi.listAuthLogs({
      page: authPage.value,
      size: pageSize.value,
      user_id: authFilters.user_id || undefined,
      event_type: authFilters.event_type || undefined,
      ip_address: authFilters.ip_address || undefined,
      start_date: authFilters.start_date || undefined,
      end_date: authFilters.end_date || undefined,
    });
    authLogs.value = data.data.items;
    authTotal.value = data.data.total;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载登录日志失败");
  } finally {
    authLoading.value = false;
  }
}

async function fetchAuditLogs() {
  auditLoading.value = true;
  try {
    const { data } = await logCenterApi.listAuditLogs({
      page: auditPage.value,
      size: pageSize.value,
      actor_id: auditFilters.actor_id || undefined,
      resource_type: auditFilters.resource_type || undefined,
      action: auditFilters.action || undefined,
      start_date: auditFilters.start_date || undefined,
      end_date: auditFilters.end_date || undefined,
    });
    auditLogs.value = data.data.items;
    auditTotal.value = data.data.total;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载审计日志失败");
  } finally {
    auditLoading.value = false;
  }
}

function resetAuthFilters() {
  authFilters.user_id = "";
  authFilters.event_type = "";
  authFilters.ip_address = "";
  authFilters.start_date = "";
  authFilters.end_date = "";
  authPage.value = 1;
  fetchAuthLogs();
}

function resetAuditFilters() {
  auditFilters.actor_id = "";
  auditFilters.resource_type = "";
  auditFilters.action = "";
  auditFilters.start_date = "";
  auditFilters.end_date = "";
  auditPage.value = 1;
  fetchAuditLogs();
}

function eventTagType(eventType: string) {
  if (eventType === "login") return "success";
  if (eventType === "login_failed") return "danger";
  if (eventType === "mfa_challenge") return "warning";
  return "info";
}

function eventLabel(eventType: string) {
  if (eventType === "login") return "登录";
  if (eventType === "login_failed") return "登录失败";
  if (eventType === "mfa_challenge") return "MFA 验证";
  if (eventType === "logout") return "登出";
  return eventType;
}

function formatDateTime(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">日志中心</h2>
      <p class="mt-2 text-sm text-zinc-500">统一查看登录日志和审计日志，支持按时间、用户、资源维度筛选。</p>
    </div>

    <div class="card-surface p-4">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="登录日志" name="auth" v-if="canViewAuthLogs">
          <div class="flex flex-col gap-4">
            <el-form inline class="flex flex-wrap gap-x-4 gap-y-2 items-end">
              <el-form-item label="用户 ID">
                <el-input v-model="authFilters.user_id" clearable class="!w-[220px]" size="small" />
              </el-form-item>
              <el-form-item label="事件类型">
                <el-select v-model="authFilters.event_type" clearable class="!w-[180px]" size="small">
                  <el-option label="登录" value="login" />
                  <el-option label="登录失败" value="login_failed" />
                </el-select>
              </el-form-item>
              <el-form-item label="IP">
                <el-input v-model="authFilters.ip_address" clearable class="!w-[180px]" size="small" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="small" @click="fetchAuthLogs">查询</el-button>
                <el-button size="small" @click="resetAuthFilters">重置</el-button>
              </el-form-item>
            </el-form>

            <el-table :data="authLogs" v-loading="authLoading" size="small" class="list-table">
              <el-table-column prop="username" label="用户名" min-width="160" />
              <el-table-column label="事件类型" width="120">
                <template #default="{ row }">
                  <el-tag :type="eventTagType(row.event_type)" effect="light">
                    {{ eventLabel(row.event_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="ip_address" label="IP" min-width="160" />
              <el-table-column label="结果" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.success ? 'success' : 'danger'" effect="light">
                    {{ row.success ? "成功" : "失败" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
              <el-table-column label="时间" min-width="180">
                <template #default="{ row }">{{ formatDateTime(row.occurred_at) }}</template>
              </el-table-column>
            </el-table>

            <div class="flex justify-end">
              <el-pagination
                background
                layout="total, prev, pager, next"
                :total="authTotal"
                :page-size="pageSize"
                :current-page="authPage"
                @current-change="(page) => { authPage = page; fetchAuthLogs(); }"
              />
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="审计日志" name="audit" v-if="canViewAuditLogs">
          <div class="flex flex-col gap-4">
            <el-form inline class="flex flex-wrap gap-x-4 gap-y-2 items-end">
              <el-form-item label="操作人 ID">
                <el-input v-model="auditFilters.actor_id" clearable class="!w-[220px]" size="small" />
              </el-form-item>
              <el-form-item label="资源类型">
                <el-input v-model="auditFilters.resource_type" clearable class="!w-[180px]" size="small" />
              </el-form-item>
              <el-form-item label="操作动作">
                <el-input v-model="auditFilters.action" clearable class="!w-[180px]" size="small" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="small" @click="fetchAuditLogs">查询</el-button>
                <el-button size="small" @click="resetAuditFilters">重置</el-button>
              </el-form-item>
            </el-form>

            <el-table :data="auditLogs" v-loading="auditLoading" size="small" class="list-table">
              <el-table-column prop="actor_id" label="操作人" min-width="180" />
              <el-table-column prop="actor_role" label="角色" width="140" />
              <el-table-column prop="resource_type" label="资源类型" min-width="160" />
              <el-table-column prop="action" label="动作" width="120" />
              <el-table-column prop="result_code" label="结果码" width="100" />
              <el-table-column prop="ip_address" label="IP" min-width="160" />
              <el-table-column label="时间" min-width="180">
                <template #default="{ row }">{{ formatDateTime(row.occurred_at) }}</template>
              </el-table-column>
            </el-table>

            <div class="flex justify-end">
              <el-pagination
                background
                layout="total, prev, pager, next"
                :total="auditTotal"
                :page-size="pageSize"
                :current-page="auditPage"
                @current-change="(page) => { auditPage = page; fetchAuditLogs(); }"
              />
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>
