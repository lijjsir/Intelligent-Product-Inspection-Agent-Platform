<template>
  <div class="flex flex-col gap-5">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">GPU 监控</h2>
      <p class="mt-2 text-sm text-zinc-500">该页面已按 CHG_006 建立入口，等待推理基础设施指标接入。</p>
    </div>
    <el-card shadow="never" class="placeholder">
      <el-empty description="GPU 利用率、显存仪表盘与队列深度尚未接入后端指标源" />
    </el-card>
  </div>
</template>

<style scoped>
</style>
