"""Exercise task-bound registration/import in Chromium with intercepted API only."""
import asyncio,json
from urllib.parse import parse_qs,urlparse
from uuid import uuid4
from playwright.async_api import async_playwright,expect
import remaining_pagination_browser as base

TASK=base.TASK;LINK,PRODUCT,BATCH,DEVICE,SAMPLE,SESSION=[str(uuid4()) for _ in range(6)]
state={'samples':[],'sessions':[],'measurements':[],'preview':None,'writes':[],'bad_import':True}
errors=[]


def context():
    return {'context_hash':'fixture-context','task_scope':{'task_id':TASK,'product_id':PRODUCT,'quality_product_id':PRODUCT,
        'quality_batch_id':BATCH,'product_name':'【模拟】验证产品','product_category':'隔离产品','production_date':None,
        'product_sku_id':None,'batch_id':None,'production_batch_ref':'ISOLATED-BATCH','unit_serial_ref':'ISOLATED-UNIT','input_mode':'measurement','issues':[]},
        'images':[],'samples':[{'id':r['id'],'label':r['name'],'kind':'platform_sample','issues':[]} for r in state['samples']],
        'sessions':[{'id':r['id'],'label':r['name'],'code':r['code'],'sample_ids':r['data']['sample_ids'],'production_date':r['data']['production_date']} for r in state['sessions']],
        'measurements':state['measurements'],'reports':[],'policies':[],'truncated':{'samples':False,'sessions':False,'measurements':False}}


