<template>
  <div class="tool-import">
    <section class="page-header">
      <div>
        <h1 class="page-title">导入与同步</h1>
        <p class="page-subtitle">统一接入内置工具、OpenAPI 接口和 MCP Server，先导入为可管理工具，再进入工具库继续测试和发布。</p>
      </div>
      <el-tag type="info" effect="plain" round>工具管理 / 外部导入</el-tag>
    </section>

    <section class="status-strip">
      <div class="status-item">
        <span class="status-label">当前能力</span>
        <strong>内置同步、OpenAPI 解析、MCP 发现</strong>
      </div>
      <div class="status-item">
        <span class="status-label">建议流程</span>
        <strong>导入后到工具库校验，再进入详情页做测试与配置</strong>
      </div>
    </section>

    <section class="cards-grid">
      <article class="entry-card">
        <div class="entry-head">
          <div>
            <h2 class="entry-title">内置工具同步</h2>
            <p class="entry-desc">扫描 `agent/tools/builtin/` 下的工具清单，并同步到当前工具注册表。</p>
          </div>
          <el-tag size="small" type="success" effect="plain">可直接执行</el-tag>
        </div>
        <ul class="entry-points">
          <li>适合代码内置工具纳管</li>
          <li>自动补齐工具元数据</li>
          <li>同步结果会展示新增、更新和未变化数量</li>
        </ul>
        <div class="entry-actions">
          <el-button type="primary" :loading="store.syncingBuiltin" @click="runSync">立即同步</el-button>
          <el-button text @click="activePanel = 'builtin'">查看结果</el-button>
        </div>
      </article>

      <article class="entry-card">
        <div class="entry-head">
          <div>
            <h2 class="entry-title">OpenAPI 导入</h2>
            <p class="entry-desc">从 OpenAPI 3.x 规范的 URL 或原始内容中解析接口，批量生成 HTTP 工具草稿。</p>
          </div>
          <el-tag size="small" type="warning" effect="plain">分步导入</el-tag>
        </div>
        <ul class="entry-points">
          <li>先解析候选接口，再选择导入</li>
          <li>适合批量纳管外部 API</li>
          <li>导入完成后建议回到工具库继续检查</li>
        </ul>
        <div class="entry-actions">
          <el-button type="primary" @click="activePanel = 'openapi'">开始导入</el-button>
          <el-button text @click="resetOpenapi">清空当前流程</el-button>
        </div>
      </article>

      <article class="entry-card">
        <div class="entry-head">
          <div>
            <h2 class="entry-title">MCP Server 导入</h2>
            <p class="entry-desc">连接 MCP Server，发现其暴露的工具列表，并为后续纳管准备候选清单。</p>
          </div>
          <el-tag size="small" type="warning" effect="plain">发现候选</el-tag>
        </div>
        <ul class="entry-points">
          <li>适合先盘点远端 MCP 能力</li>
          <li>按服务地址动态发现工具</li>
          <li>结果会展示工具名称、描述和输入结构</li>
        </ul>
        <div class="entry-actions">
          <el-button type="primary" @click="activePanel = 'mcp'">发现工具</el-button>
          <el-button text @click="resetMcp">重置</el-button>
        </div>
      </article>

      <article class="entry-card muted-card">
        <div class="entry-head">
          <div>
            <h2 class="entry-title">手动创建 HTTP 工具</h2>
            <p class="entry-desc">单个接口接入时，直接进入工具库创建工具，再在详情页补充 Schema、超时和测试参数。</p>
          </div>
          <el-tag size="small" effect="plain">单点创建</el-tag>
        </div>
        <ul class="entry-points">
          <li>适合单接口、临时接入或快速验证</li>
          <li>避免为单个接口走完整导入流程</li>
          <li>创建后可继续做版本和绑定配置</li>
        </ul>
        <div class="entry-actions">
          <el-button type="primary" plain @click="$router.push('/ops/tools/catalog')">前往工具库</el-button>
        </div>
      </article>
    </section>

    <section class="workspace-panel">
      <div class="workspace-header">
        <div>
          <h2 class="workspace-title">{{ workspaceTitle }}</h2>
          <p class="workspace-subtitle">{{ workspaceSubtitle }}</p>
        </div>
        <div class="workspace-actions">
          <el-button v-if="activePanel === 'openapi'" text @click="resetOpenapi">重置流程</el-button>
          <el-button v-if="activePanel === 'mcp'" text @click="resetMcp">重置流程</el-button>
        </div>
      </div>

      <template v-if="activePanel === 'builtin'">
        <div v-if="store.lastSyncResult" class="result-stats">
          <div class="stat-box">
            <span>新增</span>
            <strong>{{ store.lastSyncResult.created }}</strong>
          </div>
          <div class="stat-box">
            <span>更新</span>
            <strong>{{ store.lastSyncResult.updated }}</strong>
          </div>
          <div class="stat-box">
            <span>未变化</span>
            <strong>{{ store.lastSyncResult.unchanged }}</strong>
          </div>
        </div>
        <el-empty
          v-else
          description="还没有同步结果。点击上方“立即同步”后，这里会显示本次扫描明细。"
        />
        <el-table
          v-if="store.lastSyncResult?.details?.length"
          :data="store.lastSyncResult.details"
          size="small"
          stripe
        >
          <el-table-column prop="tool_key" label="Tool Key" min-width="240" />
          <el-table-column prop="action" label="结果" width="120" />
        </el-table>
      </template>

      <template v-else-if="activePanel === 'openapi'">
        <el-form label-position="top">
          <el-form-item label="OpenAPI 规范 URL 或 JSON/YAML 内容">
            <el-input
              v-model="openapiSource"
              type="textarea"
              :rows="8"
              placeholder="https://example.com/openapi.json 或直接粘贴 JSON / YAML 规范内容"
            />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="previewing" @click="previewOpenapi">解析候选工具</el-button>
            <el-button @click="resetOpenapi">清空</el-button>
          </div>
        </el-form>

        <div v-if="openapiCandidates.length" class="result-block">
          <div class="result-summary">
            <strong>已发现 {{ openapiCandidates.length }} 个候选工具</strong>
            <span>选择需要纳管的接口后导入。</span>
          </div>
          <el-table
            :data="openapiCandidates"
            stripe
            size="small"
            max-height="360"
            @selection-change="onOpenapiSelect"
          >
            <el-table-column type="selection" width="44" />
            <el-table-column prop="tool_key" label="Tool Key" min-width="220" />
            <el-table-column prop="display_name" label="名称" min-width="180" />
            <el-table-column prop="endpoint" label="路径" min-width="180" />
            <el-table-column prop="method" label="方法" width="90" />
          </el-table>
          <div class="form-actions">
            <el-button type="primary" :loading="importing" @click="importOpenapi">导入选中工具</el-button>
          </div>
        </div>

        <el-result
          v-if="openapiImported.length"
          icon="success"
          title="导入完成"
          :sub-title="`已导入 ${openapiImported.length} 个工具，请到工具库继续测试和配置。`"
        />
      </template>

      <template v-else-if="activePanel === 'mcp'">
        <el-form label-position="top">
          <el-form-item label="MCP Server 地址">
            <el-input v-model="mcpServerUrl" placeholder="http://localhost:8000/mcp" />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="discoveringMcp" @click="discoverMcp">发现工具</el-button>
            <el-button @click="resetMcp">清空</el-button>
          </div>
        </el-form>

        <div v-if="mcpCandidates.length" class="result-block">
          <div class="result-summary">
            <strong>已发现 {{ mcpCandidates.length }} 个 MCP 工具</strong>
            <span>当前页面先用于发现能力，建议后续结合工具库继续纳管。</span>
          </div>
          <el-table :data="mcpCandidates" stripe size="small" max-height="360">
            <el-table-column prop="tool_key" label="Tool Key" min-width="220" />
            <el-table-column prop="display_name" label="名称" min-width="180" />
            <el-table-column prop="description" label="描述" min-width="240" />
          </el-table>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { http } from "@/api/http";
