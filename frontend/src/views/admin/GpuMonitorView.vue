<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { useGpuInfraStore } from "@/stores/gpu-infra.store";
import type { GpuComputeNode } from "@/types/gpu-infra.types";

const store = useGpuInfraStore();
const drawerOpen = ref(false);
const editingId = ref("");
const testingId = ref("");
const refreshingId = ref("");
const search = ref("");
const statusFilter = ref("all");
const autoRefresh = ref(false);
const detailNode = ref<GpuComputeNode | null>(null);
let refreshTimer: ReturnType<typeof setInterval> | null = null;
const form = reactive({
  name: "",
  host: "",
  ssh_port: 22,
  ssh_username: "",
  ssh_password: "",
  ssh_private_key: "",
  total_gpu_count: 1,
  metadata_json: "{}",
});

const summaryCards = computed(() => [
  { label: "节点总数", value: store.items.length },
  { label: "在线节点", value: store.onlineCount },
  { label: "GPU 总数", value: store.totalGpuCount },
  { label: "已分配 GPU", value: store.allocatedGpuCount },
]);

const filteredItems = computed(() =>
  store.items.filter((item) => {
    const keyword = search.value.trim().toLowerCase();
    const statusMatched = statusFilter.value === "all" || item.status === statusFilter.value;
    const keywordMatched = !keyword || item.name.toLowerCase().includes(keyword) || item.host.toLowerCase().includes(keyword);
    return statusMatched && keywordMatched;
  }),
);

const detailDrawerOpen = computed({
  get: () => Boolean(detailNode.value),
  set: (open: boolean) => {
    if (!open) detailNode.value = null;
  },
});

function resetForm() {
  editingId.value = "";
  Object.assign(form, {
    name: "",
    host: "",
    ssh_port: 22,
    ssh_username: "",
    ssh_password: "",
    ssh_private_key: "",
    total_gpu_count: 1,
    metadata_json: "{}",
  });
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  Object.assign(form, {
    name: row.name,
    host: row.host,
    ssh_port: row.ssh_port,
    ssh_username: row.ssh_username,
    ssh_password: "",
    ssh_private_key: "",
    total_gpu_count: row.total_gpu_count,
    metadata_json: JSON.stringify(row.metadata_json || {}, null, 2),
  });
  drawerOpen.value = true;
}

async function submit() {
  let metadataJson: Record<string, unknown> = {};
  try {
    metadataJson = form.metadata_json ? JSON.parse(form.metadata_json) : {};
  } catch {
    ElMessage.error("元数据 JSON 解析失败");
    return;
  }
  const payload = {
    name: form.name,
    host: form.host,
    ssh_port: form.ssh_port,
    ssh_username: form.ssh_username,
    ssh_password: form.ssh_password || null,
    ssh_private_key: form.ssh_private_key || null,
    total_gpu_count: form.total_gpu_count,
    metadata_json: metadataJson,
  };
  if (editingId.value) {
    await store.updateOne(editingId.value, payload);
    ElMessage.success("GPU 节点已更新");
  } else {
    await store.createOne(payload);
    ElMessage.success("GPU 节点已创建");
  }
  drawerOpen.value = false;
}

