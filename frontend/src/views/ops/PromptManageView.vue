<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  RefreshRight,
  Edit,
  Upload,
} from "@element-plus/icons-vue";
import { usePromptAdminStore } from "@/stores/prompt-admin.store";
import type { PromptDefinitionSummary, PromptVersionItem } from "@/types/prompt-admin.types";

const store = usePromptAdminStore();

const loading = computed(() => store.loading);
const overview = computed(() => store.overview);
const agentGroups = computed(() => store.agentGroups);
const detail = computed(() => store.detail);

const selectedAgent = ref("");
const activeRightTab = ref<"edit" | "code" | "diff" | "history">("edit");
const editorDraft = ref("");
const changeSummary = ref("");
const saving = ref(false);
const publishing = ref(false);
const rollingBack = ref(false);
const syncing = ref(false);
const editorReadonly = ref(true);

// Initialize from active content
watch(detail, (d) => {
  if (d) {
    editorDraft.value = d.active_content;
    changeSummary.value = "";
    activeRightTab.value = "edit";
  }
});

onMounted(async () => {
  try {
    await store.fetchOverview();
    await store.fetchDefinitions();
    if (store.definitions.length > 0) {
      await selectPrompt(store.definitions[0]);
    }
  } catch {
    ElMessage.error("加载 Prompt 管理数据失败，请刷新重试");
  }
});

function selectAgent(name: string) {
  selectedAgent.value = name === selectedAgent.value ? "" : name;
}

async function selectPrompt(def: PromptDefinitionSummary) {
  store.selectPrompt(def.prompt_key);
  try {
    await store.fetchDetail(def.prompt_key);
  } catch {
    ElMessage.error("加载 Prompt 详情失败");
  }
}

function toggleEdit() {
  editorReadonly.value = !editorReadonly.value;
  if (editorReadonly.value) {
    editorDraft.value = detail.value?.active_content ?? "";
  }
}

async function saveDraft() {
  if (!detail.value) return;
  saving.value = true;
  try {
    await store.createVersion(
      detail.value.prompt_key,
      editorDraft.value,
      changeSummary.value || undefined,
      detail.value.active_content_hash,
    );
    ElMessage.success("草稿已保存");
    changeSummary.value = "";
    editorReadonly.value = true;
  } catch {
    ElMessage.error("保存草稿失败");
  } finally {
    saving.value = false;
  }
}

async function publishLatest() {
  if (!detail.value) return;
  const draft = detail.value.versions.find((v) => v.status === "draft");
  if (!draft) {
    ElMessage.warning("没有待发布的草稿版本。请先保存草稿。");
    return;
  }
  publishing.value = true;
  try {
    await store.publishVersion(draft.id);
    ElMessage.success(`版本 v${draft.version} 已发布`);
  } catch {
    ElMessage.error("发布失败");
  } finally {
    publishing.value = false;
  }
}

