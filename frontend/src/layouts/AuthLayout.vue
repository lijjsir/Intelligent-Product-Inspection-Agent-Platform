<template>
  <div class="min-h-screen grid grid-cols-[1.2fr_1fr] max-md:grid-cols-1 bg-zinc-950">
    <div class="flex flex-col justify-center px-20 max-md:px-8 py-20 text-white">
      <h1 class="text-[42px] font-bold leading-tight tracking-tight">PIAP 智能检测平台</h1>
      <p class="mt-4 text-lg text-zinc-400 max-w-md leading-relaxed">
        从任务到稳定性评估的一体化质检控制台
      </p>
      <div class="mt-12 flex gap-3">
        <span class="px-3 py-1 rounded-full text-xs border border-zinc-700 text-zinc-400">Vue 3 + Element Plus</span>
        <span class="px-3 py-1 rounded-full text-xs border border-zinc-700 text-zinc-400">ECharts 6</span>
        <span class="px-3 py-1 rounded-full text-xs border border-zinc-700 text-zinc-400">RAG 增强</span>
      </div>
    </div>
    <div class="bg-white flex items-center justify-center p-12">
      <RouterView />
    </div>
  </div>
</template>

<script setup lang="ts"></script>
