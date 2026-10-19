<script setup lang="ts">
import { onBeforeUnmount,ref,watch } from 'vue';
import { useRouter } from 'vue-router';
import { riskCompletionApi } from '@/api/risk-completion.api';
import { extractApiErrorMessage } from '@/api/http';
const props=defineProps<{taskId:string;linkId:string}>();
const router=useRouter(),data=ref<Awaited<ReturnType<typeof riskCompletionApi.labTaskOrigin>>['data']['data']|null>(null),error=ref('');
let epoch=0;
async function load(){const key=++epoch;data.value=null;error.value='';try{const value=(await riskCompletionApi.labTaskOrigin(props.linkId,props.taskId)).data.data;if(key===epoch)data.value=value;}catch(e){if(key===epoch)error.value=extractApiErrorMessage(e,'来源关联无法核对，请刷新重试');}}
watch(()=>[props.taskId,props.linkId],()=>void load(),{immediate:true});onBeforeUnmount(()=>{++epoch;});
</script>
<template><section class="risk-task-origin" aria-label="来源验证事项"><el-alert v-if="error" :title="error" type="warning" :closable="false" /><template v-if="data"><h3>来源风险事项：{{ data.case_code }} · {{ data.case_title }}</h3><p>关联原研判第 {{ data.assessment_version }} 版；验证申请与最终风险结论、独立复核分别记录。</p><p class="purpose">验证目的：{{ data.purpose }}</p><el-button type="primary" plain @click="router.push({path:'/app/risk-assessments',query:{case_id:data.case_id,assessment_id:data.assessment_id,tab:'laboratory',validation_id:data.link_id}})">返回来源事项验证与回流</el-button></template></section></template>
<style scoped>.risk-task-origin{border:1px solid var(--el-border-color);border-left:4px solid var(--el-color-primary);padding:18px;border-radius:8px;display:grid;gap:12px;overflow-wrap:anywhere;}h3,p{margin:0;line-height:1.7;}.purpose{white-space:pre-wrap;}.el-button{justify-self:start;max-width:100%;white-space:normal;min-height:44px;}</style>
