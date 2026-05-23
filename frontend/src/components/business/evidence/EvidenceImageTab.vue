<script setup lang="ts">
import { ref, computed } from "vue"
import DefectImageViewer from "@/components/business/result/DefectImageViewer.vue"
import type { Defect } from "@/types/result.types"

const props = defineProps<{
  images: string[]
  defects: Defect[] | null
  loading: boolean
  sampleLabel: (imageIndex?: number | null) => string
}>()

const activeImageIndex = ref(0)
const highlightDefectId = ref<number | null>(null)

const currentImage = computed(() => props.images[activeImageIndex.value] || "")

const defectsList = computed(() => props.defects || [])

function selectDefect(index: number) {
  highlightDefectId.value = highlightDefectId.value === index ? null : index
}

function confidenceColor(c: number) {
  if (c >= 0.8) return "danger"
  if (c >= 0.5) return "warning"
  return "info"
}

function confidencePct(c: number) {
  return (c * 100).toFixed(0) + "%"
}

function formatBbox(bbox: [number, number, number, number]) {
  return bbox.map((v) => v.toFixed(3)).join(", ")
}
</script>

<template>
  <div class="image-tab">
    <div v-if="!images.length && !defectsList.length" class="empty-full">
      <el-empty description="暂无图像证据" :image-size="80" />
    </div>

    <div v-else class="image-layout">
      <!-- Left: image viewer -->
      <div class="image-main">
        <DefectImageViewer
          v-if="currentImage"
          :key="activeImageIndex"
          :image-url="currentImage"
          :defects="defectsList"
          :loading="loading"
          :normalized="true"
        />

        <div v-if="images.length > 1" class="thumbnail-strip">
          <button
            v-for="(img, idx) in images"
            :key="idx"
            class="thumbnail"
            :class="{ active: idx === activeImageIndex }"
            @click="activeImageIndex = idx"
          >
            <img :src="img" :alt="`图片 ${idx + 1}`" />
            <span class="thumb-label">{{ sampleLabel(idx) || `图${idx + 1}` }}</span>
          </button>
        </div>
      </div>

      <!-- Right: defect list -->
      <div class="defect-panel">
        <div class="panel-header">
          <span class="panel-count">缺陷清单 ({{ defectsList.length }})</span>
        </div>

        <div v-if="!defectsList.length" class="panel-empty">
          <span class="text-zinc-400 text-sm">未检出缺陷</span>
        </div>

        <div v-else class="defect-list">
          <button
            v-for="(defect, idx) in defectsList"
            :key="idx"
            class="defect-row"
            :class="{ highlighted: highlightDefectId === idx }"
            @click="selectDefect(idx)"
          >
            <span class="defect-index">{{ idx + 1 }}</span>
            <div class="defect-body">
              <div class="defect-head">
                <span class="defect-type">{{ defect.type }}</span>
                <el-tag :type="confidenceColor(defect.confidence)" size="small" class="defect-confidence">
                  {{ confidencePct(defect.confidence) }}
                </el-tag>
              </div>
              <span v-if="defect.description" class="defect-desc">{{ defect.description }}</span>
              <code class="defect-bbox">{{ formatBbox(defect.bbox) }}</code>
            </div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.image-tab {
  padding: 24px;
}

.empty-full {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 360px;
}

.image-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 24px;
  align-items: start;
  max-height: calc(100vh - 220px);
}

.image-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.thumbnail-strip {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 4px 0;
}

.thumbnail {
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  border: 2px solid oklch(0.9 0.005 260);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  padding: 0;
  background: none;
  position: relative;
  transition: border-color 0.15s;
}

.thumbnail.active {
  border-color: oklch(0.5 0.14 250);
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-label {
  position: absolute;
  bottom: 2px;
  left: 2px;
  right: 2px;
  font-size: 10px;
  background: oklch(0 0 0 / 0.55);
  color: oklch(1 0 0);
  text-align: center;
  border-radius: 2px;
  padding: 1px 0;
}

.defect-panel {
  border: 1px solid oklch(0.92 0.005 260);
  border-radius: 10px;
  overflow: hidden;
  max-height: calc(100vh - 240px);
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid oklch(0.92 0.005 260);
  background: oklch(0.985 0.003 260);
}

.panel-count {
  font-size: 13px;
  font-weight: 600;
  color: oklch(0.35 0.01 260);
}

.panel-empty {
  padding: 48px 16px;
  text-align: center;
}

.defect-list {
  overflow-y: auto;
  flex: 1;
}

.defect-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border: none;
  border-bottom: 1px solid oklch(0.94 0.003 260);
  background: none;
  width: 100%;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s;
}

.defect-row:hover {
  background: oklch(0.97 0.005 260);
}

.defect-row.highlighted {
  background: oklch(0.95 0.04 250 / 0.12);
}

.defect-index {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: oklch(0.94 0.005 260);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: oklch(0.45 0.01 260);
}

.defect-row.highlighted .defect-index {
  background: oklch(0.5 0.14 250);
  color: oklch(1 0 0);
}

.defect-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.defect-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.defect-type {
  font-size: 14px;
  font-weight: 600;
  color: oklch(0.25 0.01 260);
}

.defect-desc {
  font-size: 12px;
  color: oklch(0.5 0.01 260);
  line-height: 1.5;
}

.defect-bbox {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: oklch(0.55 0.01 260);
  background: oklch(0.96 0.003 260);
  padding: 3px 6px;
  border-radius: 4px;
  width: fit-content;
}
</style>
