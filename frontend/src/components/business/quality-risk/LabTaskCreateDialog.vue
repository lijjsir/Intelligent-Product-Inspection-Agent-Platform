<script setup lang="ts">
import { onBeforeUnmount,ref,watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { riskCompletionApi,type LabTaskContext } from '@/api/risk-completion.api';
import { taskApi } from '@/api/task.api';
import { extractApiErrorMessage } from '@/api/http';
import type { TaskCreationStandardChoice } from '@/types/task.types';
const props=defineProps<{modelValue:boolean;linkId:string}>();
const emit=defineEmits<{'update:modelValue':[value:boolean];created:[]}>();
const router=useRouter(),context=ref<LabTaskContext|null>(null),choices=ref<TaskCreationStandardChoice[]>([]);
const standard=ref(''),priority=ref(5),loading=ref(false),saving=ref(false),error=ref('');
let epoch=0,requestKey=crypto.randomUUID();
function beforeClose(done:()=>void){if(!saving.value)done();}
async function load(){
  const key=++epoch,target=props.linkId;context.value=null;choices.value=[];standard.value='';error.value='';loading.value=true;saving.value=false;requestKey=crypto.randomUUID();
  try{
    const current=(await riskCompletionApi.labTaskContext(target)).data.data;
    const options=current.can_create?(await taskApi.creationOptions({suppressErrorToast:true})).data.data.standards:[];
    if(key!==epoch||target!==props.linkId)return;context.value=current;choices.value=options;
  }catch(e){if(key===epoch)error.value=extractApiErrorMessage(e,'任务准备信息无法读取，请刷新重试');}
  finally{if(key===epoch)loading.value=false;}
}
async function create(){
  const value=context.value,target=props.linkId,key=epoch;
  if(!value?.can_create||!standard.value||saving.value||loading.value)return;
  saving.value=true;error.value='';
  try{
    const result=(await riskCompletionApi.createLabTask(target,{expected_revision:value.revision,expected_basis_hash:value.basis_hash,
      request_key:requestKey,inspection_standard_id:standard.value,priority:priority.value})).data.data;
    if(key!==epoch||target!==props.linkId)return;
    emit('created');emit('update:modelValue',false);
    ElMessage.success(result.reused?'已返回本申请的原检测任务':'已创建待执行任务，请继续核对样品与检测要求');
    await router.push({path:'/app/tasks/'+result.task_id,query:{validation_id:target}});
  }catch(e){if(key===epoch)error.value=extractApiErrorMessage(e,'任务创建失败，请核对当前验证安排和标准配置');}
  finally{if(key===epoch)saving.value=false;}
}
watch(()=>[props.modelValue,props.linkId],()=>{if(props.modelValue)void load();else ++epoch;},{immediate:true});
onBeforeUnmount(()=>{++epoch;});
</script>
<template>
  <el-dialog :model-value="modelValue" title="从事项创建验证任务" width="min(660px,94vw)" :close-on-click-modal="false" :before-close="beforeClose" @update:model-value="emit('update:modelValue',$event)">
    <div v-loading="loading" class="lab-task-preparation">
      <el-alert title="本次仅创建待执行任务，不启动设备、模型或检测。执行前仍须确认样品、已发布检测要求及原始数据。" type="info" :closable="false" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template v-if="context">
        <p>{{ context.case_code }} · 原研判第 {{ context.assessment_version }} 版</p>
        <dl><dt>具体产品</dt><dd>{{ context.product_name }}</dd><dt>产品类别</dt><dd>{{ context.category_name }}</dd><dt>批次 / 单件</dt><dd>{{ context.production_batch_ref||'批次未知' }} / {{ context.unit_serial_ref||'单件未知' }}</dd><dt>验证目的</dt><dd>{{ context.purpose }}</dd></dl>
        <el-alert v-for="reason in context.blockers" :key="reason" :title="reason" type="warning" :closable="false" />
        <el-form v-if="context.can_create" label-position="top" :disabled="saving">
          <el-form-item label="检测标准配置" required><el-select v-model="standard" filterable placeholder="选择本单位有效配置"><el-option v-for="item in choices" :key="item.id" :value="item.id" :label="item.name" /></el-select></el-form-item>
          <p v-if="!choices.length">没有可用配置，请由有权限的人员在现有标准模块维护后重试。</p>
          <el-form-item label="优先级"><el-input-number v-model="priority" :min="1" :max="10" /></el-form-item>
        </el-form>
      </template>
    </div>
    <template #footer><el-button :disabled="saving" @click="emit('update:modelValue',false)">取消</el-button><el-button v-if="context?.task_id" @click="router.push({path:'/app/tasks/'+context.task_id,query:{validation_id:linkId}})">查看已关联任务</el-button><el-button v-if="error" :disabled="loading||saving" @click="load">重试</el-button><el-button v-if="!context?.task_id" type="primary" :disabled="loading||saving||!context?.can_create||!standard" :loading="saving" @click="create">确认创建待执行任务</el-button></template>
  </el-dialog>
</template>
<style scoped>.lab-task-preparation{display:grid;gap:14px;min-width:0;}dl{display:grid;grid-template-columns:90px minmax(0,1fr);gap:12px;margin:0;}dt{color:var(--el-text-color-secondary);}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;}.el-select{width:100%;}</style>
