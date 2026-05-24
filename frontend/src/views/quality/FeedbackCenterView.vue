<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useFeedbackStore } from "@/stores/feedback.store";
import { useAuthStore } from "@/stores/auth.store";
import { usePagination } from "@/composables/usePagination";
import type { FeedbackCategory, FeedbackSeverity, FeedbackSourceType, FeedbackStatus, ResultFeedback } from "@/types/governance.types";

const store = useFeedbackStore();
const auth = useAuthStore();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const activeTab = ref<"all" | "pending" | "high_risk" | "mine">("all");
const drawerVisible = ref(false);
const detailLoading = ref(false);
const resolveDialogVisible = ref(false);
const assignDialogVisible = ref(false);
const reopenDialogVisible = ref(false);
const showAdvancedFilter = ref(false);
const resolveForm = ref({ resolution: "" });
const assignForm = ref({ assigned_to: "" });
const reopenForm = ref({ reason: "" });
const operatingId = ref("");
const detailTab = ref("content");
const filterForm = ref<{
  status: FeedbackStatus | "";
  severity: FeedbackSeverity | "";
  source_type: FeedbackSourceType | "";
  category: FeedbackCategory | "";
  date_range: string[];
}>({
  status: "",
  severity: "",
  source_type: "",
  category: "",
  date_range: [],
});

const summaryCards = computed(() => {
  const s = store.summary;
  return [
    { label: "今日新增", value: s?.today_new ?? 0, key: "new" },
    { label: "待处理", value: s?.pending_count ?? 0, key: "pending" },
    { label: "高风险", value: s?.high_risk_count ?? 0, key: "high" },
    { label: "已解决率", value: s ? `${Math.round(s.resolved_rate * 100)}%` : "0%", key: "rate" },
    { label: "平均处理时长", value: s?.avg_resolution_hours != null ? `${s.avg_resolution_hours}h` : "--", key: "time" },
  ];
});

const cardVars: Record<string, { accent: string; bg: string }> = {
  new: { accent: "#409eff", bg: "#ecf5ff" },
  pending: { accent: "#e6a23c", bg: "#fdf6ec" },
  high: { accent: "#f56c6c", bg: "#fef0f0" },
  rate: { accent: "#67c23a", bg: "#f0f9eb" },
  time: { accent: "#909399", bg: "#f4f4f5" },
};

const statusMap: Record<FeedbackStatus, { label: string; type: "" | "warning" | "success" | "info" | "danger" }> = {
  pending: { label: "待处理", type: "warning" },
  processing: { label: "处理中", type: "" },
  resolved: { label: "已解决", type: "success" },
  closed: { label: "已关闭", type: "info" },
  reopened: { label: "重新打开", type: "danger" },
};

const severityMap: Record<FeedbackSeverity, { label: string; type: "" | "warning" | "success" | "info" | "danger" }> = {
  low: { label: "低", type: "info" },
  medium: { label: "中", type: "warning" },
  high: { label: "高", type: "danger" },
  critical: { label: "严重", type: "danger" },
};

const sourceMap: Record<FeedbackSourceType, string> = {
  result: "检测结果",
  chat: "AI 对话",
  meeting: "会议消息",
};

const categoryMap: Record<string, string> = {
  reliable: "真实可靠",
  wrong_verdict: "判定错误",
  weak_evidence: "证据不足",
  bad_bbox: "定位不准",
  unclear_reasoning: "描述模糊",
};

onMounted(() => {
  store.fetchSummary();
  fetchData();
});

watch([activeTab, filterForm], () => {
  resetPage();
  fetchData();
}, { deep: true });

async function fetchData() {
  const query: Record<string, any> = {
    page: page.value,
    size: pageSize.value,
  };
  if (activeTab.value === "pending") query.status = "pending";
  if (activeTab.value === "high_risk") query.severity = "high";
  if (activeTab.value === "mine") query.assigned_to = auth.userId;
  if (filterForm.value.status) query.status = filterForm.value.status;
  if (filterForm.value.severity) query.severity = filterForm.value.severity;
  if (filterForm.value.source_type) query.source_type = filterForm.value.source_type;
  if (filterForm.value.category) query.category = filterForm.value.category;
  await store.fetchList(query);
  total.value = store.total;
}

