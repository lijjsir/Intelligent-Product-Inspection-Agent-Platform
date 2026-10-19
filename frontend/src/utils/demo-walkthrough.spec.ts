import { describe,expect,it } from 'vitest';
import type { RiskWorkspace } from '@/types/quality-risk.types';
import { demoWalkthrough,skipValidationExample } from './demo-walkthrough';
import type { RiskReport } from '@/api/risk-completion.api';

function workspace():RiskWorkspace{return {
  case:{id:'case-a',code:'DEMO-QS-001',title:'模拟案例',scope_type:'product',scope:{product_id:'product-a'},status:'demo_reviewed',
    source_record_ids:['record-a'],evidence_ids:[],created_by:'author',created_at:'',updated_at:''},
  records:[{id:'record-a',record_type:'consumer_complaint',data_nature:'synthetic'} as RiskWorkspace['records'][number]],
  unavailable_source_ids:[],workflow_context:{enabled:true,execution_mode:'demo',can_author:true,eligible:false,assessment_id:'assessment-a',basis_hash:'fixture',blockers:[],boundary:'模拟'},
  latest_assessment:{id:'assessment-a',risk_case_id:'case-a',version:7,status:'demo_reviewed',risk_level:'unknown',scope:{product_id:'product-a'},
    evidence_ids:[],standard_matches:[],conflicts:[],possible_causes:[],recommendations:[],trust_status:'demo_reviewed',
    missing_inputs:['缺少实际测量'],demo_validation:{is_current:true,blockers:[],boundary:'模拟',basis_hash:'fixture'}},
  assessment_versions:[{id:'assessment-a',version:7,status:'demo_reviewed',risk_level:'unknown'}],
};}

describe('demo case walkthrough identity and limits',()=>{
  it('uses the saved case and version without implying completion or creating business actions',()=>{
    const result=demoWalkthrough(workspace(),'DEMO-QS-001');
    expect(result.version).toBe(7);expect(result.recordCount).toBe(1);
    expect(result.steps.map(s=>s.key)).toEqual(['intake','monitor','assessment','collaboration','sampling','report']);
    expect(result.steps[0]!.to.query).toEqual({record:'record-a',product_id:'product-a'});
    expect(result.steps[2]!.to.query).toEqual({case_id:'case-a',assessment_id:'assessment-a'});
    expect(result.laboratory.query).toEqual({case_id:'case-a',assessment_id:'assessment-a',tab:'laboratory'});
    expect(JSON.stringify(result.steps)).not.toMatch(/create|completed|task_id/);
  });
  it.each(['wrong_code','business','unavailable','observed','duplicate','wrong_version'])('rejects %s rather than opening an unrelated record',problem=>{
    const value=workspace();
    if(problem==='wrong_code')value.case.code='ANOTHER';
    if(problem==='business')value.workflow_context!.execution_mode='business';
    if(problem==='unavailable')value.unavailable_source_ids=['record-x'];
    if(problem==='observed')value.records[0]!.data_nature='observed';
    if(problem==='duplicate')value.records.push(value.records[0]!);
    if(problem==='wrong_version')value.latest_assessment!.risk_case_id='another-case';
    expect(()=>demoWalkthrough(value,'DEMO-QS-001')).toThrow();
  });
  it('preserves missing evidence and never fabricates an assessment version',()=>{
    const value=workspace();value.latest_assessment=null;value.assessment_versions=[];
    const result=demoWalkthrough(value,'DEMO-QS-001');
    expect(result.version).toBeNull();expect(result.status).toBe('尚无研判版本');
    expect(result.steps[2]!.to.query).toEqual({case_id:'case-a'});
  });
  it('shows reassessment when a saved review no longer matches current evidence',()=>{
    const value=workspace();value.latest_assessment!.demo_validation!.is_current=false;
    const result=demoWalkthrough(value,'DEMO-QS-001');
    expect(result.status).toBe('资料变化，需重评');expect(result.missing).toEqual(['缺少实际测量']);
  });
  it('selects only a matching demo snapshot that skipped validation for its own assessment',()=>{
    const report={id:'saved',effective_status:'historical_snapshot',snapshot:{case_id:'case-a',assessment_id:'a5',assessment_version:5,
      execution_mode:'demo',laboratory:[{mode:'skip',assessment_id:'a5'}]}} as RiskReport;
    const unrelated={...report,id:'unrelated',snapshot:{...report.snapshot,case_id:'other'}};
    const mixed={...report,id:'mixed',snapshot:{...report.snapshot,assessment_id:'a6',assessment_version:6}};
    const business={...report,id:'business',snapshot:{...report.snapshot,execution_mode:'business' as const}};
    expect(skipValidationExample('case-a',[business,unrelated,mixed,report])?.id).toBe('saved');
    expect(skipValidationExample('case-a',[business,unrelated,mixed])).toBeNull();
  });
});
