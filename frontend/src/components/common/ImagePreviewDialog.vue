<script setup lang="ts">
defineProps<{
  modelValue: boolean;
  src: string;
  title?: string;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
}>();

function close() {
  emit("update:modelValue", false);
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="title || '图片预览'"
    width="min(92vw, 980px)"
    class="image-preview-dialog"
    append-to-body
    align-center
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="image-preview-body">
      <img v-if="src" :src="src" :alt="title || '图片预览'" />
    </div>
    <template #footer>
      <el-button @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.image-preview-body {
  display: grid;
  place-items: center;
  min-height: min(58vh, 560px);
  max-height: 72vh;
  overflow: auto;
  border-radius: 8px;
  background: #0f172a;
}

.image-preview-body img {
  display: block;
  max-width: 100%;
  max-height: 72vh;
  object-fit: contain;
}
</style>
