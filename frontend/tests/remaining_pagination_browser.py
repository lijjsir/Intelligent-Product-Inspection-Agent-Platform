"""Remaining-list UI contracts. Every API is isolated; no business rows are written."""
import asyncio,copy,json
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from uuid import uuid4
from playwright.async_api import async_playwright,expect
import quality_pagination_browser as base

BASE=base.BASE;OUT=base.OUT;CASE=base.CASE;STAMP=base.STAMP
TASK=str(uuid4());source=f"/app/risk-assessments?case_id={CASE['id']}&assessment_id={base.assessment['id']}&tab=collaboration"
def refs(prefix,count):return [{'value':str(uuid4()),'label':f'隔离{prefix}{i:04}'} for i in range(count)]
sessions=refs('会话',241);samples=refs('样品',531);policies=refs('策略',231);members=refs('专家',251)
work=[{'id':'action_request:'+str(uuid4()),'resource_id':str(uuid4()),'item_type':'action_request','title':f'隔离工作项{i:04}',
    'description':'【隔离界面验收】未知信息保持未知。','status':'pending','source':{'type':'user','id':'writer','label':'编写人'},
    'target':{'type':'meeting_room','id':str(uuid4()),'label':'同单位讨论'},'requested_by':'writer','requester_label':'编写人',
    'evidence':[],'allowed_actions':[],'history':[],'source_link':source,'payload':{'source_context':{'kind':'risk_assessment',
    'risk_case_id':CASE['id'],'risk_assessment_id':base.assessment['id'],'risk_assessment_version':1,'case_code':CASE['code'],'execution_mode':'business'}},
    'created_at':STAMP,'updated_at':STAMP} for i in range(251)]
snapshot={'case_id':CASE['id'],'case_code':CASE['code'],'case_title':CASE['title'],'assessment_id':base.assessment['id'],'assessment_version':1,
    'source_record_ids':[],'evidence_ids':[],'scope':{},'objects':[],'review':{'reviewed_by':'peer','reviewed_at':STAMP,'comment':'隔离复核说明'},
    'source_link':source,'opinions':[],'decision_note':'仅测试界面','conclusion':{'summary':'模拟摘要','limitations':'模拟','missing_inputs':[]},'execution_mode':'business','llm_called':False}
suggestions=[{'id':str(uuid4()),'title':f'隔离建议{i:04}','status':'draft','effective_status':'draft','revision':1,'is_current':True,
    'can_edit':False,'content':{'rationale':'隔离理由','focus':'隔离内容','limitations':'未知','sample_quantity':None,'batch':None,'location':None,'proposed_time':None},
    'snapshot':snapshot,'context_hash':'fixture','boundary':'【模拟】界面契约','confirmed_at':None,'events':[]} for i in range(231)]
state={'revoke_member':False,'bad_work':False,'contexts':[]};errors=[];unexpected=[];writes=[]

def reference(rows,q):
    chosen=q.get('selected_ids',[]);word=q.get('keyword',[''])[0];p=int(q.get('page',['1'])[0]);size=20
    selected=[r for r in rows if r['value'] in chosen];filtered=[r for r in rows if word in r['label']]
    return {'items':filtered[(p-1)*size:p*size],'selected':selected,'unavailable_selected_ids':[x for x in chosen if x not in {r['value'] for r in rows}],
        'total':len(filtered),'has_more':p*size<len(filtered),'page':p,'size':size}

def context(selection=None):
    selection=selection or {};selected_session=selection.get('session_id');chosen=selection.get('sample_ids',[]);selected_policy=selection.get('policy_id')
    native_sessions=sessions[:200]+[r for r in sessions[200:] if r['value']==selected_session]
    native_samples=samples[:500]+[r for r in samples[500:] if r['value'] in chosen]
    native_policies=policies[:200]+[r for r in policies[200:] if r['value']==selected_policy]
    return {'context_hash':'fixture-selected-'+str(len(state['contexts'])),'task_scope':{'task_id':TASK,'product_category':'模拟产品','production_date':'2026-10-01','input_mode':'measurement','issues':[]},
        'sessions':[{'id':r['value'],'label':r['label'],'code':r['label'],'sample_ids':[]} for r in native_sessions],
        'samples':[{'id':r['value'],'label':r['label'],'kind':'platform_sample','issues':[]} for r in native_samples]+[{'id':'report-original','label':'原报告样品','kind':'report_sample','issues':[]}],
        'policies':[{'id':r['value'],'snapshot':{'name':r['label'],'version':'fixture'},'issues':[],'definition_hash':'fixture'} for r in native_policies],
        'measurements':[],'reports':[],'images':[],'truncated':{'sessions':True,'samples':True,'measurements':False}}