function handlePageChange(val: number) {
  onPageChange(val);
  fetchData();
}

function handleSizeChange(val: number) {
  onSizeChange(val);
  fetchData();
}

function handleReset() {
  filterForm.value = { status: "", severity: "", source_type: "", category: "", date_range: [] };
  activeTab.value = "all";
  resetPage();
  fetchData();
}

async function openDetail(row: ResultFeedback) {
  detailLoading.value = true;
  drawerVisible.value = true;
  detailTab.value = "content";
  try {
    await store.fetchDetail(row.id);
  } finally {
    detailLoading.value = false;
  }
}

function openResolveDialog(id: string) {
  operatingId.value = id;
  resolveForm.value.resolution = "";
  resolveDialogVisible.value = true;
}

async function handleResolve() {
  if (!resolveForm.value.resolution.trim()) {
    ElMessage.warning("请填写处理结论");
    return;
  }
  await store.updateStatus(operatingId.value, "resolved", resolveForm.value.resolution);
  resolveDialogVisible.value = false;
  ElMessage.success("已标记为已解决");
  store.fetchSummary();
  fetchData();
}

function openAssignDialog(id: string) {
  operatingId.value = id;
  assignForm.value.assigned_to = "";
  assignDialogVisible.value = true;
}

async function handleAssign() {
  if (!assignForm.value.assigned_to.trim()) {
    ElMessage.warning("请输入处理人 ID");
    return;
  }
  await store.assign(operatingId.value, assignForm.value.assigned_to);
  assignDialogVisible.value = false;
  ElMessage.success("已分派处理人");
  fetchData();
}

async function handleMarkProcessing(id: string) {
  await store.updateStatus(id, "processing");
  ElMessage.success("已标记为处理中");
  fetchData();
}

async function handleClose(id: string) {
  await ElMessageBox.confirm("确认关闭此反馈？", "关闭反馈", { type: "warning" });
  await store.updateStatus(id, "closed");
  ElMessage.success("已关闭");
  store.fetchSummary();
  fetchData();
}

function openReopenDialog(id: string) {
  operatingId.value = id;
  reopenForm.value.reason = "";
  reopenDialogVisible.value = true;
}

async function handleReopen() {
  if (!reopenForm.value.reason.trim()) {
    ElMessage.warning("请填写重新打开的原因");
    return;
  }
  await store.updateStatus(operatingId.value, "reopened", reopenForm.value.reason);
  reopenDialogVisible.value = false;
  ElMessage.success("已重新打开");
  store.fetchSummary();
  fetchData();
}


function formatTime(t: string | null) {
  if (!t) return "--";
  return t.replace("T", " ").slice(0, 19);
}

