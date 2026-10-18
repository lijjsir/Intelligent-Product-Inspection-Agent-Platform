"""Read-only checks for the new pages against the isolated local demo API."""
import json
from verify import request,envelope,RUNTIME

CASE='90daba62-f80d-55b5-9d25-f05d0c0ffdfe'


def pages(path,token):
    items=[];cursor=None
    for _ in range(100):
        data=envelope(path+('&' if '?' in path else '?')+('cursor='+cursor if cursor else ''),token=token)
        items.extend(data['items']);cursor=data['next_cursor']
        if not cursor:return items
    raise AssertionError('Pagination did not finish')


def main():
    assert envelope('/runtime-context')['execution_mode']=='demo'
    config=json.loads((RUNTIME/'accounts.json').read_text(encoding='utf-8'));tokens={}
    for account in config['accounts']:
        tokens[account['username']]=envelope('/auth/token',org=config['organization'],body={
            'username':account['username'],'password':account['password']})['access_token']
    author,reviewer=tokens['demo_analyst'],tokens['demo_reviewer']
    before=envelope(f'/risk-cases/{CASE}/workspace',token=author)
    report_ids={row['id'] for row in pages('/risk-report-pages?case_id='+CASE,author)}
    summary_counts={}
    for label,token in [('author',author),('reviewer',reviewer)]:
        for kind in ('suggestions','candidates'):
            data=pages(f'/risk-sampling/pages/{kind}?case_id={CASE}',token)
            summary_counts[label+'_'+kind]=len(data)
            if kind=='suggestions':
                old=envelope('/risk-sampling/suggestions?case_id='+CASE,token=token)
                assert {row['id'] for row in data}=={row['id'] for row in old}
        links=pages(f'/risk-cases/{CASE}/collaboration-pages?',token)
        old=envelope(f'/risk-cases/{CASE}/collaborations',token=token)
        assert {row['id'] for row in links}=={row['id'] for row in old}
        for view in ('pending','initiated','processed'):
            items=pages('/collab/work-item-pages?view='+view,token)
            assert len(items)==len({row['id'] for row in items})
            for row in items:
                kind,rid=row['id'].split(':',1)
                assert envelope(f'/collab/work-item-detail/{kind}/{rid}',token=token)['id']==row['id']
        option=envelope('/risk-collaborations/participant-pages?keyword=demo',token=token)
        assert option['items']
        envelope('/collab/target-pages/user?keyword=demo',token=token)
        envelope('/collab/target-pages/meeting_room',token=token)
        assert envelope('/quality-supervision/laboratory-summary',token=token)=={'collecting':0,'review':0,'signed':0,'online':0}
        assert not envelope('/quality-supervision/options/sessions',token=token)['items']
        assert request('/collab/work-item-pages?size=51',token=token)[0]==422
    assert request('/risk-sampling/pages/suggestions',token=tokens['demo_admin'])[0]==403
    after=envelope(f'/risk-cases/{CASE}/workspace',token=author)
    assert before['case']==after['case'] and before['assessment_versions']==after['assessment_versions']
    assert len(after['records'])==16 and len(after['assessment_versions'])==6 and len(report_ids)==3
    assert not envelope('/tasks?page=1&size=20',token=author)['items']
    assert not envelope('/sampling-plans',token=author)['items']
    result={'passed':True,'mode':'read-only real local demo MySQL APIs','new_pages_match_legacy_case_records':True,
        'mixed_work_item_pages_and_direct_access':True,'native_reference_auth_and_limits':True,'role_boundaries':True,
        'case_sources':16,'assessment_versions':6,'reports':3,'no_business_rows_created':True,'real_model_called':False,
        'summary_counts':summary_counts}
    (RUNTIME/'remaining-live-api.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
