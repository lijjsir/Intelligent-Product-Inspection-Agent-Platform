<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();

const agents = [
  {
    order: "01",
    code: "MKT",
    title: "市场监控",
    action: "持续发现变化",
    path: "/app/quality-analytics",
    color: "#0b63ce",
  },
  {
    order: "02",
    code: "VOC",
    title: "舆情监测",
    action: "核实风险线索",
    path: "/app/risk-cases",
    color: "#087f8c",
  },
  {
    order: "03",
    code: "SAM",
    title: "监督抽查",
    action: "制定约束计划",
    path: "/app/sampling-plans",
    color: "#c96a0a",
  },
  {
    order: "04",
    code: "LAB",
    title: "实验室检测",
    action: "设备闭环取证",
    path: "/app/laboratory",
    color: "#6d4bc3",
  },
];

function active(path: string) {
  if (path === "/app/laboratory") {
    return ["/app/laboratory", "/app/inspection-sessions", "/app/samples"].some(
      (item) => route.path === item || route.path.startsWith(`${item}/`),
    );
  }
  return route.path === path || route.path.startsWith(`${path}/`);
}
</script>

<template>
  <nav class="agent-rail" aria-label="四类质量监督 Agent">
    <RouterLink
      v-for="agent in agents"
      :key="agent.code"
      :to="agent.path"
      class="agent-rail-item"
      :class="{ active: active(agent.path) }"
      :style="{ '--agent-color': agent.color }"
      :aria-current="active(agent.path) ? 'page' : undefined"
    >
      <span class="agent-order">{{ agent.order }}</span>
      <span class="agent-name"
        ><strong>{{ agent.title }}</strong
        ><small>{{ agent.action }}</small></span
      >
      <span class="agent-code">{{ agent.code }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.agent-rail {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid #dce6f0;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(16, 42, 67, 0.05);
}

.agent-rail-item {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  min-height: 76px;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  color: #42566b;
  text-decoration: none;
  transition:
    background-color 180ms ease,
    color 180ms ease;
}

.agent-rail-item + .agent-rail-item {
  border-left: 1px solid #e5edf5;
}

.agent-rail-item::after {
  position: absolute;
  right: 16px;
  bottom: 0;
  left: 16px;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: var(--agent-color);
  content: "";
  opacity: 0;
  transform: scaleX(0.3);
  transition:
    opacity 180ms ease,
    transform 180ms ease;
}

.agent-rail-item:hover,
.agent-rail-item.active {
  background: color-mix(in srgb, var(--agent-color) 6%, white);
  color: #102a43;
}

.agent-rail-item.active::after {
  opacity: 1;
  transform: scaleX(1);
}

.agent-rail-item:focus-visible {
  z-index: 1;
  outline: 2px solid var(--agent-color);
  outline-offset: -3px;
}

.agent-order,
.agent-code {
  color: var(--agent-color);
  font:
    700 10px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
}

.agent-order {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 8px;
  background: color-mix(in srgb, var(--agent-color) 10%, white);
}

.agent-name {
  min-width: 0;
}

.agent-name strong,
.agent-name small {
  display: block;
}

.agent-name strong {
  font-size: 14px;
}

.agent-name small {
  margin-top: 4px;
  overflow: hidden;
  color: #7a8fa4;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-code {
  opacity: 0.55;
}

@media (max-width: 980px) {
  .agent-rail {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agent-rail-item:nth-child(3) {
    border-top: 1px solid #e5edf5;
    border-left: 0;
  }

  .agent-rail-item:nth-child(4) {
    border-top: 1px solid #e5edf5;
  }
}

@media (max-width: 560px) {
  .agent-rail {
    grid-template-columns: 1fr;
  }

  .agent-rail-item {
    min-height: 64px;
  }

  .agent-rail-item + .agent-rail-item,
  .agent-rail-item:nth-child(4) {
    border-top: 1px solid #e5edf5;
    border-left: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-rail-item,
  .agent-rail-item::after {
    transition: none;
  }
}
</style>
