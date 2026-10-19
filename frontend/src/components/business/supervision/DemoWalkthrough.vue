<script setup lang="ts">
import { computed,nextTick,onBeforeUnmount,ref,watch } from 'vue';
import { useRoute } from 'vue-router';
import { useRuntimeContext } from '@/composables/useRuntimeContext';
import { useAuthStore } from '@/stores/auth.store';
import { qualityRiskApi } from '@/api/quality-risk.api';
import { extractApiErrorMessage } from '@/api/http';
import { demoWalkthrough,skipValidationExample } from '@/utils/demo-walkthrough';
import { riskCompletionApi,type RiskReport } from '@/api/risk-completion.api';
const runtime=useRuntimeContext(),auth=useAuthStore();
const route=useRoute(),panel=ref<HTMLElement|null>(null);
const enabled=computed(()=>runtime.context.value?.execution_mode==='demo'&&auth.primaryRole==='expert'&&auth.hasPermission('quality_material_read_business'));
const loading=ref(false),error=ref(''),guide=ref<ReturnType<typeof demoWalkthrough>|null>(null);
const skipExample=ref<RiskReport|null>(null),reportNotice=ref('');
let epoch=0;
async function load(){
  const key=++epoch;guide.value=null;skipExample.value=null;reportNotice.value='';error.value='';loading.value=false;
  if(!enabled.value)return;
  const code=runtime.context.value?.case_code;
  if(!code){error.value='服务端未提供演示案例编号，请检查演示环境配置。';return;}
  loading.value=true;
  try{
    let page=1,found;
    do{
      const result=(await qualityRiskApi.riskCases({page,size:100,keyword:code},{suppressErrorToast:true})).data.data;
      if(key!==epoch)return;
      found=result.items.find(row=>row.code===code);
      if(found||page*100>=result.total)break;
      page++;
    }while(!found);
    if(!found)throw new Error(`尚未找到指定演示案例 ${code}，请先按本地演示说明初始化。`);
    const workspace=(await qualityRiskApi.riskWorkspace(found.id,{suppressErrorToast:true})).data.data;
    if(key!==epoch)return;
    guide.value=demoWalkthrough(workspace,code);
    loading.value=false;
    await nextTick();
    if(key!==epoch)return;
    if(route.hash==='#demo-case-guide')panel.value?.scrollIntoView({block:'start'});
    try{
      const page=(await riskCompletionApi.reportPage({case_id:found.id,size:20})).data.data;
      if(key!==epoch)return;
      const reports=await Promise.allSettled(page.items.map(r=>riskCompletionApi.report(r.id)));
      if(key!==epoch)return;
      skipExample.value=skipValidationExample(found.id,reports.flatMap(r=>r.status==='fulfilled'?[r.value.data.data]:[]));
      if(reports.some(r=>r.status==='rejected'))reportNotice.value='部分报告示例暂不可访问，请到报告中心核对。';
      else if(page.has_more&&!skipExample.value)reportNotice.value='当前页未找到跳过验证示例，可到报告中心翻页查看。';
    }catch{if(key===epoch)reportNotice.value='历史报告示例暂不可读取，六步业务入口仍可使用。';}
  }catch(e){if(key===epoch)error.value=extractApiErrorMessage(e,e instanceof Error?e.message:'演示案例读取失败，请重试');}
  finally{if(key===epoch)loading.value=false;}
}
watch(()=>[enabled.value,runtime.context.value?.case_code,auth.orgId,auth.userId],()=>void load(),{immediate:true});
onBeforeUnmount(()=>{++epoch;});
</script>
<template>
  <section v-if="enabled" ref="panel" class="demo-walkthrough" aria-labelledby="walkthrough-title" v-loading="loading">
    <header class="walkthrough-heading"><div><p class="eyebrow">演示案例 · 按业务顺序查看</p><h2 id="walkthrough-title">没有实物检测资料，也可以讲清质量风险分析流程</h2><p>先走六步主线；实验室作为可选补证分支。导览读取已保存记录，不自动创建版本、复核、建议或报告。</p></div><el-button :disabled="loading" @click="load">刷新演示导览</el-button></header>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" />
    <template v-if="guide">
      <div class="case-state"><div><span>{{ guide.case.code }}</span><h3>{{ guide.case.title }}</h3></div><p>{{ guide.recordCount }} 条模拟资料 · {{ guide.version?`最新第 ${guide.version} 版`:'尚无研判版本' }} · {{ guide.status }}</p></div>
      <p class="guide-notice">以下编号表示讲解顺序，不表示各环节已经完成。各业务页面会继续核对当前版本、权限和独立复核条件。</p>
      <div v-if="skipExample" class="skip-example"><p>已保存无需实验室的报告示例：第 {{ skipExample.snapshot.assessment_version }} 版<span v-if="skipExample.effective_status==='historical_snapshot'">（历史快照）</span>。它只说明当时的演示分析结果。</p><router-link class="step-action" :to="{path:'/app/risk-reports',query:{case_id:guide.case.id,assessment_id:skipExample.snapshot.assessment_id,report:skipExample.id}}">查看跳过验证的报告示例</router-link></div>
      <p v-if="reportNotice" class="guide-notice">{{ reportNotice }}</p>
      <ol class="walkthrough-steps"><li v-for="(step,index) in guide.steps" :key="step.key"><span class="step-number">{{ String(index+1).padStart(2,'0') }}</span><div class="step-copy"><div class="step-heading"><h3>{{ step.title }}</h3><span>{{ step.role }}</span></div><p>{{ step.description }}</p><small>{{ step.expectation }}</small></div><router-link :to="step.to" class="step-action" :aria-label="`演示步骤${index+1}：${step.title}`">打开{{ step.title }} <span aria-hidden="true">↗</span></router-link></li></ol>
      <aside class="lab-branch" aria-labelledby="optional-lab-title"><header><div><p class="eyebrow">可选分支</p><h3 id="optional-lab-title">实验室在什么情况下进入</h3></div><router-link :to="guide.laboratory" class="step-action">查看本事项可选验证</router-link></header><dl><div><dt>暂不验证 <span>无需任务</span></dt><dd>没有实际检测资料时，说明原因并保留证据缺口，继续人工演示研判与报告。</dd></div><div><dt>引用已有报告 <span>无需平台任务</span></dt><dd>有报告时接入并核对对象；本演示只能使用明确标注的模拟资料，回流后形成新版。</dd></div><div><dt>组织新的检测 <span>需要任务</span></dt><dd>实际工作需具备样品、原始测量及校准依据。当前演示不创建实际任务，保留准备条件说明。</dd></div></dl></aside>
      <div class="acceptance-boundary"><h3>软件流程与实际检测分别验收</h3><p>演示复核和隔离软件测试不代表产品合格、实际检测完成或真实模型推理成功。实物样品、原始测量、历史校准和适用标准仍待真实资料核验。</p><p v-if="guide.missing.length">当前研判记录的缺口：{{ guide.missing.join('；') }}</p><details><summary>怎样重复演示</summary><p>按六步打开既有记录，使用页面顶部“返回演示导览”继续下一步。需要展示编辑与复核时，在原事项手动创建新版；编写人与复核人使用两个不同专家账号。刷新或再次打开不会重置案例，也不会自动代替人工复核。</p></details></div>
    </template>
  </section>