async function rollbackTo(version: PromptVersionItem) {
  if (!detail.value) return;
  try {
    await ElMessageBox.confirm(
      `确定回滚到版本 v${version.version}？当前生效版本将被替换。`,
      "确认回滚",
      { confirmButtonText: "确认回滚", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  rollingBack.value = true;
  try {
    await store.rollback(detail.value.prompt_key, version.id);
    ElMessage.success(`已回滚到版本 v${version.version}`);
  } catch {
    ElMessage.error("回滚失败");
  } finally {
    rollingBack.value = false;
  }
}

async function showDiff() {
  if (!detail.value) return;
  activeRightTab.value = "diff";
  try {
    await store.fetchDiff(detail.value.prompt_key);
  } catch {
    ElMessage.error("加载差异对比失败");
  }
}

async function syncScan() {
  syncing.value = true;
  try {
    const result = await store.scanCodePrompts();
    ElMessage.success(`扫描完成：发现 ${result.scanned}，新建 ${result.created}，更新 ${result.updated}，缺失 ${result.missing}`);
  } catch {
    ElMessage.error("同步扫描失败");
  } finally {
    syncing.value = false;
  }
}

function syncStatusLabel(s: string): string {
  const map: Record<string, string> = {
    synced: "代码默认",
    code_changed: "代码已变化",
    db_override: "数据库覆盖",
    conflict: "有冲突",
    missing_in_code: "缺失代码",
  };
  return map[s] ?? s;
}

function syncStatusClass(s: string): string {
  const map: Record<string, string> = {
    synced: "tag-blue",
    code_changed: "tag-amber",
    db_override: "tag-green",
    conflict: "tag-red",
    missing_in_code: "tag-gray",
  };
  return map[s] ?? "tag-gray";
}

function versionStatusClass(s: string): string {
  const map: Record<string, string> = {
    draft: "tag-gray",
    review: "tag-amber",
    approved: "tag-green",
    deprecated: "tag-gray",
  };
  return map[s] ?? "tag-gray";
}

function formatDate(d?: string): string {
  if (!d) return "--";
  return new Date(d).toLocaleString("zh-CN");
}

function editorLineCount(content: string): number {
  return (content || "").split("\n").length;
}
</script>

<template>
  <div class="prompt-admin-root">
    <!-- Page header -->
    <div class="page-masthead">
      <h1 class="page-title">Prompt 管理</h1>
      <p class="page-subtitle">集中管理各 Agent 与流程阶段使用的提示词，支持代码默认版本、数据库生效版本、差异对比、发布和回滚。</p>
    </div>

    <!-- Top overview strip -->
    <div class="overview-strip">
      <div class="overview-item">
        <span class="overview-value">{{ overview?.total ?? 0 }}</span>
        <span class="overview-label">总 Prompt</span>
      </div>
      <div class="overview-sep" />
      <div class="overview-item accent-green">
        <span class="overview-value">{{ overview?.db_override ?? 0 }}</span>
        <span class="overview-label">数据库覆盖</span>
      </div>
      <div class="overview-sep" />
      <div class="overview-item accent-amber">
        <span class="overview-value">{{ overview?.code_changed ?? 0 }}</span>
        <span class="overview-label">代码有变化</span>
      </div>
      <div class="overview-sep" />
      <div class="overview-item accent-red">
        <span class="overview-value">{{ overview?.conflict ?? 0 }}</span>
        <span class="overview-label">有冲突</span>
      </div>
      <div class="overview-sep" />
      <div class="overview-item accent-gray">
        <span class="overview-value">{{ overview?.missing_in_code ?? 0 }}</span>
        <span class="overview-label">缺失代码</span>
      </div>
      <div class="overview-spacer" />
      <el-button :icon="RefreshRight" :loading="syncing" size="small" text @click="syncScan">
        同步代码
      </el-button>
    </div>

    <!-- Three-column body -->
    <div class="columns-shell">
      <!-- Left: Location tree -->
      <aside class="left-tree">
        <div class="tree-header">
          <span class="tree-title">位置</span>
        </div>
        <nav class="tree-body">
          <div v-for="group in agentGroups" :key="group.name" class="tree-group">
            <button
              class="tree-group-btn"
              :class="{ open: selectedAgent === group.name }"
              @click="selectAgent(group.name)"
            >
              <span class="tree-chevron">{{ selectedAgent === group.name ? "▾" : "▸" }}</span>
              <span class="tree-group-name">{{ group.name }}</span>
              <span class="tree-group-count">{{ group.items.length }}</span>
            </button>
            <div v-if="selectedAgent === group.name" class="tree-items">
              <button
                v-for="item in group.items"
                :key="item.prompt_key"
                class="tree-item"
                :class="{ active: store.selectedPromptKey === item.prompt_key }"
                @click="selectPrompt(item)"
              >
                <span class="tree-item-name">{{ item.display_name }}</span>
                <span v-if="item.sync_status !== 'synced'" class="tree-item-dot" :class="syncStatusClass(item.sync_status)" />
              </button>
            </div>
          </div>
        </nav>
      </aside>

      <!-- Middle: Prompt cards -->
      <section class="mid-list">
        <div class="mid-list-header">
          <span class="mid-list-title">Prompt 详情</span>
          <span v-if="store.definitions.length" class="mid-list-count">{{ store.definitions.length }}</span>
        </div>
        <div class="mid-list-body" v-loading="loading">
          <button
            v-for="def in store.definitions"
            :key="def.prompt_key"
            class="prompt-card"
            :class="{ active: store.selectedPromptKey === def.prompt_key }"
            @click="selectPrompt(def)"
          >
            <div class="card-top">
              <span class="card-name">{{ def.display_name }}</span>
              <span class="card-tag" :class="syncStatusClass(def.sync_status)">
                {{ syncStatusLabel(def.sync_status) }}
              </span>
            </div>
            <div class="card-location">{{ def.usage_location || def.agent_name }}</div>
            <div class="card-key mono">{{ def.prompt_key }}</div>
            <div class="card-meta">
              <span v-if="def.active_version">v{{ def.active_version }} · {{ def.current_source === "database" ? "数据库生效" : "代码默认" }}</span>
              <span v-else>代码默认</span>
              <span>{{ formatDate(def.updated_at) }}</span>
            </div>
          </button>
          <el-empty v-if="!store.definitions.length && !loading" description="暂无 Prompt 定义，请先同步代码" :image-size="80" />
        </div>
      </section>

      <!-- Right: Editor + detail -->
      <section class="right-panel" v-if="detail">
        <!-- Header with back button -->
        <div class="panel-header">
          <div class="panel-header-left">
            <h2 class="panel-title">{{ detail.display_name }}</h2>
            <div class="panel-badges">
              <span class="card-tag" :class="syncStatusClass(detail.sync_status)">
                {{ syncStatusLabel(detail.sync_status) }}
              </span>
              <span v-if="detail.active_version" class="card-tag tag-green">v{{ detail.active_version }}</span>
            </div>
          </div>
          <div class="panel-header-actions">
            <el-button v-if="editorReadonly" :icon="Edit" size="small" @click="toggleEdit">编辑</el-button>
            <el-button v-else size="small" text @click="toggleEdit">取消编辑</el-button>
            <el-button
              v-if="!editorReadonly"
              type="primary"
              size="small"
              :loading="saving"
              @click="saveDraft"
            >
              保存草稿
            </el-button>
            <el-button
              :icon="Upload"
              size="small"
              :loading="publishing"
              @click="publishLatest"
            >
              发布
            </el-button>
          </div>
        </div>

        <!-- Meta info row -->
        <div class="panel-meta">
          <div class="meta-item">
            <span class="meta-label">位置</span>
            <span class="meta-value">{{ detail.usage_location || detail.agent_name + " / " + detail.stage_name }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">代码文件</span>
            <span class="meta-value mono">{{ detail.source_file || "--" }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Prompt Key</span>
            <span class="meta-value mono">{{ detail.prompt_key }}</span>
          </div>
          <div class="meta-item" v-if="detail.description">
            <span class="meta-label">说明</span>
            <span class="meta-value">{{ detail.description }}</span>
          </div>
        </div>

        <!-- Tab bar -->
        <div class="tab-bar">
          <button
            class="tab-btn"
            :class="{ active: activeRightTab === 'edit' }"
            @click="activeRightTab = 'edit'"
          >编辑</button>
          <button
            class="tab-btn"
            :class="{ active: activeRightTab === 'code' }"
            @click="activeRightTab = 'code'"
          >代码默认版本</button>
          <button
            class="tab-btn"
            :class="{ active: activeRightTab === 'diff' }"
            @click="showDiff"
          >差异对比</button>
          <button
            class="tab-btn"
            :class="{ active: activeRightTab === 'history' }"
            @click="activeRightTab = 'history'"
          >历史版本</button>
        </div>

        <!-- Tab content -->
        <div class="tab-content">
          <!-- Edit tab -->
          <div v-if="activeRightTab === 'edit'" class="editor-shell">
            <div class="editor-meta-row">
              <span class="editor-meta">行数：{{ editorLineCount(editorDraft) }} · 字符数：{{ editorDraft.length }}</span>
              <span class="editor-meta" v-if="!editorReadonly">编辑模式 · 内容将保存为草稿</span>
              <span class="editor-meta" v-else>只读模式 · 点击"编辑"开始修改</span>
            </div>
            <textarea
              v-model="editorDraft"
              class="prompt-editor"
              :readonly="editorReadonly"
              spellcheck="false"
            />
            <div v-if="!editorReadonly" class="editor-footer">
              <el-input
                v-model="changeSummary"
                placeholder="变更说明（可选）"
                size="small"
                class="change-input"
              />
            </div>
          </div>

          <!-- Code default tab -->
          <div v-if="activeRightTab === 'code'" class="editor-shell">
            <div class="editor-meta-row">
              <span class="editor-meta">代码默认版本 · 只读 · 行数：{{ editorLineCount(detail.code_default_content) }}</span>
            </div>
            <textarea
              :value="detail.code_default_content"
              class="prompt-editor"
              readonly
              spellcheck="false"
            />
          </div>

          <!-- Diff tab -->
          <div v-if="activeRightTab === 'diff'" class="diff-panel">
            <div v-if="store.diff" class="diff-columns">
              <div class="diff-col">
                <div class="diff-col-header">{{ store.diff.left_label }}</div>
                <pre class="diff-content">{{ store.diff.left_content }}</pre>
              </div>
              <div class="diff-col">
                <div class="diff-col-header">{{ store.diff.right_label }}</div>
                <pre class="diff-content">{{ store.diff.right_content }}</pre>
              </div>
            </div>
            <el-empty v-else description="加载差异中..." :image-size="60" />
          </div>

          <!-- History tab -->
          <div v-if="activeRightTab === 'history'" class="history-panel">
            <div v-if="detail.versions.length" class="version-list">
              <div
                v-for="v in detail.versions"
                :key="v.id"
                class="version-item"
                :class="{ current: v.version === detail.active_version }"
              >
                <div class="version-top">
                  <div class="version-left">
                    <strong>v{{ v.version }}</strong>
                    <span class="card-tag" :class="versionStatusClass(v.status)">{{ v.status === "approved" ? "已发布" : v.status === "draft" ? "草稿" : v.status === "review" ? "审核中" : "已废弃" }}</span>
                    <span v-if="v.version === detail.active_version" class="card-tag tag-green">当前生效</span>
                  </div>
                  <div class="version-right">
                    <span class="version-date">{{ formatDate(v.created_at) }}</span>
                    <el-button
                      v-if="v.version !== detail.active_version && v.status === 'approved'"
                      size="small"
                      text
                      :loading="rollingBack"
                      @click="rollbackTo(v)"
                    >
                      回滚到此版本
                    </el-button>
                  </div>
                </div>
                <div v-if="v.change_summary" class="version-summary">{{ v.change_summary }}</div>
                <pre class="version-preview">{{ v.content.slice(0, 200) }}{{ v.content.length > 200 ? "..." : "" }}</pre>
              </div>
            </div>
            <el-empty v-else description="暂无历史版本" :image-size="80" />
          </div>
        </div>
      </section>

      <!-- Right panel empty state -->
      <section class="right-panel empty-panel" v-else>
        <el-empty description="请从左侧选择一个 Prompt" :image-size="100" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.prompt-admin-root {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 64px);
  background: oklch(0.97 0.003 260);
}

/* ── Page masthead ── */
.page-masthead {
  padding: 16px 20px 6px;
  flex-shrink: 0;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: oklch(0.18 0.012 260);
  line-height: 1.3;
}

.page-subtitle {
  margin: 2px 0 0;
  font-size: 13px;
  color: oklch(0.5 0.012 260);
  max-width: 780px;
}

/* ── Overview strip ── */
.overview-strip {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 14px 20px;
  border-bottom: 1px solid oklch(0.89 0.006 260);
  background: oklch(0.99 0.002 260);
  flex-shrink: 0;
}

.overview-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 90px;
  padding: 0 16px;
}

.overview-value {
  font-size: 22px;
  font-weight: 700;
  color: oklch(0.2 0.012 260);
  line-height: 1.2;
}

.overview-label {
  font-size: 12px;
  color: oklch(0.5 0.012 260);
  margin-top: 2px;
}

.overview-item.accent-green .overview-value { color: oklch(0.48 0.12 175); }
.overview-item.accent-amber .overview-value { color: oklch(0.55 0.12 85); }
.overview-item.accent-red .overview-value { color: oklch(0.48 0.16 25); }
.overview-item.accent-gray .overview-value { color: oklch(0.45 0.01 260); }

.overview-sep {
  width: 1px;
  height: 32px;
  background: oklch(0.88 0.006 260);
}

.overview-spacer {
  flex: 1;
}

/* ── Three column shell ── */
.columns-shell {
  display: grid;
  grid-template-columns: 240px minmax(280px, 340px) 1fr;
  flex: 1;
  overflow: hidden;
}

/* ── Left tree ── */
.left-tree {
  border-right: 1px solid oklch(0.89 0.006 260);
  background: oklch(0.985 0.002 260);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tree-header {
  padding: 16px 16px 10px;
  flex-shrink: 0;
}

.tree-title {
  font-size: 13px;
  font-weight: 700;
  color: oklch(0.35 0.012 260);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.tree-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 16px;
}

.tree-group {
  margin-bottom: 4px;
}

.tree-group-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: oklch(0.3 0.012 260);
  transition: background 0.15s ease;
}

.tree-group-btn:hover {
  background: oklch(0.94 0.006 260);
}

.tree-group-btn.open {
  font-weight: 600;
}

.tree-chevron {
  font-size: 10px;
  width: 14px;
  text-align: center;
  color: oklch(0.5 0.012 260);
}

.tree-group-name {
  flex: 1;
  text-align: left;
}

.tree-group-count {
  font-size: 11px;
  color: oklch(0.5 0.012 260);
  background: oklch(0.92 0.006 260);
  padding: 1px 6px;
  border-radius: 999px;
}

.tree-items {
  padding-left: 20px;
}

.tree-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 5px 10px;
  border: none;
  border-radius: 5px;
  background: transparent;
  cursor: pointer;
  font-size: 12.5px;
  color: oklch(0.38 0.012 260);
  transition: background 0.15s ease;
  text-align: left;
}

.tree-item:hover {
  background: oklch(0.93 0.006 260);
}

.tree-item.active {
  background: oklch(0.9 0.03 200);
  color: oklch(0.35 0.08 230);
  font-weight: 600;
}

.tree-item-name {
  flex: 1;
}

.tree-item-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ── Middle list ── */
.mid-list {
  border-right: 1px solid oklch(0.89 0.006 260);
  background: oklch(0.99 0.002 260);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mid-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 10px;
  flex-shrink: 0;
}

.mid-list-title {
  font-size: 13px;
  font-weight: 700;
  color: oklch(0.35 0.012 260);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.mid-list-count {
  font-size: 11px;
  color: oklch(0.5 0.012 260);
  background: oklch(0.92 0.006 260);
  padding: 2px 8px;
  border-radius: 999px;
}

.mid-list-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Prompt card ── */
.prompt-card {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid oklch(0.9 0.006 260);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.prompt-card:hover {
  border-color: oklch(0.78 0.03 215);
}

.prompt-card.active {
  border-color: oklch(0.72 0.06 220);
  box-shadow: 0 0 0 2px oklch(0.72 0.06 220 / 0.25);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: oklch(0.2 0.012 260);
}

.card-location {
  margin-top: 4px;
  font-size: 12.5px;
  color: oklch(0.48 0.012 260);
  line-height: 1.4;
}

.card-key {
  margin-top: 1px;
  font-size: 11px;
  color: oklch(0.55 0.01 260);
}

.card-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11.5px;
  color: oklch(0.55 0.012 260);
}

/* ── Tags ── */
.card-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.5;
}

.tag-blue {
  background: oklch(0.92 0.03 240);
  color: oklch(0.42 0.08 235);
}

.tag-green {
  background: oklch(0.92 0.06 165);
  color: oklch(0.45 0.1 165);
}

.tag-amber {
  background: oklch(0.93 0.08 85);
  color: oklch(0.5 0.1 80);
}

.tag-red {
  background: oklch(0.93 0.06 25);
  color: oklch(0.48 0.14 22);
}

.tag-gray {
  background: oklch(0.92 0.006 260);
  color: oklch(0.45 0.01 260);
}

/* ── Right panel ── */
.right-panel {
  background: oklch(0.99 0.002 260);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-panel.empty-panel {
  display: flex;
  align-items: center;
  justify-content: center;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid oklch(0.9 0.006 260);
  flex-shrink: 0;
}

.panel-header-left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: oklch(0.18 0.012 260);
  margin: 0;
  line-height: 1.25;
}

.panel-badges {
  display: flex;
  gap: 6px;
}

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.panel-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 20px;
  padding: 10px 20px;
  border-bottom: 1px solid oklch(0.92 0.006 260);
  flex-shrink: 0;
}

.meta-item {
  display: flex;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.6;
}

.meta-label {
  color: oklch(0.5 0.01 260);
  white-space: nowrap;
  min-width: 60px;
}

.meta-value {
  color: oklch(0.25 0.012 260);
}

.meta-value.mono {
  font-family: "ui-monospace", "SF Mono", "Menlo", "Consolas", monospace;
  font-size: 11.5px;
}

/* ── Tab bar ── */
.tab-bar {
  display: flex;
  gap: 0;
  padding: 0 20px;
  border-bottom: 1px solid oklch(0.9 0.006 260);
  flex-shrink: 0;
}

.tab-btn {
  padding: 10px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  font-size: 13px;
  color: oklch(0.5 0.012 260);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.tab-btn:hover {
  color: oklch(0.25 0.012 260);
}

.tab-btn.active {
  color: oklch(0.35 0.08 230);
  border-bottom-color: oklch(0.5 0.1 235);
  font-weight: 600;
}

.tab-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── Editor ── */
.editor-shell {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 20px;
  flex-shrink: 0;
}

.editor-meta {
  font-size: 11.5px;
  color: oklch(0.5 0.01 260);
}

.prompt-editor {
  flex: 1;
  width: 100%;
  padding: 16px 20px;
  border: none;
  outline: none;
  resize: none;
  font-family: "ui-monospace", "SF Mono", "Menlo", "Monaco", "Consolas", monospace;
  font-size: 13.5px;
  line-height: 1.65;
  color: oklch(0.2 0.012 260);
  background: oklch(0.985 0.002 260);
  tab-size: 2;
}

.prompt-editor:focus {
  background: #fff;
}

.editor-footer {
  padding: 8px 20px 12px;
  border-top: 1px solid oklch(0.92 0.006 260);
  flex-shrink: 0;
}

.change-input {
  max-width: 360px;
}

/* ── Diff ── */
.diff-panel {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}

.diff-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  height: 100%;
}

.diff-col {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.diff-col-header {
  font-size: 13px;
  font-weight: 600;
  color: oklch(0.3 0.012 260);
  padding-bottom: 8px;
  border-bottom: 1px solid oklch(0.9 0.006 260);
  flex-shrink: 0;
}

.diff-content {
  flex: 1;
  overflow: auto;
  margin: 0;
  padding: 10px 0;
  font-family: "ui-monospace", "SF Mono", "Menlo", "Monaco", "Consolas", monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: oklch(0.25 0.012 260);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── History ── */
.history-panel {
  flex: 1;
  overflow: auto;
  padding: 12px 20px;
}

.version-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.version-item {
  padding: 12px 14px;
  border: 1px solid oklch(0.9 0.006 260);
  border-radius: 8px;
  background: #fff;
}

.version-item.current {
  border-color: oklch(0.72 0.06 220);
  background: oklch(0.97 0.02 225);
}

.version-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.version-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: oklch(0.25 0.012 260);
}

.version-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-date {
  font-size: 11.5px;
  color: oklch(0.5 0.01 260);
}

.version-summary {
  margin-top: 6px;
  font-size: 12.5px;
  color: oklch(0.4 0.012 260);
}

.version-preview {
  margin: 8px 0 0;
  padding: 8px 10px;
  background: oklch(0.98 0.003 260);
  border-radius: 4px;
  font-family: "ui-monospace", "SF Mono", "Menlo", "Monaco", "Consolas", monospace;
  font-size: 11.5px;
  line-height: 1.5;
  color: oklch(0.4 0.01 260);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Responsive ── */
@media (max-width: 1400px) {
  .columns-shell {
    grid-template-columns: 220px minmax(240px, 300px) 1fr;
  }
}

@media (max-width: 1100px) {
  .columns-shell {
    grid-template-columns: 1fr;
  }

  .left-tree,
  .mid-list {
    display: none;
  }

  .panel-meta {
    grid-template-columns: 1fr;
  }

  .diff-columns {
    grid-template-columns: 1fr;
  }
}
</style>
