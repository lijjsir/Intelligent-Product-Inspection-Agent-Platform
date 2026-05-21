<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { graphic, init, type ECharts, use } from "echarts/core";

import type { TrendPoint } from "@/types/analytics.types";

interface Props {
  points: TrendPoint[];
}

const props = defineProps<Props>();
const chartRef = ref<HTMLElement | null>(null);
let chart: ECharts | null = null;

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent]);

function handleResize() {
  chart?.resize();
}

function renderChart() {
  if (!chartRef.value || !props.points.length) return;
  chart ??= init(chartRef.value);
  chart.setOption({
    animationDuration: 500,
    color: ["#dc2626"],
    tooltip: { trigger: "axis", valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%` },
    grid: { left: 40, right: 24, top: 32, bottom: 28 },
    xAxis: {
      type: "category",
      data: props.points.map((p) => p.bucket),
      axisLabel: { color: "#5b6472" },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      axisLabel: {
        color: "#5b6472",
        formatter: (value: number) => `${Math.round(value * 100)}%`,
      },
      splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
    },
    series: [
      {
        name: "点踩率",
        type: "line",
        smooth: true,
        symbolSize: 7,
        data: props.points.map((p) => p.value),
        lineStyle: { width: 3 },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(220,38,38,0.28)" },
            { offset: 1, color: "rgba(220,38,38,0.02)" },
          ]),
        },
      },
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

watch(() => props.points, async () => { await nextTick(); renderChart(); }, { deep: true });
</script>

<template>
  <div ref="chartRef" class="chart-host"></div>
</template>

<style scoped>
.chart-host { width: 100%; height: 280px; }
</style>
