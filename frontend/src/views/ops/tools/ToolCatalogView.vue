<template>
  <div class="tool-catalog">
    <section class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          placeholder="搜索工具名称、tool_key 或描述"
          clearable
          class="toolbar-search"
          @keyup.enter="loadTools"
          @clear="loadTools"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="createDialog.visible = true">新增工具</el-button>
        <el-button @click="$router.push('/ops/tools/import')">导入与同步</el-button>
      </div>
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button value="card">
          <el-icon><Grid /></el-icon>
        </el-radio-button>
        <el-radio-button value="table">
          <el-icon><List /></el-icon>
        </el-radio-button>
      </el-radio-group>
    </section>

    <section class="filters">
      <el-select v-model="filterCategory" clearable placeholder="分类" class="filter" @change="loadTools">
        <el-option label="RAG" value="RAG" />
        <el-option label="文件解析" value="file_parse" />
        <el-option label="检测计算" value="inspection_calc" />
        <el-option label="报告生成" value="report_gen" />
        <el-option label="HTTP API" value="http_api" />
        <el-option label="MCP" value="MCP" />
        <el-option label="数据库" value="database" />
      </el-select>
      <el-select v-model="filterStatus" clearable placeholder="状态" class="filter" @change="loadTools">
        <el-option label="启用" value="active" />
        <el-option label="停用" value="disabled" />
        <el-option label="草稿" value="draft" />
        <el-option label="废弃" value="deprecated" />
      </el-select>
      <el-select v-model="filterHealth" clearable placeholder="健康状态" class="filter" @change="loadTools">
        <el-option label="健康" value="healthy" />
        <el-option label="降级" value="degraded" />
        <el-option label="异常" value="unhealthy" />
        <el-option label="未知" value="unknown" />
      </el-select>
      <el-select v-model="filterRisk" clearable placeholder="风险" class="filter" @change="loadTools">
        <el-option label="低风险" value="low" />
        <el-option label="中风险" value="medium" />
        <el-option label="高风险" value="high" />
      </el-select>
      <el-select v-model="filterSource" clearable placeholder="来源" class="filter" @change="loadTools">
        <el-option label="内置" value="builtin" />
        <el-option label="手动" value="manual" />
        <el-option label="OpenAPI" value="openapi" />
        <el-option label="MCP" value="mcp" />
      </el-select>
    </section>

    <section v-if="viewMode === 'card'" class="card-grid" v-loading="store.toolsLoading">
      <article
        v-for="tool in store.tools"
        :key="tool.id"
        class="tool-card"
        @click="$router.push(`/ops/tools/catalog/${tool.id}`)"
      >
        <div class="tool-card-header">
          <div>
            <h3 class="tool-name">{{ tool.display_name }}</h3>
            <p class="tool-key">{{ tool.tool_key }}</p>
          </div>
          <el-tag size="small" :type="statusTag(tool.status)">{{ statusLabel(tool.status) }}</el-tag>
        </div>

        <div class="tool-tags">
          <el-tag size="small" effect="plain">{{ categoryLabel(tool.category) }}</el-tag>
          <el-tag size="small" effect="plain" :type="riskTag(tool.risk_level)">{{ riskLabel(tool.risk_level) }}</el-tag>
          <el-tag size="small" effect="plain" :type="healthTag(tool.health_status)">{{ healthLabel(tool.health_status) }}</el-tag>
          <el-tag size="small" effect="plain">{{ sourceLabel(tool.source_type) }}</el-tag>
        </div>

        <p class="tool-description">{{ tool.description }}</p>

        <div class="tool-metrics">
          <span>今日调用 {{ tool.today_calls }}</span>
          <span>成功率 {{ (tool.success_rate * 100).toFixed(1) }}%</span>
          <span>平均延迟 {{ tool.avg_latency_ms }} ms</span>
        </div>

        <div class="tool-footer">
          <span class="footer-text">
            {{ tool.bound_agent_names.length ? `绑定 ${tool.bound_agent_names.length} 个 Agent` : "未绑定 Agent" }}
          </span>
          <div class="footer-actions" @click.stop>
            <el-button size="small" text @click="$router.push(`/ops/tools/catalog/${tool.id}`)">详情</el-button>
            <el-button size="small" text @click="openTest(tool)">测试</el-button>
            <el-button
              v-if="tool.status === 'active'"
              size="small"
              text
              type="warning"
              @click="disableTool(tool)"
            >
              停用
            </el-button>
          </div>
        </div>
      </article>

      <div v-if="!store.tools.length && !store.toolsLoading" class="empty-state">没有匹配的工具</div>
    </section>

    <section v-else class="table-wrap">
      <el-table
        :data="store.tools"
        stripe
        size="small"
        v-loading="store.toolsLoading"
        @row-click="(row: ToolDefinition) => $router.push(`/ops/tools/catalog/${row.id}`)"
      >
        <el-table-column prop="display_name" label="名称" min-width="180" />
        <el-table-column prop="tool_key" label="Tool Key" min-width="180" />
        <el-table-column label="分类" width="110">
          <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="健康" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="healthTag(row.health_status)" effect="plain">
              {{ healthLabel(row.health_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="今日调用" width="100" align="right">
          <template #default="{ row }">{{ row.today_calls }}</template>
        </el-table-column>
        <el-table-column label="成功率" width="100" align="right">
          <template #default="{ row }">{{ (row.success_rate * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="平均延迟" width="110" align="right">
          <template #default="{ row }">{{ row.avg_latency_ms }} ms</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click.stop="$router.push(`/ops/tools/catalog/${row.id}`)">详情</el-button>
            <el-button size="small" text @click.stop="openTest(row)">测试</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="pager">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="store.toolsTotal"
        :page-sizes="[12, 24, 48]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadTools"
        @size-change="handleSizeChange"
      />
    </section>

    <el-dialog v-model="testDialog.visible" title="工具测试" width="640px" destroy-on-close>
      <div class="dialog-meta">
        <strong>{{ testDialog.tool?.display_name }}</strong>
        <span>{{ testDialog.tool?.tool_key }}</span>
      </div>
      <el-form label-position="top">
        <el-form-item label="测试参数（JSON）">
          <el-input v-model="testDialog.params" type="textarea" :rows="8" />
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

      <template #footer>
        <el-button @click="testDialog.visible = false">关闭</el-button>
        <el-button type="primary" :loading="store.testRunning" @click="runTest">运行测试</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="createDialog.visible" title="新增工具" width="620px" destroy-on-close>
      <el-form :model="createDialog.form" label-position="top">
        <el-form-item label="Tool Key">
          <el-input v-model="createDialog.form.tool_key" placeholder="例如：rag.custom_search" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="createDialog.form.display_name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createDialog.form.description" type="textarea" :rows="3" />
        </el-form-item>
        <div class="dialog-grid">
          <el-form-item label="分类">
            <el-select v-model="createDialog.form.category">
              <el-option label="RAG" value="RAG" />
              <el-option label="文件解析" value="file_parse" />
              <el-option label="检测计算" value="inspection_calc" />
              <el-option label="报告生成" value="report_gen" />
              <el-option label="HTTP API" value="http_api" />
              <el-option label="MCP" value="MCP" />
              <el-option label="数据库" value="database" />
            </el-select>
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="createDialog.form.tool_type">
              <el-option label="Native" value="native" />
              <el-option label="HTTP" value="http" />
              <el-option label="RAG" value="rag" />
              <el-option label="MCP" value="mcp" />
            </el-select>
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="createTool">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Grid, List, Search } from "@element-plus/icons-vue";
import { useToolsStore } from "@/stores/tools.store";
import type {
  HealthStatus,
  RiskLevel,
  SourceType,
  ToolCategory,
  ToolDefinition,
  ToolStatus,
} from "@/types/tools.types";

const store = useToolsStore();

const viewMode = ref<"card" | "table">("card");
const keyword = ref("");
const currentPage = ref(1);
const pageSize = ref(12);

const filterCategory = ref<ToolCategory>();
const filterStatus = ref<ToolStatus>();
const filterHealth = ref<HealthStatus>();
const filterRisk = ref<RiskLevel>();
const filterSource = ref<SourceType>();

const testDialog = reactive<{
  visible: boolean;
  tool: ToolDefinition | null;
  params: string;
}>({
  visible: false,
  tool: null,
  params: '{\n  "query": "示例查询"\n}',
});

const createDialog = reactive({
  visible: false,
  form: {
    tool_key: "",
    display_name: "",
    description: "",
    category: "RAG" as ToolCategory,
    tool_type: "native" as ToolDefinition["tool_type"],
  },
});

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

function sourceLabel(value: SourceType) {
  return {
    builtin: "内置",
    manual: "手动",
    openapi: "OpenAPI",
    mcp: "MCP",
  }[value];
}

async function loadTools() {
  await store.fetchTools({
    page: currentPage.value,
    size: pageSize.value,
    keyword: keyword.value || undefined,
    category: filterCategory.value,
    status: filterStatus.value,
    health_status: filterHealth.value,
    risk_level: filterRisk.value,
    source_type: filterSource.value,
  });
}

function handleSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  loadTools();
}

function openTest(tool: ToolDefinition) {
  testDialog.tool = tool;
  testDialog.params = '{\n  "query": "示例查询"\n}';
  testDialog.visible = true;
  store.testResult = null;
}

async function runTest() {
  if (!testDialog.tool) return;
  try {
    const params = JSON.parse(testDialog.params);
    await store.testTool(testDialog.tool.id, params);
  } catch {
    ElMessage.warning("请输入合法的 JSON");
  }
}

async function disableTool(tool: ToolDefinition) {
  await store.updateToolStatus(tool.id, "disabled");
  ElMessage.success(`已停用 ${tool.display_name}`);
  await loadTools();
}

async function createTool() {
  if (!createDialog.form.tool_key || !createDialog.form.display_name) {
    ElMessage.warning("请先填写 tool_key 和显示名称");
    return;
  }

  await store.createTool({
    ...createDialog.form,
    risk_level: "low",
    is_readonly: true,
    parameters_schema: { type: "object", properties: {} },
    returns_schema: { type: "object", properties: {} },
  });

  ElMessage.success("工具已创建");
  createDialog.visible = false;
  createDialog.form.tool_key = "";
  createDialog.form.display_name = "";
  createDialog.form.description = "";
  await loadTools();
}

onMounted(loadTools);
</script>

<style scoped>
.tool-catalog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar,
.filters,
.table-wrap,
.tool-card,
.result-box {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.toolbar,
.filters {
  padding: 14px 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left,
.filters,
.footer-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-search {
  width: 360px;
}

.filter {
  width: 140px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.tool-card {
  padding: 18px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tool-card-header,
.tool-footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.tool-name {
  margin: 0;
  font-size: 16px;
  color: #0f172a;
}

.tool-key,
.tool-description,
.footer-text,
.dialog-meta span {
  color: #64748b;
}

.tool-key {
  margin: 6px 0 0;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, monospace;
}

.tool-tags,
.tool-metrics {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tool-description {
  margin: 0;
  line-height: 1.6;
  min-height: 44px;
}

.tool-metrics {
  font-size: 12px;
}

.tool-footer {
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}

.footer-text {
  font-size: 12px;
}

.empty-state {
  grid-column: 1 / -1;
  padding: 48px 16px;
  text-align: center;
  color: #94a3b8;
}

.pager {
  display: flex;
  justify-content: flex-end;
}

.dialog-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 12px;
  margin-bottom: 16px;
}

.dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
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

.result-body {
  margin: 0;
  padding: 14px;
  max-height: 260px;
  overflow: auto;
  background: #fff;
}

.result-error {
  padding: 12px 14px;
  color: #dc2626;
  background: #fef2f2;
  font-size: 13px;
}

@media (max-width: 1200px) {
  .card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .toolbar-search,
  .filter {
    width: 100%;
  }

  .card-grid,
  .dialog-grid {
    grid-template-columns: 1fr;
  }
}
</style>
