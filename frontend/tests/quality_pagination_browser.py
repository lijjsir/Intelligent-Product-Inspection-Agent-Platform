"""Pagination and delayed-response UI contracts; no fixture writes to any API/database."""
import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import NAMESPACE_URL, uuid5

from playwright.async_api import async_playwright, expect

BASE = 'http://127.0.0.1:5173'
OUT = Path(__file__).resolve().parents[2]/'.codex_tmp/piap_quality_demo'
OUT.mkdir(parents=True, exist_ok=True)
STAMP = '2026-10-17T01:00:00Z'
uid = lambda name:str(uuid5(NAMESPACE_URL, 'pagination-ui:'+name))
cases = [{'id':uid(f'case-{i}'), 'org_id':'fixture-org', 'code':f'CASE-{i+1:04}', 'title':f'事项{i+1:04}',
          'scope_type':'product', 'scope':{}, 'status':'risk_assessed', 'source_record_ids':[], 'evidence_ids':[],
          'created_by':'writer'} for i in range(251)]
CASE = cases[-1]
tasks = [{'id':uid(f'task-{i}'), 'label':f'任务{i:04}', 'status':'pending'} for i in range(250)]
records = [{'id':uid(f'record-{i}'), 'label':f'资料{i:04}', 'already_linked':False} for i in range(250)]
reports = [{'id':uid(f'report-{i}'), 'title':f'隔离报告{i+1:04}', 'frozen_at':STAMP,
            'effective_status':'snapshot_unchecked', 'validation_checked':False, 'source_issues':[]} for i in range(251)]
assessment = {'id':uid('assessment'), 'version':1, 'status':'accepted', 'submitted_by':'writer', 'reviewed_by':'reviewer'}
link = {'id':uid('lab'), 'status':'requested', 'revision':1, 'created_by':'reviewer', 'case_id':CASE['id'],
        'case_code':CASE['code'], 'assessment_id':assessment['id'], 'assessment_version':1, 'mode':'verify',
        'purpose':'隔离分页契约', 'task_id':tasks[-1]['id'], 'record_ids':[], 'issues':[], 'events':[], 'boundary':'隔离测试'}
state = {'fail_reports':False, 'revoke_record':False, 'detail_requests':0}
errors, unexpected = [], []

def page_of(items, query):
    page, size = int(query.get('page',['1'])[0]), int(query.get('size',['20'])[0])
    return {'items':items[(page-1)*size:page*size], 'total':len(items), 'page':page, 'size':size}