import { useToolsStore } from "@/stores/tools.store";

type ActivePanel = "builtin" | "openapi" | "mcp";
type ToolCandidate = Record<string, unknown>;

const store = useToolsStore();

const activePanel = ref<ActivePanel>("builtin");

const openapiSource = ref("");
const openapiCandidates = ref<ToolCandidate[]>([]);
const openapiSelected = ref<ToolCandidate[]>([]);
const openapiImported = ref<ToolCandidate[]>([]);
const previewing = ref(false);
const importing = ref(false);

const mcpServerUrl = ref("");
const mcpCandidates = ref<ToolCandidate[]>([]);
const discoveringMcp = ref(false);

const workspaceTitle = computed(() => {
  if (activePanel.value === "openapi") return "OpenAPI 导入工作台";
  if (activePanel.value === "mcp") return "MCP 发现工作台";
  return "内置同步结果";
});

const workspaceSubtitle = computed(() => {
  if (activePanel.value === "openapi") {
    return "先解析候选工具，再批量导入需要纳管的接口。";
  }
  if (activePanel.value === "mcp") {
    return "先发现远端 MCP 工具，再决定后续纳管和绑定策略。";
  }
  return "查看最近一次内置工具扫描结果。";
});

async function runSync() {
  activePanel.value = "builtin";
  const result = await store.syncBuiltin();
  ElMessage.success(
    `同步完成：新增 ${result.created}，更新 ${result.updated}，未变化 ${result.unchanged}`,
  );
}

function onOpenapiSelect(selection: ToolCandidate[]) {
  openapiSelected.value = selection;
}

