<script setup lang="ts">
import { computed, ref, watch } from "vue";

const props = defineProps<{
  src?: string | null;
  name?: string | null;
}>();

const emit = defineEmits<{
  (event: "preview"): void;
}>();

const failed = ref(false);
const imageSrc = computed(() => String(props.src || ""));
const imageName = computed(() => String(props.name || "图片"));
const canPreview = computed(() => Boolean(imageSrc.value) && !failed.value);

watch(imageSrc, () => {
  failed.value = false;
});

function preview() {
  if (canPreview.value) emit("preview");
}
</script>

<template>
  <button
    type="button"
    class="image-attachment-card"
    :class="{ 'is-unavailable': !canPreview }"
    :title="imageName"
    :aria-label="canPreview ? `预览图片 ${imageName}` : `图片暂不可用 ${imageName}`"
    :disabled="!canPreview"
    @click="preview"
  >
    <img v-if="imageSrc && !failed" :src="imageSrc" :alt="imageName" loading="lazy" @error="failed = true" />
    <span v-else class="image-attachment-fallback">图片暂不可用</span>
    <span class="image-attachment-name">{{ imageName }}</span>
  </button>
</template>

<style scoped>
.image-attachment-card {
  position: relative;
  display: block;
  width: min(220px, 58vw);
  aspect-ratio: 4 / 3;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 8px;
  background: #111827;
  cursor: zoom-in;
  font: inherit;
  line-height: 0;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.12);
}

.image-attachment-card:disabled {
  cursor: default;
}

.image-attachment-card img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: #f3f4f6;
  transition: transform 0.18s ease;
}

.image-attachment-card:not(:disabled):hover img,
.image-attachment-card:not(:disabled):focus-visible img {
  transform: scale(1.03);
}

.image-attachment-card:focus-visible {
  outline: 2px solid #60a5fa;
  outline-offset: 2px;
}

.image-attachment-fallback {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  background: #f1f5f9;
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
}

.image-attachment-name {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  padding: 22px 9px 8px;
  overflow: hidden;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: linear-gradient(to top, rgba(15, 23, 42, 0.82), rgba(15, 23, 42, 0));
}

.is-unavailable .image-attachment-name {
  color: #334155;
  background: linear-gradient(to top, rgba(226, 232, 240, 0.96), rgba(226, 232, 240, 0));
}
</style>
