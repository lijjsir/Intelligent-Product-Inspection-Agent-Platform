<script setup lang="ts">
import {ref,watch} from 'vue';
import {useRouter} from 'vue-router';
import {inspectionExecutionApi as api} from '@/api/inspection-execution.api';
import {extractApiErrorMessage} from '@/api/http';
import {useAuthStore} from '@/stores/auth.store';
import type {InspectionCaseWorkflow} from '@/types/inspection-execution.types';
const props=defineProps<{taskId:string}>();
const workflow=ref<InspectionCaseWorkflow|null>(null),loading=ref(false),error=ref('');
const router=useRouter(),auth=useAuthStore();
async function load(){loading.value=true;error.value='';try{workflow.value=(await api.caseWorkflow(props.taskId)).data.data;}
catch(e){error.value=extractApiErrorMessage(e,'案例进度暂时无法读取');}finally{loading.value=false;}}
watch(()=>props.taskId,load,{immediate:true});
function reviewStandard(){if(workflow.value)router.push({path:'/app/standard-reviews',query:{document_id:workflow.value.standard_document_id,
  revision_id:workflow.value.standard_revision_id,keyword:workflow.value.standard_no}});}
</script>
<template><section class="case-workflow" v-loading="loading"><header><div><small>工业案例 / 原件与流程</small><h2>{{workflow?.title||'案例准备与核验'}}</h2></div><el-button @click="load">刷新进度</el-button></header>
<el-alert v-if="error" :title="error" type="warning" :closable="false"/>
<template v-if="workflow"><el-alert title="资料已准备；专业确认仍以审核记录为准，产品整体未评定。" type="info" :closable="false"/>
<div class="case-readings"><article v-for="item in workflow.planned_items" :key="item.measurement_key"><span>{{item.indicator}}</span><strong>{{item.value}} <small>{{item.unit}}</small></strong><p>上传报告第 {{item.report_page}} 页 · 原始PDF第 {{item.original_pdf_page}} 页</p><small v-if="item.minimum_observations>1">标准要求 {{item.minimum_observations}} 次观测；当前仅有公开报告汇总值，仍需补证。</small></article></div>
<ol class="case-stages"><li v-for="(step,index) in workflow.steps" :key="step.key"><span class="step-number">{{index+1}}</span><div><strong>{{step.label}}</strong><p>{{step.detail}}</p></div><el-tag :type="step.status==='complete'?'success':'info'">{{step.status==='complete'?'已具备':'待办理'}}</el-tag></li></ol>
<div class="case-actions"><el-button v-if="auth.primaryRole==='expert'&&auth.hasPermission('standard_admission_review')&&workflow.standard_document_id" type="primary" plain @click="reviewStandard">打开本案标准核对</el-button><el-button v-if="workflow.execution_run_id" @click="router.push({path:`/app/results/${taskId}`,query:{execution_run_id:workflow.execution_run_id}})">查看本案结果与报告</el-button></div>
<details><summary>本案使用范围与缺项</summary><ul><li v-for="note in workflow.limitations" :key="note">{{note}}</li></ul></details></template></section></template>
<style scoped>.case-workflow{display:grid;gap:16px;padding:24px;background:#fff;border:1px solid #dbe5f2;border-radius:12px;border-top:4px solid #0d7480}.case-workflow header{display:flex;justify-content:space-between;gap:16px}.case-workflow header small{color:#0d7480}.case-workflow h2{margin:6px 0;font-size:22px;color:#183451}.case-readings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.case-readings article{padding:16px;background:#f6f9fc;border:1px solid #e2e8f0;border-radius:8px;display:grid;gap:8px}.case-readings strong{font-size:24px}.case-readings p{margin:0;font-size:13px;color:#64748b}.case-readings small{font-size:12px;color:#64748b}.case-stages{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.case-stages li{display:flex;gap:12px;align-items:flex-start;border-bottom:1px solid #edf1f5;padding:12px 0}.step-number{display:grid;place-items:center;min-width:26px;height:26px;background:#eaf4f5;color:#0d7480;border-radius:50%;font-size:12px}.case-stages li>div{flex:1}.case-stages strong{font-size:14px}.case-stages p{margin:6px 0;font-size:13px;color:#64748b;line-height:1.5}.case-actions{display:flex;gap:10px;flex-wrap:wrap}details{color:#64748b;font-size:13px}details li{margin:8px 0}@media(max-width:760px){.case-workflow{padding:16px}.case-readings,.case-stages{grid-template-columns:1fr}.case-workflow header{flex-direction:column}}</style>
