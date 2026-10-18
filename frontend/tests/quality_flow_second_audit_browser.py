"""Real frontend + explicit read-failure injection. Never writes fixture business data."""
import asyncio
import copy
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'.codex_tmp/piap_quality_demo'
config=json.loads((OUT/'accounts.json').read_text(encoding='utf-8'));BASE=config['url']
CASE='90daba62-f80d-55b5-9d25-f05d0c0ffdfe';OTHER='22222222-2222-4222-8222-222222222222'


async def main():
    errors=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1450,'height':1000},timezone_id='Asia/Shanghai')
        page.on('pageerror',lambda e:errors.append(str(e)))
        a=next(a for a in config['accounts'] if a['username']=='demo_analyst')
        await page.goto(BASE+'/login',wait_until='networkidle')
        await page.locator('#login-username').fill(a['username']);await page.locator('#login-password').fill(a['password'])
        await page.get_by_role('button',name='登录',exact=False).click();await page.wait_for_url('**/app/**')
        # A freshly opened market page must work on the next calendar day too.
        # The shell owns a persistent collaboration stream. Assert the business
        # content is ready rather than waiting for every network connection.
        analytics_requests=[]
        page.on('request',lambda r:analytics_requests.append(r.url) if '/quality-supervision/analytics' in r.url else None)
        await page.goto(BASE+'/app/quality-analytics',wait_until='domcontentloaded')
        await expect(page.get_by_label('统计截止日',exact=True)).to_have_value('2026-10-17')
        await expect(page.locator('.market-monitor')).to_contain_text('固定统计日期为 2026-10-17')
        await expect(page.locator('.market-monitor')).to_contain_text('不代表今日实时市场')
        assert not analytics_requests,'Collapsed historical statistics must not start analysis'
        await page.screenshot(path=str(OUT/'second-audit-market-default.png'),full_page=True)
        # Provide one in-memory selector option. The ID does not exist in MySQL;
        # its reads will deliberately fail. All real case reads stay untouched.
        async def choices(route):
            response=await route.fetch();body=await response.json()
            extra=copy.deepcopy(body['data']['items'][0]);extra.update(id=OTHER,code='AUDIT-READ-FAILURE',title='故障注入测试选项（未入库）')
            body['data']['items'].append(extra);body['data']['total']+=1
            await route.fulfill(status=200,content_type='application/json',body=json.dumps(body,ensure_ascii=False))
        async def report_failure(route):
            await route.fulfill(status=503,json={'success':False,'code':'service_unavailable','message':'故障注入：报告列表不可用','error':{'code':'service_unavailable','message':'故障注入：报告列表不可用'}})
        async def slow_failure(route):
            await asyncio.sleep(1.5)
            await route.fulfill(status=503,json={'success':False,'code':'service_unavailable','message':'故障注入：旧请求失败','error':{'code':'service_unavailable','message':'故障注入：旧请求失败'}})
        await page.route(re.compile(r'/api/v1/risk-cases(?:\?.*)?$'),choices)
        await page.route(re.compile(r'/api/v1/risk-report-pages\?case_id='+OTHER+r'(?:&.*)?$'),report_failure)
        await page.route('**/api/v1/risk-cases/'+OTHER+'/workspace',slow_failure)
        await page.goto(BASE+f'/app/risk-reports?case_id={CASE}',wait_until='domcontentloaded')
        await expect(page.locator('.report-row')).to_have_count(3)
        await page.locator('#report-case').select_option(OTHER)
        await expect(page.locator('.report-row')).to_have_count(0)
        await expect(page.locator('.risk-report-center')).to_contain_text('故障注入：报告列表不可用')
        await expect(page.locator('.report-preview')).to_have_count(0)
        await page.screenshot(path=str(OUT/'second-audit-report-failure-cleared.png'),full_page=True)
        await page.goto(BASE+f'/app/laboratory?case_id={CASE}',wait_until='domcontentloaded')
        await expect(page.locator('.lab-history')).to_have_count(1)
        await page.locator('#lab-case').select_option(OTHER)
        await expect(page.locator('.risk-lab-panel')).to_have_count(0,timeout=700)
        await page.locator('#lab-case').select_option(CASE)
        await expect(page.locator('.lab-history')).to_have_count(1)
        await asyncio.sleep(1.7)
        await expect(page.locator('.lab-history')).to_have_count(1)
        await expect(page.locator('.demo-lab-workspace')).not_to_contain_text('故障注入：旧请求失败')
        await expect(page.locator('.el-message')).to_have_count(0)
        await page.screenshot(path=str(OUT/'second-audit-lab-context-restored.png'),full_page=True)
        # A successful mutation arriving after leaving the page must not alter
        # the new page's route. Reuse a real report body, without posting data.
        record=json.loads((OUT/'phase5-browser-acceptance.json').read_text(encoding='utf-8'))
        token=await page.evaluate("sessionStorage.getItem('piap_token')")
        response=await page.context.request.get(BASE+'/api/v1/risk-reports/'+record['new_report_id'],headers={'Authorization':'Bearer '+token})
        assert response.status==200
        existing=(await response.json())['data']
        async def delayed_success(route):
            await asyncio.sleep(1.5)
            await route.fulfill(status=200,json={'success':True,'code':'ok','data':existing})
        await page.route('**/api/v1/risk-cases/'+CASE+'/reports',delayed_success)
        await page.goto(BASE+f'/app/risk-reports?case_id={CASE}',wait_until='domcontentloaded')
        await page.get_by_role('button',name='生成本版演示研判报告',exact=True).click()
        await page.locator('.app-sidebar').get_by_role('button',name='质量监督',exact=True).click()
        await page.locator('.app-sidebar').get_by_text('市场监控',exact=True).click()
        await page.wait_for_url('**/app/quality-analytics**')
        await asyncio.sleep(1.8)
        assert 'report=' not in page.url
        # Exercise queued/running/success and failed export responses in the
        # real component; download bytes still come from the authorized API.
        jobs_response=await page.context.request.get(BASE+'/api/v1/exports?report_type=risk_assessment&page=1&size=200',headers={'Authorization':'Bearer '+token})
        jobs=(await jobs_response.json())['data']['items']
        job=next(j for j in jobs if j['status']=='success' and j['format']=='pdf' and json.loads(j['config_json']).get('risk_report_id')==record['new_report_id'])
        export_mode='pending';reads=[]
        async def start_export(route):
            data={**job,'status':'failed' if export_mode=='failure' else 'pending','error_message':'故障注入：导出失败' if export_mode=='failure' else None}
            await route.fulfill(status=200,json={'success':True,'code':'ok','data':data})
        async def export_status(route):
            reads.append(job['id']);data={**job,'status':'running' if len(reads)==1 else 'success'}
            await route.fulfill(status=200,json={'success':True,'code':'ok','data':data})
        await page.route('**/api/v1/risk-reports/'+record['new_report_id']+'/exports',start_export)
        await page.route(re.compile(r'/api/v1/exports/'+job['id']+r'$'),export_status)
        await page.goto(BASE+f"/app/risk-reports?case_id={CASE}&report={record['new_report_id']}",wait_until='domcontentloaded')
        async with page.expect_download(timeout=30000) as event:
            await page.locator('.report-preview').get_by_role('button',name='导出 PDF',exact=True).click()
        await (await event.value).save_as(str(OUT/'second-audit-polled-export.pdf'))
        assert reads==[job['id'],job['id']]
        export_mode='failure'
        await page.locator('.report-preview').get_by_role('button',name='导出 PDF',exact=True).click()
        await expect(page.locator('.risk-report-center')).to_contain_text('故障注入：导出失败')
        assert not errors,errors
        result={'passed':True,'api_mode':'real frontend with explicit read-failure injection','demo_anchor_after_midnight':True,
            'collapsed_statistics_do_not_start_analysis':True,
            'report_failure_drops_old_rows':True,'case_switch_hides_old_lab_actions':True,'late_failure_cannot_replace_current_case':True,'late_failure_has_no_global_toast':True,
            'late_success_cannot_rewrite_new_page_route':True,'inflight_export_waits_for_same_job':True,'failed_export_shows_failure':True,
            'fixture_business_rows_written':False,'page_errors':errors}
        (OUT/'second-audit-browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