async function previewOpenapi() {
  if (!openapiSource.value.trim()) {
    ElMessage.warning("请输入 OpenAPI 规范 URL 或原始内容。");
    return;
  }

  previewing.value = true;
  openapiImported.value = [];

  try {
    const response = await http.post<{ candidates: ToolCandidate[] }>(
      "/v1/tools/import/openapi/preview",
      { source: openapiSource.value },
    );
    openapiCandidates.value = response.data.data.candidates;
    openapiSelected.value = [];

    if (!openapiCandidates.value.length) {
      ElMessage.info("当前规范中没有可导入的接口。");
    }
  } catch {
    ElMessage.error("解析失败，请检查 OpenAPI 内容是否有效。");
  } finally {
    previewing.value = false;
  }
}

async function importOpenapi() {
  if (!openapiSelected.value.length) {
    ElMessage.warning("请至少选择一个候选工具。");
    return;
  }

  importing.value = true;
  try {
    const toolKeys = openapiSelected.value
      .map((item) => String(item.tool_key || ""))
      .filter(Boolean);

    const response = await http.post<{ imported: ToolCandidate[] }>("/v1/tools/import/openapi", {
      source: openapiSource.value,
      tool_keys: toolKeys,
    });

    openapiImported.value = response.data.data.imported;
    ElMessage.success(`已导入 ${openapiImported.value.length} 个工具。`);
  } catch {
    ElMessage.error("导入失败，请稍后重试。");
  } finally {
    importing.value = false;
  }
}

function resetOpenapi() {
  openapiSource.value = "";
  openapiCandidates.value = [];
  openapiSelected.value = [];
  openapiImported.value = [];
}

async function discoverMcp() {
  if (!mcpServerUrl.value.trim()) {
    ElMessage.warning("请输入 MCP Server 地址。");
    return;
  }

  discoveringMcp.value = true;
  try {
    const response = await http.post<{ candidates: ToolCandidate[] }>(
      "/v1/tools/import/mcp/preview",
      { server_url: mcpServerUrl.value },
    );
    mcpCandidates.value = response.data.data.candidates;

    if (!mcpCandidates.value.length) {
      ElMessage.info("当前服务没有返回可发现的工具。");
    }
  } catch {
    ElMessage.error("发现失败，请检查 MCP Server 地址或服务状态。");
  } finally {
    discoveringMcp.value = false;
  }
}

function resetMcp() {
  mcpServerUrl.value = "";
  mcpCandidates.value = [];
}
</script>

<style scoped>
.tool-import {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header,
.status-strip,
.entry-card,
.workspace-panel {
  border: 1px solid oklch(0.91 0.005 260);
  background: oklch(1 0 0);
  border-radius: 18px;
  box-shadow: 0 8px 24px oklch(0.2 0.01 260 / 0.04);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 24px 28px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: oklch(0.2 0.01 260);
}

.page-subtitle {
  margin: 8px 0 0;
  max-width: 74ch;
  color: oklch(0.45 0.01 260);
  line-height: 1.7;
}

.status-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  overflow: hidden;
}

.status-item {
  padding: 16px 20px;
}

.status-item + .status-item {
  border-left: 1px solid oklch(0.91 0.005 260);
}

.status-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: oklch(0.55 0.01 260);
}

.status-item strong {
  color: oklch(0.2 0.01 260);
  font-size: 14px;
  line-height: 1.6;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.entry-card {
  display: flex;
  min-height: 248px;
  flex-direction: column;
  gap: 16px;
  padding: 22px;
}

.muted-card {
  background: oklch(0.985 0.003 260);
}

.entry-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.entry-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: oklch(0.2 0.01 260);
}

.entry-desc {
  margin: 8px 0 0;
  color: oklch(0.45 0.01 260);
  line-height: 1.7;
}

.entry-points {
  margin: 0;
  padding-left: 18px;
  color: oklch(0.38 0.01 260);
  line-height: 1.8;
}

.entry-actions {
  margin-top: auto;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.workspace-panel {
  padding: 22px;
}

.workspace-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}

.workspace-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: oklch(0.2 0.01 260);
}

.workspace-subtitle {
  margin: 8px 0 0;
  color: oklch(0.45 0.01 260);
}

.workspace-actions,
.form-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.result-block {
  margin-top: 20px;
}

.result-summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
  color: oklch(0.45 0.01 260);
}

.result-summary strong {
  color: oklch(0.2 0.01 260);
  font-size: 14px;
}

.result-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-box {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 14px;
  background: oklch(0.98 0.004 260);
  padding: 14px 16px;
  color: oklch(0.45 0.01 260);
}

.stat-box strong {
  color: oklch(0.2 0.01 260);
  font-size: 20px;
}

@media (max-width: 960px) {
  .status-strip,
  .cards-grid,
  .result-stats {
    grid-template-columns: 1fr;
  }

  .status-item + .status-item {
    border-left: none;
    border-top: 1px solid oklch(0.91 0.005 260);
  }
}

@media (max-width: 768px) {
  .page-header,
  .workspace-header,
  .result-summary {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
