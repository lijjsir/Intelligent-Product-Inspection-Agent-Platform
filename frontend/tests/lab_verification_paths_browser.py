"""Three validation paths and preparation handoff, with isolated API fixtures only."""
import asyncio,copy,json,re
from urllib.parse import parse_qs,urlparse
from uuid import uuid4
from playwright.async_api import async_playwright,expect
import remaining_pagination_browser as old

BASE=old.BASE;OUT=old.OUT;CASE=copy.deepcopy(old.CASE);TASK=old.TASK;STAMP=old.STAMP
PRODUCT,CATEGORY,STANDARD=[str(uuid4()) for _ in range(3)]
CASE['scope']={'product_id':PRODUCT,'category_id':CATEGORY};CASE['status']='awaiting_evidence'
state={'links':[],'version':1,'assessment_id':old.base.assessment['id'],'records':[],'task_creates':0,'body':None,'bad_origin':False}
errors=[];unexpected=[];mutations=[]

def assessment():return {'id':state['assessment_id'],'risk_case_id':CASE['id'],'version':state['version'],'status':'awaiting_review','effective_status':'awaiting_evidence',
    'submitted_by':'reviewer','reviewed_by':None,'scope':CASE['scope'],'risk_type':'隔离验证事项','risk_level':'unknown','evidence_ids':[],
    'standard_matches':[],'conflicts':[],'missing_inputs':['真实测量仍未知'],'possible_causes':[],'recommendations':[],
    'trust_status':'unverified','created_at':STAMP,'source_validation':{'blockers':[],'uncertainties':[]}}

def preparation(link):return {'link_id':link['id'],'case_id':CASE['id'],'case_code':CASE['code'],'case_title':CASE['title'],
    'assessment_id':link['assessment_id'],'assessment_version':link['assessment_version'],'purpose':link['purpose'],'revision':link['revision'],
    'basis_hash':'b'*64,'task_id':link['task_id'],'can_create':not link['task_id'],'blockers':[],
    'product_id':PRODUCT,'product_name':'【模拟】验证产品','category_id':CATEGORY,'category_name':'模拟类别','quality_batch_id':None,
    'production_batch_ref':None,'unit_serial_ref':None,'request_stage':'preliminary'}

