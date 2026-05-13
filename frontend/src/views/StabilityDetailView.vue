<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStabilityStore } from '@/stores/stability.store'
import { ElMessage } from 'element-plus'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { LegendComponent, RadarComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { init, type ECharts, type EChartsOption, use } from 'echarts/core'

const route = useRoute()
const router = useRouter()
const store = useStabilityStore()

const loading = ref(true)
const taskId = route.params.id as string

const radarChartRef = ref<HTMLElement | null>(null)
let chartInstance: ECharts | null = null

use([CanvasRenderer, RadarChart, RadarComponent, LegendComponent, TitleComponent, TooltipComponent])

const getRiskType = (level: string) => {
  const map: Record<string, "info"|"primary"|"success"|"danger"|"warning"> = {
    low: "success",
    medium: "primary",
    high: "warning",
    critical: "danger",
  };
  return map[level?.toLowerCase()] || "info";
}

onMounted(async () => {
  try {
    await store.fetchByTask(taskId)
  } catch (err: any) {
    if (err.response?.status === 404) {
      ElMessage.warning("该任务暂无稳定性评估报告")
    } else {
      ElMessage.error("获取评估报告失败")
    }
  } finally {
    loading.value = false
  }

  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (chartInstance) {
    chartInstance.dispose()
  }
  window.removeEventListener('resize', handleResize)
})

function handleResize() {
  if (chartInstance) {
    chartInstance.resize()
  }
}

async function renderChart() {
  if (!radarChartRef.value || !store.current) return

  await nextTick()

  const width = radarChartRef.value.clientWidth
  const height = radarChartRef.value.clientHeight
  if (width <= 0 || height <= 0) {
    requestAnimationFrame(() => {
      void renderChart()
    })
    return
  }

  chartInstance ??= init(radarChartRef.value)
  const report = store.current
  const option: EChartsOption = {
    title: {
      text: 'AI Agent 五维稳定性雷达',
      left: 'center'
    },
    tooltip: {},
    radar: {
      indicator: [
        { name: '引证佐证 (Evidence)', max: 1 },
        { name: '前后一致性 (Consistency)', max: 1 },
        { name: '置信度 (Confidence)', max: 1 },
        { name: '规则溯源 (Traceability)', max: 1 },
        { name: '异常波动 (Anomaly)', max: 1 }
      ],
      splitArea: {
        areaStyle: {
          color: ['#f8f9fa', '#e9ecef', '#dee2e6', '#ced4da']
        }
      }
    },
    series: [
      {
        name: '模型决策稳定性',
        type: 'radar',
        data: [
          {
            value: [
              report.evidence_score,
              report.consistency_score,
              report.confidence_score,
              report.traceability_score,
              report.anomaly_score
            ],
            name: '评分数据',
            areaStyle: {
              color: 'rgba(64, 158, 255, 0.2)'
            },
            lineStyle: {
              color: '#409EFF',
              width: 2
            },
            itemStyle: {
              color: '#409EFF'
            }
          }
        ]
      }
    ]
  }
  chartInstance.setOption(option)
  chartInstance.resize()
}

function goBack() {
  router.back()
}

watch(
  () => store.current,
  async (report) => {
    if (!report) return
    await renderChart()
  },
  { deep: true },
)
</script>

<template>
  <div class="flex flex-col gap-5" v-loading="loading">
    <div>
      <el-button @click="goBack" class="mb-4">
        &larr; 返回
      </el-button>
      <div v-if="store.current" class="title-area">
        <h2 class="text-2xl font-bold text-zinc-900">稳定性评估 (Stability)</h2>
        <el-tag :type="getRiskType(store.current.risk_level)" size="large" class="ml-4">
          判定面: {{ store.current.risk_level.toUpperCase() }} RISK
        </el-tag>
      </div>
    </div>

    <div v-if="store.current" class="content">
      <div class="flex gap-5">
        <!-- 雷达图面板 -->
        <div>
          <el-card shadow="never" class="info-card echarts-wrapper">
            <div ref="radarChartRef" class="chart-container"></div>
          </el-card>
        </div>
        
        <!-- 数据细节和复查面板 -->
        <div>
          <el-card shadow="never" class="mb-4">
            <template #header>关键参数概览</template>
            <el-descriptions :column="2">
              <el-descriptions-item label="综合风险指数" span="2">
                <span class="text-xl font-bold" :class="`risk-${store.current.risk_level.toLowerCase()}`">
                  {{ (store.current.risk_score * 10).toFixed(1) }} / 10.0
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="引证佐证 (Evidence)">{{ store.current.evidence_score }}</el-descriptions-item>
              <el-descriptions-item label="前后一致性 (Consistency)">{{ store.current.consistency_score }}</el-descriptions-item>
              <el-descriptions-item label="置信度 (Confidence)">{{ store.current.confidence_score }}</el-descriptions-item>
              <el-descriptions-item label="规则溯源 (Traceability)">{{ store.current.traceability_score }}</el-descriptions-item>
              <el-descriptions-item label="异常波动 (Anomaly)">{{ store.current.anomaly_score }}</el-descriptions-item>
              <el-descriptions-item label="任务生成时间">{{ store.current.created_at ? new Date(store.current.created_at).toLocaleString() : '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 诊断原因与溯源 -->
          <el-card shadow="never" class="mb-4">
            <template #header>根因溯源 (Root Cause)</template>
            <p v-if="store.current.root_cause">{{ store.current.root_cause }}</p>
            <el-empty v-else description="无高危根因警报" :image-size="60" />
          </el-card>
        </div>
      </div>
    </div>
    
    <div v-else-if="!loading" class="empty-state">
      <el-empty description="无法获取稳定性评估报告（可能仍在生成或暂无数据）" />
    </div>
  </div>
</template>

<style scoped>


.title-area {
  display: flex;
  align-items: center;
}


.ml-4 {
  margin-left: 16px;
}


.text-xl {
  font-size: 1.5rem;
  line-height: 2rem;
}

.font-bold {
  font-weight: 700;
}

.risk-low { color: #67c23a; }
.risk-medium { color: #409eff; }
.risk-high { color: #e6a23c; }
.risk-critical { color: #f56c6c; }

.echarts-wrapper {
  height: 500px;
}

.echarts-wrapper :deep(.el-card__body) {
  height: 100%;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing:-box;
}

.chart-container {
  width: 100%;
  height: 450px;
}
</style>