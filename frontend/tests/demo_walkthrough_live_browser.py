"""Read and navigate the existing local demo; failure fixtures never write data."""
import asyncio,json,re
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'.codex_tmp/piap_quality_demo'
config=json.loads((OUT/'accounts.json').read_text(encoding='utf-8'));BASE=config['url']
errors=[];server_errors=[];writes=[]


async def login(browser,name,business_fixture=False):
    context=await browser.new_context(viewport={'width':1500,'height':1050},timezone_id='Asia/Shanghai')
    page=await context.new_page();account=next(a for a in config['accounts'] if a['username']==name)
    if business_fixture:
        async def business(route):await route.fulfill(json={'data':{'execution_mode':'business','label':'业务环境','notice':None,'organization_slug':config['organization'],'case_code':None}})
        await page.route('**/api/v1/runtime-context',business)
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r:server_errors.append(r.url.split('?')[0]) if r.status>=500 else None)
    page.on('request',lambda r:writes.append(urlparse(r.url).path) if '/api/v1/' in r.url and r.method not in ['GET','HEAD','OPTIONS'] else None)
    await page.goto(BASE+'/login',wait_until='networkidle')
    await page.locator('#login-username').fill(account['username']);await page.locator('#login-password').fill(account['password'])
    await page.get_by_role('button',name='登录',exact=False).click();await page.wait_for_url('**/app/**')
    return context,page


