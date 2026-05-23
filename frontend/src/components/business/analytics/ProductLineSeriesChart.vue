<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";

import type { ProductLineSeries } from "@/types/analytics.types";

interface Props {
  series: ProductLineSeries[];
}

interface Emits {
  (e: "select", productLine: string): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();
const chartRef = ref<HTMLElement | null>(null);
let chart: ECharts | null = null;

use([CanvasRenderer, LineChart, GridComponent, LegendComponent, TooltipComponent] as any);

function handleResize() {
  chart?.resize();
}

function bindClick() {
  if (!chart) {
    return;
  }
  chart.off("click");
  chart.on("click", (params) => {
    if (typeof params.seriesName === "string") {
      emit("select", params.seriesName);
    }
  });
}

function renderChart() {
  if (!chartRef.value) {
    return;
  }

  chart ??= init(chartRef.value);
  const xAxisData = props.series[0]?.points.map((item) => item.bucket) ?? [];
  chart.setOption({
    animationDuration: 500,
    tooltip: { trigger: "axis" },
    legend: { top: 0, textStyle: { color: "#5b6472" } },
    grid: { left: 40, right: 24, top: 48, bottom: 28 },
    xAxis: {
      type: "category",
      data: xAxisData,
      axisLabel: { color: "#5b6472" },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#5b6472" },
      splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
    },
    series: props.series.map((item) => ({
      name: item.name,
      type: "line",
      smooth: true,
      symbolSize: 6,
      data: item.points.map((point) => point.value),
    })),
  });
  bindClick();
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
  () => props.series,
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
