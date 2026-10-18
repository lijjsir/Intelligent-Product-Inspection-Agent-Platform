<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRuntimeContext } from "@/composables/useRuntimeContext";

const { context, unavailable, load } = useRuntimeContext();
const banner = ref<HTMLElement | null>(null);
let observer: ResizeObserver | null = null;
function updateHeight() {
  document.documentElement.style.setProperty(
    "--runtime-banner-height",
    `${banner.value?.offsetHeight || 0}px`,
  );
}
watch(
  () => [context.value?.execution_mode, unavailable.value],
  async () => {
    await nextTick();
    observer?.disconnect();
    if (banner.value) observer?.observe(banner.value);
    updateHeight();
  },
);
onMounted(() => {
  observer = new ResizeObserver(updateHeight);
  void load();
});
onBeforeUnmount(() => {
  observer?.disconnect();
  document.documentElement.style.removeProperty("--runtime-banner-height");
});
</script>

<template>
  <div
    v-if="context?.execution_mode === 'demo' || unavailable"
    ref="banner"
    class="runtime-banner"
    :class="{ unavailable }"
    role="status"
  >
    <template v-if="context?.execution_mode === 'demo'"
      ><strong>演示环境</strong><span>模拟资料 · 不用于正式风险结论</span
      ><small>{{ context.case_code }}</small></template
    >
    <template v-else
      ><span>环境信息暂不可用</span><button type="button" @click="load">重试</button></template
    >
  </div>
</template>

<style scoped>
.runtime-banner {
  position: relative;
  z-index: 4000;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 6px 16px;
  min-height: 38px;
  padding: 7px 16px;
  border-bottom: 1px solid #e8d4a2;
  background: #fff5d9;
  color: #634811;
  font-size: 13px;
  line-height: 1.5;
}
.runtime-banner strong {
  font-weight: 700;
}
.runtime-banner small {
  font-size: 12px;
}
.runtime-banner.unavailable {
  background: #f1f5f9;
  border-color: #dbe5ea;
  color: #52677d;
}
.runtime-banner button {
  text-decoration: underline;
}
.runtime-banner button:focus-visible {
  outline: 2px solid #52677d;
  outline-offset: 3px;
}
@media (max-width: 600px) {
  .runtime-banner {
    justify-content: flex-start;
    gap: 4px 10px;
    font-size: 12px;
  }
  .runtime-banner small {
    display: none;
  }
}
</style>
