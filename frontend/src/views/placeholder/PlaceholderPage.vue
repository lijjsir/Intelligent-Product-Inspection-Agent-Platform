<template>
  <div class="flex items-center justify-center min-h-[60vh]">
    <div class="text-center">
      <el-icon class="text-6xl text-zinc-300 mb-4">
        <Tools />
      </el-icon>
      <h2 class="text-xl font-semibold text-zinc-600 mb-2">{{ pageTitle }}</h2>
      <p class="text-sm text-zinc-400 mb-1">该功能正在开发中，敬请期待</p>
      <p class="text-xs text-zinc-300">当前页面为占位页，具体功能将在后续版本中实现</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { Tools } from "@element-plus/icons-vue";

const route = useRoute();

const pageTitle = computed(() => {
  const title = route.meta?.title;
  return typeof title === "string" ? title : "功能开发中";
});
</script>