async def handle(route):
    request = route.request
    parsed = urlparse(request.url); path = parsed.path.removeprefix('/api/v1'); query = parse_qs(parsed.query)
    data = None
    if path == '/users/me':
        data = {'id':'reviewer', 'org_id':'fixture-org', 'username':'fixture', 'role':'expert', 'is_active':True,
            'effective_permissions':['quality','quality_material_read_business','quality_material_submit','task','result','report_read','report_generate']}
    elif path == '/runtime-context': data = {'execution_mode':'business','label':'业务环境','notice':None}
    elif path == '/risk-cases':
        word = query.get('keyword',[''])[0]
        if word == 'slow-failure':
            await asyncio.sleep(0.8)
            await route.fulfill(status=503,json={'error':{'code':'unavailable','message':'旧选项请求失败'}}); return
        data = page_of([r for r in cases if word in r['title'] or word in r['code']], query)
    elif path == f"/risk-cases/{CASE['id']}/workspace":
        data = {'case':CASE, 'records':[], 'unavailable_source_ids':[], 'latest_assessment':assessment,
            'assessment_versions':[{**assessment,'risk_level':'high'}], 'workflow_context':{'enabled':True,'execution_mode':'business',
                'can_author':True,'eligible':True,'assessment_id':assessment['id'],'basis_hash':'a'*64,'blockers':[],'boundary':'fixture'}}
    elif path == '/risk-report-pages':
        if state['fail_reports']:
            await route.fulfill(status=503,json={'error':{'code':'unavailable','message':'分页故障注入'}}); return
        word = query.get('keyword',[''])[0]; visible = [r for r in reports if word in r['title']]
        number = int(query.get('cursor',['0'])[0]); start = number*20
        data = {'items':visible[start:start+20], 'size':20, 'next_cursor':str(number+1) if start+20<len(visible) else None,
                'has_more':start+20<len(visible), 'notice':'打开报告核对当前来源'}
    elif path.startswith('/risk-reports/'):
        state['detail_requests'] += 1
        row = next(r for r in reports if r['id'] == path.split('/')[-1])
        data = {**row, 'snapshot_hash':'fixture', 'snapshot':{'case_id':CASE['id'], 'assessment_id':assessment['id'], 'assessment_version':1, 'source_refs':[]},
                'sections':[{'title':'隔离报告预览','paragraphs':[row['title']]}]}
    elif path == '/quality-supervision/settings': data = {'enabled':True,'laboratory_validation_enabled':True}
    elif path in ['/inspection-sessions','/devices']: data = page_of([],query)
    elif path == f"/risk-cases/{CASE['id']}/laboratory-verifications": data = [link]
    elif path == f"/risk-laboratory-verifications/{link['id']}/execution-results": data = page_of([],query)
    elif path in [f"/risk-cases/{CASE['id']}/laboratory-tasks-options", f"/risk-cases/{CASE['id']}/laboratory-records-options"]:
        assert 'selected_ids[]' not in query
        items = tasks if 'tasks-options' in path else records
        word = query.get('keyword',[''])[0]; selected = query.get('selected_ids',[])
        allowed = [r for r in items if not (state['revoke_record'] and r['id'] == records[243]['id'])]
        data = {**page_of([r for r in allowed if word in r['label'] or word in r['id']],query),
                'selected':[r for r in allowed if r['id'] in selected], 'unavailable_selected_ids':[s for s in selected if s not in {r['id'] for r in allowed}]}
    else:
        unexpected.append((request.method,path)); await route.fulfill(status=404,json={'message':'unexpected fixture request'}); return
    await route.fulfill(json={'data':data,'success':True})

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1500,'height':1000})
        saved = {'piap_token':'fixture-pagination','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'reviewer','piap_org_id':'fixture-org','piap_username':'fixture'}
        await context.add_init_script('for(const [k,v] of Object.entries('+json.dumps(saved)+'))sessionStorage.setItem(k,v)')
        await context.route('**/api/v1/**', handle)
        page = await context.new_page(); page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(BASE+f"/app/risk-reports?case_id={CASE['id']}&report={reports[-1]['id']}",wait_until='networkidle')
        await expect(page.locator('.report-row')).to_have_count(20)
        await expect(page.locator('.report-preview')).to_contain_text('隔离报告0251')
        initial_detail_requests = state['detail_requests']
        assert await page.locator('#report-case').input_value() == CASE['id']
        assert await page.locator('#report-case option').count() <= 22
        await page.get_by_role('button',name='下一页事项',exact=True).click()
        await expect(page.locator('.risk-case-picker')).to_contain_text('第 2 页')
        assert await page.locator('#report-case').input_value() == CASE['id']
        search = page.get_by_role('textbox',name='来源事项搜索',exact=True)
        await search.fill('slow-failure'); await asyncio.sleep(0.3); await search.fill('事项0251')
        await expect(page.locator('#report-case option')).to_have_count(2)
        await asyncio.sleep(1)
        await expect(page.locator('.risk-case-picker')).not_to_contain_text('旧选项请求失败')
        await expect(page.locator('.el-message')).to_have_count(0)
        await expect(page.locator('#report-case option')).to_have_count(2)
        await page.get_by_role('button',name='下一页报告',exact=True).click()
        await expect(page.locator('.report-row').first).to_contain_text('隔离报告0021')
        await expect(page.locator('.report-preview')).to_contain_text('隔离报告0251')
        await page.get_by_role('button',name='上一页报告',exact=True).click()
        await expect(page.locator('.report-row').first).to_contain_text('隔离报告0001')
        await page.get_by_role('textbox',name='报告标题搜索',exact=True).fill('0251')
        await page.get_by_role('button',name='搜索报告',exact=True).click()
        await expect(page.locator('.report-row')).to_have_count(1)
        await expect(page.get_by_role('button',name='下一页报告',exact=True)).to_be_disabled()
        assert state['detail_requests'] == initial_detail_requests, 'Paging must not reload full evidence or report bodies'
        state['fail_reports'] = True
        await page.get_by_role('button',name='刷新报告',exact=True).click()
        await expect(page.locator('.report-row')).to_have_count(0)
        await expect(page.locator('.report-preview')).to_have_count(0)
        await expect(page.locator('.risk-report-center')).to_contain_text('分页故障注入')
        state['fail_reports'] = False
        await page.get_by_role('button',name='刷新报告',exact=True).click()
        await expect(page.locator('.report-row')).to_have_count(1)
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(OUT/'pagination-report-mobile.png'))
        await page.set_viewport_size({'width':1500,'height':1000})
        await page.goto(BASE+f"/app/laboratory?case_id={CASE['id']}",wait_until='networkidle')
        await page.get_by_text('风险事项的可选验证与资料回流',exact=True).click()
        task_picker = page.get_by_role('group',name='关联既有检测任务分页选择',exact=True)
        await expect(task_picker).to_contain_text('任务0249')
        await task_picker.get_by_role('combobox').fill('任务0243')
        await page.get_by_role('option',name='任务0243',exact=True).click()
        await expect(task_picker).to_contain_text('任务0243')
        record_picker = page.get_by_role('group',name='选择已接入的检测资料分页选择',exact=True)
        await record_picker.get_by_role('combobox').fill('资料0243')
        await page.get_by_role('option',name='资料0243',exact=True).click()
        await record_picker.get_by_role('combobox').fill('')
        await expect(record_picker).to_contain_text('250')
        await page.get_by_role('button',name='下一页选项',exact=True).last.click()
        await expect(record_picker).to_contain_text('资料0243')
        state['revoke_record'] = True
        await page.get_by_role('button',name='上一页选项',exact=True).last.click()
        await expect(record_picker).to_contain_text('部分原关联已不可访问')
        await expect(record_picker).not_to_contain_text('资料0243')
        assert not errors and not unexpected, (errors,unexpected)
        result = {'passed':True,'api_mode':'isolated UI fixtures','case_report_task_and_record_counts':[251,251,250,250],
            'selected_item_outside_first_page_preserved':True,'search_and_paging_verified':True,'late_failure_discarded':True,
            'report_failure_clears_previous_preview':True,'revoked_selection_label_removed':True,'mobile_layout':True,'late_failure_has_no_global_toast':True,
            'page_errors':errors,'unexpected_requests':unexpected,'business_rows_written':False}
        (OUT/'pagination-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False)); await browser.close()

if __name__ == '__main__': asyncio.run(main())