async def api(context,page,path):
    token=await page.evaluate("sessionStorage.getItem('piap_token')")
    response=await context.request.get(BASE+'/api/v1'+path,headers={'Authorization':'Bearer '+token})
    assert response.status==200,(path,response.status)
    return (await response.json())['data']


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);ctx,page=await login(browser,'demo_analyst')
        code='DEMO-QS-001';case=(await api(ctx,page,'/risk-cases?keyword='+code+'&page=1&size=100'))['items'][0]
        assert case['code']==code
        before=await api(ctx,page,f"/risk-cases/{case['id']}/workspace")
        await page.goto(BASE+'/app/workbench',wait_until='networkidle')
        guide=page.locator('.demo-walkthrough');await expect(guide).to_contain_text(code)
        await expect(guide.locator('.walkthrough-steps li')).to_have_count(6)
        await expect(page.locator('.agent-line')).to_have_count(0)
        await expect(guide.get_by_role('link',name='查看跳过验证的报告示例',exact=True)).to_be_visible()
        await guide.locator('h2').scroll_into_view_if_needed();await page.screenshot(path=str(OUT/'walkthrough-desktop.png'))
        steps=[('数据接入','/app/quality-data'),('异常发现','/app/quality-analytics'),('风险研判','/app/risk-assessments'),
               ('协同复核','/app/risk-assessments'),('抽查建议','/app/risk-sampling'),('分析报告','/app/risk-reports')]
        for index,(title,path) in enumerate(steps,1):
            await guide.get_by_role('link',name=f'演示步骤{index}：{title}',exact=True).click()
            await page.wait_for_url('**'+path+'?**');await page.wait_for_load_state('networkidle')
            assert urlparse(page.url).path==path
            if index>=3:assert parse_qs(urlparse(page.url).query)['case_id']==[case['id']]
            if index in [3,4]:assert parse_qs(urlparse(page.url).query)['assessment_id']==[before['latest_assessment']['id']]
            await page.get_by_role('link',name='返回演示导览',exact=True).click()
            await expect(guide).to_contain_text(code)
        # Leaving while a scan is still loading must not restore the old page.
        async def slow_scan(route):
            response=await route.fetch();await asyncio.sleep(.6);await route.fulfill(response=response)
        await page.route('**/api/v1/market-monitoring/scan',slow_scan)
        await guide.get_by_role('link',name='演示步骤2：异常发现',exact=True).click()
        await page.wait_for_url('**/app/quality-analytics?**')
        await page.get_by_role('link',name='返回演示导览',exact=True).click()
        await page.wait_for_url('**/app/workbench#demo-case-guide');await page.wait_for_load_state('networkidle')
        await expect(guide).to_contain_text(code)
        await page.unroute('**/api/v1/market-monitoring/scan',slow_scan)
        await guide.get_by_role('link',name='查看跳过验证的报告示例',exact=True).click();await page.wait_for_url('**/app/risk-reports?**');await page.wait_for_load_state('networkidle')
        assert 'report' in parse_qs(urlparse(page.url).query)
        await expect(page.get_by_text('历史快照',exact=False).first).to_be_visible()
        await page.get_by_role('link',name='返回演示导览',exact=True).click();await expect(guide).to_contain_text(code)
        await guide.get_by_role('link',name='查看本事项可选验证',exact=True).click();await page.wait_for_url('**/app/risk-assessments?**');await page.wait_for_load_state('networkidle')
        await expect(page.locator('.risk-lab-panel')).to_be_visible()
        await expect(page.locator('.risk-lab-panel label.el-radio').filter(has_text='组织新的检测')).to_have_class(re.compile('is-disabled'))
        await page.get_by_role('link',name='返回演示导览',exact=True).click();await expect(guide).to_contain_text(code)
        await page.reload(wait_until='networkidle');await expect(guide).to_contain_text(f"最新第 {before['latest_assessment']['version']} 版")
        # An inaccessible source must clear all old case links and recover explicitly.
        async def revoked(route):await route.fulfill(status=403,json={'message':'案例资料权限已变化，请重新核对'})
        endpoint='**/api/v1/risk-cases/*/workspace';await page.route(endpoint,revoked)
        await guide.get_by_role('button',name='刷新演示导览',exact=True).click();await expect(guide).to_contain_text('案例资料权限已变化')
        await expect(guide.locator('.walkthrough-steps')).to_have_count(0)
        await page.unroute(endpoint,revoked);await guide.get_by_role('button',name='刷新演示导览',exact=True).click();await expect(guide).to_contain_text(code)
        # Exact code matching and later-page lookup never substitute the first case.
        async def later_page(route):
            query=parse_qs(urlparse(route.request.url).query)
            if query.get('keyword')!=[code]:await route.continue_();return
            other={**case,'id':'00000000-0000-0000-0000-000000000001','code':'UNRELATED'}
            await route.fulfill(json={'data':{'items':[case] if query.get('page')==['2'] else [other],'page':int(query.get('page',['1'])[0]),'size':100,'total':101}})
        await page.route('**/api/v1/risk-cases?**',later_page)
        await guide.get_by_role('button',name='刷新演示导览',exact=True).click();await expect(guide.locator('.case-state')).to_contain_text(code)
        await page.unroute('**/api/v1/risk-cases?**',later_page)
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
        await page.wait_for_function("document.querySelector('.demo-walkthrough').getBoundingClientRect().right<=innerWidth+1")
        await guide.locator('h2').scroll_into_view_if_needed();await page.screenshot(path=str(OUT/'walkthrough-mobile.png'))
        await guide.locator('.lab-branch').scroll_into_view_if_needed();await page.screenshot(path=str(OUT/'walkthrough-lab-mobile.png'))
        await guide.get_by_role('link',name='演示步骤3：风险研判',exact=True).click();await page.wait_for_load_state('networkidle')
        await expect(page.get_by_role('link',name='返回演示导览',exact=True)).to_be_visible()
        banner_height=await page.locator('.runtime-banner').evaluate('(el)=>el.offsetHeight')
        css_height=await page.evaluate("parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--runtime-banner-height'))")
        assert abs(banner_height-css_height)<=1
        await page.get_by_role('link',name='返回演示导览',exact=True).click();await expect(guide).to_contain_text(code)
        await page.wait_for_load_state('networkidle')
        assert (await guide.bounding_box())['y']<200
        after=await api(ctx,page,f"/risk-cases/{case['id']}/workspace")
        assert before['case']==after['case'] and before['assessment_versions']==after['assessment_versions']
        assert (await api(ctx,page,'/tasks?page=1&size=1'))['total']==0
        assert (await api(ctx,page,'/sampling-plans?page=1&size=1'))['total']==0
        peer,peer_page=await login(browser,'demo_reviewer');await peer_page.goto(BASE+'/app/workbench',wait_until='networkidle')
        await expect(peer_page.locator('.demo-walkthrough')).to_contain_text(code)
        await expect(peer_page.locator('.demo-walkthrough .walkthrough-steps li')).to_have_count(6)
        normal,normal_page=await login(browser,'demo_analyst',business_fixture=True)
        await normal_page.goto(BASE+'/app/workbench?demo=1&execution_mode=demo',wait_until='networkidle')
        await expect(normal_page.locator('.demo-walkthrough')).to_have_count(0)
        await expect(normal_page.get_by_role('link',name='返回演示导览',exact=True)).to_have_count(0)
        assert not errors and not server_errors,(errors,server_errors)
        allowed={'/api/v1/auth/token','/api/v1/streams/session','/api/v1/market-monitoring/scan'}
        assert not set(writes)-allowed,set(writes)-allowed
        result={'passed':True,'mode':'real local demo plus isolated read failure fixtures','six_steps_and_return_link':True,
            'saved_skip_validation_report_opened':True,'laboratory_remains_optional_and_task_creation_disabled':True,
            'refresh_preserves_progress':True,'inaccessible_case_clears_links_and_retry_recovers':True,'exact_case_found_on_later_page':True,
            'two_expert_accounts':True,'desktop_and_mobile':True,'runtime_banner_height_tracks_mobile_link':True,
            'late_market_scan_does_not_override_return_navigation':True,
            'business_runtime_hides_guide_despite_query_parameters':True,
            'case_and_assessment_versions_unchanged':True,'no_task_plan_review_or_report_created':True,'real_model_or_device_called':False,
            'page_errors':errors,'http_5xx':server_errors}
        (OUT/'walkthrough-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));await ctx.close();await peer.close();await normal.close();await browser.close()


if __name__=='__main__':asyncio.run(main())
