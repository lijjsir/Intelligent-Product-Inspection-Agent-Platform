<script setup lang="ts">
import { ref } from "vue"
import { ElMessage } from "element-plus"

defineProps<{
  title: string
  data: Record<string, any> | null
}>()

const visible = ref(false)
const formatted = ref("")

function open() {
  visible.value = true
}

function close() {
  visible.value = false
}

function copyJson(data: Record<string, any> | null) {
  if (!data) return
  try {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    ElMessage.success("已复制到剪贴板")
  } catch {
    ElMessage.error("复制失败")
  }
}

defineExpose({ open, close })
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="720px"
    :close-on-click-modal="true"
    destroy-on-close
    class="json-dialog"
  >
    <div class="json-toolbar">
      <el-button size="small" text @click="copyJson(data)">
        复制 JSON
      </el-button>
    </div>
    <div class="json-viewer">
      <pre><code>{{ data ? JSON.stringify(data, null, 2) : '无数据' }}</code></pre>
    </div>
  </el-dialog>
</template>

<style scoped>
.json-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.json-viewer {
  background: oklch(0.18 0.005 260);
  border-radius: 6px;
  padding: 20px;
  max-height: 480px;
  overflow: auto;
}

.json-viewer pre {
  margin: 0;
  white-space: pre;
}

.json-viewer code {
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.7;
  color: oklch(0.82 0.01 260);
}
</style>
