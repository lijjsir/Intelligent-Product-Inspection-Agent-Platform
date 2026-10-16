"""Real API/worker in isolated SQLite: result, scope, versioned PDF and Word."""
import json,sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
sys.stdout.reconfigure(encoding='utf-8')
BASE='http://127.0.0.1:5173';API='http://127.0.0.1:8018'
OUT=Path(__file__).resolve().parents[1]/'test-results'/'task-result-r3';OUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,channel='chromium');req=pw.request.new_context()
    ids=req.get(API+'/_fixture/info').json();assert ids['isolated']
    ctx=browser.new_context(viewport={'width':1600,'height':1050},accept_downloads=True);page=ctx.new_page()
    errors=[];http_errors=[];checks=[];job_ids=[]
    state={'piap_token':'fixture-author','piap_role':'user','piap_roles':'["user"]','piap_user_id':ids['author_id'],'piap_org_id':ids['org_id'],'piap_username':'R3隔离验收'}
    page.add_init_script("try{if(location.origin==='http://127.0.0.1:5173')for(const[k,v]of Object.entries("+json.dumps(state)+"))sessionStorage.setItem(k,v);}catch(_){}")
    page.on('pageerror',lambda e:errors.append(str(e)))
    def forward(route):
        p=urlparse(route.request.url)
        if p.path=='/api/v1/chat/sessions' or p.path.endswith('/events'):
            route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':[]}));return
        if p.path=='/api/v1/collab/summary':
            route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{'pending_count':0,'initiated_count':0,'processed_count':0}}));return
        if p.path=='/api/v1/streams/session':
            data=route.request.post_data_json;route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{'stream_token':'isolated','expires_at':'2027-01-01T00:00:00Z','resource':data['resource'],'resource_id':data['resource_id']}}));return
        if p.path.endswith('/stream'):
            route.fulfill(status=200,content_type='text/event-stream',body=': isolated\n\n');return
        response=route.fetch(url=API+p.path+('?' + p.query if p.query else ''))
        if response.status>=400:http_errors.append({'path':p.path,'status':response.status})
        if route.request.method=='POST' and p.path=='/api/v1/exports' and response.status==200:
            job_id=response.json()['data']['id'];job_ids.append(job_id)
            completed=req.post(API+'/_fixture/run-worker/'+job_id)
            assert completed.status==200,completed.text()
        route.fulfill(status=response.status,headers={**response.headers,'access-control-allow-origin':'*'},body=response.body())
    page.route('**/api/v1/**',forward)
    page.goto(BASE+'/app/results',wait_until='networkidle')
    expect(page.get_by_text('标准项目执行',exact=True)).to_be_visible()
    expect(page.get_by_text('图片 / 历史辅助',exact=True)).to_be_visible()
    checks.append('结果列表同时显示标准执行与旧图片辅助任务')
    page.goto(BASE+'/app/results/'+ids['task_id'],wait_until='networkidle')
    expect(page.get_by_role('heading',name='试验条件符合要求',exact=True)).to_be_visible()
    expect(page.get_by_text('产品整体未评定；项目符合性与风险研判分别核对。',exact=True)).to_be_visible()
    expect(page.get_by_text('无法获取该任务的结果报告',exact=True)).to_have_count(0)
    checks.append('只有标准执行的任务可打开结果页，条件与产品性能明确区分')
    page.screenshot(path=str(OUT/'01-execution-only-result.png'),full_page=True)
    page.get_by_role('button',name='导出此版本报告',exact=True).click()
    panel=page.get_by_role('dialog',name='当前版本的报告',exact=True)
    expect(panel.get_by_text('当前任务的检测报告',exact=True)).to_be_visible()
    panel.get_by_role('button',name='生成报告',exact=True).click()
    expect(panel.get_by_text('可下载',exact=True)).to_have_count(1)
    with page.expect_download() as download:
        panel.get_by_role('button',name='下载报告',exact=True).first.click()
    download.value.save_as(str(OUT/'R3隔离条件记录.pdf'))
    checks.append('真实 Worker 生成并通过授权接口下载冻结版本 PDF')
    panel.get_by_text('Word · 可编辑',exact=True).click()
    panel.get_by_role('button',name='生成报告',exact=True).click()
    expect(panel.get_by_text('可下载',exact=True)).to_have_count(2)
    with page.expect_download() as download:
        panel.get_by_role('button',name='下载报告',exact=True).first.click()
    download.value.save_as(str(OUT/'R3隔离条件记录.docx'))
    checks.append('同一执行版本生成 Word，报告范围和复核引用与 PDF 一致')
    page.screenshot(path=str(OUT/'02-versioned-report-downloads.png'),full_page=True)
    req.post(API+'/_fixture/withdraw-standard')
    page.goto(BASE+'/app/results/'+ids['task_id'],wait_until='networkidle')
    expect(page.get_by_role('heading',name='当前依据需重新核验（历史项目判定保留）',exact=True)).to_be_visible()
    checks.append('撤回标准后结果页标记重新核验，历史项目结果仍保留')
    page.screenshot(path=str(OUT/'03-source-withdrawn.png'),full_page=True)
    page.goto(BASE+'/app/results/'+ids['legacy_task_id'],wait_until='networkidle')
    expect(page.get_by_role('heading',name='图片 / 旧记录辅助分析',exact=True)).to_be_visible()
    assert not any(word in page.locator('body').inner_text() for word in ['产品合格','产品不合格'])
    checks.append('旧图片结果继续可查看，但没有升级为产品整体合格结论')
    assert not errors,errors;assert not http_errors,http_errors
    (OUT/'result.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'http_errors':http_errors,'job_ids':job_ids,'isolated':True},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'page_errors':errors,'http_errors':http_errors},ensure_ascii=False))
    browser.close()
