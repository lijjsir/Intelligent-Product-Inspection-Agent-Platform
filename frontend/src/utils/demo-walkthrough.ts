import type { RiskWorkspace } from '@/types/quality-risk.types';
import type { RiskReport } from '@/api/risk-completion.api';

export function skipValidationExample(caseId:string,reports:RiskReport[]){
  return reports.filter(r=>r.snapshot.case_id===caseId&&r.snapshot.execution_mode==='demo'&&
    ['demo_frozen','historical_snapshot'].includes(r.effective_status)&&
    r.snapshot.laboratory?.some(l=>l.mode==='skip'&&l.assessment_id===r.snapshot.assessment_id))
    .sort((a,b)=>b.snapshot.assessment_version-a.snapshot.assessment_version)[0]||null;
}

export function demoWalkthrough(workspace: RiskWorkspace, code: string) {
  const context=workspace.workflow_context||workspace.demo_context;
  if(!code||workspace.case.code!==code||!context?.enabled||context.execution_mode!=='demo')
    throw new Error('来源事项与服务端指定的演示案例不一致，请检查演示初始化。');
  const ids=new Set(workspace.case.source_record_ids);
  const records=workspace.records;
  if(workspace.unavailable_source_ids.length||records.length!==ids.size||new Set(records.map(r=>r.id)).size!==ids.size||
    records.some(r=>!ids.has(r.id)||r.data_nature!=='synthetic'))
    throw new Error('案例资料缺失、不可访问或未标记为模拟，请先核对资料来源。');
  const assessment=workspace.latest_assessment;
  if(assessment&&(assessment.risk_case_id!==workspace.case.id||!workspace.assessment_versions.some(v=>v.id===assessment.id)))
    throw new Error('研判版本不属于当前演示事项，请重新加载。');
  const caseQuery={case_id:workspace.case.id};
  const versionQuery={...caseQuery,...(assessment?{assessment_id:assessment.id}:{})};
  const record=records.find(r=>r.record_type==='consumer_complaint')||records[0];
  const labels:Record<string,string>={draft:'草稿',demo_draft:'演示草稿',demo_submitted:'演示待独立复核',demo_reviewed:'演示复核通过'};
  const status=assessment?assessment.demo_validation?.is_current===false?'资料变化，需重评':labels[assessment.status]||'待核对状态':'尚无研判版本';
  return {case:workspace.case,version:assessment?.version||null,status,recordCount:records.length,
    missing:assessment?.demo_workflow?.content.missing_inputs||assessment?.missing_inputs||[],
    steps:[
      {key:'intake',title:'数据接入',role:'编写专家',description:'查看模拟投诉、舆情和资料原文，核对同一产品、企业、时间和出处。',expectation:'同一材料保持同一记录；未知信息留空。',
        to:{path:'/app/quality-data',query:{...(record?{record:record.id}:{}),...(workspace.case.scope.product_id?{product_id:String(workspace.case.scope.product_id)}:{})}}},
      {key:'monitor',title:'异常发现',role:'编写专家',description:'查看市场异常的统计窗口、增长规则和来源记录。',expectation:'数量线索提供研判入口，不直接等于风险结论。',to:{path:'/app/quality-analytics',query:{tab:'anomalies'}}},
      {key:'assessment',title:'风险研判',role:'编写专家 → 独立复核专家',description:'打开已保存版本，核对引用资料、证据缺口、限制和历史。',expectation:'需要操作时手动创建新版；另一位专家执行演示复核。',to:{path:'/app/risk-assessments',query:versionQuery}},
      {key:'collaboration',title:'协同复核',role:'受邀专家',description:'从事项查看关联版本的协同记录、公开意见及处理状态。',expectation:'协同固定来源版本；新证据仍需回到事项重评。',to:{path:'/app/risk-assessments',query:{...versionQuery,tab:'collaboration'}}},
      {key:'sampling',title:'抽查建议',role:'编写专家',description:'查看对象、核查方向、建议依据和适用限制。',expectation:'演示建议不进入正式抽查计划，不自动启动检测。',to:{path:'/app/risk-sampling',query:caseQuery}},
      {key:'report',title:'分析报告',role:'编写或复核专家',description:'查看已生成报告和历史快照；具备条件后可手动生成并导出。',expectation:'报告保留对象、证据、结论、限制、复核和建议。',to:{path:'/app/risk-reports',query:caseQuery}},
    ],laboratory:{path:'/app/risk-assessments',query:{...versionQuery,tab:'laboratory'}}};
}
