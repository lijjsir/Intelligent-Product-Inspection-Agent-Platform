"""Read-only live case verification. Tokens remain in process memory."""
import json,subprocess,sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2];BASE='http://127.0.0.1:5173'
prepared=json.loads((ROOT/'backend/runtime/industrial_case_20261014/prepared.json').read_text(encoding='utf-8'))
inventory=json.loads((ROOT/'backend/runtime/industrial_case_20261014/runtime_inventory.json').read_text(encoding='utf-8'))
OUT=ROOT/'frontend/test-results/industrial-case-r4';OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];http_errors=[]

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,channel='chromium')
    for username,width in [('user',1600),('expert',1600),('user',430)]:
        actor=next(u for u in inventory['users'] if u['username']==username)
        code="from app.core.security import create_access_token; print(create_access_token("+repr(actor['id'])+", "+repr({'org_id':inventory['org_id'],'role':actor['role']})+"))"
        token=subprocess.run(['docker','exec','-w','/app/backend','piap-backend','python','-c',code],capture_output=True,check=True).stdout.decode().strip()
        ctx=browser.new_context(viewport={'width':width,'height':1050})
        state={'piap_token':token,'piap_role':actor['role'],'piap_roles':json.dumps([actor['role']]),
            'piap_user_id':actor['id'],'piap_org_id':inventory['org_id'],'piap_username':username}
        ctx.add_init_script("try{if(location.origin==='"+BASE+"')for(const[k,v]of Object.entries("+json.dumps(state)+"))sessionStorage.setItem(k,v);}catch(_){}")
        page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        response=ctx.request.get(BASE+'/api/v1/tasks?page=1&size=20',headers={'Authorization':'Bearer '+token})
        assert response.status==200,'Task list must work with the real case data'
        def guard(route):
            path=urlparse(route.request.url).path
            if path=='/api/v1/chat/sessions' or path.endswith('/events'):
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':[]}));return
            if path=='/api/v1/collab/summary':
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{'pending_count':0,'initiated_count':0,'processed_count':0}}));return
            if path=='/api/v1/streams/session':
                data=route.request.post_data_json
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'data':{'stream_token':'readonly-test','expires_at':'2027-01-01T00:00:00Z','resource':data['resource'],'resource_id':data['resource_id']}}));return
            if path.endswith('/stream'):
                route.fulfill(status=200,content_type='text/event-stream',body=': readonly\n\n');return
            assert route.request.method=='GET','Live browser tests cannot mutate business data'
            response=route.fetch()
            if response.status>=400:http_errors.append({'path':path,'status':response.status})
            route.fulfill(response=response)
        page.route('**/api/v1/**',guard)
        page.goto(BASE+'/app/tasks/'+prepared['task_id'],wait_until='networkidle')
        expect(page.get_by_text('电动自行车历史报告核对 · JG2128520085',exact=True)).to_be_visible()
        expect(page.get_by_text('标准要求 3 次观测；当前仅有公开报告汇总值，仍需补证。',exact=True)).to_be_visible()
        expect(page.get_by_text('原件已接收；适用日期、范围和正文仍待专家核验及发布。',exact=True)).to_be_visible()
        page.screenshot(path=str(OUT/f'{username}-{width}-case.png'),full_page=True)
        if username=='expert':
            page.get_by_role('button',name='打开本案标准核对',exact=True).click()
            page.wait_for_load_state('networkidle')
            expect(page.get_by_text('标准原文与逐项核对',exact=True)).to_be_visible()
            expect(page.get_by_role('dialog',name='标准原文与逐项核对').locator('strong').filter(has_text='整车质量').first).to_be_visible()
            page.screenshot(path=str(OUT/'expert-standard-review.png'),full_page=True)
            checks.append('专家从任务直达本案指定标准修订与待核对条款')
        if username=='user' and width==1600:
            page.get_by_role('button',name='新建执行记录',exact=True).click()
            page.get_by_role('button',name='带入本案首轮报告转录',exact=True).click()
            expect(page.get_by_text('首轮条款尚未确认发布，或报告来源不可用；请先完成标准核对并刷新。',exact=True)).to_be_visible()
            checks.append('未发布标准不能通过资料预填变成可执行依据')
        if width==430:
            assert page.locator('.case-workflow').evaluate('(e)=>e.scrollWidth<=e.clientWidth+2')
            checks.append('430px案例卡片与流程没有横向溢出')
        checks.append(f'{username} {width}px 可查看真实案例待办和缺证范围')
        ctx.close()
    browser.close()
assert not errors and not http_errors,{'page_errors':errors,'http_errors':http_errors}
result={'checks':checks,'page_errors':errors,'http_errors':http_errors,'read_only':True,'tokens_persisted':False}
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
