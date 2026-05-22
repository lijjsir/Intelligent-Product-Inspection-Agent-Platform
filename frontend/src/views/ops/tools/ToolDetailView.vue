<template>
  <div class="tool-detail" v-loading="store.currentToolLoading">
    <template v-if="tool">
      <section class="header-card">
        <div class="header-top">
          <el-button text @click="$router.push('/ops/tools/catalog')">返回工具库</el-button>
        </div>
        <div class="header-main">
          <div class="header-info">
            <div class="title-row">
              <h1 class="tool-title">{{ tool.display_name }}</h1>
              <el-tag :type="statusTag(tool.status)">{{ statusLabel(tool.status) }}</el-tag>
            </div>
            <div class="tool-key">{{ tool.tool_key }}</div>
            <div class="meta-tags">
              <el-tag effect="plain">{{ categoryLabel(tool.category) }}</el-tag>
              <el-tag effect="plain" :type="riskTag(tool.risk_level)">{{ riskLabel(tool.risk_level) }}</el-tag>
              <el-tag effect="plain" :type="healthTag(tool.health_status)">{{ healthLabel(tool.health_status) }}</el-tag>
              <el-tag effect="plain">{{ tool.is_readonly ? "只读" : "可写" }}</el-tag>
              <el-tag effect="plain">v{{ tool.active_version }}</el-tag>
            </div>
            <div class="meta-line">
              <span>今日调用 {{ tool.today_calls }}</span>
              <span>成功率 {{ (tool.success_rate * 100).toFixed(1) }}%</span>
              <span>平均延迟 {{ tool.avg_latency_ms }} ms</span>
              <span>{{ tool.bound_agent_names.length ? `绑定 ${tool.bound_agent_names.length} 个 Agent` : "未绑定 Agent" }}</span>
            </div>
          </div>
          <div class="header-actions">
            <el-button @click="activeTab = 'test'">测试工具</el-button>
            <el-button type="primary" @click="showEditDialog = true">编辑配置</el-button>
            <el-button v-if="tool.status === 'active'" type="warning" @click="disableTool">停用</el-button>
          </div>
        </div>
      </section>


      <el-tabs v-model="activeTab" class="detail-tabs">
        <el-tab-pane label="概览" name="overview">
          <div class="grid-two">
            <article class="panel">
              <div class="panel-title">工具说明</div>
              <p class="description">{{ tool.description || "暂无描述" }}</p>
            </article>
            <article class="panel">
              <div class="panel-title">运行摘要</div>
              <div class="summary-grid">
                <div class="summary-item">
                  <span>今日调用</span>
                  <strong>{{ tool.today_calls }}</strong>
                </div>
                <div class="summary-item">
                  <span>成功率</span>
                  <strong>{{ (tool.success_rate * 100).toFixed(1) }}%</strong>
                </div>
                <div class="summary-item">
                  <span>平均延迟</span>
                  <strong>{{ tool.avg_latency_ms }} ms</strong>
                </div>
                <div class="summary-item">
                  <span>健康状态</span>
                  <strong>{{ healthLabel(tool.health_status) }}</strong>
                </div>
              </div>
            </article>
            <article class="panel">
              <div class="panel-title">风险与调用建议</div>
              <div class="advice-list">
                <div>风险等级：{{ riskLabel(tool.risk_level) }}</div>
                <div>读写权限：{{ tool.is_readonly ? "只读工具，可由 Agent 自动调用" : "可写工具，请评估影响面" }}</div>
                <div>调用建议：{{ riskAdvice(tool.risk_level, tool.is_readonly) }}</div>
              </div>
            </article>
            <article class="panel">
              <div class="panel-title">最近失败记录</div>
              <div v-if="recentFailures.length" class="failure-list">
                <div v-for="item in recentFailures" :key="item.id" class="failure-row">
                  <span>{{ formatTime(item.created_at) }}</span>
                  <span>{{ item.error_message }}</span>
                </div>
              </div>
              <div v-else class="empty-text">最近没有失败记录</div>
            </article>
          </div>
        </el-tab-pane>

        <el-tab-pane label="配置" name="config">
          <article class="panel">
            <div class="panel-title">调用配置</div>
            <div class="config-grid">
              <div class="config-item">
                <span>工具类型</span>
                <strong>{{ tool.tool_type }}</strong>
              </div>
              <div class="config-item">
                <span>Endpoint</span>
                <strong>{{ tool.endpoint || "-" }}</strong>
              </div>
              <div class="config-item">
                <span>Method</span>
                <strong>{{ tool.method || "-" }}</strong>
              </div>
              <div class="config-item">
                <span>Handler Path</span>
                <strong>{{ tool.handler_path || "-" }}</strong>
              </div>
              <div class="config-item">
                <span>超时</span>
                <strong>{{ tool.timeout_ms }} ms</strong>
              </div>
              <div class="config-item">
                <span>认证方式</span>
                <strong>{{ tool.auth_type }}</strong>
              </div>
              <div class="config-item">
                <span>限流</span>
                <strong>{{ tool.rate_limit_rpm }} rpm</strong>
              </div>
              <div class="config-item">
                <span>密钥引用</span>
                <strong>{{ tool.secret_ref || "-" }}</strong>
              </div>
            </div>
          </article>
        </el-tab-pane>

        <el-tab-pane label="Schema" name="schema">
          <div class="grid-two">
            <article class="panel">
              <div class="panel-title">Parameters Schema</div>
              <pre class="code-block">{{ JSON.stringify(tool.parameters_schema, null, 2) }}</pre>
            </article>
            <article class="panel">
              <div class="panel-title">Returns Schema</div>
              <pre class="code-block">{{ JSON.stringify(tool.returns_schema, null, 2) }}</pre>
            </article>
          </div>
        </el-tab-pane>

        <el-tab-pane label="测试" name="test">
          <article class="panel panel-narrow">
            <div class="panel-title">工具测试</div>
            <el-form label-position="top">
              <el-form-item label="测试参数（JSON）">
                <el-input v-model="testParams" type="textarea" :rows="8" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="store.testRunning" @click="runTest">运行测试</el-button>
              </el-form-item>
            </el-form>

            <div v-if="store.testResult" class="result-box">
              <div class="result-head">
                <el-tag :type="store.testResult.status === 'success' ? 'success' : 'danger'">
                  {{ store.testResult.status }}
                </el-tag>
                <span>{{ store.testResult.duration_ms }} ms</span>
                <span>{{ store.testResult.trace_id }}</span>
              </div>
              <pre class="result-body">{{ JSON.stringify(store.testResult.output, null, 2) }}</pre>
              <div v-if="store.testResult.error" class="result-error">{{ store.testResult.error }}</div>
            </div>
          </article>
        </el-tab-pane>

        <el-tab-pane label="版本历史" name="versions">
          <article class="panel">
            <div class="panel-header-row">
              <span class="panel-title">版本历史</span>
              <el-button size="small" @click="showCreateVersionDialog = true">创建新版本</el-button>
            </div>
            <el-table :data="store.toolVersions" stripe size="small" v-loading="versionsLoading">
              <el-table-column prop="version" label="版本" width="100" />
              <el-table-column prop="status" label="状态" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
                    {{ row.status === 'active' ? '当前' : row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="display_name" label="名称" min-width="160" />
              <el-table-column label="操作" width="200">
                <template #default="{ row }">
                  <el-button
                    v-if="row.status !== 'active'"
                    text type="primary" size="small"
                    @click="publishVer(row)"
                  >发布</el-button>
                  <el-button
                    v-if="row.status === 'active' && store.toolVersions.length > 1"
                    text type="warning" size="small"
                    @click="rollbackVer(row)"
                  >回滚</el-button>
                </template>
              </el-table-column>
            </el-table>
          </article>
        </el-tab-pane>

        <el-tab-pane label="Agent 绑定" name="bindings">
          <article class="panel">
            <div class="panel-header-row">
              <span class="panel-title">Agent 绑定</span>
              <el-button size="small" @click="showAddBindingDialog = true">添加绑定</el-button>
            </div>
            <el-table :data="store.toolBindings" stripe size="small" v-loading="bindingsLoading">
              <el-table-column prop="agent_name" label="Agent" width="180" />
              <el-table-column prop="tool_version" label="版本" width="100" />
              <el-table-column label="自动调用" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.auto_call_enabled ? 'success' : 'info'" size="small">
                    {{ row.auto_call_enabled ? '允许' : '禁止' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="审批" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.approval_required ? 'warning' : 'info'" size="small">
                    {{ row.approval_required ? '需要' : '不需要' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button text type="danger" size="small" @click="removeBinding(row)">解除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </article>
        </el-tab-pane>

        <el-tab-pane label="执行记录" name="executions">
          <article class="panel">
            <div class="panel-title">最近执行</div>
            <el-table :data="tool.executions" stripe size="small">
              <el-table-column label="时间" width="170">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column prop="agent_name" label="Agent" width="160" />
              <el-table-column label="类型" width="90">
                <template #default="{ row }">{{ row.execution_type }}</template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'success' ? 'success' : 'danger'">
                    {{ row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="耗时" width="100" align="right">
                <template #default="{ row }">{{ row.duration_ms }} ms</template>
              </el-table-column>
              <el-table-column prop="input_summary" label="输入摘要" min-width="180" :show-overflow-tooltip="true" />
              <el-table-column prop="output_summary" label="输出摘要" min-width="180" :show-overflow-tooltip="true" />
              <el-table-column prop="error_message" label="错误信息" width="180" :show-overflow-tooltip="true" />
              <el-table-column prop="trace_id" label="Trace ID" width="170" :show-overflow-tooltip="true" />
            </el-table>
          </article>
        </el-tab-pane>
      </el-tabs>

      <el-dialog v-model="showEditDialog" title="编辑工具配置" width="560px" destroy-on-close>
        <el-form :model="editForm" label-position="top">
          <el-form-item label="显示名称">
            <el-input v-model="editForm.display_name" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="editForm.description" type="textarea" :rows="3" />
          </el-form-item>
          <div class="dialog-grid">
            <el-form-item label="分类">
              <el-select v-model="editForm.category">
                <el-option label="RAG" value="RAG" />
                <el-option label="文件解析" value="file_parse" />
                <el-option label="检测计算" value="inspection_calc" />
                <el-option label="报告生成" value="report_gen" />
                <el-option label="HTTP API" value="http_api" />
                <el-option label="MCP" value="MCP" />
                <el-option label="数据库" value="database" />
              </el-select>
            </el-form-item>
            <el-form-item label="风险等级">
              <el-select v-model="editForm.risk_level">
                <el-option label="低风险" value="low" />
                <el-option label="中风险" value="medium" />
                <el-option label="高风险" value="high" />
              </el-select>
            </el-form-item>
          </div>
        </el-form>

        <template #footer>
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" @click="saveEdit">保存</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="showCreateVersionDialog" title="创建新版本" width="480px" destroy-on-close>
        <el-form :model="versionForm" label-position="top">
          <el-form-item label="版本号">
            <el-input v-model="versionForm.version" placeholder="例如 1.1.0" />
          </el-form-item>
          <el-form-item label="显示名称">
            <el-input v-model="versionForm.display_name" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCreateVersionDialog = false">取消</el-button>
          <el-button type="primary" @click="doCreateVersion">创建</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="showAddBindingDialog" title="添加 Agent 绑定" width="480px" destroy-on-close>
        <el-form :model="bindingForm" label-position="top">
          <el-form-item label="Agent ID">
            <el-input v-model="bindingForm.agent_id" placeholder="输入 Agent ID" />
          </el-form-item>
          <el-form-item label="自动调用">
            <el-switch v-model="bindingForm.auto_call_enabled" />
          </el-form-item>
          <el-form-item label="需要审批">
            <el-switch v-model="bindingForm.approval_required" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddBindingDialog = false">取消</el-button>
          <el-button type="primary" @click="doAddBinding">添加</el-button>
        </template>
      </el-dialog>
    </template>

    <div v-else-if="!store.currentToolLoading" class="empty-text page-empty">工具不存在</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { ElMessageBox } from "element-plus";
import { useToolsStore } from "@/stores/tools.store";
import type {
  AgentToolBinding,
  BindingCreateRequest,
  HealthStatus,
  RiskLevel,
  ToolCategory,
  ToolStatus,
  ToolVersion,
} from "@/types/tools.types";

const route = useRoute();
const store = useToolsStore();
const tool = computed(() => store.currentTool);

const activeTab = ref("overview");
const showEditDialog = ref(false);
const testParams = ref('{\n  "query": "示例查询"\n}');

const editForm = reactive({
  display_name: "",
  description: "",
  category: "RAG" as ToolCategory,
  risk_level: "low" as RiskLevel,
});

const versionsLoading = ref(false);
const bindingsLoading = ref(false);
const showCreateVersionDialog = ref(false);
const showAddBindingDialog = ref(false);

const versionForm = reactive({
  version: "",
  display_name: "",
});

const bindingForm = reactive<BindingCreateRequest>({
  agent_id: "",
  tool_id: "",
  tool_version_id: "",
  auto_call_enabled: true,
  approval_required: false,
});

const recentFailures = computed(() =>
  (tool.value?.executions ?? []).filter((item) => item.status !== "success").slice(0, 5)
);

function categoryLabel(value: ToolCategory) {
  return {
    RAG: "RAG",
    file_parse: "文件解析",
    inspection_calc: "检测计算",
    report_gen: "报告生成",
    http_api: "HTTP API",
    MCP: "MCP",
    database: "数据库",
  }[value];
}

function statusLabel(value: ToolStatus) {
  return {
    active: "启用",
    disabled: "停用",
    draft: "草稿",
    deprecated: "废弃",
    deleted: "删除",
    error: "异常",
  }[value] ?? value;
}

function statusTag(value: ToolStatus) {
  return {
    active: "success",
    disabled: "info",
    draft: "warning",
    deprecated: "info",
    deleted: "danger",
    error: "danger",
  }[value] as "success" | "info" | "warning" | "danger";
}

function riskLabel(value: RiskLevel) {
  return {
    low: "低风险",
    medium: "中风险",
    high: "高风险",
  }[value];
}

function riskTag(value: RiskLevel) {
  return {
    low: "info",
    medium: "warning",
    high: "danger",
  }[value] as "info" | "warning" | "danger";
}

function healthLabel(value: HealthStatus) {
  return {
    healthy: "健康",
    degraded: "降级",
    unhealthy: "异常",
    unknown: "未知",
  }[value];
}

function healthTag(value: HealthStatus) {
  return {
    healthy: "success",
    degraded: "warning",
    unhealthy: "danger",
    unknown: "info",
  }[value] as "success" | "warning" | "danger" | "info";
}

function riskAdvice(riskLevel: RiskLevel, readonly: boolean) {
  if (riskLevel === "low" && readonly) return "可直接供 Agent 自动调用。";
  if (riskLevel === "medium") return "建议保留测试记录并关注失败趋势。";
  if (riskLevel === "high") return "建议先人工评估，再开放到运行时链路。";
  return "建议在发布前补充更多验证样例。";
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

async function loadTool() {
  const id = route.params.id;
  if (typeof id === "string" && id) {
    await store.fetchToolDetail(id);
  }
}

async function runTest() {
  if (!tool.value) return;
  try {
    const params = JSON.parse(testParams.value);
    await store.testTool(tool.value.id, params);
  } catch {
    ElMessage.warning("请输入合法的 JSON");
  }
}

async function saveEdit() {
  if (!tool.value) return;
  await store.updateTool(tool.value.id, editForm);
  showEditDialog.value = false;
  ElMessage.success("工具配置已更新");
  await loadTool();
}

async function disableTool() {
  if (!tool.value) return;
  await store.updateToolStatus(tool.value.id, "disabled");
  ElMessage.success(`已停用 ${tool.value.display_name}`);
  await loadTool();
}

async function loadVersions() {
  if (!tool.value) return;
  versionsLoading.value = true;
  try {
    await store.fetchVersions(tool.value.id);
  } finally {
    versionsLoading.value = false;
  }
}

async function loadBindings() {
  if (!tool.value) return;
  bindingsLoading.value = true;
  try {
    await store.fetchBindings(tool.value.id);
  } finally {
    bindingsLoading.value = false;
  }
}

async function doCreateVersion() {
  if (!tool.value || !versionForm.version.trim()) return;
  await store.createVersion(tool.value.id, {
    version: versionForm.version.trim(),
    display_name: versionForm.display_name || versionForm.version.trim(),
    description: tool.value.description,
  });
  showCreateVersionDialog.value = false;
  ElMessage.success("版本已创建");
  versionForm.version = "";
  versionForm.display_name = "";
}

async function publishVer(row: ToolVersion) {
  if (!tool.value) return;
  await store.publishVersion(tool.value.id, row.id);
  ElMessage.success(`已发布版本 ${row.version}`);
  await loadVersions();
  await loadTool();
}

async function rollbackVer(row: ToolVersion) {
  if (!tool.value) return;
  await store.rollbackVersion(tool.value.id, row.id);
  ElMessage.success(`已回滚到版本 ${row.version}`);
  await loadVersions();
  await loadTool();
}

async function doAddBinding() {
  if (!tool.value || !bindingForm.agent_id.trim()) return;
  await store.createBinding({
    ...bindingForm,
    tool_id: tool.value.id,
  });
  showAddBindingDialog.value = false;
  ElMessage.success("绑定已添加");
  bindingForm.agent_id = "";
  await loadBindings();
}

async function removeBinding(row: AgentToolBinding) {
  await ElMessageBox.confirm("确认解除此绑定？", "解除绑定", { type: "warning" });
  await store.deleteBinding(row.id);
  ElMessage.success("绑定已解除");
  await loadBindings();
}

watch(activeTab, (tab) => {
  if (tab === "versions") loadVersions();
  if (tab === "bindings") loadBindings();
});

watch(
  tool,
  (value) => {
    if (!value) return;
    editForm.display_name = value.display_name;
    editForm.description = value.description;
    editForm.category = value.category;
    editForm.risk_level = value.risk_level;
  },
  { immediate: true }
);

watch(
  () => route.params.id,
  () => {
    loadTool();
  }
);

onMounted(loadTool);
</script>

<style scoped>
.tool-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-card,
.panel,
.result-box {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.header-card {
  padding: 18px 20px;
}

.header-top {
  margin-bottom: 10px;
}

.header-main {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tool-title {
  margin: 0;
  font-size: 24px;
  color: #0f172a;
}

.tool-key {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, monospace;
}

.meta-tags,
.meta-line,
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-tags {
  margin-top: 12px;
}

.meta-line {
  margin-top: 12px;
  font-size: 13px;
  color: #64748b;
}

.phase-alert {
  margin-top: -4px;
}

.detail-tabs {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 4px 16px 16px;
}

.grid-two,
.dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  padding: 18px;
}

.panel-narrow {
  max-width: 720px;
}

.panel-title {
  margin-bottom: 14px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.panel-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.description,
.advice-list {
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.summary-grid,
.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.summary-item,
.config-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 12px;
  color: #475569;
}

.summary-item strong,
.config-item strong {
  color: #0f172a;
}

.failure-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.failure-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  background: #fff7ed;
  border-radius: 12px;
  color: #9a3412;
  font-size: 13px;
}

.code-block,
.result-body {
  margin: 0;
  padding: 14px;
  border-radius: 12px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
}

.result-box {
  margin-top: 16px;
  overflow: hidden;
}

.result-head {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  background: #f8fafc;
  font-size: 12px;
  color: #64748b;
}

.result-error {
  padding: 12px 14px;
  color: #dc2626;
  background: #fef2f2;
}

.empty-text {
  color: #94a3b8;
  text-align: center;
}

.page-empty {
  padding: 64px 0;
}

@media (max-width: 900px) {
  .grid-two,
  .dialog-grid,
  .summary-grid,
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
