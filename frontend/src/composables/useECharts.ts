import { nextTick, ref, onMounted, onUnmounted } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart, GraphChart, LineChart, PieChart, RadarChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { init, type ECharts, type EChartsCoreOption, use } from "echarts/core";

const chartExtensions = [
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  RadarChart,
  GraphChart,
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
];

use(chartExtensions as unknown as Parameters<typeof use>[0]);

export function useECharts() {
  const chartRef = ref<HTMLElement | null>(null);
  let chart: ECharts | null = null;
  let pendingOption: EChartsCoreOption | null = null;
  let resizeObserver: ResizeObserver | null = null;

  function ensureChart() {
    if (!chartRef.value) return;
    if (!chart) {
      chart = init(chartRef.value);
    }
    if (pendingOption) {
      chart.setOption(pendingOption, true);
      pendingOption = null;
    }
  }

  function setOption(option: EChartsCoreOption) {
    pendingOption = option;
    ensureChart();
  }

  function resize() {
    ensureChart();
    chart?.resize();
  }

  onMounted(() => {
    window.addEventListener("resize", resize);
    nextTick(() => {
      ensureChart();
      if (typeof ResizeObserver !== "undefined" && chartRef.value) {
        resizeObserver = new ResizeObserver(() => resize());
        resizeObserver.observe(chartRef.value);
      }
    });
  });

  onUnmounted(() => {
    window.removeEventListener("resize", resize);
    resizeObserver?.disconnect();
    resizeObserver = null;
    chart?.dispose();
    chart = null;
  });

  return { chartRef, chart, setOption, resize };
}
