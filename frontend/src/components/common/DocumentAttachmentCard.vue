<script setup lang="ts">
import { computed } from 'vue';
import { Document } from '@element-plus/icons-vue';

const props = defineProps<{ name: string; url?: string | null; sizeBytes?: number | null; compact?: boolean }>();
const extension = computed(() => props.name.split('.').pop()?.toUpperCase() || '文件');
const typeLabels: Record<string,string> = {DOCX:'Word 文档',DOC:'Word 文档',XLSX:'Excel 表格',XLS:'Excel 表格',CSV:'数据表格',PDF:'PDF 文档',TXT:'文本文件'};
const typeLabel = computed(() => typeLabels[extension.value] || '文档');
const fileSize = computed(() => { const size=props.sizeBytes || 0; return !size ? '' : size < 1024*1024 ? `${Math.max(1,Math.round(size/1024))} KB` : `${(size/1024/1024).toFixed(1)} MB`; });
const safeUrl = computed(() => { const value=props.url || ''; return /^(https?:\/\/|\/(?!\/))/.test(value) ? value : undefined; });
</script>

<template>
  <a class="document-attachment" :class="{ compact }" :href="safeUrl" target="_blank" rel="noopener noreferrer" :title="name">
    <span class="document-type-icon" :data-type="extension"><Document /><small>{{ extension.slice(0,4) }}</small></span>
    <span class="document-copy"><strong>{{ name }}</strong><small>{{ typeLabel }}<template v-if="fileSize"> · {{ fileSize }}</template></small></span>
  </a>
</template>

<style scoped>
.document-attachment { display:flex; align-items:center; gap:12px; width:270px; max-width:100%; min-height:74px; padding:12px 14px; border:1px solid #dfe6f0; border-radius:13px; background:#fff; text-decoration:none; color:#33475f; line-height:1.5; }
.document-attachment:hover { border-color:#98b5db; background:#fbfdff; }
.document-type-icon { display:flex; flex-direction:column; align-items:center; justify-content:center; width:38px; height:44px; flex:none; border-radius:8px; background:#edf3fb; color:#517aac; }
.document-type-icon[data-type="PDF"] { background:#fff0f0; color:#bd6971; }
.document-type-icon svg { width:20px; height:20px; }
.document-type-icon small { font-size:8px; font-weight:600; }
.document-copy { min-width:0; display:flex; flex-direction:column; gap:5px; }
.document-copy strong { font-size:12px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.document-copy small { font-size:10px; color:#91a0b4; }
.document-attachment.compact { width:230px; min-height:70px; padding:10px 12px; }
</style>
