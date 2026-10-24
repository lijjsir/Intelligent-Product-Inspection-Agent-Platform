"""Isolated UI requests exercise queue restore, polling outages and warnings."""
import copy,json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import expect,sync_playwright
OUT=Path(__file__).resolve().parents[1]/'test-results/risk-analysis-background'
OUT.mkdir(parents=True,exist_ok=True)
state={'job':None,'draft':None,'posts':[],'release':False,'offline':False,'warning':False}
stamp='2026-10-23T08:00:00Z';errors=[]
case={'id':'case-fixture','code':'RISK-001','title':'后台研判页面隔离验收','scope_type':'category','scope':{'name':'电动自行车'},
    'status':'collecting','source_record_ids':[],'evidence_ids':[],'created_by':'user-fixture','created_at':stamp,'updated_at':stamp}


def reply(route,data,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps({'code':'ok' if status==200 else 'unavailable','message':'进度暂不可用' if status!=200 else '', 'data':data}))
def handle(route):
    req=route.request;path=urlparse(req.url).path.removeprefix('/api/v1/')
    if req.method=='POST':
        assert path=='risk-cases/case-fixture/analysis-jobs',path
        body=req.post_data_json;state['posts'].append(body)
        assert body['base_assessment_id']==(state['draft']['id'] if state['draft'] else None)
        state['release']=False
        state['job']={'id':'job-'+str(len(state['posts'])),'case_id':case['id'],'created_by':'expert-fixture','status':'queued','assessment_id':None,'error_code':None,
            'message':'请求已保存，等待后台分析','created_at':stamp,'started_at':None,'finished_at':None}
        reply(route,state['job']);return
    if path=='users/me':reply(route,{'id':'expert-fixture','org_id':'org-fixture','username':'expert','role':'expert','is_active':True,'effective_permissions':['quality','quality_material_read_business']});return
    if path=='runtime-context':reply(route,{'execution_mode':'business','label':'业务环境'});return
    if path=='risk-cases':reply(route,{'items':[case],'total':1,'page':1,'size':20});return
    if path.endswith('/analysis-jobs/latest'):reply(route,state['job']);return
    if '/analysis-jobs/' in path:
        if state['offline']:reply(route,None,503);return
        job=state['job'];job['status']='running';job['message']='正在分析原始证据，可离开页面'
        if state['release']:
            job['status']='completed_with_warnings' if state['warning'] else 'succeeded'
            job['message']='模型服务限流；已保存待人工核对草稿，可稍后重新分析' if state['warning'] else '研判草稿已保存，仍须独立专业复核'
            job['assessment_id']='assessment-'+str(len(state['posts']))
            state['draft']={'id':job['assessment_id'],'risk_case_id':case['id'],'version':len(state['posts']),'risk_level':'unknown' if state['warning'] else 'medium',
                'scope':case['scope'],'risk_type':None,'evidence_ids':[],'standard_matches':[],'conflicts':[],'missing_inputs':[],'possible_causes':[],'recommendations':[],
                'trust_status':'needs_review','status':'awaiting_evidence' if state['warning'] else 'awaiting_review','submitted_by':'expert-fixture','reviewed_by':None}
        reply(route,job);return
    if path.endswith('/workspace'):reply(route,{'case':case,'records':[],'unavailable_source_ids':[],'latest_assessment':state['draft'],'assessment_versions':[state['draft']] if state['draft'] else [],'workflow_context':None});return
    if path=='risk-policies':reply(route,[]);return
    if path.startswith('streams/'):reply(route,{});return
    reply(route,[])


with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000})
    auth={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'expert-fixture','piap_org_id':'org-fixture','piap_username':'expert'}
    context.add_init_script('for(const[k,v]of Object.entries('+json.dumps(auth)+'))sessionStorage.setItem(k,v)')
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.route('**/api/v1/**',handle)
    page.goto('http://127.0.0.1:5173/app/risk-assessments?case_id=case-fixture',wait_until='networkidle')
    button=page.get_by_role('button',name='生成风险研判草稿',exact=True);expect(button).to_be_enabled();button.click()
    expect(page.locator('.analysis-job-status')).to_contain_text('排队中');expect(button).to_be_disabled()
    page.reload(wait_until='networkidle');expect(page.locator('.analysis-job-status')).to_contain_text('排队中');expect(button).to_be_disabled();assert len(state['posts'])==1
    state['offline']=True
    expect(page.locator('.case-detail')).to_contain_text('进度暂不可用',timeout=10000);expect(button).to_be_disabled()
    state['offline']=False;state['release']=True;page.get_by_role('button',name='刷新任务进度',exact=True).click()
    expect(page.locator('.analysis-job-status')).to_contain_text('草稿已生成',timeout=15000);expect(button).to_be_enabled()
    assert len(state['posts'])==1
    state['warning']=True;button.click();state['release']=True
    expect(page.locator('.analysis-job-status')).to_contain_text('草稿需人工核对',timeout=15000)
    expect(page.locator('.analysis-job-status')).to_contain_text('限流')
    expect(button).to_be_enabled()
    assert state['posts'][0]['request_key']!=state['posts'][1]['request_key']
    page.screenshot(path=str(OUT/'background-warning.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=0")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(OUT/'background-warning-mobile.png'),full_page=True)
    assert not errors,errors
    (OUT/'checks.json').write_text(json.dumps({'passed':True,'mode':'isolated API fixtures','posts':len(state['posts']),'reviews_submitted':0,'page_errors':errors},indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'posts':len(state['posts']),'page_errors':errors}))
    context.close();browser.close()