async def handle(route):
    req=route.request;parsed=urlparse(req.url);path=parsed.path.removeprefix('/api/v1');q=parse_qs(parsed.query);status=200
    if req.method not in {'GET','HEAD'}:
        if path.endswith('/context-selection'):state['contexts'].append(req.post_data_json)
        elif path!='/streams/session':writes.append(path)
    if path=='/users/me':
        data={'id':'reviewer','org_id':'fixture-org','username':'fixture','role':'expert','roles':['expert'],'is_active':True,
            'effective_permissions':['quality','quality_material_read_business','quality_material_submit','task','result','report_read','report_generate','collab','meeting','inspection_execution']}
    elif path=='/runtime-context':data={'execution_mode':'business','label':'业务环境','notice':None}
    elif path=='/collab/summary':data={'pending_count':500,'initiated_count':0,'processed_count':0}
    elif path in ['/chat/sessions','/collab/threads','/collab/targets']:data=[]
    elif path=='/streams/session':data={'stream_token':'isolated','resource':'collab','resource_id':'reviewer'}
    elif path.endswith('/stream'):
        await route.fulfill(content_type='text/event-stream',body=': isolated\n\n');return
    elif path=='/collab/work-item-pages':
        word=q.get('keyword',[''])[0]
        if word=='slow-failure':await asyncio.sleep(.8);await route.fulfill(status=503,json={'message':'过期工作项请求失败'});return
        filtered=[r for r in work if word in r['title']];offset=int(q.get('cursor',['0'])[0]);items=filtered[offset:offset+20]
        data={'items':items,'next_cursor':str(offset+20) if offset+20<len(filtered) else None,'has_more':offset+20<len(filtered)}
    elif path.startswith('/collab/work-item-detail/'):
        rid=path.split('/')[-1]
        if state['bad_work']:status=403;data=None
        else:data=next(r for r in work if r['id'].endswith(rid))
    elif path.startswith('/collab/target-pages/') or path=='/risk-collaborations/participant-pages':
        data=reference([r for r in members if not(state['revoke_member'] and r==members[-1])],q)
    elif path==f'/tasks/{TASK}':data={'id':TASK,'org_id':'fixture-org','product_id':'mock-product','product_name':'模拟产品','spec_code':'模拟执行范围','status':'pending',
        'priority':2,'has_result':False,'has_stability':False,'has_case_workflow':False,'created_at':STAMP,'image_urls':[]}
    elif path==f'/tasks/{TASK}/events':data=[]
    elif path=='/inspection-execution/run-pages':data={'items':[],'total':0,'page':int(q.get('page',['1'])[0]),'size':20}
    elif path=='/inspection-execution/requirements':data=[]
    elif path==f'/inspection-execution/tasks/{TASK}/context':data=context()
    elif path==f'/inspection-execution/tasks/{TASK}/context-selection':data=context(req.post_data_json)
    elif path.startswith(f'/inspection-execution/tasks/{TASK}/reference-pages/'):
        kind=path.split('/')[-1];data=reference({'sessions':sessions,'samples':samples,'policies':policies}[kind],q)
    elif path==f"/risk-cases/{CASE['id']}/collaboration-pages":data={'items':[],'next_cursor':None,'has_more':False}
    elif path.startswith('/risk-sampling/pages/'):
        items=[] if path.endswith('/candidates') else suggestions;word=q.get('keyword',[''])[0];items=[r for r in items if word in r['title']]
        offset=int(q.get('cursor',['0'])[0]);data={'items':items[offset:offset+20],'next_cursor':str(offset+20) if offset+20<len(items) else None,'has_more':offset+20<len(items),'blockers':[],'boundary':'模拟'}
    elif path.startswith('/risk-sampling/suggestions/'):
        data=next(r for r in suggestions if r['id']==path.split('/')[-1])
    elif path=='/risk-policies':data=[]
    elif path==f"/risk-cases/{CASE['id']}/workspace":
        a={**base.assessment,'risk_case_id':CASE['id'],'risk_type':'模拟事项','risk_level':'unknown','scope':{},'evidence_ids':[],'standard_matches':[],
            'conflicts':[],'missing_inputs':[],'possible_causes':[],'recommendations':[],'trust_status':'needs_review','source_validation':{'blockers':[],'uncertainties':[]}}
        data={'case':CASE,'records':[],'unavailable_source_ids':[],'latest_assessment':a,'assessment_versions':[{**a,'created_at':STAMP}],'workflow_context':{'enabled':True,'execution_mode':'business','can_author':False,'eligible':False,'blockers':[]}}
    elif path==f"/risk-assessments/{base.assessment['id']}":
        data={**base.assessment,'risk_case_id':CASE['id'],'risk_type':'模拟事项','risk_level':'unknown','scope':{},'evidence_ids':[],'standard_matches':[],
            'conflicts':[],'missing_inputs':[],'possible_causes':[],'recommendations':[],'trust_status':'needs_review','source_validation':{'blockers':[],'uncertainties':[]}}
    else:
        await base.handle(route);return
    await route.fulfill(status=status,json={'success':status==200,'data':data,'message':'当前工作项不可访问' if status==403 else '隔离响应'})


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);ctx=await browser.new_context(viewport={'width':1500,'height':1050})
        saved={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'reviewer','piap_org_id':'fixture-org','piap_username':'fixture'}
        await ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(saved)+'))sessionStorage.setItem(k,v)')
        await ctx.route('**/api/v1/**',handle)
        page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(BASE+f'/app/tasks/{TASK}?session={sessions[-1]["value"]}',wait_until='networkidle')
        await page.get_by_role('button',name='新建执行记录',exact=True).click()
        dialog=page.get_by_role('dialog',name='新建标准执行记录',exact=True)
        await expect(dialog).to_be_visible()
        picker=dialog.get_by_role('group',name='检测会话分页选择',exact=True)
        await expect(picker).to_contain_text(sessions[-1]['label'])
        await picker.get_by_role('combobox').fill('隔离会话0230')
        await page.get_by_role('option',name='隔离会话0230',exact=True).click()
        await expect(picker).to_contain_text('隔离会话0230')
        sample_picker=dialog.get_by_role('group',name='本次样品分页选择',exact=True)
        await sample_picker.get_by_role('combobox').fill('隔离样品0530')
        await page.get_by_role('option',name='隔离样品0530',exact=True).click()
        await dialog.get_by_role('heading',name='新建标准执行记录',exact=True).click()
        await expect(sample_picker).to_contain_text('隔离样品0530')
        await expect(dialog.get_by_role('group',name='已发布适用策略分页选择')).to_be_visible()
        assert state['contexts'][-1]['session_id']==sessions[230]['value'] and samples[-1]['value'] in state['contexts'][-1]['sample_ids']
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(OUT/'remaining-native-mobile.png'),full_page=True)
        await dialog.get_by_role('button',name='取消',exact=True).click()
        await page.set_viewport_size({'width':1500,'height':1050})
        await page.goto(BASE+f"/app/risk-sampling?case_id={CASE['id']}&suggestion={suggestions[-1]['id']}",wait_until='networkidle')
        await expect(page.get_by_role('heading',name='隔离建议0230',exact=True)).to_be_visible()
        await expect(page.locator('.suggestion-row')).to_have_count(20)
        await page.get_by_role('button',name='下一页建议',exact=True).click()
        await expect(page.locator('.suggestion-row').first).to_contain_text('隔离建议0020')
        await expect(page.get_by_role('heading',name='隔离建议0230',exact=True)).to_be_visible()
        await page.get_by_role('button',name='查看本版研判与协同',exact=True).click()
        await page.wait_for_url('**/app/risk-assessments?**')
        assert f"case_id={CASE['id']}" in page.url
        await page.goto(BASE+f'/app/collab?view=pending&work_item={work[-1]["id"]}',wait_until='networkidle')
        await expect(page.locator('.work-detail')).to_contain_text('隔离工作项0250')
        await page.get_by_role('button',name='下一页工作项',exact=True).click()
        await expect(page.locator('.work-card').first).to_contain_text('隔离工作项0020')
        await expect(page.locator('.work-detail')).to_contain_text('隔离工作项0250')
        await page.get_by_role('button',name='发起处理请求',exact=True).click()
        target=page.get_by_role('group',name='处理请求接收对象分页选择',exact=True)
        await target.get_by_role('combobox').fill('隔离专家0250')
        await page.get_by_role('option',name='隔离专家0250',exact=True).click()
        await expect(target).to_contain_text('隔离专家0250')
        state['revoke_member']=True
        await target.get_by_role('combobox').fill('重新核对')
        await expect(target).to_contain_text('部分原选项已不可用')
        await expect(target).not_to_contain_text('隔离专家0250')
        await page.keyboard.press('Escape');await page.get_by_role('dialog').get_by_role('button',name='取消',exact=True).click()
        state['bad_work']=True
        await page.get_by_role('button',name='回到工作项首页',exact=True).click()
        await expect(page.locator('.work-detail')).not_to_contain_text('隔离工作项0250')
        await expect(page.locator('.collab-center')).to_contain_text('当前工作项不可访问')
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(OUT/'remaining-collab-mobile.png'),full_page=True)
        assert not errors and not writes and not base.unexpected,(errors,writes,base.unexpected)
        result={'passed':True,'api_mode':'isolated UI fixtures','native_session_and_sample_beyond_200_500':True,'selection_context_refresh':True,
            'sampling_deep_link_outside_page':True,'collab_deep_link_outside_page':True,'member_search_and_revocation':True,
            'case_return_link':True,'failed_deep_link_does_not_open_first_item':True,'desktop_mobile':True,'business_rows_written':False,'page_errors':errors}
        (OUT/'remaining-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));await browser.close()

if __name__=='__main__':asyncio.run(main())