async function remove(id: string) {
  await ElMessageBox.confirm("确定删除该 GPU 节点吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  await store.removeOne(id);
  ElMessage.success("GPU 节点已删除");
}

async function testConnection(id: string) {
  testingId.value = id;
  try {
    const result = await store.testConnection(id);
    if (result.success) ElMessage.success(result.message || "SSH 连接成功");
    else ElMessage.error(result.message || "SSH 连接失败");
  } finally {
    testingId.value = "";
  }
}

async function refreshMetrics(id: string) {
  refreshingId.value = id;
  try {
    await store.refreshMetrics(id);
    ElMessage.success("节点指标已刷新");
  } finally {
    refreshingId.value = "";
  }
}

async function toggleEnabled(row: any) {
  await store.toggleEnabled(row.id, row.status === "disabled");
  ElMessage.success(row.status === "disabled" ? "节点已启用" : "节点已禁用");
}

function openDetail(row: GpuComputeNode) {
  detailNode.value = row;
}

function statusText(row: GpuComputeNode) {
  if (row.status === "disabled") return "已禁用";
  if (row.probe_status === "ssh_failed") return "SSH 失败";
  if (row.probe_status === "probe_failed") return "探针失败";
  if (row.status === "offline") return "离线/心跳超时";
  if (row.status === "online") return "在线";
  return row.status;
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function syncAutoRefresh() {
  stopAutoRefresh();
  if (!autoRefresh.value) return;
  refreshTimer = setInterval(() => {
    store.fetchAll().catch(() => {});
  }, 15000);
}

onMounted(() => {
  store.fetchAll();
});
watch(autoRefresh, syncAutoRefresh);
onBeforeUnmount(stopAutoRefresh);
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-zinc-900">GPU 调度</h2>
        <p class="mt-2 text-sm text-zinc-500">管理 SSH 裸机 GPU 节点，供训练、微调和离线评测调度使用。</p>
      </div>
      <div class="flex gap-3">
        <el-switch v-model="autoRefresh" active-text="自动刷新" inactive-text="手动刷新" />
        <el-button @click="store.fetchAll()" :loading="store.loading">刷新列表</el-button>
        <el-button type="primary" @click="openCreate">新增节点</el-button>
      </div>
    </div>

    <section class="grid gap-4 md:grid-cols-4">
      <el-card v-for="item in summaryCards" :key="item.label" shadow="never">
        <div class="text-sm text-zinc-500">{{ item.label }}</div>
        <div class="mt-2 text-2xl font-semibold text-zinc-900">{{ item.value }}</div>
      </el-card>
    </section>

    <el-card shadow="never">
      <div class="mb-4 flex flex-wrap gap-3">
        <el-input v-model="search" placeholder="按节点名或主机搜索" clearable class="max-w-sm" />
        <el-select v-model="statusFilter" class="w-44">
          <el-option label="全部状态" value="all" />
          <el-option label="在线" value="online" />
          <el-option label="离线" value="offline" />
          <el-option label="错误" value="error" />
          <el-option label="禁用" value="disabled" />
        </el-select>
      </div>
      <el-table :data="filteredItems" v-loading="store.loading">
        <el-table-column prop="name" label="节点名" min-width="140" />
        <el-table-column prop="host" label="主机" min-width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : row.status === 'disabled' ? 'info' : row.status === 'error' ? 'danger' : 'warning'">
              {{ statusText(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_gpu_count" label="GPU 总数" width="90" />
        <el-table-column prop="available_gpu_count" label="可用 GPU" width="90" />
        <el-table-column label="GPU 使用率" width="110">
          <template #default="{ row }">{{ row.gpu_usage ?? "-" }}</template>
        </el-table-column>
        <el-table-column label="CPU" width="90">
          <template #default="{ row }">{{ row.cpu_usage ?? "-" }}</template>
        </el-table-column>
        <el-table-column label="内存" width="90">
          <template #default="{ row }">{{ row.memory_usage ?? "-" }}</template>
        </el-table-column>
        <el-table-column prop="last_heartbeat" label="最后心跳" min-width="180" />
        <el-table-column label="最近探针" min-width="180">
          <template #default="{ row }">{{ row.last_probe_at || "-" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="360" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="testConnection(row.id)" :loading="testingId === row.id">测试连接</el-button>
            <el-button link type="primary" @click="refreshMetrics(row.id)" :loading="refreshingId === row.id">刷新指标</el-button>
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="toggleEnabled(row)">{{ row.status === "disabled" ? "启用" : "禁用" }}</el-button>
            <el-button link type="danger" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑 GPU 节点' : '新增 GPU 节点'" size="520px">
      <el-form label-position="top">
        <el-form-item label="节点名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="主机"><el-input v-model="form.host" /></el-form-item>
        <el-form-item label="SSH 端口"><el-input-number v-model="form.ssh_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="SSH 用户名"><el-input v-model="form.ssh_username" /></el-form-item>
        <el-form-item label="SSH 密码"><el-input v-model="form.ssh_password" type="password" show-password /></el-form-item>
        <el-form-item label="SSH 私钥"><el-input v-model="form.ssh_private_key" type="textarea" :rows="5" placeholder="可选；密码和私钥至少填写一种" /></el-form-item>
        <el-form-item label="GPU 总数"><el-input-number v-model="form.total_gpu_count" :min="1" :max="64" /></el-form-item>
        <el-form-item label="元数据 JSON"><el-input v-model="form.metadata_json" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerOpen = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-drawer>

    <el-drawer v-model="detailDrawerOpen" title="节点详情" size="560px" @close="detailNode = null">
      <template v-if="detailNode">
        <div class="flex flex-col gap-4">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="节点">{{ detailNode.name }}</el-descriptions-item>
            <el-descriptions-item label="主机">{{ detailNode.host }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ statusText(detailNode) }}</el-descriptions-item>
            <el-descriptions-item label="最近探针">{{ detailNode.last_probe_at || "-" }}</el-descriptions-item>
            <el-descriptions-item label="最近错误">{{ detailNode.last_probe_error || "-" }}</el-descriptions-item>
          </el-descriptions>
          <el-card shadow="never">
            <template #header>主机摘要</template>
            <pre class="overflow-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">{{ JSON.stringify(detailNode.hardware_summary || {}, null, 2) }}</pre>
          </el-card>
          <el-card shadow="never">
            <template #header>GPU 明细</template>
            <el-empty v-if="!(detailNode.gpu_devices || []).length" description="暂无 GPU 明细" />
            <el-table v-else :data="detailNode.gpu_devices || []">
              <el-table-column prop="index" label="卡号" width="80" />
              <el-table-column prop="name" label="型号" min-width="180" />
              <el-table-column prop="memory_total_mb" label="总显存(MB)" width="120" />
              <el-table-column prop="memory_used_mb" label="已用显存(MB)" width="120" />
              <el-table-column prop="utilization_gpu" label="利用率" width="100" />
            </el-table>
          </el-card>
        </div>
      </template>
    </el-drawer>
  </div>
</template>
