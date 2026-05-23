<script setup lang="ts">
import { Delete, InfoFilled, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { http } from "@/api/http";
import type { AdminMeetingRoom, MeetingRoomDetail } from "@/types/meeting.types";

const rooms = ref<AdminMeetingRoom[]>([]);
const loading = ref(false);
const total = ref(0);
const page = ref(1);
const size = ref(20);
const keyword = ref("");
const status = ref("");
const drawerOpen = ref(false);
const detail = ref<MeetingRoomDetail | null>(null);
const detailLoading = ref(false);

const pageParams = computed(() => ({ page: page.value, size: size.value, keyword: keyword.value || undefined, status: status.value || undefined }));

async function fetchRooms() {
  loading.value = true;
  try {
    const { data } = await http.get("/v1/admin/meetings/", { params: pageParams.value });
    const payload = data as { data?: { items?: AdminMeetingRoom[]; total?: number } };
    const body = payload.data || (payload as unknown as { items: AdminMeetingRoom[]; total: number });
    rooms.value = body.items || [];
    total.value = body.total || 0;
  } catch {
    ElMessage.error("获取会议室列表失败");
  } finally {
    loading.value = false;
  }
}

async function openDetail(roomId: string) {
  drawerOpen.value = true;
  detailLoading.value = true;
  try {
    const { data } = await http.get(`/v1/admin/meetings/${roomId}`);
    const payload = data as { data?: MeetingRoomDetail };
    detail.value = payload.data || null;
  } catch {
    ElMessage.error("获取详情失败");
  } finally {
    detailLoading.value = false;
  }
}

async function handleArchive(room: AdminMeetingRoom) {
  try {
    await ElMessageBox.confirm(
      `确定要归档会议室「${room.title}」吗？归档后用户将无法访问。`,
      "确认归档",
      { confirmButtonText: "归档", cancelButtonText: "取消", type: "warning" }
    );
    await http.delete(`/v1/admin/meetings/${room.id}`);
    ElMessage.success("已归档");
    await fetchRooms();
  } catch {
    // cancelled or error
  }
}

async function handleRemoveMember(roomId: string, userId: string) {
  try {
    await http.delete(`/v1/admin/meetings/${roomId}/members/${userId}`);
    ElMessage.success("已移除成员");
    await openDetail(roomId);
  } catch {
    ElMessage.error("移除成员失败");
  }
}

function onSearch() {
  page.value = 1;
  fetchRooms();
}

function onPageChange(p: number) {
  page.value = p;
  fetchRooms();
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { hour12: false });
}

onMounted(() => fetchRooms());
</script>

<template>
  <div class="meeting-admin">
    <div class="admin-header">
      <h1>会议管理</h1>
      <p class="admin-sub">管理所有会议室，包括归档、查看详情和移除成员。</p>
    </div>

    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索标题" clearable style="width: 240px" :prefix-icon="Search" @clear="onSearch" @keydown.enter="onSearch" />
      <el-select v-model="status" placeholder="状态" clearable style="width: 140px" @change="onSearch">
        <el-option label="活跃" value="active" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-button type="primary" @click="onSearch">搜索</el-button>
    </div>

    <el-table :data="rooms" v-loading="loading" stripe border style="width: 100%">
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="access_code" label="会议码" width="100" />
      <el-table-column prop="member_count" label="成员" width="70" align="center" />
      <el-table-column prop="agent_count" label="Agent" width="70" align="center" />
      <el-table-column prop="message_count" label="消息" width="70" align="center" />
      <el-table-column prop="created_by_username" label="创建者" width="120" />
      <el-table-column prop="status" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status === 'active' ? '活跃' : row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" :icon="InfoFilled" @click="openDetail(row.id)">详情</el-button>
          <el-button text type="danger" :icon="Delete" @click="handleArchive(row)">归档</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="onPageChange"
      />
    </div>

    <!-- Detail drawer -->
    <el-drawer v-model="drawerOpen" title="会议室详情" size="480px">
      <div v-if="detailLoading" v-loading="detailLoading" style="min-height: 200px" />
      <template v-else-if="detail">
        <div class="detail-section">
          <h3>基本信息</h3>
          <p><strong>标题：</strong>{{ detail.title }}</p>
          <p><strong>会议码：</strong>{{ detail.access_code }}</p>
          <p><strong>成员数：</strong>{{ detail.member_count }}</p>
          <p><strong>Agent 数：</strong>{{ detail.agent_count || 0 }}</p>
        </div>
        <div v-if="detail.agents?.length" class="detail-section">
          <h3>Agent 列表</h3>
          <div v-for="agent in detail.agents" :key="agent.id" class="detail-chip">
            <span class="agent-tag">AI</span>
            {{ agent.agent_name }}
            <span class="detail-role">{{ agent.role }}</span>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.meeting-admin {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.admin-header h1 {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.admin-sub {
  margin-top: 4px;
  color: #71717a;
  font-size: 13px;
}

.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pager {
  display: flex;
  justify-content: flex-end;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h3 {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.detail-section p {
  font-size: 13px;
  color: #52525b;
  line-height: 1.8;
}

.detail-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  font-size: 13px;
}

.agent-tag {
  font-size: 10px;
  font-weight: 700;
  color: #2563eb;
  background: #dbeafe;
  padding: 1px 5px;
  border-radius: 4px;
}

.detail-role {
  margin-left: auto;
  color: #a1a1aa;
  font-size: 11px;
}
</style>
