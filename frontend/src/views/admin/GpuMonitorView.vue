<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { useGpuInfraStore } from "@/stores/gpu-infra.store";

const store = useGpuInfraStore();
const drawerOpen = ref(false);
const editingId = ref("");
const testingId = ref("");
const refreshingId = ref("");
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

onMounted(() => {
  store.fetchAll();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-zinc-900">GPU 调度</h2>
        <p class="mt-2 text-sm text-zinc-500">管理 SSH 裸机 GPU 节点，供训练、微调和离线评测调度使用。</p>
      </div>
      <div class="flex gap-3">
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
      <el-table :data="store.items" v-loading="store.loading">
        <el-table-column prop="name" label="节点名" min-width="140" />
        <el-table-column prop="host" label="主机" min-width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : row.status === 'disabled' ? 'info' : row.status === 'error' ? 'danger' : 'warning'">
              {{ row.status }}
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
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="testConnection(row.id)" :loading="testingId === row.id">测试连接</el-button>
            <el-button link type="primary" @click="refreshMetrics(row.id)" :loading="refreshingId === row.id">刷新指标</el-button>
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
  </div>
</template>
