<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { qualityRiskApi } from '@/api/quality-risk.api';
import { extractApiErrorMessage } from '@/api/http';
import type { RiskCaseV4 } from '@/types/quality-risk.types';
const props = defineProps<{id: string; label: string; modelValue?: string | null; selectedCase?: RiskCaseV4 | null; disabled?: boolean; emptyLabel?: string}>();
const emit = defineEmits<{'update:modelValue':[value: string | undefined]}>();
const query = ref(''), page = ref(1), total = ref(0), loading = ref(false), error = ref('');
const rows = ref<RiskCaseV4[]>([]);
const options = computed(() => props.selectedCase && props.selectedCase.id === props.modelValue && !rows.value.some(r => r.id === props.modelValue)
  ? [props.selectedCase, ...rows.value] : rows.value);
let epoch = 0, timer: ReturnType<typeof setTimeout> | undefined;
async function load() {
  const key = ++epoch, requestedQuery = query.value;
  loading.value = true; error.value = ''; rows.value = [];
  try {
    const result = (await qualityRiskApi.riskCases({page:page.value, size:20, keyword:requestedQuery || undefined}, {suppressErrorToast:true})).data.data;
    if (key === epoch) { rows.value = result.items; total.value = result.total; }
  } catch (e) { if (key === epoch) { total.value = 0; error.value = extractApiErrorMessage(e, '事项选项加载失败'); } }
  finally { if (key === epoch) loading.value = false; }
}
watch(query, () => { ++epoch; rows.value = []; loading.value = true; clearTimeout(timer); page.value = 1; timer = setTimeout(load, 250); });
void load();
onBeforeUnmount(() => { ++epoch; clearTimeout(timer); });
</script>
<template>
  <div class="risk-case-picker">
    <label :for="id">{{ label }}</label>
    <el-input v-model="query" :aria-label="label + '搜索'" placeholder="按事项编号或标题搜索" clearable :disabled="disabled" />
    <select :id="id" :value="modelValue || ''" :disabled="disabled || loading" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value || undefined)">
      <option value="">{{ emptyLabel || '全部事项' }}</option>
      <option v-if="modelValue && !options.some(r => r.id === modelValue)" :value="modelValue">当前事项（正在核对）</option>
      <option v-for="row in options" :key="row.id" :value="row.id">{{ row.code }} · {{ row.title }}</option>
    </select>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="picker-pages">
      <el-button :disabled="disabled || loading || page <= 1" @click="page--; load()">上一页事项</el-button>
      <span>第 {{ page }} 页 · 共 {{ total }} 条</span>
      <el-button :disabled="disabled || loading || page * 20 >= total" @click="page++; load()">下一页事项</el-button>
      <el-button v-if="error" :disabled="disabled || loading" @click="load">重试事项</el-button>
    </div>
  </div>
</template>
<style scoped>
.risk-case-picker { display:grid; gap:10px; min-width:0; }
select { width:100%; max-width:100%; min-height:44px; padding:8px; border:1px solid var(--el-border-color); border-radius:5px; color:inherit; background:var(--el-bg-color); }
.picker-pages { display:flex; gap:10px; align-items:center; flex-wrap:wrap; color:var(--el-text-color-regular); }
.picker-pages :deep(.el-button) { margin-left:0; min-height:44px; }
</style>
