<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAlertStore } from "@/stores/alert.store";
import { usePagination } from "@/composables/usePagination";
import { ElMessage, ElMessageBox } from "element-plus";

const store = useAlertStore();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = ref({ status: "", severity: "" });

onMounted(() => {
  fetchData();
});

async function fetchData() {
  await store.fetchAlerts({
    page: page.value,
    size: pageSize.value,
    status: filters.value.status || undefined,
    severity: filters.value.severity || undefined,
  });
  total.value = store.total;
}

function handleSearch() {
  resetPage();
  fetchData();
}

function handleReset() {
  filters.value = { status: "", severity: "" };
  resetPage();
  fetchData();
}

function handleSizeChange(val: number) {
  onSizeChange(val);
  fetchData();
}

function handleCurrentChange(val: number) {
  onPageChange(val);
  fetchData();
}

function handleResolve(id: string) {
  ElMessageBox.confirm('确认已审阅并消除该异常告警吗？', '消除警告', {
    confirmButtonText: '强制消除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await store.resolveAlert(id);
      ElMessage.success('告警已标记为解决');
    } catch (e: any) {
      ElMessage.error('消除失败，请重试');
    }
  }).catch(() => {});
}

const getSeverityType = (severity: string) => {
  const map: Record<string, "info"|"primary"|"success"|"danger"|"warning"> = {
    info: "info",
    warning: "warning",
    error: "danger",
    critical: "danger", // custom styling via css could also be done
  };
  return map[severity] || "info";
};

const getStatusType = (status: string) => {
  return status === 'resolved' ? 'success' : 'danger';
};
</script>

<template>
  <div class="page-container">
    <div class="header">
      <div>
        <h2 class="title">系统异常与告警管理</h2>
        <p class="subtitle">追踪及排查 AI 检测稳定性异常及其他运行阻碍</p>
      </div>
    </div>

    <!-- Filters -->
    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline class="filter-form">
        <el-form-item label="告警状态">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width: 140px">
            <el-option label="未处理 (Open)" value="open" />
            <el-option label="已消除 (Resolved)" value="resolved" />
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
          <el-button type="primary" @click="handleSearch">过滤器查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Table -->
    <el-card shadow="never" class="table-card">
      <el-table :data="store.items" v-loading="store.loading" border stripe style="width: 100%">
        <el-table-column prop="title" label="告警信息标题" min-width="250" show-overflow-tooltip />
        <el-table-column prop="alert_type" label="类型" width="140" />
        <el-table-column prop="severity" label="严重程度" width="120">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)" disable-transitions>
              {{ row.severity.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="现时状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" effect="dark" disable-transitions>
              {{ row.status.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="触发时间" width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="resolved_at" label="根因消除时间" width="180">
          <template #default="{ row }">
            {{ row.resolved_at ? new Date(row.resolved_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="动作面板" width="120" fixed="right">
          <template #default="{ row }">
            <el-button 
              v-if="row.status === 'open'" 
              link 
              type="primary" 
              @click="handleResolve(row.id)">
              消除告警
            </el-button>
            <span v-else class="text-xs text-gray-500">已闭环</span>
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
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background-color: #f3f4f6;
  min-height: 100vh;
}

.header {
  margin-bottom: 24px;
}

.title {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
}

.mb-4 {
  margin-bottom: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
}

.text-xs { font-size: 0.75rem; }
.text-gray-500 { color: #6b7280; }
</style>
