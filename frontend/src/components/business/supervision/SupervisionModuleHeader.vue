<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    index: string;
    code: string;
    title: string;
    agentName: string;
    description: string;
    principle: string;
    tone?: "blue" | "cyan" | "amber" | "violet";
  }>(),
  { tone: "blue" },
);

const palette = computed(
  () =>
    ({
      blue: { accent: "#0b63ce", soft: "#eaf3ff", glow: "rgba(11, 99, 206, 0.16)" },
      cyan: { accent: "#087f8c", soft: "#e9f8f8", glow: "rgba(8, 127, 140, 0.15)" },
      amber: { accent: "#c96a0a", soft: "#fff4e5", glow: "rgba(201, 106, 10, 0.16)" },
      violet: { accent: "#6d4bc3", soft: "#f2edff", glow: "rgba(109, 75, 195, 0.15)" },
    })[props.tone],
);
</script>

<template>
  <section
    class="module-header"
    :style="{
      '--module-accent': palette.accent,
      '--module-soft': palette.soft,
      '--module-glow': palette.glow,
    }"
  >
    <div class="module-index" aria-hidden="true">
      <span>{{ index }}</span>
      <strong>{{ code }}</strong>
    </div>
    <div class="module-copy">
      <p class="module-kicker">QUALITY SUPERVISION · {{ agentName }}</p>
      <h1>{{ title }}</h1>
      <p class="module-description">{{ description }}</p>
      <div class="module-principle">
        <span>工作原则</span>
        <strong>{{ principle }}</strong>
      </div>
    </div>
    <div v-if="$slots.actions" class="module-actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<style scoped>
.module-header {
  position: relative;
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr) auto;
  align-items: center;
  gap: 24px;
  min-height: 184px;
  overflow: hidden;
  padding: 26px 30px;
  border: 1px solid color-mix(in srgb, var(--module-accent) 22%, #dbe5f0);
  border-radius: 20px;
  background:
    radial-gradient(circle at 88% 12%, var(--module-glow), transparent 30%),
    linear-gradient(120deg, var(--module-soft), #fff 46%, #f8fbff);
  box-shadow: 0 14px 38px rgba(15, 54, 96, 0.08);
}

.module-header::after {
  position: absolute;
  right: -60px;
  bottom: -110px;
  width: 270px;
  height: 270px;
  border: 1px solid color-mix(in srgb, var(--module-accent) 16%, transparent);
  border-radius: 50%;
  content: "";
}

.module-index {
  position: relative;
  z-index: 1;
  display: grid;
  width: 82px;
  height: 104px;
  place-items: center;
  align-content: center;
  gap: 9px;
  border-radius: 16px;
  background: var(--module-accent);
  color: #fff;
  box-shadow: 0 14px 28px var(--module-glow);
}

.module-index span {
  font:
    750 28px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.module-index strong {
  font:
    700 11px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
  letter-spacing: 0.15em;
  opacity: 0.82;
}

.module-copy {
  position: relative;
  z-index: 1;
  min-width: 0;
}

.module-kicker {
  margin: 0 0 8px;
  color: var(--module-accent);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.12em;
}

.module-copy h1 {
  margin: 0;
  color: #102a43;
  font-size: clamp(28px, 3vw, 40px);
  letter-spacing: -0.035em;
  line-height: 1.1;
}

.module-description {
  max-width: 780px;
  margin: 12px 0 0;
  color: #52677d;
  font-size: 14px;
  line-height: 1.75;
}

.module-principle {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  margin-top: 16px;
  padding: 6px 10px 6px 7px;
  border: 1px solid color-mix(in srgb, var(--module-accent) 18%, #dbe5f0);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #42566b;
  font-size: 12px;
}

.module-principle span {
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--module-soft);
  color: var(--module-accent);
  font-weight: 700;
}

.module-principle strong {
  font-weight: 650;
}

.module-actions {
  position: relative;
  z-index: 1;
  display: flex;
  max-width: 360px;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.module-actions :deep(.el-button) {
  min-height: 42px;
  margin-left: 0;
  border-radius: 10px;
}

@media (max-width: 880px) {
  .module-header {
    grid-template-columns: 72px minmax(0, 1fr);
  }

  .module-index {
    width: 66px;
    height: 90px;
  }

  .module-actions {
    grid-column: 1 / -1;
    max-width: none;
    justify-content: flex-start;
  }
}

@media (max-width: 560px) {
  .module-header {
    grid-template-columns: 1fr;
    gap: 16px;
    min-height: 0;
    padding: 22px 18px;
    border-radius: 15px;
  }

  .module-index {
    width: auto;
    height: 42px;
    grid-template-columns: auto auto;
    justify-content: start;
    padding: 0 14px;
  }

  .module-index span {
    font-size: 18px;
  }

  .module-actions {
    grid-column: auto;
  }

  .module-actions :deep(.el-button) {
    min-height: 44px;
    flex: 1;
  }
}
</style>
