<template>
  <div class="page-container">
    <div class="hero">
      <h2>GPU 监控</h2>
      <p>该页面已按 CHG_006 建立入口，等待推理基础设施指标接入。</p>
    </div>
    <el-card shadow="never" class="placeholder">
      <el-empty description="GPU 利用率、显存仪表盘与队列深度尚未接入后端指标源" />
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: grid; gap: 16px; }
.hero h2 { margin: 0; color: #1b3a5c; }
.hero p { margin: 6px 0 0; color: #64748b; }
.placeholder { min-height: 320px; display: flex; align-items: center; justify-content: center; }
</style>

