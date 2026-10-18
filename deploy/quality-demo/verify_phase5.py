"""Repeatable real local phase-five permissions, snapshots and idempotency."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from verify import RUNTIME,envelope,request


def main():
    config=json.loads((RUNTIME/"accounts.json").read_text(encoding="utf-8"))
    browser=json.loads((RUNTIME/"phase5-browser-acceptance.json").read_text(encoding="utf-8"))
    tokens={}
    for name in ("demo_analyst","demo_reviewer","demo_admin"):
        account=next(a for a in config["accounts"] if a["username"]==name)
        tokens[name]=envelope('/auth/token',org=config['organization'],body={'username':name,'password':account['password']})['access_token']
    author,peer,admin=tokens.values()
    case=browser['case_id'];before=envelope(f'/risk-cases/{case}/workspace',token=author)
    assessment=before['latest_assessment'];assert assessment['version']==6 and assessment['status']=='demo_reviewed'
    assert assessment['probability'] is None and assessment['model_versions']['llm_called'] is False
    assert len(before['records'])==16 and len(before['assessment_versions'])==6
    assert all(r['data_nature']=='synthetic' for r in before['records'])
    assert request('/knowledge/source-preview',token=author,body={'kind':'intake_record','id':browser['returned_record_id']})[0]==422
    report=envelope('/risk-reports/'+browser['new_report_id'],token=author)
    old=envelope('/risk-reports/'+browser['skip_report_id'],token=author)
    assert old['effective_status']=='historical_snapshot' and report['effective_status']=='demo_frozen'
    assert len(old['snapshot']['records'])==15 and len(report['snapshot']['records'])==16
    assert old['snapshot']['laboratory'][0]['mode']=='skip' and report['snapshot']['laboratory'][0]['mode']=='verify'
    assert not any('私聊' in str(s.get('snapshot',{}).get('opinions',[])) for s in report['snapshot']['sampling'])
    assert any(s['effective_status']=='needs_reassessment' for s in report['snapshot']['sampling'])
    progress=json.loads((RUNTIME/'phase5-browser-progress.json').read_text(encoding='utf-8'))
    if progress.get('followthrough_completed'):
        assert any(s['snapshot']['assessment_id']==assessment['id'] and s['effective_status']=='demo_confirmed' for s in report['snapshot']['sampling'])
    body={'assessment_id':assessment['id'],'expected_basis_hash':assessment['demo_validation']['basis_hash']}
    def repeat(_):return envelope(f'/risk-cases/{case}/reports',token=author,body=body)
    with ThreadPoolExecutor(max_workers=2) as pool:repeated=list(pool.map(repeat,range(2)))
    assert all(r['id']==report['id'] and r['reused'] for r in repeated)
    report_count=len(envelope('/risk-reports?case_id='+case,token=author))
    assert report_count==(3 if progress.get('followthrough_completed') else 2)
    lab=envelope(f'/risk-cases/{case}/laboratory-verifications',token=author)[0]
    assert lab['id']==browser['lab_id'] and lab['task_id'] is None and lab['status']=='demo_returned'
    evidence={'expected_revision':1,'record_ids':lab['record_ids'],'note':lab['return_note']}
    before_events=lab['events']
    def return_again(_):return envelope('/risk-laboratory-verifications/'+lab['id']+'/evidence',token=author,body=evidence)
    with ThreadPoolExecutor(max_workers=2) as pool:returned=list(pool.map(return_again,range(2)))
    assert all(r['id']==lab['id'] and r['reused'] and r['events']==before_events for r in returned)
    assert request('/risk-laboratory-verifications/'+lab['id']+'/evidence',token=author,body={**evidence,'note':'不可覆盖已回流记录'})[0]==409
    assert request('/risk-reports/'+report['id'],token=admin)[0]==403
    assert request('/risk-reports',token=admin)[0]==403
    assert request(f'/risk-cases/{case}/laboratory-verifications',token=admin)[0]==403
    assert request(f'/risk-cases/{case}/reports',token=author,body={**body,'expected_basis_hash':'0'*64})[0]==409
    assert request(f'/risk-cases/{case}/reports',token=author,body={**body,'assessment_id':browser['base_assessment_id']})[0]==409
    assert request(f'/risk-cases/{case}/laboratory-verifications',token=author,body={**body,'mode':'verify','purpose':'测试不存在的任务','task_id':str(uuid4())})[0]==404
    assert request(f'/risk-cases/{case}/reports',token=author,body={**body,'task_id':str(uuid4())})[0]==422
    assert request('/exports',token=author,body={'report_name':'不能传入客户端快照','report_type':'risk_assessment','format':'pdf','config_json':{'risk_report_id':report['id'],'report_snapshot':{}}})[0]==422
    for format in ['pdf','docx']:
        job=envelope('/risk-reports/'+report['id']+'/exports',token=author,body={'format':format})
        again=envelope('/risk-reports/'+report['id']+'/exports',token=author,body={'format':format})
        assert job['id']==again['id'] and job['status']=='success'
        config_job=json.loads(job['config_json']);assert 'task_id' not in config_job
        assert config_job['snapshot_hash']==report['snapshot_hash']
        assert request('/exports/'+job['id']+'/download',token=peer)[0]==403
        assert request('/exports/'+job['id']+'/download',token=admin)[0]==403
        file_path=job['file_url'].removeprefix('/api/v1')
        assert request(file_path,token=peer)[0]==403
        assert request(file_path)[0] in [401,403]
        assert request('/exports/'+job['id']+'/download',token=author)[0]==200
    assert envelope('/exports?report_type=risk_assessment',token=peer)['total']==0
    assert envelope('/tasks?page=1&size=20',token=author)['total']==0
    assert envelope('/sampling-plans',token=author)['total']==0
    assert not envelope('/quality-supervision/sampling-candidates',token=author)['items']
    after=envelope(f'/risk-cases/{case}/workspace',token=author)
    assert before['case']==after['case'] and before['assessment_versions']==after['assessment_versions']
    assert report['snapshot']==envelope('/risk-reports/'+report['id'],token=peer)['snapshot']
    result={'stage':5,'passed':True,'api_mode':'real_local_mysql','case_id':case,'current_assessment_version':6,'case_sources':16,
        'report_count':report_count,'concurrent_report_creation_reused':True,'concurrent_return_reused':True,'frozen_snapshot_unchanged':True,
        'report_and_file_scope_enforced':True,'synthetic_knowledge_blocked':True,'wrong_version_context_task_rejected':True,'no_task_created':True,
        'formal_plans_and_candidates_empty':True,'real_model_called':False}
    (RUNTIME/'phase5-api-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
