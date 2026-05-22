<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAlertStore } from "@/stores/alert.store";
import { usePagination } from "@/composables/usePagination";
import { ElMessage, ElMessageBox } from "element-plus";
import type { AlertStatus } from "@/types/alert.types";
import { severityLabel, SEVERITY_TAG_TYPES } from "@/constants/spec";

const store = useAlertStore();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = ref({ status: "", severity: "" });
const suppressDialogVisible = ref(false);
const suppressTargetId = ref("");
const suppressNote = ref("");

onMounted(() => fetchData());

async function fetchData() {
  await store.fetchAlerts({
    page: page.value,
    size: pageSize.value,
    status: filters.value.status || undefined,
    severity: filters.value.severity || undefined,
  });
  total.value = store.total;
}

function handleSearch() { resetPage(); fetchData(); }
function handleReset() { filters.value = { status: "", severity: "" }; resetPage(); fetchData(); }
function handleSizeChange(val: number) { onSizeChange(val); fetchData(); }
function handleCurrentChange(val: number) { onPageChange(val); fetchData(); }

async function handleAck(id: string) {
  try {
    await store.ackAlert(id);
    ElMessage.success("已确认告警");
  } catch { ElMessage.error("确认失败"); }
}

function openSuppressDialog(id: string) {
  suppressTargetId.value = id;
  suppressNote.value = "";
  suppressDialogVisible.value = true;
}

async function confirmSuppress() {
  if (!suppressNote.value.trim()) { ElMessage.warning("压制原因为必填项"); return; }
  try {
    await store.suppressAlert(suppressTargetId.value, suppressNote.value);
    ElMessage.success("告警已压制");
    suppressDialogVisible.value = false;
  } catch { ElMessage.error("压制失败"); }
}
function handleResolve(id: string) {
  ElMessageBox.confirm("确认已审阅并消除该异常告警吗？", "消除告警", {
    confirmButtonText: "确认消除",
    cancelButtonText: "取消",
    type: "warning",
  }).then(async () => {
    try {
      await store.resolveAlert(id);
      ElMessage.success("告警已解决");
    } catch { ElMessage.error("消除失败"); }
  }).catch(() => {});
}

const canAct = (status: string) => status === "open" || status === "acknowledged";

const getSeverityType = (severity: string) => {
  return (SEVERITY_TAG_TYPES[severity] as "info"|"danger"|"warning") || "info";
};

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    open: "待处理", acknowledged: "已确认", suppressed: "已压制", resolved: "已解决",
  };
  return map[status] || status;
};

const getStatusType = (status: string) => {
  const map: Record<string, "danger" | "warning" | "info" | "success"> = {
    open: "danger", acknowledged: "warning", suppressed: "info", resolved: "success",
  };
  return map[status] || "info";
};
</script>

<template>
  <div class="alert-tab-root">
    <!-- Filters -->
    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline class="filter-form">
        <el-form-item label="告警状态">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width: 140px">
            <el-option label="待处理" value="open" />
            <el-option label="已确认" value="acknowledged" />
            <el-option label="已压制" value="suppressed" />
            <el-option label="已解决" value="resolved" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重程度">
          <el-select v-model="filters.severity" placeholder="全部" clearable style="width: 140px">
            <el-option label="普通 (Info)" value="info" />
            <el-option label="警告 (Warning)" value="warning" />
            <el-option label="错误 (Error)" value="error" />
            <el-option label="严重 (Critical)" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Table -->
    <el-card shadow="never">
      <el-table :data="store.items" v-loading="store.loading" border stripe style="width: 100%">
        <el-table-column prop="title" label="告警标题" min-width="250" show-overflow-tooltip />
        <el-table-column prop="alert_type" label="类型" width="140" />
        <el-table-column prop="severity" label="严重程度" width="110">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)" disable-transitions>{{ severityLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" effect="dark" disable-transitions>{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="触发时间" width="170">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : "-" }}</template>
        </el-table-column>
        <el-table-column prop="action_note" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <template v-if="canAct(row.status)">
              <el-button v-if="row.status === 'open'" link type="primary" @click="handleAck(row.id)">确认</el-button>
              <el-button link type="warning" @click="openSuppressDialog(row.id)">压制</el-button>
              <el-button link type="success" @click="handleResolve(row.id)">解决</el-button>
            </template>
            <span v-else class="closed-label">{{ getStatusLabel(row.status) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper mt-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
    <!-- 压制备注弹窗 -->
    <el-dialog v-model="suppressDialogVisible" title="压制告警" width="440px" :close-on-click-modal="false">
      <el-form>
        <el-form-item label="压制原因" required>
          <el-input v-model="suppressNote" type="textarea" :rows="3" maxlength="1024" show-word-limit placeholder="请填写压制原因（必填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="suppressDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSuppress">确认压制</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.alert-tab-root { overflow: hidden; min-width: 0; }
.mb-4 { margin-bottom: 16px; }
.mt-4 { margin-top: 16px; }
.filter-form { display: flex; flex-wrap: wrap; align-items: flex-end; }
.pagination-wrapper { display: flex; justify-content: flex-end; }
.closed-label { font-size: 12px; color: #9ca3af; }
</style>
