<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import type { ReferenceLoader, ReferenceOption } from '@/api/supervision.api';
import { extractApiErrorMessage } from '@/api/http';
const props=defineProps<{modelValue?: string | string[] | null; loader: ReferenceLoader; label: string; multiple?: boolean; disabled?: boolean; contextKey?: string; selectionLimit?:number; clearable?:boolean;showLabel?:boolean}>();
const emit=defineEmits<{'update:modelValue':[value: string | string[] | null]}>();
const rows=ref<ReferenceOption[]>([]), selected=ref<ReferenceOption[]>([]), unavailable=ref<string[]>([]);
const page=ref(1), total=ref<number | null>(null), more=ref(false), loading=ref(false), error=ref(''), query=ref('');
const selectedIds=computed(()=>Array.isArray(props.modelValue)?props.modelValue:props.modelValue?[props.modelValue]:[]);
const options=computed(()=>[...new Map([...selected.value,...rows.value].map(r=>[r.value,r])).values()]);
let epoch=0, timer: ReturnType<typeof setTimeout> | undefined;
async function load() {
  const key=++epoch; loading.value=true; error.value=''; rows.value=[]; selected.value=[]; unavailable.value=[]; more.value=false;
  try {
    const ids=[...selectedIds.value],request={page:page.value,keyword:query.value};
    const result=await props.loader({...request,selected_ids:ids.slice(0,20)});
    for(let start=20;start<ids.length;start+=20){
      if(key!==epoch)return;
      const extra=await props.loader({...request,selected_ids:ids.slice(start,start+20)});
      result.selected.push(...extra.selected);result.unavailable_selected_ids.push(...extra.unavailable_selected_ids);
    }
    if(key!==epoch)return;
    rows.value=result.items;selected.value=result.selected;unavailable.value=result.unavailable_selected_ids;total.value=result.total;more.value=result.has_more;
  } catch(e) {if(key===epoch){error.value=extractApiErrorMessage(e,'选项加载失败，请重试');total.value=null;}}
  finally {if(key===epoch)loading.value=false;}
}
function search(value: string) {++epoch;loading.value=true;rows.value=[];query.value=value;page.value=1;clearTimeout(timer);timer=setTimeout(load,250);}
watch(()=>[props.contextKey,props.loader,selectedIds.value.join(',')],(now,old)=>{if(now[0]!==old?.[0]||now[1]!==old?.[1]){page.value=1;query.value='';}clearTimeout(timer);void load();},{immediate:true});
onBeforeUnmount(()=>{++epoch;clearTimeout(timer);});
</script>
<template>
  <div class="paged-reference" role="group" :aria-label="label+'分页选择'">
    <label v-if="showLabel">{{ label }}</label>
    <el-select :model-value="modelValue" :multiple="multiple" :multiple-limit="selectionLimit || 0" :disabled="disabled" :loading="loading" filterable remote :clearable="clearable!==false" :remote-method="search" :aria-label="label" placeholder="输入编号或名称搜索" @update:model-value="emit('update:modelValue',$event)">
      <el-option v-for="row in options" :key="row.value" :label="row.label" :value="row.value" :disabled="row.disabled" />
      <el-option v-for="id in unavailable" :key="id" :value="id" label="原选项当前不可用，请核对权限、状态和关联对象" disabled />
      <template #footer><div class="reference-pages"><el-button :disabled="disabled||loading||page<=1" @click="page--;load()">上一页选项</el-button><span>第 {{ page }} 页<span v-if="total!==null"> · 共 {{ total }} 条</span></span><el-button :disabled="disabled||loading||!more" @click="page++;load()">下一页选项</el-button></div></template>
    </el-select>
    <small>支持搜索和翻页，已选项会单独核对。</small>
    <el-alert v-if="error||unavailable.length" :title="error||'部分原选项已不可用，请核对权限、状态和关联对象。'" type="warning" :closable="false" />
    <el-button v-if="error" :disabled="disabled||loading" @click="load">重试选项</el-button>
  </div>
</template>
<style scoped>
.paged-reference{display:grid;gap:8px;min-width:0;width:100%;}.reference-pages{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}.reference-pages :deep(.el-button){margin-left:0;min-height:40px;}small{color:var(--el-text-color-secondary);}
</style>
