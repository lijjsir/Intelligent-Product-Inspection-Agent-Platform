"""Current UI flow after retiring the center; all mutations use isolated fixtures."""
import asyncio,copy,json
from urllib.parse import parse_qs,urlparse
from uuid import uuid4
from playwright.async_api import async_playwright,expect
import remaining_pagination_browser as base

CASE=base.CASE;ASSESSMENT=base.base.assessment['id'];ID=str(uuid4());state={'rows':[],'posts':[],'report':False};errors=[]
snapshot={'schema':'risk-sampling-assessment-v2','case_id':CASE['id'],'case_code':CASE['code'],'case_title':CASE['title'],'scope':{},'objects':[],
    'assessment_id':ASSESSMENT,'assessment_version':7,'source_record_ids':[],'evidence_ids':[],
    'review':{'reviewed_by':'peer','reviewed_at':base.STAMP,'comment':'独立核对证据'},'conclusion':{'summary':'【模拟】异常需进一步核实','limitations':'仅软件测试','missing_inputs':['真实数据待补充']},
    'collaboration_id':None,'collaboration_purpose':'','decision_note':'','opinions':[],'execution_mode':'business','llm_called':False,'source_link':'/app/risk-assessments?case_id='+CASE['id']}
candidate={'snapshot':snapshot,'context_hash':'a'*64}


async def handle(route):
    req=route.request;url=urlparse(req.url);path=url.path.removeprefix('/api/v1');query=parse_qs(url.query)
    if path.startswith('/risk-sampling/pages/'):
        data={'items':[candidate] if path.endswith('/candidates') else state['rows'],'next_cursor':None,'has_more':False,'size':20,'blockers':[],'boundary':'【模拟】独立复核后的建议'}
    elif path==f"/risk-cases/{CASE['id']}/risk-sampling-suggestions":
        body=req.post_data_json;state['posts'].append(body);assert 'collaboration_id' not in body and body['assessment_id']==ASSESSMENT
        row={'id':ID,'title':'【模拟】直接研判建议','status':'draft','effective_status':'draft','revision':1,'is_current':True,'can_edit':True,
            'snapshot':copy.deepcopy(snapshot),'context_hash':'a'*64,'content':{'rationale':'','focus':'','limitations':'','sample_quantity':None,'batch':None,'location':None,'proposed_time':None},'boundary':'【模拟】不执行抽查','events':[]}
        state['rows']=[row];data=row
    elif path==f'/risk-sampling/suggestions/{ID}' or path==f'/risk-sampling/suggestions/{ID}/confirm':
        row=state['rows'][0]
        if req.method=='PATCH':row['content']=req.post_data_json['content'];row['revision']+=1
        elif req.method=='POST':row.update(status='confirmed',effective_status='confirmed',can_edit=False,confirmed_at=base.STAMP);row['revision']+=1
        data=row
    elif path.startswith('/risk-collaborations/') or path.endswith('/collaboration-pages'):
        raise AssertionError('New UI must not request retired collaboration data')
    else:await base.handle(route);return
    await route.fulfill(json={'data':data})


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);ctx=await browser.new_context(viewport={'width':1500,'height':1000})
        stored={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'reviewer','piap_org_id':'fixture-org','piap_username':'fixture'}
        await ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(stored)+'))sessionStorage.setItem(k,v)')
        await ctx.route('**/api/v1/**',handle);page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(base.BASE+'/app/risk-sampling?case_id='+CASE['id'],wait_until='networkidle')
        nav=page.locator('.app-sidebar nav');await expect(nav.get_by_role('link',name='协同中心',exact=True)).to_have_count(0)
        await expect(nav.get_by_role('link',name='协作中心',exact=True)).to_have_count(0)
        await expect(nav.get_by_role('link',name='会议室',exact=True)).to_be_visible()
        await page.get_by_role('button',name='编写建议',exact=True).click();await expect(page.get_by_role('heading',name='【模拟】直接研判建议',exact=True)).to_be_visible()
        await page.get_by_label('抽查理由',exact=True).fill('【模拟】来自已复核事项')
        await page.get_by_label('关注内容',exact=True).fill('核查当前对象')
        await page.get_by_label('资源假设、限制与待核实事项',exact=True).fill('没有实际抽样，不执行检测')
        await page.get_by_role('button',name='保存草稿',exact=True).click();await page.get_by_role('button',name='确认并固定建议',exact=True).click()
        await expect(page.get_by_text('建议已固定，未创建执行任务',exact=True)).to_be_visible()
        await page.get_by_role('button',name='返回来源事项',exact=True).click();await page.wait_for_url('**/app/risk-assessments?**')
        await expect(page.get_by_role('tab',name='协同讨论',exact=True)).to_have_count(0)
        await page.goto(base.BASE+'/app/collab',wait_until='networkidle')
        await expect(page.get_by_role('heading',name='历史共享与请求记录',exact=True)).to_be_visible()
        await expect(page.get_by_role('button',name='发起处理请求',exact=True)).to_have_count(0)
        await page.set_viewport_size({'width':390,'height':844});await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
        await page.screenshot(path=str(base.OUT/'collab-retirement-history-mobile.png'))
        assert not errors,errors
        result={'passed':True,'mode':'isolated UI fixtures','center_absent_from_menu':True,'meeting_entry_kept':True,
            'direct_suggestion_create_save_confirm':True,'no_collaboration_payload_or_query':True,'risk_collaboration_tab_removed':True,
            'legacy_route_read_only':True,'mobile':True,'business_rows_written':False,'page_errors':errors}
        (base.OUT/'collab-retirement-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
