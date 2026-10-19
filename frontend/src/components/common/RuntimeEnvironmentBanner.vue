<script setup lang="ts">
import { computed,nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRuntimeContext } from "@/composables/useRuntimeContext";
import { useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth.store';

const { context, unavailable, load } = useRuntimeContext();
const route=useRoute(),auth=useAuthStore();
const showGuideLink=computed(()=>auth.primaryRole==='expert'&&auth.hasPermission('quality_material_read_business')&&route.path.startsWith('/app/')&&route.path!=='/app/workbench');
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
onMounted(async () => {
  observer = new ResizeObserver(updateHeight);
  await load();await nextTick();
  if(banner.value){observer?.observe(banner.value);updateHeight();}
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
      ><small>{{ context.case_code }}</small><router-link v-if="showGuideLink" to="/app/workbench#demo-case-guide">返回演示导览</router-link></template
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
.runtime-banner a{color:inherit;text-decoration:underline;text-underline-offset:3px;min-height:30px;display:inline-flex;align-items:center;}
.runtime-banner a:focus-visible{outline:2px solid #52677d;outline-offset:3px;}
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