function shortId(id: string | null) {
  if (!id) return "--";
  return id.length > 8 ? id.slice(0, 8) + "…" : id;
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="hero">
      <div>
        <h2>异常反馈中心</h2>
        <p>查看、分派、处理异常反馈，实现问题闭环管理。</p>
      </div>
    </div>

    <div class="grid grid-cols-5 gap-4">
      <div
        v-for="card in summaryCards"
        :key="card.label"
        class="stat-card rounded-xl p-4 border border-zinc-100 transition-shadow hover:shadow-sm"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
            :style="{ backgroundColor: cardVars[card.key]?.bg }"
          >
            <div class="w-2.5 h-2.5 rounded-full" :style="{ backgroundColor: cardVars[card.key]?.accent }" />
          </div>
          <div class="min-w-0">
            <div class="text-xs text-zinc-400 truncate">{{ card.label }}</div>
            <div class="text-xl font-bold tracking-tight" :style="{ color: cardVars[card.key]?.accent }">{{ card.value }}</div>
          </div>
        </div>
      </div>
    </div>

    <el-card shadow="never">
      <div class="flex items-center justify-between mb-4">
        <el-tabs v-model="activeTab" class="!mb-0">
          <el-tab-pane label="全部反馈" name="all" />
          <el-tab-pane label="待处理" name="pending" />
          <el-tab-pane label="高风险" name="high_risk" />
          <el-tab-pane label="我的反馈" name="mine" />
        </el-tabs>
        <div class="flex items-center gap-2">
          <el-button link @click="showAdvancedFilter = !showAdvancedFilter">
            {{ showAdvancedFilter ? '收起筛选' : '高级筛选' }}
          </el-button>
          <el-button text @click="handleReset">重置</el-button>
        </div>
      </div>

      <div v-show="showAdvancedFilter" class="flex gap-3 mb-4 flex-wrap">
        <el-select v-model="filterForm.status" placeholder="状态" clearable size="default" class="!w-28">
          <el-option v-for="(v, k) in statusMap" :key="k" :label="v.label" :value="k" />
        </el-select>
        <el-select v-model="filterForm.severity" placeholder="严重程度" clearable size="default" class="!w-28">
          <el-option v-for="(v, k) in severityMap" :key="k" :label="v.label" :value="k" />
        </el-select>
        <el-select v-model="filterForm.source_type" placeholder="来源" clearable size="default" class="!w-28">
          <el-option v-for="(v, k) in sourceMap" :key="k" :label="v" :value="k" />
        </el-select>
        <el-select v-model="filterForm.category" placeholder="异常类型" clearable size="default" class="!w-32">
          <el-option v-for="(v, k) in categoryMap" :key="k" :label="v" :value="k" />
        </el-select>
      </div>

      <el-table :data="store.items" v-loading="store.loading" @row-click="openDetail" class="cursor-pointer" stripe>
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="source_type" label="来源" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source_type === 'result' ? '' : 'info'">
              {{ sourceMap[row.source_type as FeedbackSourceType] || row.source_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="异常类型" width="110">
          <template #default="{ row }">
            <span>{{ categoryMap[row.category] || row.category || "--" }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="严重程度" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.severity" size="small" :type="severityMap[row.severity as FeedbackSeverity]?.type ?? 'info'">
              {{ severityMap[row.severity as FeedbackSeverity]?.label ?? row.severity }}
            </el-tag>
            <span v-else class="text-gray-400">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusMap[row.status as FeedbackStatus]?.type ?? 'info'">
              {{ statusMap[row.status as FeedbackStatus]?.label ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="comment" label="摘要" min-width="200" show-overflow-tooltip />
        <el-table-column prop="actor_id" label="反馈人" width="110">
          <template #default="{ row }">{{ shortId(row.actor_id) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="openDetail(row)">查看</el-button>
            <el-button v-if="row.status === 'pending'" link type="warning" size="small" @click.stop="handleMarkProcessing(row.id)">处理</el-button>
            <el-button v-if="row.status === 'pending' || row.status === 'processing'" link size="small" @click.stop="openAssignDialog(row.id)">分派</el-button>
            <el-button v-if="row.status === 'processing'" link type="success" size="small" @click.stop="openResolveDialog(row.id)">解决</el-button>
            <el-button v-if="row.status === 'resolved'" link type="info" size="small" @click.stop="handleClose(row.id)">关闭</el-button>
            <el-button v-if="row.status === 'closed' || row.status === 'resolved'" link type="danger" size="small" @click.stop="openReopenDialog(row.id)">重开</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-drawer v-model="drawerVisible" title="反馈详情" size="720px" :destroy-on-close="true">
      <div v-loading="detailLoading">
        <template v-if="store.currentDetail">
          <div class="flex items-center gap-3 mb-5">
            <el-tag :type="statusMap[store.currentDetail.status as FeedbackStatus]?.type ?? 'info'">
              {{ statusMap[store.currentDetail.status as FeedbackStatus]?.label ?? store.currentDetail.status }}
            </el-tag>
            <el-tag v-if="store.currentDetail.severity" :type="severityMap[store.currentDetail.severity as FeedbackSeverity]?.type ?? 'info'">
              {{ severityMap[store.currentDetail.severity as FeedbackSeverity]?.label ?? store.currentDetail.severity }}
            </el-tag>
            <el-tag type="info">{{ sourceMap[store.currentDetail.source_type as FeedbackSourceType] || "未知" }}</el-tag>
          </div>

          <el-tabs v-model="detailTab">
            <el-tab-pane label="反馈内容" name="content">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="反馈人">{{ shortId(store.currentDetail.actor_id) }}</el-descriptions-item>
                <el-descriptions-item label="反馈时间">{{ formatTime(store.currentDetail.created_at) }}</el-descriptions-item>
                <el-descriptions-item label="反馈类型">{{ store.currentDetail.feedback_type === "up" ? "点赞" : "点踩" }}</el-descriptions-item>
                <el-descriptions-item label="评分">{{ store.currentDetail.rating ?? "--" }}</el-descriptions-item>
                <el-descriptions-item label="异常分类">{{ categoryMap[store.currentDetail.category ?? ""] || "--" }}</el-descriptions-item>
                <el-descriptions-item label="严重程度">{{ store.currentDetail.severity ? severityMap[store.currentDetail.severity as FeedbackSeverity]?.label : "--" }}</el-descriptions-item>
                <el-descriptions-item label="评论" :span="2">{{ store.currentDetail.comment || "--" }}</el-descriptions-item>
              </el-descriptions>
            </el-tab-pane>

            <el-tab-pane label="关联结果" name="result">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="结果 ID">
                  <el-button link type="primary" size="small" @click="$router.push(`/app/results/${store.currentDetail?.result_id}`)">
                    {{ shortId(store.currentDetail.result_id) }}
                  </el-button>
                </el-descriptions-item>
                <el-descriptions-item label="任务 ID">
                  <el-button v-if="store.currentDetail.task_id" link type="primary" size="small" @click="$router.push(`/app/tasks/${store.currentDetail.task_id}`)">
                    {{ shortId(store.currentDetail.task_id) }}
                  </el-button>
                  <span v-else>--</span>
                </el-descriptions-item>
                <el-descriptions-item label="来源">{{ sourceMap[store.currentDetail.source_type as FeedbackSourceType] || "--" }}</el-descriptions-item>
                <el-descriptions-item label="反馈类型">{{ store.currentDetail.feedback_type === "up" ? "点赞" : "点踩" }}</el-descriptions-item>
                <el-descriptions-item label="更新时间">{{ formatTime(store.currentDetail.updated_at) }}</el-descriptions-item>
                <el-descriptions-item label="反馈人">{{ shortId(store.currentDetail.actor_id) }}</el-descriptions-item>
              </el-descriptions>
              <div class="flex gap-2 mt-3">
                <el-button size="small" @click="$router.push(`/app/results/${store.currentDetail?.result_id}`)">查看结果详情</el-button>
                <el-button size="small" plain @click="$router.push(`/app/export?report=single_task&task_id=${store.currentDetail?.task_id || ''}`)">导出该结果报告</el-button>
              </div>
            </el-tab-pane>

            <el-tab-pane label="证据链路" name="evidence">
              <div v-if="!store.currentDetail.result_id && !store.currentDetail.task_id" class="text-gray-400 text-sm py-8 text-center">
                暂无关联的任务或结果数据
              </div>
              <div v-else class="flex flex-col gap-4">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="结果 ID">
                    <el-button link type="primary" size="small" @click="$router.push(`/app/results/${store.currentDetail?.result_id}`)">
                      {{ shortId(store.currentDetail.result_id) }}
                    </el-button>
                  </el-descriptions-item>
                  <el-descriptions-item label="任务 ID">
                    <el-button v-if="store.currentDetail.task_id" link type="primary" size="small" @click="$router.push(`/app/tasks/${store.currentDetail.task_id}`)">
                      {{ shortId(store.currentDetail.task_id) }}
                    </el-button>
                    <span v-else>--</span>
                  </el-descriptions-item>
                </el-descriptions>
                <el-collapse>
                  <el-collapse-item title="推理链 (reasoning_chain)" name="reasoning">
                    <div class="text-xs text-gray-400 mb-2">推理链数据可通过任务详情页或分析中心查看完整内容。</div>
                    <el-button size="small" @click="$router.push(`/app/tasks/${store.currentDetail?.task_id}`)">前往任务详情查看</el-button>
                  </el-collapse-item>
                  <el-collapse-item title="引用证据 (citations)" name="citations">
                    <div class="text-xs text-gray-400 mb-2">引用证据在检测结果中展示。</div>
                    <el-button size="small" @click="$router.push(`/app/results/${store.currentDetail?.result_id}`)">前往结果详情查看</el-button>
                  </el-collapse-item>
                  <el-collapse-item title="Trace 链路" name="trace">
                    <div class="text-xs text-gray-400 mb-2">完整的检测追踪链可在分析中心查看，包含模型调用、Token 消耗和延迟信息。</div>
                    <el-button size="small" @click="$router.push('/ops/analysis')">前往分析中心</el-button>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </el-tab-pane>

            <el-tab-pane label="处理记录" name="timeline">
              <el-timeline>
                <el-timeline-item timestamp="提交反馈" placement="top" :hollow="false">
                  <div class="text-sm text-gray-500">{{ formatTime(store.currentDetail.created_at) }}</div>
                  <div>用户 {{ shortId(store.currentDetail.actor_id) }} 提交了反馈</div>
                </el-timeline-item>
                <el-timeline-item v-if="store.currentDetail.assigned_to" timestamp="分派处理" placement="top" :hollow="store.currentDetail.status === 'pending'">
                  <div>分派给 {{ shortId(store.currentDetail.assigned_to) }}</div>
                </el-timeline-item>
                <el-timeline-item v-if="store.currentDetail.resolution" timestamp="处理结论" placement="top" type="success">
                  <div>{{ store.currentDetail.resolution }}</div>
                  <div v-if="store.currentDetail.resolved_at" class="text-sm text-gray-500">{{ formatTime(store.currentDetail.resolved_at) }}</div>
                </el-timeline-item>
                <el-timeline-item v-if="store.currentDetail.status === 'closed'" timestamp="已关闭" placement="top" type="info">
                  <div>反馈已关闭</div>
                </el-timeline-item>
              </el-timeline>
            </el-tab-pane>
          </el-tabs>

          <div class="flex gap-3 mt-6 pt-4 border-t border-zinc-100">
            <el-button v-if="store.currentDetail.status === 'pending'" type="warning" size="small" @click="handleMarkProcessing(store.currentDetail.id); drawerVisible = false">标记处理中</el-button>
            <el-button v-if="store.currentDetail.status === 'pending' || store.currentDetail.status === 'processing'" size="small" @click="openAssignDialog(store.currentDetail.id)">分派</el-button>
            <el-button v-if="store.currentDetail.status === 'processing'" type="success" size="small" @click="openResolveDialog(store.currentDetail.id)">标记解决</el-button>
            <el-button v-if="store.currentDetail.status === 'resolved'" type="info" size="small" @click="handleClose(store.currentDetail.id); drawerVisible = false">关闭</el-button>
            <el-button v-if="store.currentDetail.status === 'closed' || store.currentDetail.status === 'resolved'" type="danger" size="small" plain @click="openReopenDialog(store.currentDetail.id)">重新打开</el-button>
          </div>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="resolveDialogVisible" title="标记已解决" width="480px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="处理结论" required>
          <el-input v-model="resolveForm.resolution" type="textarea" :rows="4" placeholder="请输入处理结论" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resolveDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResolve">确认解决</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignDialogVisible" title="分派处理人" width="480px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="处理人 ID" required>
          <el-input v-model="assignForm.assigned_to" placeholder="请输入处理人用户 ID" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssign">确认分派</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="reopenDialogVisible" title="重新打开反馈" width="480px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="重新打开原因" required>
          <el-input v-model="reopenForm.reason" type="textarea" :rows="3" placeholder="请填写重新打开的原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reopenDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleReopen">确认重新打开</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.stat-card {
  transition: box-shadow 0.2s;
}
.stat-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
</style>
