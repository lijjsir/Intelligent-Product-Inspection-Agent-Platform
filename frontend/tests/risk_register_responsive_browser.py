"""Check every register field is visible without horizontal scrolling at narrow widths."""
import json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import expect,sync_playwright

OUT=Path(__file__).resolve().parents[1]/'test-results/risk-register-responsive'
OUT.mkdir(parents=True,exist_ok=True)
stamp='2026-10-23T08:00:00Z';errors=[];writes=[]
titles=['真实公开抽查复盘｜电动自行车充电器安全项目','真实公开执法复盘｜万州电动自行车鞍座超长案','真实历史资料复盘｜速珂TDR009Z-2Z国家监督抽查与报告核对']
rows=[{'id':f'case-{index}','code':code,'title':titles[index],'scope_type':'product' if index==2 else 'category',
    'scope':{'name':titles[index]},'status':status,'source_record_ids':[],'evidence_ids':[f'e-{i}' for i in range(index+1)],
    'created_by':'author','created_at':stamp,'updated_at':stamp}
    for index,(code,status) in enumerate([('RISK-696B86A754EE','awaiting_evidence'),('RISK-91C9D96E8B3C','awaiting_review'),('RISK-7A5605B00C57','collecting')])]


def reply(route,data):route.fulfill(status=200,content_type='application/json',body=json.dumps({'code':'ok','data':data}))
def handle(route):
    request=route.request;parsed=urlparse(request.url);path=parsed.path.removeprefix('/api/v1/')
    if request.method!='GET':writes.append(path);route.abort();return
    if path=='users/me':reply(route,{'id':'expert','org_id':'org','role':'expert','username':'expert','is_active':True,'effective_permissions':['quality','quality_material_read_business']});return
    if path=='runtime-context':reply(route,{'execution_mode':'business','label':'业务环境'});return
    if path=='risk-cases':
        query=parse_qs(parsed.query);keyword=query.get('keyword',[''])[0];status=query.get('status',[''])[0]
        found=[row for row in rows if keyword in row['title'] and (not status or row['status']==status)]
        reply(route,{'items':found,'total':len(found),'page':1,'size':20});return
    if path.endswith('/workspace'):
        row=next(row for row in rows if row['id']==path.split('/')[1])
        reply(route,{'case':row,'records':[],'unavailable_source_ids':[],'latest_assessment':None,'assessment_versions':[],'workflow_context':None});return
    if path.endswith('/analysis-jobs/latest'):reply(route,None);return
    reply(route,[])


with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000})
    auth={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'expert','piap_org_id':'org','piap_username':'expert'}
    context.add_init_script('for(const[k,v]of Object.entries('+json.dumps(auth)+'))sessionStorage.setItem(k,v)')
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.route('**/api/v1/**',handle)
    page.goto('http://127.0.0.1:5173/app/risk-assessments',wait_until='networkidle')
    register=page.locator('#risk-case-register');table=register.locator('.case-table')
    expect(table).to_be_visible()
    register.get_by_role('button',name=titles[2],exact=True).click()
    detail=page.locator('#risk-case-detail');expect(detail).to_contain_text(titles[2])
    expect(detail).to_be_focused()
    assert detail.bounding_box()['y']>=register.bounding_box()['y']+register.bounding_box()['height']
    detail.get_by_role('button',name='返回台账',exact=True).click();expect(register).to_be_focused()
    register.get_by_role('textbox').fill('充电器');register.get_by_role('textbox').press('Enter')
    expect(table.locator('.el-table__body tbody tr')).to_have_count(1)
    register.get_by_role('textbox').fill('');register.get_by_role('textbox').press('Enter')
    expect(table.locator('.el-table__body tbody tr')).to_have_count(3)
    checks=[]
    for width in [1920,1440,1280,1100,1024,768,390]:
        page.set_viewport_size({'width':width,'height':1000})
        page.wait_for_timeout(250)  # allow the sidebar/ResizeObserver transition to finish
        if width<768:page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=0")
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        if table.is_visible():
            for label in ['编号','风险对象','范围','证据','状态']:expect(table.get_by_role('columnheader',name=label,exact=True)).to_be_visible()
            assert table.locator('.el-scrollbar__wrap').first.evaluate('(element)=>element.scrollWidth<=element.clientWidth+1'),width
            checks.append({'width':width,'mode':'table','all_columns_visible':True})
        else:
            cards=register.locator('.case-cards');expect(cards).to_be_visible()
            for index,title in enumerate(titles):
                card=cards.locator('.case-card').nth(index)
                expect(card).to_contain_text(title);expect(card).to_contain_text('范围：');expect(card).to_contain_text(f'证据：{index+1} 项')
                assert card.locator('.case-card-title').evaluate('(element)=>element.scrollHeight<=element.clientHeight+1'),width
            checks.append({'width':width,'mode':'cards','all_fields_visible':True})
        if width in [1440,390]:
            detail.get_by_role('button',name='返回台账',exact=True).click()
            page.screenshot(path=str(OUT/f'register-{width}.png'),full_page=True)
    cards=register.locator('.case-cards');cards.get_by_role('button',name=__import__('re').compile('RISK-696B86A754EE')).click()
    expect(detail).to_contain_text(titles[0]);expect(detail).to_be_focused()
    detail.get_by_role('button',name='收起',exact=True).click();expect(detail).to_have_count(0);expect(register).to_be_focused()
    assert not errors and not writes,{'errors':errors,'writes':writes}
    result={'passed':True,'mode':'isolated API fixtures; no live data writes','viewports':checks,'page_errors':errors}
    (OUT/'checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    context.close();browser.close()
