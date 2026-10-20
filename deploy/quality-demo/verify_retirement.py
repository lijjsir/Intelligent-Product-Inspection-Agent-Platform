"""Read-only retirement checks on the existing isolated local demo stack."""
import json
from urllib.parse import urlencode
from uuid import uuid4
from verify import envelope,request,RUNTIME


def main():
    runtime=envelope('/runtime-context');assert runtime['execution_mode']=='demo'
    config=json.loads((RUNTIME/'accounts.json').read_text(encoding='utf-8'))
    account=next(a for a in config['accounts'] if a['username']=='demo_analyst')
    login=envelope('/auth/token',org=config['organization'],body={'username':account['username'],'password':account['password']});token=login['access_token']
    cases=envelope('/risk-cases?'+urlencode({'keyword':runtime['case_code'],'size':100}),token=token)['items'];case=next(c for c in cases if c['code']==runtime['case_code'])
    before=envelope('/risk-cases/'+case['id']+'/workspace',token=token)
    reports=envelope('/risk-reports?case_id='+case['id'],token=token)
    hashes={r['id']:envelope('/risk-reports/'+r['id'],token=token)['snapshot_hash'] for r in reports}
    candidates=envelope('/risk-sampling/pages/candidates?case_id='+case['id'],token=token)['items']
    assert candidates and all(c['snapshot']['collaboration_id'] is None and c['snapshot']['schema']=='risk-sampling-assessment-v2' for c in candidates)
    assert request('/collab/action-requests',token=token,body={'target_type':'user','target_id':str(uuid4()),'title':'retired','description':'must not create'})[0]==422
    assert request('/risk-cases/'+case['id']+'/collaborations',token=token,body={'assessment_id':before['latest_assessment']['id'],
        'expected_basis_hash':before['workflow_context']['basis_hash'],'request_key':str(uuid4()),'coordinator_id':str(uuid4()),'purpose':'retired'})[0]==422
    assert request('/meetings/memories/retired-probe/share-requests',token=token,body={'target_scope_type':'user','target_scope_id':str(uuid4()),'idempotency_key':str(uuid4())})[0]==422
    after=envelope('/risk-cases/'+case['id']+'/workspace',token=token)
    assert before['case']==after['case'] and before['assessment_versions']==after['assessment_versions']
    for rid,checksum in hashes.items():assert envelope('/risk-reports/'+rid,token=token)['snapshot_hash']==checksum
    assert len(envelope('/risk-reports?case_id='+case['id'],token=token))==len(hashes)
    result={'passed':True,'mode':'real local demo APIs, no business mutations','new_candidates_independent_of_collaboration':True,
        'request_creation_risk_collaboration_and_personal_sharing_rejected':True,'existing_report_hashes_unchanged':True,
        'case_sources':len(after['records']),'assessment_versions':len(after['assessment_versions']),'reports':len(hashes),'real_model_called':False}
    (RUNTIME/'collab-retirement-live-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
