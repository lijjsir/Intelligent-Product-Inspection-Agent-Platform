<script setup lang="ts">
import { useRouter } from "vue-router";

const props = withDefaults(defineProps<{
  title: string;
  description: string;
  eyebrow?: string;
  backPath?: string;
  backText?: string;
  showBack?: boolean;
}>(), {
  eyebrow: "Algorithm Workspace",
  backPath: "",
  backText: "返回列表",
  showBack: false,
});

const router = useRouter();

function goBack() {
  if (props.backPath) {
    router.push(props.backPath);
    return;
  }
  router.back();
}
</script>

<template>
  <section class="workspace-hero">
    <div class="workspace-hero__main">
      <el-button
        v-if="showBack"
        link
        type="primary"
        class="workspace-hero__back"
        @click="goBack"
      >
        {{ backText }}
      </el-button>
      <div class="workspace-hero__copy">
        <p class="workspace-hero__eyebrow">{{ eyebrow }}</p>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
    </div>

    <div v-if="$slots.aside || $slots.actions" class="workspace-hero__side">
      <div v-if="$slots.aside" class="workspace-hero__aside">
        <slot name="aside" />
      </div>
      <div v-if="$slots.actions" class="workspace-hero__actions">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.workspace-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px 30px;
  border-radius: 24px;
  border: 1px solid rgba(14, 116, 144, 0.12);
  background:
    radial-gradient(circle at top right, rgba(14, 116, 144, 0.16), transparent 28%),
    linear-gradient(135deg, #fffdf8 0%, #f0f9ff 100%);
}

.workspace-hero__main {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.workspace-hero__back {
  align-self: flex-start;
  margin-left: -8px;
  font-weight: 600;
}

.workspace-hero__copy h2 {
  margin: 4px 0 8px;
  font-size: 28px;
  color: #0f172a;
}

.workspace-hero__copy p:last-child {
  margin: 0;
  max-width: 760px;
  color: #475569;
  line-height: 1.7;
}

.workspace-hero__eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

.workspace-hero__side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
}

.workspace-hero__aside,
.workspace-hero__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 767px) {
  .workspace-hero {
    flex-direction: column;
    padding: 24px 20px;
  }

  .workspace-hero__side,
  .workspace-hero__aside,
  .workspace-hero__actions {
    align-items: flex-start;
    justify-content: flex-start;
  }
}
</style>
