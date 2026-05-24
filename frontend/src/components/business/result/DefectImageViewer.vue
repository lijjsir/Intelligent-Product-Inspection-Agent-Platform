<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'

interface Defect {
  id?: string
  type: string
  confidence: number
  bbox: [number, number, number, number] // [x, y, width, height] in pixels or normalized [0-1]
  description?: string
}

interface Props {
  imageUrl: string
  defects: Defect[]
  loading?: boolean
  // If true, bbox coordinates are normalized [0-1], otherwise in pixels
  normalized?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  normalized: true,
})

const canvasRef = ref<HTMLCanvasElement>()
const containerRef = ref<HTMLDivElement>()
const imageLoaded = ref(false)
const scale = ref(1)
let resizeObserver: ResizeObserver | null = null

// Colors for different defect types
const DEFECT_COLORS: Record<string, string> = {
  scratch: '#FF4444',
  dent: '#FF8800',
  stain: '#FFCC00',
  crack: '#CC0000',
  default: '#FF4444',
}

function getDefectColor(type: string): string {
  return DEFECT_COLORS[type.toLowerCase()] || DEFECT_COLORS.default
}

function drawImageAndDefects() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const img = new Image()
  img.crossOrigin = 'anonymous'
  
  img.onload = () => {
    imageLoaded.value = true
    
    // Calculate scale to fit container while maintaining aspect ratio
    const containerWidth = container.clientWidth
    const containerHeight = container.clientHeight || 600
    
    const imgAspect = img.width / img.height
    const containerAspect = containerWidth / containerHeight
    
    let drawWidth: number
    let drawHeight: number
    
    if (imgAspect > containerAspect) {
      drawWidth = containerWidth
      drawHeight = containerWidth / imgAspect
      scale.value = containerWidth / img.width
    } else {
      drawHeight = containerHeight
      drawWidth = containerHeight * imgAspect
      scale.value = containerHeight / img.height
    }
    
    // Set canvas size
    canvas.width = drawWidth
    canvas.height = drawHeight
    
    // Clear and draw image
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, drawWidth, drawHeight)
    
    // Draw defect boxes
    if (props.defects && props.defects.length > 0) {
      props.defects.forEach((defect, index) => {
        drawDefectBox(ctx, defect, index)
      })
    }
  }
  
  img.onerror = () => {
    imageLoaded.value = false
    // Draw placeholder
    canvas.width = container.clientWidth
    canvas.height = 400
    ctx.fillStyle = '#f0f0f0'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#999'
    ctx.font = '16px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('图片加载失败', canvas.width / 2, canvas.height / 2)
  }
  
  img.src = props.imageUrl
}

function drawDefectBox(ctx: CanvasRenderingContext2D, defect: Defect, index: number) {
  const color = getDefectColor(defect.type)
  
  // Calculate box coordinates
  let x: number, y: number, w: number, h: number
  
  if (props.normalized) {
    // Normalized coordinates [0-1]
    const canvasWidth = ctx.canvas.width
    const canvasHeight = ctx.canvas.height
    x = defect.bbox[0] * canvasWidth
    y = defect.bbox[1] * canvasHeight
    w = defect.bbox[2] * canvasWidth
    h = defect.bbox[3] * canvasHeight
  } else {
    // Pixel coordinates - scale to canvas
    x = defect.bbox[0] * scale.value
    y = defect.bbox[1] * scale.value
    w = defect.bbox[2] * scale.value
    h = defect.bbox[3] * scale.value
  }
  
  // Draw box
  ctx.strokeStyle = color
  ctx.lineWidth = 3
  ctx.strokeRect(x, y, w, h)
  
  // Draw fill with transparency
  ctx.fillStyle = color + '20' // 20 hex = ~12% opacity
  ctx.fillRect(x, y, w, h)
  
  // Draw label background
  const label = `${index + 1}. ${defect.type} (${(defect.confidence * 100).toFixed(0)}%)`
  ctx.font = 'bold 14px sans-serif'
  const textMetrics = ctx.measureText(label)
  const padding = 6
  const labelHeight = 24
  
  ctx.fillStyle = color
  ctx.fillRect(x, y - labelHeight, textMetrics.width + padding * 2, labelHeight)
  
  // Draw label text
  ctx.fillStyle = '#fff'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, x + padding, y - labelHeight / 2)
  
  // Draw corner markers for better visibility
  const cornerSize = 10
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  
  // Top-left corner
  ctx.beginPath()
  ctx.moveTo(x, y + cornerSize)
  ctx.lineTo(x, y)
  ctx.lineTo(x + cornerSize, y)
  ctx.stroke()
  
  // Top-right corner
  ctx.beginPath()
  ctx.moveTo(x + w - cornerSize, y)
  ctx.lineTo(x + w, y)
  ctx.lineTo(x + w, y + cornerSize)
  ctx.stroke()
  
  // Bottom-left corner
  ctx.beginPath()
  ctx.moveTo(x, y + h - cornerSize)
  ctx.lineTo(x, y + h)
  ctx.lineTo(x + cornerSize, y + h)
  ctx.stroke()
  
  // Bottom-right corner
  ctx.beginPath()
  ctx.moveTo(x + w - cornerSize, y + h)
  ctx.lineTo(x + w, y + h)
  ctx.lineTo(x + w, y + h - cornerSize)
  ctx.stroke()
}

// Redraw when props change
watch(() => [props.imageUrl, props.defects, props.normalized], () => {
  if (props.imageUrl) {
    drawImageAndDefects()
  }
}, { deep: true })

onMounted(() => {
  if (props.imageUrl && containerRef.value) {
    drawImageAndDefects()
    resizeObserver = new ResizeObserver(() => {
      if (props.imageUrl) drawImageAndDefects()
    })
    resizeObserver.observe(containerRef.value)
  }
})

import { onUnmounted } from 'vue'
onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<template>
  <div ref="containerRef" class="defect-image-viewer" v-loading="loading">
    <canvas
      v-if="imageUrl"
      ref="canvasRef"
      class="defect-canvas"
    />
    <el-empty v-else description="暂无图片" />
    
    <!-- Legend -->
    <div v-if="defects && defects.length > 0" class="defect-legend">
      <div class="legend-title">缺陷图例</div>
      <div class="legend-items">
        <div
          v-for="(defect, index) in defects"
          :key="defect.id || index"
          class="legend-item"
        >
          <span
            class="legend-color"
            :style="{ backgroundColor: getDefectColor(defect.type) }"
          />
          <span class="legend-text">
            {{ index + 1 }}. {{ defect.type }}
            <span class="legend-confidence">
              ({{ (defect.confidence * 100).toFixed(0) }}%)
            </span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.defect-image-viewer {
  width: 100%;
  min-height: 400px;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: #f5f5f5;
  border-radius: 8px;
  overflow: hidden;
}

.defect-canvas {
  max-width: 100%;
  max-height: 600px;
  object-fit: contain;
}

.defect-legend {
  width: 100%;
  padding: 16px;
  background: #fff;
  border-top: 1px solid #e0e0e0;
}

.legend-title {
  font-weight: 600;
  font-size: 14px;
  color: #333;
  margin-bottom: 12px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 4px;
}

.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 3px;
}

.legend-text {
  font-size: 13px;
  color: #333;
}

.legend-confidence {
  color: #666;
  font-size: 12px;
}
</style>
