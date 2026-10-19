"""Read existing demo progress; never seed, review, create a task or call a model."""
import json
from urllib.parse import urlencode
from verify import RUNTIME,envelope


def main():
    runtime=envelope('/runtime-context')
    assert runtime['execution_mode']=='demo' and runtime['organization_slug']=='piap-quality-demo'
    code=runtime['case_code'];assert code
    config=json.loads((RUNTIME/'accounts.json').read_text(encoding='utf-8'))
    assert config['organization']==runtime['organization_slug']
    sessions=[]
    for username in ('demo_analyst','demo_reviewer'):
        account=next(a for a in config['accounts'] if a['username']==username)
        login=envelope('/auth/token',org=config['organization'],body={'username':username,'password':account['password']})
        me=envelope('/users/me',token=login['access_token']);assert me['role']=='expert' and me['is_active']
        sessions.append(login)
    assert sessions[0]['user_id']!=sessions[1]['user_id']
    token=sessions[0]['access_token'];case=None;page=1
    while case is None:
        result=envelope('/risk-cases?'+urlencode({'keyword':code,'page':page,'size':100}),token=token)
        case=next((c for c in result['items'] if c['code']==code),None)
        if case is not None or page*100>=result['total']:break
        page+=1
    assert case is not None,'请先初始化服务端指定的演示案例'
    before=envelope(f"/risk-cases/{case['id']}/workspace",token=token)
    assert not before['unavailable_source_ids']
    assert {r['data_nature'] for r in before['records']} <= {'synthetic'}
    assert {r['id'] for r in before['records']}==set(case['source_record_ids'])
    assert before['workflow_context']['execution_mode']=='demo'
    reports=envelope('/risk-reports?'+urlencode({'case_id':case['id']}),token=token)
    skip_versions=[]
    for report in reports:
        snapshot=envelope('/risk-reports/'+report['id'],token=token)['snapshot']
        if any(l['mode']=='skip' and l['assessment_id']==snapshot['assessment_id'] for l in snapshot.get('laboratory',[])):
            skip_versions.append(snapshot['assessment_version'])
    after=envelope(f"/risk-cases/{case['id']}/workspace",token=token)
    assert before['case']==after['case'] and before['assessment_versions']==after['assessment_versions']
    assert not envelope('/tasks?page=1&size=1',token=token)['total']
    assert not envelope('/sampling-plans?page=1&size=1',token=token)['total']
    latest=before['latest_assessment']
    result={'passed':True,'mode':'read existing local demo data','case_code':code,'source_records':len(before['records']),
        'assessment_versions':len(before['assessment_versions']),'latest_assessment_version':latest['version'] if latest else None,
        'latest_status':latest['status'] if latest else None,'report_count':len(reports),'saved_skip_validation_report_versions':sorted(set(skip_versions)),
        'independent_expert_accounts':True,'case_and_versions_unchanged':True,'all_case_records_synthetic':True,
        'tasks_or_formal_plans_created':False,'real_model_or_equipment_called':False}
    (RUNTIME/'walkthrough-api-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
