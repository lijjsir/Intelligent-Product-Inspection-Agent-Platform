<script setup lang="ts">
import {computed,ref,watch} from 'vue';
import {useRouter} from 'vue-router';
import {knowledgeApi} from '@/api/knowledge.api';
import {http} from '@/api/http';
const props=defineProps<{modelValue:boolean;recordId:string}>();const emit=defineEmits<{"update:modelValue":[boolean]}>();
const open=computed({get:()=>props.modelValue,set:(v:boolean)=>emit('update:modelValue',v)});
const router=useRouter();const standards=ref<{id:string;name:string}[]>([]);const selected=ref('');const busy=ref(false);const error=ref('');
watch(()=>props.modelValue,async value=>{if(value){error.value='';standards.value=(await http.get<{standards:{id:string;name:string}[]}>('/v1/tasks/meta/creation-options')).data.data.standards;}});
async function create(){busy.value=true;try{const result=await knowledgeApi.taskDraft(props.recordId,{inspection_standard_id:selected.value,input_mode:'image',priority:5});open.value=false;await router.push(`/app/tasks/${result.data.data.task_id}`);}catch(e:any){error.value=e.response?.data?.error?.message||'任务草稿未创建，请核对材料与输入要求';}finally{busy.value=false;}}
</script>
<template><el-dialog v-model="open" title="从已有材料创建任务草稿" width="600px" append-to-body><el-alert title="复用原图片及文件哈希，不重复上传。先创建待执行任务，再核对依据和检测条件。" type="info" :closable="false"/><el-alert v-if="error" :title="error" type="error" :closable="false"/><el-form label-position="top" style="margin-top:20px"><el-form-item label="检测场景 / 关联标准专题" required><el-select v-model="selected" filterable style="width:100%"><el-option v-for="standard in standards" :key="standard.id" :value="standard.id" :label="standard.name"/></el-select></el-form-item></el-form><template #footer><el-button @click="open=false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!selected" @click="create">创建待执行任务</el-button></template></el-dialog></template>
