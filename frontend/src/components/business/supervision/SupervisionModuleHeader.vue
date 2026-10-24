<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    title: string;
    description: string;
    principle?: string;
    agentName?: string;
    eyebrow?: string;
    tone?: "blue" | "cyan" | "amber" | "violet";
  }>(),
  { tone: "blue", eyebrow: "质量监督" },
);
const accent = computed(
  () => ({ blue: "#2563eb", cyan: "#087f8c", amber: "#a55c11", violet: "#5964ab" })[props.tone],
);
</script>

<template>
  <header class="module-header" :style="{ '--module-accent': accent }">
    <div class="module-copy">
      <p class="module-kicker">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p class="module-description">{{ description }}</p>
      <p v-if="principle" class="module-principle">{{ principle }}</p>
    </div>
    <div v-if="$slots.actions" class="module-actions"><slot name="actions" /></div>
  </header>
</template>

<style scoped>
.module-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 24px;
  margin-bottom: 20px;
  border: 1px solid var(--piap-line, #dbe5f2);
  border-left: 3px solid var(--module-accent);
  border-radius: 12px;
  background: #fff;
}
.module-copy {
  min-width: 0;
}
.module-kicker {
  margin: 0 0 7px;
  color: var(--module-accent);
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.08em;
}
.module-copy h1 {
  margin: 0;
  color: var(--piap-ink, #13213a);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.3;
}
.module-description {
  max-width: 760px;
  margin: 9px 0 0;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.75;
}
.module-principle {
  margin: 7px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.75;
}
.module-actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  max-width: 440px;
}
.module-actions :deep(.el-button) {
  min-height: 40px;
  margin: 0;
}
@media (max-width: 960px) {
  .module-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 16px;
  }
  .module-actions {
    justify-content: flex-start;
    max-width: none;
  }
}
@media (max-width: 600px) {
  .module-header {
    padding: 18px 16px;
    margin-bottom: 16px;
  }
  .module-copy h1 {
    font-size: 25px;
  }
  .module-actions {
    width: 100%;
  }
  .module-actions :deep(.el-button) {
    min-height: 44px;
  }
}
</style>
