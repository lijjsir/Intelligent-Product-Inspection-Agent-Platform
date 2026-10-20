"""Authenticated read-only collaboration smoke test on the local demo stack."""
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'.codex_tmp/piap_quality_demo'
config=json.loads((OUT/'accounts.json').read_text(encoding='utf-8'));BASE=config['url']
account=next(a for a in config['accounts'] if a['username']=='demo_analyst')
errors=[];failed=[];writes=[];counts={}
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1500,'height':1000},timezone_id='Asia/Shanghai')
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r:failed.append({'path':urlparse(r.url).path,'status':r.status}) if r.status>=500 else None)
    page.on('request',lambda r:writes.append(urlparse(r.url).path) if '/api/v1/' in r.url and r.method not in {'GET','HEAD','OPTIONS'} else None)
    page.goto(BASE+'/login',wait_until='networkidle');page.locator('#login-username').fill(account['username']);page.locator('#login-password').fill(account['password'])
    page.get_by_role('button',name='登录',exact=False).click();page.wait_for_url('**/app/**')
    page.goto(BASE+'/app/collab',wait_until='networkidle')
    token=page.evaluate("sessionStorage.getItem('piap_token')")
    for view,label in [('pending','待我处理'),('initiated','我发起的'),('processed','已处理')]:
        response=context.request.get(BASE+'/api/v1/collab/work-item-pages?view='+view,headers={'Authorization':'Bearer '+token})
        assert response.status==200,(view,response.status)
        data=response.json()['data'];counts[view]=len(data['items'])
        page.get_by_role('button',name=label,exact=False).click();page.wait_for_load_state('networkidle')
        expect(page.locator('.error-state')).to_have_count(0)
        expect(page.locator('.el-alert--error')).to_have_count(0)
    page.screenshot(path=str(OUT/'collab-500-live-recovered.png'))
    assert not errors and not failed,(errors,failed)
    assert not set(writes)-{'/api/v1/auth/token','/api/v1/streams/session'},writes
    result={'passed':True,'mode':'authenticated real local demo API','three_work_item_views_http_200':True,
        'shown_counts':counts,'page_errors':errors,'http_5xx':failed,'messages_or_approvals_created':False}
    (OUT/'collab-500-live-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));browser.close()
