"""R2 UI with real disposable services: publish, link, select, execute, review."""
import json,sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
sys.stdout.reconfigure(encoding='utf-8')
BASE='http://127.0.0.1:5173';API='http://127.0.0.1:8017'
OUT=Path(__file__).resolve().parents[1]/'test-results'/'execution-context-r2';OUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,channel='chromium');req=pw.request.new_context()
    ids=req.get(API+'/_fixture/info').json();assert ids['isolated']
    errors=[];checks=[];actions=[];http_failures=[]
    def new_page(token,role,uid):
        ctx=browser.new_context(viewport={'width':1600,'height':1050});page=ctx.new_page()
        state={'piap_token':token,'piap_role':role,'piap_roles':json.dumps([role]),'piap_user_id':uid,'piap_org_id':ids['org_id'],'piap_username':'隔离工作流验收'}
        page.add_init_script("try{if(location.origin==='http://127.0.0.1:5173'){for(const[k,v]of Object.entries("+json.dumps(state)+"))sessionStorage.setItem(k,v);}}catch(_){}")
        page.on('pageerror',lambda e:errors.append(str(e)))
        def forward(route):
            parsed=urlparse(route.request.url)
            if parsed.path=='/api/v1/chat/sessions':
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':[]}));return
            if parsed.path=='/api/v1/collab/summary':
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{'pending_count':0,'initiated_count':0,'processed_count':0}}));return
            if parsed.path.endswith('/events'):
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':[]}));return
            if parsed.path=='/api/v1/streams/session':
                data=route.request.post_data_json
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{'stream_token':'isolated',
                    'expires_at':'2027-01-01T00:00:00Z','resource':data['resource'],'resource_id':data['resource_id']}}));return
            if parsed.path.endswith('/stream'):
                route.fulfill(status=200,content_type='text/event-stream',body='retry: 60000\n\n: isolated\n\n');return
            response=route.fetch(url=API+parsed.path+('?' + parsed.query if parsed.query else ''))
            if response.status>=400:http_failures.append({'path':parsed.path,'status':response.status})
            if route.request.method=='POST':actions.append({'path':parsed.path,'status':response.status,'body':route.request.post_data_json})
            route.fulfill(status=response.status,headers={**response.headers,'access-control-allow-origin':'*'},body=response.body())
        page.route('**/api/v1/**',forward)
        return ctx,page
    def field(dialog,label):return dialog.locator('.el-form-item').filter(has_text=label).locator('input,textarea').first
    def choose(page,dialog,label,option):
        dialog.locator('.el-form-item').filter(has_text=label).locator('.el-select').click()
        page.get_by_role('option',name=option,exact=False).last.click()
        expect(page.get_by_role('option',name=option,exact=False).last).not_to_be_visible()
    def task(page,task_id):
        page.goto(BASE+'/app/tasks/'+task_id,wait_until='networkidle')
        page.get_by_role('button',name='新建执行记录',exact=True).click()
        dialog=page.get_by_role('dialog',name='新建标准执行记录',exact=True);expect(dialog).to_be_visible();return dialog
    def select_requirement(dialog):dialog.locator('.requirement-option').filter(has_text='最高车速').click()

    ca,a=new_page('fixture-admin','admin',ids['admin_id'])
    a.goto(BASE+'/governance/admin/ai-review-gates',wait_until='networkidle')
    a.get_by_role('button',name='查看并发布',exact=True).click()
    policy=a.get_by_role('dialog',name='发布检测执行策略',exact=True)
    field(policy,'图片最少数量').fill('2');field(policy,'所需图片视角').fill('正面\n背面')
    field(policy,'发布说明').fill('隔离验收：报告和测量不强制图片，混合任务需要正背面图片')
    a.get_by_role('button',name='预览完整策略',exact=True).click()
    expect(policy.get_by_text('发布内容核对',exact=True)).to_be_visible()
    policy.get_by_role('button',name='确认发布并保留版本',exact=True).click();expect(policy).not_to_be_visible()
    expect(a.get_by_text('v1 · 第 1 发布版',exact=True)).to_be_visible();checks.append('管理员从新页面发布明确输入类型、图片数量和视角策略')
    a.screenshot(path=str(OUT/'01-published-policy.png'),full_page=True)

    cu,u=new_page('fixture-author','user',ids['author_id'])
    create=task(u,ids['report_task_id'])
    expect(field(create,'产品类别')).to_have_value('电动自行车');expect(field(create,'实际生产日期')).to_be_disabled()
    expect(create.get_by_text('BATCH-A',exact=True)).to_be_visible()
    select_requirement(create)
    create.get_by_role('button',name='关联已有检测报告',exact=True).click()
    link=u.get_by_role('dialog',name='关联已有检测报告',exact=True)
    choose(u,link,'检测报告资料','fixture-report.pdf')
    field(link,'报告原样品编号').fill('report-sample')
    field(link,'核对说明').fill('隔离工业产品 BATCH-A 与报告原样品 report-sample 对应')
    link.get_by_role('button',name='核对并关联到任务',exact=True).click();expect(link).not_to_be_visible()
    choose(u,create,'已关联检测报告','fixture-report.pdf')
    choose(u,create,'对应标准项目','最高车速')
    field(create,'报告原文数值').fill('30.8');field(create,'报告 / 实测方法').fill('7.1')
    field(create,'报告页码').fill('3');field(create,'报告原文项目').fill('最高车速')
    field(create,'试验模式').fill('maximum')
    create.get_by_role('button',name='查看报告原件',exact=True).click()
    expect(u.locator('iframe[title="检测报告原件"]')).to_be_visible();u.wait_for_timeout(800)
    u.get_by_role('dialog',name='fixture-report.pdf · 第 3 页',exact=True).locator('.el-dialog__headerbtn').click()
    expect(u.get_by_role('dialog',name='fixture-report.pdf · 第 3 页',exact=True)).not_to_be_visible()
    u.wait_for_timeout(400)
    checks.append('用户选择已接入报告并关联原样品，填数前可打开真实 PDF 原件')
    u.screenshot(path=str(OUT/'02-linked-report-input.png'),full_page=True)
    create.get_by_role('button',name='保存证据并执行',exact=True).click();expect(create).not_to_be_visible()
    expect(u.get_by_role('heading',name='存在不符合项目',exact=True)).to_be_visible()
    checks.append('报告任务消费已发布策略，图片数量要求不误用到纯报告任务')
    u.screenshot(path=str(OUT/'03-report-result.png'),full_page=True)

    ce,e=new_page('fixture-expert','expert',ids['expert_id'])
    e.goto(BASE+'/app/tasks/'+ids['report_task_id'],wait_until='networkidle')
    e.get_by_role('button',name='查看执行详情',exact=True).click()
    e.get_by_role('button',name='独立专业复核',exact=True).click();review=e.get_by_role('dialog',name='独立专业复核',exact=True)
    field(review,'复核说明').fill('独立核对报告原样品、第三页读数、方法和试验模式')
    field(review,'复核依据').fill('原报告第3页，最高车速30.8 km/h，7.1方法')
    review.locator('.el-checkbox').filter(has_text='涉及报告转录时').click()
    review.locator('.el-checkbox').filter(has_text='已核对 最高车速').click()
    review.get_by_role('button',name='确认并记录',exact=True).click();expect(review).not_to_be_visible()
    checks.append('R1独立复核继续可用，报告原编号和策略版本一起留存')

    create=task(u,ids['measurement_task_id']);select_requirement(create)
    choose(u,create,'任务原始测量记录','24')
    expect(field(create,'原始实测值（只读）')).to_have_value('24');expect(field(create,'原始实测值（只读）')).to_be_disabled()
    expect(field(create,'单位')).to_have_value('km/h');expect(field(create,'报告 / 实测方法')).to_have_value('7.1')
    expect(create.get_by_text('试验模式：maximum',exact=True)).to_be_visible()
    u.wait_for_timeout(250)
    u.screenshot(path=str(OUT/'04-selected-measurement.png'),full_page=True)
    create.get_by_role('button',name='保存证据并执行',exact=True).click();expect(create).not_to_be_visible()
    expect(u.get_by_role('heading',name='选定项目符合要求',exact=True)).to_be_visible()
    checks.append('任务会话和原测量可直接选择，读数、方法、单位与条件只读带入')

    req.post(API+'/_fixture/change-input-mode')
    create=task(u,ids['measurement_task_id']);select_requirement(create);choose(u,create,'任务原始测量记录','24')
    create.get_by_role('button',name='保存证据并执行',exact=True).click();expect(create).not_to_be_visible()
    expect(u.get_by_text('策略要求至少2张独立图片，当前0张',exact=True)).to_be_visible()
    expect(u.get_by_role('heading',name='检测或依据尚不完整',exact=True)).to_be_visible()
    checks.append('混合任务缺图片和视角时保持不完整，不能把数值通过当作策略通过')
    u.screenshot(path=str(OUT/'05-policy-blocks-incomplete-input.png'),full_page=True)
    result=req.get(API+'/_fixture/results').json();assert result['isolated']
    assert len(result['policies'])==1 and len(result['runs'])==3
    policy_id=result['policies'][0]['id'];assert all(r['snapshot']['policy']['publication_id']==policy_id for r in result['runs'])
    assert result['runs'][0]['snapshot']['observations'][0]['sample_label']=='report-sample'
    a.get_by_role('button',name='刷新',exact=True).last.click()
    a.get_by_role('button',name='撤回版本',exact=True).click()
    prompt=a.get_by_role('dialog',name='撤回执行策略',exact=True)
    prompt.locator('textarea').fill('隔离验收：撤回策略应保留历史并提示重新核验')
    prompt.get_by_role('button',name='确定',exact=True).click();expect(prompt).not_to_be_visible()
    expect(a.get_by_text('已撤回',exact=True)).to_be_visible()
    report_run=next(r for r in result['runs'] if r['task_id']==ids['report_task_id'])
    fresh=req.get(API+'/api/v1/inspection-execution/runs/'+report_run['id'],headers={'Authorization':'Bearer fixture-expert'}).json()['data']
    assert fresh['status']=='accepted' and fresh['effective_status']=='needs_reassessment'
    checks.append('管理员撤回发布版本后，历史结果保留并提示重新核验')
    assert not errors,errors
    assert not http_failures,http_failures
    (OUT/'result.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'http_failures':http_failures,'isolated':True,'actions':actions},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'page_errors':errors,'http_failures':http_failures},ensure_ascii=False))
    browser.close()
