"""R1 UI acceptance against the real disposable execution services."""
import json,sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
sys.stdout.reconfigure(encoding='utf-8')
BASE='http://127.0.0.1:5173';API='http://127.0.0.1:8016'
OUT=Path(__file__).resolve().parents[1]/'test-results'/'execution-evidence-r1';OUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,channel='chromium')
    req=pw.request.new_context();ids=req.get(API+'/_fixture/info').json();assert ids['isolated']
    context=browser.new_context(viewport={'width':1600,'height':1050});page=context.new_page();errors=[];checks=[]
    state={'piap_token':'fixture-expert','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':ids['expert_id'],
        'piap_org_id':ids['org_id'],'piap_username':'隔离复核专家'}
    page.add_init_script("try{if(location.origin==='http://127.0.0.1:5173'){for(const[k,v]of Object.entries("+json.dumps(state)+"))sessionStorage.setItem(k,v);}}catch(_){}")
    page.on('pageerror',lambda error:errors.append(str(error)))
    def forward(route):
        parsed=urlparse(route.request.url)
        if parsed.path.endswith('/events'):route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':[]}));return
        if parsed.path=='/api/v1/streams/session':
            data=route.request.post_data_json;route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{
                'stream_token':'isolated-no-events','expires_at':'2027-01-01T00:00:00Z','resource':data['resource'],'resource_id':data['resource_id']}}));return
        if parsed.path.endswith('/stream'):route.fulfill(status=200,content_type='text/event-stream',body='retry: 60000\n\n: isolated\n\n');return
        response=route.fetch(url=API+parsed.path+('?' + parsed.query if parsed.query else ''))
        route.fulfill(status=response.status,headers={**response.headers,'access-control-allow-origin':'*'},body=response.body())
    page.route('**/api/v1/**',forward)
    page.goto(BASE+'/app/tasks/'+ids['task_id'],wait_until='networkidle')
    expect(page.get_by_role('heading',name='标准要求执行与独立复核',exact=True)).to_be_visible()
    # Latest duplicate run is genuinely incomplete, so acceptance is unavailable.
    page.get_by_role('button',name='查看执行详情',exact=True).first.click()
    page.get_by_role('button',name='处理复核意见',exact=True).click()
    review=page.get_by_role('dialog',name='独立专业复核',exact=True)
    review.locator('.el-select').click()
    expect(page.get_by_role('option',name='确认选定项目结论',exact=True)).to_have_class(__import__('re').compile('.*is-disabled.*'))
    page.keyboard.press('Escape');review.get_by_role('button',name='取消',exact=True).click()
    page.locator('.el-drawer__close-btn').click()
    checks.append('重复证据不能满足两次观测；页面禁止确认')
    page.get_by_role('button',name='查看执行详情',exact=True).last.click()
    page.get_by_role('button',name='独立专业复核',exact=True).click()
    review=page.get_by_role('dialog',name='独立专业复核',exact=True)
    review.locator('.el-form-item').filter(has_text='复核说明').locator('textarea').fill('对照隔离原报告第三页核对速度、样品和方法')
    review.locator('.el-form-item').filter(has_text='复核依据').locator('textarea').fill('隔离报告第3页：最高车速30.8 km/h，方法7.1')
    review.locator('.el-checkbox').filter(has_text='涉及报告转录时').click()
    expect(review.get_by_role('button',name='确认并记录',exact=True)).to_be_disabled()
    checks.append('总开关和说明不能代替逐项核对')
    review.get_by_role('button',name='查看原件第 3 页',exact=True).click()
    expect(page.locator('iframe[title="检测报告原件"]')).to_be_visible()
    page.wait_for_timeout(1200)  # Wait for the dialog transition and native PDF renderer.
    frame=page.locator('iframe[title="检测报告原件"]')
    assert frame.evaluate("e => {const r=e.getBoundingClientRect(); return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===e;}")
    page.screenshot(path=str(OUT/'01-report-original.png'),full_page=True)
    page.get_by_role('dialog',name='fixture-report.pdf · 第 3 页',exact=True).locator('.el-dialog__headerbtn').click()
    review.locator('.el-checkbox').filter(has_text='已核对 最高车速').click()
    expect(review.get_by_role('button',name='确认并记录',exact=True)).to_be_enabled()
    review.get_by_role('button',name='确认并记录',exact=True).click();expect(review).not_to_be_visible()
    expect(page.get_by_text('独立复核记录',exact=True)).to_be_visible()
    checks.append('查看受保护原件后逐项确认，真实服务保存复核凭据')
    page.screenshot(path=str(OUT/'02-reviewed-result.png'),full_page=True)
    response=req.get(API+'/api/v1/inspection-execution/runs/'+ids['good_run_id'],headers={'Authorization':'Bearer fixture-expert'}).json()['data']
    assert response['effective_status']=='accepted' and response['review_history'][0]['verification_snapshot']['verified_evidence_ids']
    req.post(API+'/_fixture/remove-report')
    page.reload(wait_until='networkidle')
    expect(page.get_by_text('需重新评估',exact=True)).to_have_count(2)
    response=req.get(API+'/api/v1/inspection-execution/runs/'+ids['good_run_id'],headers={'Authorization':'Bearer fixture-expert'}).json()['data']
    assert response['status']=='accepted' and response['effective_status']=='needs_reassessment'
    checks.append('原件丢失后显示需重新评估，历史确认和快照仍保留')
    page.screenshot(path=str(OUT/'03-withdrawn-source.png'),full_page=True)
    assert not errors,errors
    (OUT/'result.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'isolated':True},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'page_errors':errors},ensure_ascii=False))
    browser.close()
