import { ref, onMounted, onUnmounted } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart, BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, type EChartsOption, use } from "echarts/core";

use([CanvasRenderer, LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent]);

export function useECharts() {
  const chartRef = ref<HTMLElement | null>(null);
  let chart: ECharts | null = null;

  function setOption(option: EChartsOption) {
    if (chartRef.value && !chart) {
      chart = init(chartRef.value);
    }
    if (chart) {
      chart.setOption(option, true);
    }
  }

  function resize() {
    chart?.resize();
  }

  onMounted(() => {
    window.addEventListener("resize", resize);
  });

  onUnmounted(() => {
    window.removeEventListener("resize", resize);
    chart?.dispose();
    chart = null;
  });

  return { chartRef, chart, setOption, resize };
}
