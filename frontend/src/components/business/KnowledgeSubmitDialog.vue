<script setup lang="ts">
import {computed,reactive,ref,watch} from "vue";
import {ElMessage} from "element-plus";
import {knowledgeApi} from "@/api/knowledge.api";
import type {KnowledgeSourceRef} from "@/types/knowledge.types";
const props=defineProps<{modelValue:boolean;sourceKind?:string;sourceId?:string}>();
const emit=defineEmits<{"update:modelValue":[boolean];submitted:[]}>();
const open=computed({get:()=>props.modelValue,set:(v:boolean)=>emit("update:modelValue",v)});
const source=ref<KnowledgeSourceRef|null>(null);
const sources=ref<KnowledgeSourceRef[]>([]);
const busy=ref(false);const error=ref("");
const qdlText=ref('');const relatedIds=ref('');
const form=reactive({kind:"rag_document",id:"",quote:"",claim:"",product_category:"",applicability:"",limitations:"",
  requested_scope:"private",consent_to_review:false,consent_to_share:false});
async function preview(){busy.value=true;error.value="";try{source.value=(await knowledgeApi.source(form.kind,form.id)).data.data;}catch(e:any){error.value=e.response?.data?.error?.message||"无法读取所选来源";}finally{busy.value=false;}}
function addSource(){if(!source.value)return;const ref={kind:form.kind,id:form.id,quote:form.quote};if(!sources.value.some(s=>s.kind===ref.kind&&s.id===ref.id))sources.value.push(ref);source.value=null;form.quote="";}
async function submit(){if(!form.consent_to_review||!sources.value.length)return;busy.value=true;error.value="";try{
  const qdl=qdlText.value.trim()?JSON.parse(qdlText.value):null;
  await knowledgeApi.submit({request_key:crypto.randomUUID(),claim:form.claim,product_category:form.product_category,applicability:form.applicability,
    limitations:form.limitations,sources:sources.value,requested_scope:form.requested_scope,consent_to_review:form.consent_to_review,
    consent_to_share:form.consent_to_share,qdl,related_memory_ids:relatedIds.value.split('\n').map(s=>s.trim()).filter(Boolean)});open.value=false;emit("submitted");ElMessage.success("候选已提交，原始资料保持原权限");
  }catch(e:any){error.value=e.response?.data?.error?.message||"提交未完成，请检查来源和授权";}finally{busy.value=false;}}
watch(()=>props.modelValue,async(value)=>{if(!value)return;qdlText.value='';relatedIds.value='';Object.assign(form,{kind:props.sourceKind||"rag_document",id:props.sourceId||"",quote:"",claim:"",product_category:"",applicability:"",limitations:"",requested_scope:"private",consent_to_review:false,consent_to_share:false});sources.value=[];source.value=null;error.value="";if(form.id)await preview();});
</script>
<template>
<el-dialog v-model="open" title="从已有来源提交知识候选" width="min(880px,96vw)" top="4vh" class="knowledge-submit-dialog" append-to-body>
  <el-alert type="info" :closable="false" title="只提交主张和选定引用片段；原文件不会自动共享，也不会直接成为公共标准。"/>
  <el-alert v-if="error" :title="error" type="error" :closable="false" class="error"/>
  <el-form label-position="top" class="candidate-form">
    <div class="source-picker"><el-form-item label="来源类型"><el-select v-model="form.kind"><el-option v-for="type in [{v:'rag_document',l:'知识资料文件'},{v:'task_result',l:'任务结果'},{v:'meeting_message',l:'会议发言'},{v:'intake_record',l:'资料接入记录'},{v:'standard_revision',l:'标准修订'},{v:'inspection_execution',l:'已复核的项目执行结果'}]" :key="type.v" :label="type.l" :value="type.v"/></el-select></el-form-item><el-form-item label="来源记录编号"><el-input v-model="form.id"/></el-form-item><el-button :loading="busy" @click="preview">核对来源</el-button></div>
    <div v-if="source" class="source-box"><strong>{{ source.metadata?.title }} · {{ source.authority==='formal_standard'?'已发布标准':'来源性质需在核验时确认' }}</strong><pre>{{ source.available_excerpt }}</pre><el-form-item label="选定引用片段（须与来源一致）"><el-input v-model="form.quote" type="textarea" :rows="3" placeholder="复制所需原文；仅凭结果存在，不能证明新的主张成立"/></el-form-item><el-button @click="addSource">加入来源清单</el-button></div>
    <div class="sources"><el-tag v-for="(s,i) in sources" :key="`${s.kind}:${s.id}`" closable @close="sources.splice(i,1)">{{ s.kind }} · {{ s.id.slice(0,8) }} · {{ s.quote ? '已选片段':'仅记录出处' }}</el-tag></div>
    <el-form-item label="可复用的知识主张" required><el-input v-model="form.claim" type="textarea" :rows="3" placeholder="描述待核对的经验、规律或方法，避免直接复制整份报告"/></el-form-item>
    <el-form-item label="相关产品类别" required><el-input v-model="form.product_category"/></el-form-item>
    <el-form-item label="适用条件与场景" required><el-input v-model="form.applicability" type="textarea" :rows="2"/></el-form-item>
    <el-form-item label="限制、反例与尚缺证据" required><el-input v-model="form.limitations" type="textarea" :rows="2"/></el-form-item>
    <el-collapse><el-collapse-item title="结构化主张与知识依赖（已有资料再提供）"><el-form-item label="QDL结构化主张（JSON，选填）"><el-input v-model="qdlText" type="textarea" :rows="5"/></el-form-item><el-form-item label="依赖的已授权知识编号（每行一条）"><el-input v-model="relatedIds" type="textarea" :rows="2"/></el-form-item></el-collapse-item></el-collapse>
    <el-form-item label="目标使用范围"><el-radio-group v-model="form.requested_scope"><el-radio value="private">本人使用</el-radio><el-radio value="organization">申请组织使用</el-radio></el-radio-group></el-form-item>
    <el-checkbox v-model="form.consent_to_review">同意审核者读取本次主张及选定的引用片段</el-checkbox>
    <el-checkbox v-if="form.requested_scope==='organization'" v-model="form.consent_to_share">同意将本次知识申请在本组织共享，仍需范围审批与专业核验</el-checkbox>
  </el-form>
  <template #footer><el-button @click="open=false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!form.consent_to_review||!sources.length||!form.claim.trim()||!form.applicability.trim()||!form.limitations.trim()||(form.requested_scope==='organization'&&!form.consent_to_share)" @click="submit">提交待核对候选</el-button></template>
</el-dialog>
</template>
<style scoped>.knowledge-submit-dialog :deep(.el-dialog__body){max-height:calc(92dvh - 150px);overflow:auto}.candidate-form{margin-top:18px;display:flex;flex-direction:column;gap:6px}.source-picker{display:grid;grid-template-columns:200px 1fr auto;gap:12px;align-items:center}.source-box{padding:16px;border:1px solid var(--el-border-color);border-left:3px solid var(--el-color-primary);margin-bottom:12px;border-radius:6px}.source-box pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto;font:13px/1.8 'Microsoft YaHei',sans-serif}.sources{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.error{margin-top:12px}@media(max-width:680px){.source-picker{grid-template-columns:1fr}}</style>
