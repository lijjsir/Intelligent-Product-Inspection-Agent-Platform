<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { approvalApi } from "@/api/approval.api";
import type { Approval } from "@/types/governance.types";

const loading = ref(false);
const detailLoading = ref(false);
const dialogOpen = ref(false);
const dialogMode = ref<"approve" | "reject">("approve");
const approvals = ref<Approval[]>([]);
const selectedApproval = ref<Approval | null>(null);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const reviewComment = ref("");

const filters = reactive({
  status: "",
  source_module: "",
  risk_level: "",
});

const summaryCards = computed(() => [
  { label: "待审批", value: approvals.value.filter((item) => item.status === "pending").length },
  { label: "已通过", value: approvals.value.filter((item) => item.status === "approved").length },
  { label: "已驳回", value: approvals.value.filter((item) => item.status === "rejected").length },
  { label: "当前页总数", value: approvals.value.length },
]);

onMounted(() => {
  fetchApprovals();
});

async function fetchApprovals() {
  loading.value = true;
  try {
    const { data } = await approvalApi.list({
      page: page.value,
      size: pageSize.value,
      status: filters.status || undefined,
      source_module: filters.source_module || undefined,
      risk_level: filters.risk_level || undefined,
    });
    approvals.value = data.data.items;
    total.value = data.data.total;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载审批列表失败");
  } finally {
    loading.value = false;
  }
}

async function openReview(row: Approval, mode: "approve" | "reject") {
  detailLoading.value = true;
  try {
    const { data } = await approvalApi.get(row.id);
    selectedApproval.value = data.data;
    dialogMode.value = mode;
    reviewComment.value = "";
    dialogOpen.value = true;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载审批详情失败");
  } finally {
    detailLoading.value = false;
  }
}

async function submitReview() {
  if (!selectedApproval.value) return;
  detailLoading.value = true;
  try {
    if (dialogMode.value === "approve") {
      await approvalApi.approve(selectedApproval.value.id, reviewComment.value || undefined);
      ElMessage.success("审批已通过");
    } else {
      await approvalApi.reject(selectedApproval.value.id, reviewComment.value || undefined);
      ElMessage.success("审批已驳回");
    }
    dialogOpen.value = false;
    await fetchApprovals();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "审批提交失败");
  } finally {
    detailLoading.value = false;
  }
}

function resetFilters() {
  filters.status = "";
  filters.source_module = "";
  filters.risk_level = "";
  page.value = 1;
  fetchApprovals();
}

function riskTagType(level: string) {
  if (level === "low") return "success";
  if (level === "medium") return "warning";
  return "danger";
}

function statusTagType(status: string) {
  if (status === "pending") return "warning";
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "info";
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function payloadPreview(value?: Record<string, unknown> | null) {
  if (!value) return "{}";
  return JSON.stringify(value, null, 2);
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">高风险审批</h2>
      <p class="mt-2 text-sm text-zinc-500">统一查看高风险操作复核单，当前支持记忆回滚的事后复核留痕。</p>
    </div>

    <section class="grid gap-4 md:grid-cols-4">
      <el-card v-for="item in summaryCards" :key="item.label" shadow="never">
        <div class="text-sm text-zinc-500">{{ item.label }}</div>
        <div class="mt-2 text-2xl font-semibold text-zinc-900">{{ item.value }}</div>
      </el-card>
    </section>

    <el-card shadow="never">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <el-select v-model="filters.status" clearable class="!w-[180px]" placeholder="状态">
          <el-option label="待审批" value="pending" />
          <el-option label="已通过" value="approved" />
          <el-option label="已驳回" value="rejected" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <el-input v-model="filters.source_module" clearable class="!w-[220px]" placeholder="来源模块" />
        <el-select v-model="filters.risk_level" clearable class="!w-[180px]" placeholder="风险等级">
          <el-option label="低" value="low" />
          <el-option label="中" value="medium" />
          <el-option label="高" value="high" />
          <el-option label="极高" value="critical" />
        </el-select>
        <el-button type="primary" @click="fetchApprovals">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table :data="approvals" v-loading="loading" size="small" class="list-table">
        <el-table-column prop="operation_summary" label="操作摘要" min-width="260" />
        <el-table-column prop="source_module" label="来源模块" width="160" />
        <el-table-column label="风险等级" width="110">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.risk_level)" effect="light">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="requester_role" label="申请角色" width="140" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" effect="light">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="申请时间" min-width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="openReview(row, 'approve')" :disabled="row.status !== 'pending'">通过</el-button>
            <el-button link type="danger" @click="openReview(row, 'reject')" :disabled="row.status !== 'pending'">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="(nextPage) => { page = nextPage; fetchApprovals(); }"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogOpen" :title="dialogMode === 'approve' ? '审批通过' : '审批驳回'" width="760px">
      <div v-if="selectedApproval" class="flex flex-col gap-4">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="来源模块">{{ selectedApproval.source_module }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">{{ selectedApproval.risk_level }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedApproval.status }}</el-descriptions-item>
          <el-descriptions-item label="申请角色">{{ selectedApproval.requester_role }}</el-descriptions-item>
          <el-descriptions-item label="操作摘要" :span="2">{{ selectedApproval.operation_summary }}</el-descriptions-item>
          <el-descriptions-item label="申请时间" :span="2">{{ formatDateTime(selectedApproval.created_at) }}</el-descriptions-item>
        </el-descriptions>
        <el-form label-position="top">
          <el-form-item label="审批评论">
            <el-input v-model="reviewComment" type="textarea" :rows="4" placeholder="填写审批意见（可选）" />
          </el-form-item>
          <el-form-item label="载荷摘要">
            <el-input :model-value="payloadPreview(selectedApproval.payload_json)" type="textarea" :rows="8" readonly />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button :type="dialogMode === 'approve' ? 'success' : 'danger'" :loading="detailLoading" @click="submitReview">
          {{ dialogMode === "approve" ? "确认通过" : "确认驳回" }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
