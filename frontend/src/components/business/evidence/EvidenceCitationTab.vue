<script setup lang="ts">
import { computed, ref, watch } from "vue"
import EvidenceJsonDialog from "./EvidenceJsonDialog.vue"

const props = defineProps<{
  citations: Record<string, any> | any[] | null
}>()

const selectedIdx = ref(0)
const jsonDialogRef = ref<InstanceType<typeof EvidenceJsonDialog>>()

interface CitationItem {
  name: string
  source: string
  sourceLabel: string
  rawType: string
  relevance: number
  excerpt: string
  page?: string
  chapter?: string
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function toNumber(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeSourceLabel(raw: Record<string, any>) {
  const kind = String(raw.kind || raw.type || raw.category || raw.evidence_type || "").toLowerCase()
  const source = String(raw.source || "").toLowerCase()
  const id = String(raw.id || "").toLowerCase()
  const attachmentType = String(raw.attachment_type || "").toLowerCase()

  if (kind.includes("rag")) return "RAG 引用"

  if (
    source === "chat_query"
    || id === "structured-query"
    || attachmentType === "structured_input"
    || kind === "structured_input"
  ) {
    return "结构化输入"
  }

  if (kind.includes("attachment") || attachmentType) {
    return "附件证据"
  }

  return "引用证据"
}

function normalizeCitationList(citations: Record<string, any> | any[] | null) {
  if (!citations) return []
  if (Array.isArray(citations)) return citations
  if (Array.isArray(citations.items)) return citations.items
  return Object.entries(citations).map(([key, value]) => (
    isRecord(value) ? { __key: key, ...value } : { __key: key, value }
  ))
}

const citationList = computed<CitationItem[]>(() => {
  return normalizeCitationList(props.citations)
    .filter((item) => isRecord(item))
    .map((item, index) => {
      const rawType = String(item.kind || item.type || item.category || item.evidence_type || "unknown")
      return {
        name: String(item.name || item.title || item.document || item.filename || item.__key || `引用 ${index + 1}`),
        source: String(item.source || item.file || item.url || item.path || "-"),
        sourceLabel: normalizeSourceLabel(item),
        rawType,
        relevance: toNumber(item.relevance ?? item.score ?? item.similarity),
        excerpt: String(item.excerpt || item.text || item.content || item.snippet || ""),
        page: item.page || item.section || undefined,
        chapter: item.chapter || item.clause || undefined,
      }
    })
})

watch(
  citationList,
  (items) => {
    if (!items.length) {
      selectedIdx.value = 0
      return
    }
    if (selectedIdx.value >= items.length) {
      selectedIdx.value = 0
    }
  },
  { immediate: true },
)

const selected = computed(() => citationList.value[selectedIdx.value] || null)

function relevanceColor(value: number) {
  if (value >= 0.8) return "success"
  if (value >= 0.5) return "warning"
  return "info"
}

function relevancePct(value: number) {
  return `${(value * 100).toFixed(0)}%`
}

function openRawJson() {
  jsonDialogRef.value?.open()
}
</script>

<template>
  <div class="citation-tab">
    <div v-if="!citationList.length" class="empty-full">
      <el-empty description="暂无引用证据" :image-size="80" />
    </div>

    <div v-else class="citation-layout">
      <div class="source-list">
        <div class="list-header">
          <span>引用证据 ({{ citationList.length }})</span>
          <el-button size="small" text @click="openRawJson">原始 JSON</el-button>
        </div>
        <button
          v-for="(item, idx) in citationList"
          :key="`${item.name}-${idx}`"
          class="source-row"
          :class="{ active: idx === selectedIdx }"
          @click="selectedIdx = idx"
        >
          <div class="source-head">
            <span class="source-name">{{ item.name }}</span>
            <el-tag :type="relevanceColor(item.relevance)" size="small">
              {{ relevancePct(item.relevance) }}
            </el-tag>
          </div>
          <div class="source-meta">
            <span class="source-type">{{ item.sourceLabel }}</span>
            <span v-if="item.source !== '-'" class="source-file">{{ item.source }}</span>
          </div>
        </button>
      </div>

      <div class="citation-detail">
        <template v-if="selected">
          <div class="detail-header">
            <h3 class="detail-title">{{ selected.name }}</h3>
            <div class="detail-tags">
              <el-tag size="small">{{ selected.sourceLabel }}</el-tag>
              <el-tag v-if="selected.rawType && selected.rawType !== 'unknown'" size="small" type="info">
                {{ selected.rawType }}
              </el-tag>
              <el-tag v-if="selected.page" size="small" type="info">{{ selected.page }}</el-tag>
              <el-tag v-if="selected.chapter" size="small" type="info">{{ selected.chapter }}</el-tag>
            </div>
          </div>

          <div class="detail-section">
            <span class="section-label">来源位置</span>
            <code class="section-value">{{ selected.source }}</code>
          </div>

          <div class="detail-section">
            <span class="section-label">引用片段</span>
            <blockquote class="excerpt">
              {{ selected.excerpt || "暂无文本片段" }}
            </blockquote>
          </div>

          <div class="detail-actions">
            <el-button size="small" @click="openRawJson">查看原始 JSON</el-button>
          </div>
        </template>
        <div v-else class="detail-empty">
          <span class="text-zinc-400 text-sm">选择左侧引用证据查看详情</span>
        </div>
      </div>
    </div>

    <EvidenceJsonDialog
      ref="jsonDialogRef"
      title="引用证据原始 JSON"
      :data="citations"
    />
  </div>
</template>

<style scoped>
.citation-tab {
  padding: 24px;
}

.empty-full {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.citation-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 0;
  border: 1px solid oklch(0.92 0.005 260);
  border-radius: 10px;
  overflow: hidden;
  max-height: calc(100vh - 220px);
}

.source-list {
  border-right: 1px solid oklch(0.92 0.005 260);
  overflow-y: auto;
  background: oklch(0.985 0.003 260);
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid oklch(0.92 0.005 260);
  font-size: 13px;
  font-weight: 600;
  color: oklch(0.35 0.01 260);
  position: sticky;
  top: 0;
  background: oklch(0.985 0.003 260);
}

.source-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 14px 16px;
  border: none;
  border-bottom: 1px solid oklch(0.94 0.003 260);
  background: none;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s;
}

.source-row:hover {
  background: oklch(0.96 0.005 260);
}

.source-row.active {
  background: oklch(0.95 0.04 250 / 0.1);
  border-left: 3px solid oklch(0.5 0.14 250);
}

.source-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.source-name {
  font-size: 14px;
  font-weight: 600;
  color: oklch(0.25 0.01 260);
}

.source-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: oklch(0.5 0.01 260);
  flex-wrap: wrap;
}

.source-type {
  padding: 1px 6px;
  background: oklch(0.94 0.005 260);
  border-radius: 3px;
}

.source-file {
  word-break: break-all;
}

.citation-detail {
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-title {
  font-size: 16px;
  font-weight: 700;
  color: oklch(0.2 0.01 260);
  margin: 0;
}

.detail-tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: oklch(0.45 0.01 260);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.section-value {
  font-size: 13px;
  font-family: "JetBrains Mono", monospace;
  color: oklch(0.45 0.01 260);
  background: oklch(0.97 0.005 260);
  padding: 6px 10px;
  border-radius: 4px;
  word-break: break-all;
}

.excerpt {
  margin: 0;
  padding: 14px 16px;
  background: oklch(0.97 0.005 260);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.7;
  color: oklch(0.35 0.01 260);
  border-left: none;
  white-space: pre-wrap;
}

.detail-actions {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid oklch(0.94 0.003 260);
}

.detail-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 960px) {
  .citation-layout {
    grid-template-columns: 1fr;
  }

  .source-list {
    border-right: none;
    border-bottom: 1px solid oklch(0.92 0.005 260);
    max-height: 280px;
  }
}
</style>
