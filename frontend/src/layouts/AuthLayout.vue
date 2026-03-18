<template>
  <div class="auth">
    <div class="left">
      <h1>PIAP 智能检测平台</h1>
      <p>从任务到稳定性评估的一体化质检控制台。</p>
    </div>
    <div class="right">
      <RouterView />
    </div>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.auth {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  background: linear-gradient(120deg, #0f2235 0%, #1b3a5c 60%, #2563a8 100%);
  color: #fff;
}

.left {
  padding: 80px;
}

.right {
  background: #f8fafc;
  color: #1f2937;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
}

@media (max-width: 960px) {
  .auth {
    grid-template-columns: 1fr;
  }

  .left {
    padding: 48px 32px;
  }
}
</style>
