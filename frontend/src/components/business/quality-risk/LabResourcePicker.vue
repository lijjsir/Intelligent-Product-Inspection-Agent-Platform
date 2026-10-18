<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { riskCompletionApi, type LabOption } from '@/api/risk-completion.api';
import { extractApiErrorMessage } from '@/api/http';
const props = defineProps<{caseId: string; kind: 'tasks' | 'records'; modelValue: string | string[] | null; label: string; disabled?: boolean}>();
const emit = defineEmits<{'update:modelValue':[value: string | string[] | null]}>();
const rows = ref<LabOption[]>([]), pinned = ref<LabOption[]>([]), unavailable = ref<string[]>([]);
const page = ref(1), total = ref(0), query = ref(''), error = ref(''), loading = ref(false);
const selectedIds = computed(() => Array.isArray(props.modelValue) ? props.modelValue : props.modelValue ? [props.modelValue] : []);
const options = computed(() => [...new Map([...pinned.value, ...rows.value].map(r => [r.id,r])).values()]);
let epoch = 0, timer: ReturnType<typeof setTimeout> | undefined;
async function load() {
  const key = ++epoch, target = props.caseId;
  rows.value = []; pinned.value = []; unavailable.value = []; error.value = ''; loading.value = true;
  try {
    const result = (await riskCompletionApi.labOptionPage(target, props.kind, {page:page.value, keyword:query.value, selected_ids:selectedIds.value})).data.data;
    if (key !== epoch || target !== props.caseId) return;
    rows.value = result.items; pinned.value = result.selected; unavailable.value = result.unavailable_selected_ids; total.value = result.total;
  } catch (e) { if (key === epoch) { total.value = 0; error.value = extractApiErrorMessage(e, '关联选项加载失败'); } }
  finally { if (key === epoch) loading.value = false; }
}
function search(value: string) { ++epoch; loading.value = true; rows.value = []; query.value = value; page.value = 1; clearTimeout(timer); timer = setTimeout(load, 250); }
watch(() => [props.caseId, selectedIds.value.join(',')], (now, old) => { if (now[0] !== old?.[0]) { page.value=1; query.value=''; } clearTimeout(timer); void load(); }, {immediate:true});
onBeforeUnmount(() => { ++epoch; clearTimeout(timer); });
</script>
<template>
  <div class="lab-resource-picker" role="group" :aria-label="label + '分页选择'">
    <el-select :model-value="modelValue" :multiple="kind === 'records'" :multiple-limit="20" filterable remote :remote-method="search" :loading="loading" clearable :disabled="disabled" :aria-label="label" placeholder="输入编号或名称搜索" @update:model-value="emit('update:modelValue', $event)">
      <el-option v-for="row in options" :key="row.id" :value="row.id" :label="`${row.already_linked ? '【已在事项中】' : ''}${row.label}`" />
      <el-option v-for="id in unavailable" :key="id" :value="id" label="原关联当前不可访问，请核对授权与对象" disabled />
      <template #footer><div class="option-pages">
        <el-button :disabled="disabled || loading || page <= 1" @click="page--; load()">上一页选项</el-button>
        <span>第 {{ page }} 页 · {{ total }} 条</span>
        <el-button :disabled="disabled || loading || page * 20 >= total" @click="page++; load()">下一页选项</el-button>
      </div></template>
    </el-select>
    <small>共 {{ total }} 条，支持搜索和翻页。</small>
    <el-alert v-if="error || unavailable.length" :title="error || '部分原关联已不可访问，请核对授权、撤回状态和对象。'" type="warning" :closable="false" />
    <el-button v-if="error" :disabled="disabled || loading" @click="load">重试关联选项</el-button>
  </div>
</template>
<style scoped>
.lab-resource-picker { width:100%; min-width:0; display:grid; gap:8px; }
.option-pages { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.option-pages :deep(.el-button) { margin-left:0; min-height:40px; }
small { color:var(--el-text-color-secondary); }
</style>