async def handle(route):
    req=route.request;parsed=urlparse(req.url);path=parsed.path.removeprefix('/api/v1');query=parse_qs(parsed.query)
    data=None;status=200
    if req.method not in {'GET','HEAD'}:mutations.append(path)
    if path==f"/risk-cases/{CASE['id']}/workspace":
        a=assessment();data={'case':CASE,'records':state['records'],'unavailable_source_ids':[],'latest_assessment':a,
            'assessment_versions':[a],'workflow_context':{'enabled':True,'execution_mode':'business','can_author':True,'eligible':False,
            'assessment_id':a['id'],'basis_hash':'b'*64,'blockers':[{'message':'最终研判尚未独立复核'}]}}
    elif path.startswith('/risk-assessments/'):data=assessment()
    elif path==f"/risk-cases/{CASE['id']}/laboratory-verifications":
        if req.method=='POST':
            body=req.post_data_json;assert body['verification_path'] in ['skip','report','task'] and body['expected_basis_hash']=='b'*64
            assert body['task_id'] is None
            link={'id':str(uuid4()),'status':'validation_planned','revision':1,'created_by':'reviewer','case_id':CASE['id'],'case_code':CASE['code'],
                'assessment_id':body['assessment_id'],'assessment_version':state['version'],'mode':body['mode'],'verification_path':body['verification_path'],
                'request_stage':'preliminary','purpose':body['purpose'],'task_id':None,'record_ids':[],'issues':[],'events':[],'is_latest_assessment':True,'boundary':'隔离申请，不是正式结论'}
            state['links'].insert(0,link);data=link
        else:data=state['links']
    elif path.startswith('/risk-laboratory-verifications/'):
        lid=path.split('/')[2];link=next(l for l in state['links'] if l['id']==lid)
        if path.endswith('/task-preparation'):data=preparation(link)
        elif path.endswith('/tasks'):
            body=req.post_data_json;assert body['inspection_standard_id']==STANDARD and body['expected_revision']==link['revision']
            state['task_creates']+=1;link.update(task_id=TASK,revision=2,task_creation={'request_key':body['request_key'],'payload_hash':'fixture'})
            data={'task_id':TASK,'link':link,'reused':False}
        elif path.endswith('/task-origin'):
            if state['bad_origin']:status=403
            data=preparation(link)
        elif path.endswith('/intake-context'):
            data={**preparation(link),'product':{'id':PRODUCT,'name':'【模拟】验证产品','category_id':CATEGORY},
                'category':{'id':CATEGORY,'name':'模拟类别'},'enterprise_id':None,'enterprise':None}
        elif path.endswith('/execution-results'):data={'items':[],'total':0,'page':1,'size':20}
        elif path.endswith('/evidence'):
            body=req.post_data_json;assert body['record_ids']==[state['records'][0]['id']]
            link.update(record_ids=body['record_ids'],return_note=body['note'],added_new_evidence=True,status='returned',revision=link['revision']+1)
            data=link
        else:unexpected.append(path)
    elif path==f"/risk-cases/{CASE['id']}/laboratory-records-options":
        data={'items':[{'id':r['id'],'label':r['content']['text']} for r in state['records']],'selected':[],'unavailable_selected_ids':[],'total':len(state['records']),'page':1,'size':20}
    elif path==f"/risk-cases/{CASE['id']}/laboratory-tasks-options":data={'items':[],'selected':[],'unavailable_selected_ids':[],'total':0,'page':1,'size':20}
    elif path=='/tasks/meta/creation-options':data={'standards':[{'id':STANDARD,'name':'【模拟】有效检测配置','is_active':True}]}
    elif path==f'/tasks/{TASK}':data={'id':TASK,'org_id':'fixture-org','product_id':PRODUCT,'product_name':'【模拟】验证产品','spec_code':'ISOLATED',
        'status':'pending','priority':5,'has_result':False,'has_stability':False,'has_case_workflow':False,'created_at':STAMP,'image_urls':[],
        'risk_verification_id':next((l['id'] for l in state['links'] if l['task_id']==TASK),None)}
    elif path=='/results/execution-options':data=[]
    elif path=='/samples':data={'items':[],'total':0,'page':1,'size':20}
    elif path=='/quality-data/reference-options':data={'categories':[{'id':CATEGORY,'name':'模拟类别'}],'products':[{'id':PRODUCT,'name':'【模拟】验证产品','category_id':CATEGORY}],'enterprises':[]}
    elif path=='/quality-data/records':data={'items':state['records'],'total':len(state['records']),'page':1,'size':20}
    elif path=='/quality-data/events':
        body=req.post_data_json;state['body']=body
        assert body['record_type']=='inspection_report' and body['occurred_at'] is None and body['product_ref']['product_id']==PRODUCT
        assert body['provenance']['object_reference_checked'] is True
        data={'id':str(uuid4()),'source_id':str(uuid4()),'record_type':'inspection_report','occurred_at':None,'received_at':STAMP,
            'content':body['content'],'content_hash':'fixture','product_ref':body['product_ref'],'enterprise_ref':body['enterprise_ref'],
            'attachment_ids':[],'provenance':body['provenance'],'data_nature':'observed','authorization_scope':'private','normalization_status':'normalized',
            'normalization_errors':[],'created_by':'reviewer','location':{}}
        state['records'].append(data)
    elif path.startswith('/quality-data/records/'):
        record=state['records'][0]
        data={'record':record,'objects':{key:{'id':None,'name':None,'status':'unlinked'} for key in ['product','category','enterprise']},
            'source':{'id':record['source_id'],'name':'隔离资料','status':'active'},'attachments':[],'unavailable_attachment_ids':[],'related_cases':[]} if path.endswith('/context') else []
    else:await old.handle(route);return
    await route.fulfill(status=status,json={'data':data,'success':status==200,'message':'来源验证不可访问' if status==403 else '隔离响应'})


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);ctx=await browser.new_context(viewport={'width':1500,'height':1050})
        stored={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'reviewer','piap_org_id':'fixture-org','piap_username':'fixture'}
        await ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(stored)+'))sessionStorage.setItem(k,v)')
        await ctx.route('**/api/v1/**',handle);page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(BASE+f"/app/risk-assessments?case_id={CASE['id']}&tab=laboratory",wait_until='networkidle')
        panel=page.locator('.risk-lab-panel');await expect(panel).to_be_visible()
        await expect(panel.locator('.execution-return')).to_have_count(0)
        await panel.locator('label.el-radio').filter(has_text='引用已有报告').click()
        await panel.locator('textarea').first.fill('【模拟】引用已有外部报告补充依据')
        await panel.get_by_role('button',name='保存本版验证选择',exact=True).click()
        await expect(panel.get_by_role('heading',name='引用已有报告并返回原事项',exact=True)).to_be_visible()
        await expect(panel).not_to_contain_text('请先在验证分支关联')
        await panel.get_by_role('button',name='接入新的检测资料',exact=True).click()
        dialog=page.get_by_role('dialog',name='提交质量资料',exact=True);await expect(dialog).to_be_visible()
        await expect(dialog).to_contain_text('【模拟】验证产品')
        await dialog.locator('textarea').first.fill('【隔离模拟报告原文】只是界面测试，没有真实温升读数')
        await dialog.locator('label.el-checkbox').click()
        await dialog.get_by_role('button',name='提交',exact=True).click()
        await expect(dialog).not_to_be_visible()
        drawer=page.get_by_role('dialog',name='原始资料详情',exact=True)
        if await drawer.is_visible():await drawer.locator('.el-drawer__close-btn').click()
        await page.get_by_role('button',name='返回来源事项选择报告回流',exact=True).click()
        panel=page.locator('.risk-lab-panel');picker=panel.get_by_role('group',name='选择已接入的检测资料分页选择',exact=True)
        await picker.get_by_role('combobox').fill('隔离');await page.get_by_role('option',name=state['records'][0]['content']['text'],exact=True).click()
        await panel.get_by_role('heading',name='引用已有报告并返回原事项',exact=True).click()
        await panel.locator('.lab-return textarea').fill('【隔离】报告资料回流，不代表风险已复核')
        await panel.get_by_role('button',name='关联资料并返回原事项',exact=True).click()
        await expect(panel).to_contain_text('已增加原事项证据')
        state['version']=2;state['assessment_id']=str(uuid4())
        await page.goto(BASE+f"/app/risk-assessments?case_id={CASE['id']}&tab=laboratory",wait_until='networkidle')
        panel=page.locator('.risk-lab-panel')
        await panel.locator('label.el-radio').filter(has_text='组织新的检测').click();await panel.locator('textarea').first.fill('【模拟】准备真实测量的检测任务')
        await panel.get_by_role('button',name='保存本版验证选择',exact=True).click()
        await panel.get_by_role('button',name='从事项创建验证任务',exact=True).click()
        task_dialog=page.get_by_role('dialog',name='从事项创建验证任务',exact=True);await expect(task_dialog).to_contain_text('【模拟】验证产品')
        await page.set_viewport_size({'width':390,'height':844});await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(OUT/'lab-task-create-mobile.png'),full_page=True)
        await page.set_viewport_size({'width':1500,'height':1050})
        await task_dialog.locator('.el-select').click();await page.get_by_role('option',name='【模拟】有效检测配置',exact=True).click()
        await task_dialog.get_by_role('button',name='确认创建待执行任务',exact=True).click()
        await page.wait_for_url('**/app/tasks/'+TASK+'**')
        await expect(page.locator('.risk-task-origin')).to_contain_text('【模拟】准备真实测量的检测任务')
        await page.goto(BASE+'/app/tasks/'+TASK,wait_until='networkidle')
        await expect(page.locator('.risk-task-origin')).to_contain_text(CASE['code'])
        await page.get_by_role('button',name='返回来源事项验证与回流',exact=True).click()
        await expect(page.locator('.risk-lab-panel .execution-return')).to_be_visible()
        assert state['task_creates']==1
        await page.set_viewport_size({'width':390,'height':844});await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(OUT/'lab-paths-mobile.png'),full_page=True)
        state['bad_origin']=True
        await page.goto(BASE+'/app/tasks/'+TASK,wait_until='networkidle')
        await expect(page.locator('.risk-task-origin')).to_contain_text('来源验证不可访问')
        await expect(page.get_by_role('button',name='返回来源事项验证与回流',exact=True)).to_have_count(0)
        assert not errors and not unexpected and not old.base.unexpected,(errors,unexpected,old.base.unexpected)
        result={'passed':True,'mode':'isolated API fixtures','planning_before_final_review':True,'three_paths_separated':True,
            'report_without_task_intake_and_return':True,'unknown_time_preserved':True,'task_created_only_on_confirmation':True,'origin_survives_refresh_without_query':True,
            'return_to_original_case_and_version':True,'revoked_origin_clears_return_action':True,'desktop_mobile':True,'real_business_rows_written':False,'page_errors':errors}
        (OUT/'lab-paths-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
        await browser.close()

if __name__=='__main__':asyncio.run(main())