async def handle(route):
    req=route.request;url=urlparse(req.url);path=url.path.removeprefix('/api/v1');q=parse_qs(url.query);data=None;status=200
    if path==f'/tasks/{TASK}':data={'id':TASK,'org_id':'fixture-org','risk_verification_id':LINK,'product_id':PRODUCT,'quality_product_id':PRODUCT,
        'status':'pending','priority':5,'supervision':True,'image_urls':[],'has_result':False,'has_stability':False,'created_at':base.STAMP,'spec_code':'隔离配置'}
    elif path==f'/risk-laboratory-verifications/{LINK}/task-origin':data={'link_id':LINK,'case_id':base.CASE['id'],'case_code':'ISOLATED-CASE',
        'case_title':'【模拟】来源事项','assessment_id':str(uuid4()),'assessment_version':2,'purpose':'【模拟】核对温升','task_id':TASK,'request_stage':'preliminary'}
    elif path==f'/inspection-execution/tasks/{TASK}/context' or path==f'/inspection-execution/tasks/{TASK}/context-selection':data=context()
    elif path.startswith('/quality-supervision/options/'):
        kind=path.split('/')[-1]
        rows=[{'value':DEVICE,'label':'【模拟】已有设备'}] if kind=='devices' else [{'value':r['id'],'label':r['name']} for r in state['samples']] if kind=='samples' else []
        selected=q.get('selected_ids',[]);data={'items':rows,'selected':[r for r in rows if r['value'] in selected],
            'unavailable_selected_ids':[],'has_more':False,'total':len(rows),'page':1,'size':20}
    elif path in ['/samples','/inspection-sessions']:
        rows=state['samples' if path=='/samples' else 'sessions']
        if req.method=='POST':
            body=req.post_data_json;state['writes'].append({'path':path,'body':body});d=body['data']
            assert d['task_id']==TASK
            if path=='/samples':
                assert d['quality_product_id']==PRODUCT and d['quality_batch_id']==BATCH and d['unit_serial_ref']=='ISOLATED-UNIT'
                assert d['product_sku_id'] is None and d['sampled_at'].startswith('2026-01-02')
            else:assert d['sample_ids']==[SAMPLE] and d['device_ids']==[DEVICE] and d['adaptive_enabled'] is False
            if path=='/inspection-sessions':d['test_items']=d.get('required_items',[])+d.get('candidate_items',[])
            data={'id':SAMPLE if path=='/samples' else SESSION,'code':'ISOLATED','name':body['name'],'version':1,'status':'active' if path=='/samples' else 'collecting','data':d}
            rows.append(data)
        else:data={'items':rows,'total':len(rows),'page':1,'size':20}
    elif path==f'/inspection-sessions/{SESSION}/measurements':data=[m['data'] for m in state['measurements']]
    elif path==f'/inspection-sessions/{SESSION}/imports/preview':
        state['writes'].append({'path':path});state['preview']=str(uuid4())
        data={'preview_id':state['preview'],'can_confirm':not state['bad_import'],'valid_count':0 if state['bad_import'] else 1,
            'errors':[{'row':2,'message':'样品或设备未绑定此会话'}] if state['bad_import'] else [],
            'rows':[] if state['bad_import'] else [{'event_id':'isolated-trial','sample_id':SAMPLE,'device_id':DEVICE,'item':'temperature','value':11,'unit':'K'}]}
    elif path==f'/inspection-sessions/{SESSION}/imports/confirm':
        assert q['preview_id']==[state['preview']] and not state['bad_import'];state['writes'].append({'path':path})
        state['measurements']=[{'id':str(uuid4()),'session_id':SESSION,'sample_id':SAMPLE,'validation_status':'accepted',
            'data':{'event_id':'isolated-trial','item':'temperature','value':11,'unit':'K','method':'fixture','conditions':{},'quality_flag':'valid','measured_at':'2026-01-03T00:00:00Z'}}]
        data={'accepted':1,'duplicate':0}
    elif path=='/results/execution-options':data=[]
    else:await base.handle(route);return
    await route.fulfill(status=status,json={'success':True,'data':data})


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);ctx=await browser.new_context(viewport={'width':1500,'height':1050})
        stored={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'reviewer','piap_org_id':'fixture-org','piap_username':'fixture'}
        await ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(stored)+'))sessionStorage.setItem(k,v)')
        await ctx.route('**/api/v1/**',handle);page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(base.BASE+f'/app/tasks/{TASK}',wait_until='networkidle')
        panel=page.locator('.measurement-panel');await expect(panel.get_by_text('样品与原始测量准备',exact=True)).to_be_visible()
        await expect(panel.get_by_role('button',name='分析检测过程',exact=True)).to_have_count(0)
        await panel.get_by_role('button',name='登记实物样品',exact=True).click()
        sample=page.get_by_role('dialog',name='登记实物样品');await expect(sample.locator('.el-date-editor input')).to_have_value('')
        await sample.get_by_role('button',name='登记',exact=True).click();assert not state['samples']
        await sample.locator('.el-date-editor input').fill('2026-01-02 08:00:00');await sample.locator('.el-date-editor input').press('Enter')
        await sample.locator('input').first.fill('【模拟】原始样品标签')
        await sample.get_by_role('button',name='登记',exact=True).click()
        form=page.get_by_role('dialog',name='配置检测批次');await expect(form).to_be_visible()
        assert state['samples'][0]['data']['sampled_at'].startswith('2026-01-02')
        await form.get_by_role('group',name='设备分页选择',exact=True).locator('.el-select').click();await page.get_by_role('option',name='【模拟】已有设备',exact=True).click();await page.keyboard.press('Escape')
        await form.locator('.repeat-section').filter(has_text='必检项目').get_by_role('button',name='添加',exact=True).click()
        for label,value in [('检测项目','temperature'),('单位','K'),('检测方法','fixture')]:
            await form.locator('.el-form-item').filter(has=page.locator('.el-form-item__label',has_text=label)).filter(has=page.locator('input')).first.locator('input').first.fill(value)
        await form.get_by_role('button',name='保存采集会话',exact=True).click();await expect(form).not_to_be_visible()
        assert state['sessions'][0]['data']['production_date'] is None
        await panel.locator('input[type=file]').set_input_files({'name':'isolated.csv','mimeType':'text/csv','buffer':b'isolated,fixture'})
        await panel.get_by_role('button',name='校验与预览',exact=True).click();await expect(panel.get_by_text('样品或设备未绑定此会话',exact=True)).to_be_visible()
        await expect(panel.get_by_role('button',name='确认导入',exact=True)).to_be_disabled()
        state['bad_import']=False
        await panel.get_by_role('button',name='校验与预览',exact=True).click();await expect(panel.get_by_role('button',name='确认导入',exact=True)).to_be_enabled()
        await panel.get_by_placeholder('来源批次编号',exact=True).fill('isolated-new-source')
        await expect(panel.get_by_role('button',name='确认导入',exact=True)).to_have_count(0)
        await panel.get_by_role('button',name='校验与预览',exact=True).click()
        await panel.get_by_text('自定义文件列名',exact=True).click()
        await panel.get_by_placeholder('item',exact=True).fill('external_item')
        await expect(panel.get_by_role('button',name='确认导入',exact=True)).to_have_count(0)
        await panel.get_by_placeholder('item',exact=True).fill('item')
        await panel.get_by_role('button',name='校验与预览',exact=True).click()
        await panel.get_by_role('button',name='确认导入',exact=True).click()
        await expect(panel.get_by_role('button',name='使用本会话核对检测项目与复核',exact=True)).to_be_visible()
        await expect(panel.locator('.el-upload-list__item')).to_have_count(0)
        await panel.locator('input[type=file]').set_input_files({'name':'isolated-next.csv','mimeType':'text/csv','buffer':b'isolated,next'})
        await expect(panel.locator('.el-upload-list__item')).to_have_count(1)
        await page.reload(wait_until='networkidle');await expect(panel.get_by_text('isolated-trial',exact=True)).to_be_visible()
        await panel.get_by_role('button',name='使用本会话核对检测项目与复核',exact=True).click()
        execution=page.get_by_role('dialog',name='新建标准执行记录');await expect(execution).to_be_visible()
        assert parse_qs(urlparse(page.url).query)['session']==[SESSION]
        await expect(execution.locator('.el-form-item').filter(has_text='实际生产日期').locator('input')).to_have_value('')
        await execution.get_by_role('button',name='取消',exact=True).click()
        await expect(execution).not_to_be_visible()
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
        await page.wait_for_function("document.querySelector('.measurement-panel').getBoundingClientRect().right<=innerWidth+1")
        await panel.locator('h2').scroll_into_view_if_needed();await page.screenshot(path=str(base.OUT/'sample-bridge-mobile.png'))
        await panel.get_by_role('button',name='使用本会话核对检测项目与复核',exact=True).scroll_into_view_if_needed();await page.screenshot(path=str(base.OUT/'sample-bridge-import-mobile.png'))
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert not errors and not base.unexpected and not base.base.unexpected,(errors,base.unexpected,base.base.unexpected)
        assert len([w for w in state['writes'] if w['path'].endswith('/imports/confirm')])==1
        result={'passed':True,'api_mode':'isolated fixtures','quality_product_without_legacy_sku':True,'sampling_time_not_fabricated':True,
            'unknown_production_date_preserved':True,'sample_session_import_and_native_execution_entry':True,'invalid_file_confirmation_blocked':True,
            'refresh_restores_session_and_measurements':True,'source_change_invalidates_preview':True,'mapping_change_invalidates_preview':True,'next_file_can_be_selected_after_import':True,
            'desktop_and_mobile':True,'page_errors':errors,'live_business_rows_written':False}
        (base.OUT/'sample-bridge-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
        await browser.close()


if __name__=='__main__':asyncio.run(main())