</template>
<style scoped>
.demo-walkthrough{--guide-ink:#17324b;display:grid;gap:22px;margin-top:24px;padding:28px;border:1px solid #d8e4ef;border-radius:16px;background:var(--el-bg-color);color:var(--guide-ink);min-width:0;overflow-wrap:anywhere;}
.walkthrough-heading,.lab-branch header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;}.walkthrough-heading>div{flex:1 1 540px;}.walkthrough-heading h2{margin:8px 0 12px;font-size:23px;line-height:1.45;}.walkthrough-heading p,.acceptance-boundary p{margin:0;line-height:1.8;color:var(--el-text-color-regular);}.eyebrow{font-size:12px;letter-spacing:.08em;color:#367088!important;margin:0;}
.case-state{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:18px 20px;background:#edf5fa;border-left:3px solid #1a7697;border-radius:4px;}.case-state span{font-size:12px;color:#41647b;}.case-state h3{margin:5px 0 0;font-size:18px;}.case-state p,.guide-notice{margin:0;font-size:13px;line-height:1.7;color:#496174;}
.skip-example{display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap;}.skip-example p{flex:1 1 380px;font-size:13px;line-height:1.8;margin:0;}
.walkthrough-steps{padding:0;margin:0;list-style:none;}.walkthrough-steps li{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:18px;align-items:center;padding:22px 0;border-top:1px solid var(--el-border-color-lighter);}.step-number{align-self:start;font-size:23px;font-variant-numeric:tabular-nums;color:#7d96ab;}.step-heading{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;}.step-heading h3{margin:0;font-size:18px;}.step-heading>span{font-size:12px;color:#587084;}.step-copy p{margin:8px 0;line-height:1.7;font-size:14px;}.step-copy small{font-size:12px;color:var(--el-text-color-secondary);line-height:1.7;}.step-action{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:8px 14px;border:1px solid #b3ccd9;border-radius:6px;color:#165e7c;text-decoration:none;font-size:13px;justify-content:center;}.step-action:hover{background:#edf6fa;}.step-action:focus-visible,summary:focus-visible{outline:2px solid #1a7697;outline-offset:3px;}
.lab-branch{padding:22px;background:#fbf7ee;border:1px solid #eadfca;border-radius:10px;}.lab-branch h3{margin:7px 0 0;font-size:18px;}.lab-branch dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;margin:22px 0 0;}.lab-branch dt{font-size:15px;font-weight:600;}.lab-branch dt span{display:block;margin-top:6px;font-size:12px;font-weight:400;color:#79684c;}.lab-branch dd{margin:10px 0 0;font-size:13px;line-height:1.8;color:#635944;}
.acceptance-boundary{display:grid;gap:10px;border-top:1px solid var(--el-border-color-lighter);padding-top:20px;}.acceptance-boundary h3{margin:0;font-size:16px;}.acceptance-boundary p{font-size:13px;}.acceptance-boundary summary{cursor:pointer;font-size:13px;min-height:44px;display:list-item;align-content:center;}
@media(max-width:700px){.demo-walkthrough{padding:18px 14px;gap:18px;}.walkthrough-heading h2{font-size:20px;}.walkthrough-steps li{grid-template-columns:30px minmax(0,1fr);gap:12px;}.step-action{max-width:100%;}.walkthrough-steps .step-action{grid-column:2;justify-self:start;}.lab-branch{padding:18px;}.lab-branch dl{grid-template-columns:1fr;gap:20px;}}
</style>
