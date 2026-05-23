<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";

import type { RiskTrendPoint } from "@/types/analytics.types";

interface Props {
  points: RiskTrendPoint[];
}

const props = defineProps<Props>();
const chartRef = ref<HTMLElement | null>(null);
let chart: ECharts | null = null;

use([CanvasRenderer, LineChart, GridComponent, LegendComponent, TooltipComponent] as any);

function handleResize() {
  chart?.resize();
}

function renderChart() {
  if (!chartRef.value) {
    return;
  }

  chart ??= init(chartRef.value);
  chart.setOption({
    animationDuration: 500,
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, textStyle: { color: "#5b6472" } },
    grid: { left: 40, right: 24, top: 48, bottom: 28 },
    xAxis: {
      type: "category",
      data: props.points.map((item) => item.bucket),
      axisLabel: { color: "#5b6472" },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#5b6472" },
      splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
    },
    series: [
      { name: "低风险", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: props.points.map((item) => item.low), color: "#0f766e" },
      { name: "中风险", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: props.points.map((item) => item.medium), color: "#f59e0b" },
      { name: "高风险", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: props.points.map((item) => item.high), color: "#ef4444" },
      { name: "严重", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: props.points.map((item) => item.critical), color: "#7c3aed" },
    ],
  });
}

onMounted(async () => {
  await nextTick();
  renderChart();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  chart?.dispose();
  window.removeEventListener("resize", handleResize);
});

watch(
  () => props.points,
  async () => {
    await nextTick();
    renderChart();
  },
  { deep: true },
);
</script>

<template>
  <div ref="chartRef" class="chart-host"></div>
</template>

<style scoped>
.chart-host { width: 100%; height: 320px; }
@media (max-width: 960px) { .chart-host { height: 280px; } }
</style>
