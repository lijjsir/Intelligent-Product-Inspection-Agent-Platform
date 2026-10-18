"""Real local optional validation, evidence return, new review and fixed reports."""
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/".codex_tmp/piap_quality_demo"
config=json.loads((OUT/"accounts.json").read_text(encoding="utf-8"))
BASE=config["url"]
CASE="90daba62-f80d-55b5-9d25-f05d0c0ffdfe"
MARKER="DEMO-QS-001-P5-VALIDATION"
SKIP="【演示】本次先依靠已接入的模拟资料完成分析，暂不需要实验室验证。"
VERIFY="【演示】补充温升使用条件的模拟验证资料，保留真实测量及标准适用性缺口。"
RETURN="【演示】模拟验证文字返回原事项，仅补充条件描述，不代表真实检测完成。"
progress_file=OUT/"phase5-browser-progress.json"
progress=json.loads(progress_file.read_text(encoding="utf-8")) if progress_file.exists() else {}
def checkpoint():progress_file.write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
errors,failures=[],[]

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    contexts,pages,headers={},{},{}
    for name in ("demo_analyst","demo_reviewer"):
        a=next(a for a in config["accounts"] if a["username"]==name)
        ctx=browser.new_context(viewport={"width":1500,"height":1050},timezone_id="Asia/Shanghai",accept_downloads=True)
        page=ctx.new_page();page.on("pageerror",lambda e:errors.append(str(e)));page.on("response",lambda r:failures.append(r.status) if r.status>=500 else None)
        page.goto(BASE+"/login",wait_until="networkidle");page.locator("#login-username").fill(name);page.locator("#login-password").fill(a["password"])
        page.get_by_role("button",name="登录",exact=False).click();page.wait_for_url("**/app/**")
        contexts[name],pages[name],headers[name]=ctx,page,{"Authorization":"Bearer "+page.evaluate("sessionStorage.getItem('piap_token')")}
    author,peer=pages.values()
    def get(path,name="demo_analyst"):
        r=contexts[name].request.get(BASE+"/api/v1"+path,headers=headers[name]);assert r.status==200,(path,r.status);return r.json()["data"]
    def workspace():return get(f"/risk-cases/{CASE}/workspace")
    def field(page,container,label):return container.locator('.el-form-item').filter(has=page.locator('label',has_text=re.compile('^'+re.escape(label)+'$'))).locator('textarea')
    def download(page,format,label,name):
        with page.expect_download(timeout=120000) as event:page.locator('.report-preview').get_by_role('button',name=label,exact=True).click()
        event.value.save_as(str(OUT/f"phase5-{name}.{format}"))
    before=workspace()
    if "base_assessment_id" not in progress:
        a=before["latest_assessment"];assert a["version"]==5
        progress.update(base_assessment_id=a["id"],base_content=a["demo_workflow"]["content"],base_review=a["review_comment"],base_record_ids=[r["id"] for r in before["records"]]);checkpoint()
    if not progress.get("skip_exports_verified"):
        author.goto(BASE+f"/app/risk-assessments?case_id={CASE}&tab=laboratory",wait_until="networkidle")
        panel=author.locator('.risk-lab-panel');expect(panel).to_be_visible()
        # Form labels discovered from the rendered page during reconnaissance.
        assert panel.locator('.el-form-item__label').all_text_contents()[:2]==['本版是否需要实验室验证','验证目的或跳过理由']
        rows=get(f"/risk-cases/{CASE}/laboratory-verifications")
        if not rows:
            panel.get_by_role('radio',name='暂不验证',exact=True).check();field(author,panel,'验证目的或跳过理由').fill(SKIP)
            panel.get_by_role('button',name='保存本版验证选择',exact=True).click();expect(panel).to_contain_text('演示已跳过')
        rows=get(f"/risk-cases/{CASE}/laboratory-verifications");progress['lab_id']=rows[0]['id'];checkpoint()
        panel.get_by_role('button',name='查看研判报告',exact=True).click();author.wait_for_url('**/app/risk-reports?case_id='+CASE)
        author.get_by_role('button',name='生成本版演示研判报告',exact=True).click();expect(author.locator('.report-preview')).to_be_visible()
        progress['skip_report_id']=get('/risk-reports?case_id='+CASE)[0]['id'];checkpoint()
        expect(author.locator('.report-preview')).to_contain_text('跳过验证')
        download(author,'pdf','导出 PDF','skipped');download(author,'docx','导出 Word','skipped')
        progress['skip_exports_verified']=True;checkpoint()
        author.screenshot(path=str(OUT/'phase5-skip-report-desktop.png'),full_page=True)
    if not progress.get('returned'):
        author.goto(BASE+f"/app/risk-assessments?case_id={CASE}&tab=laboratory",wait_until='networkidle');panel=author.locator('.risk-lab-panel')
        rows=get(f"/risk-cases/{CASE}/laboratory-verifications");link=next(r for r in rows if r['id']==progress['lab_id'])
        if link['mode']=='skip':
            panel.locator('label.el-radio').filter(has_text='需要验证资料').click();field(author,panel,'验证目的或跳过理由').fill(VERIFY)
            panel.get_by_role('button',name='保存本版验证选择',exact=True).click();expect(panel.locator('.lab-return')).to_be_visible()
        raw=get('/quality-data/records?page=1&size=200')['items'];record=next((r for r in raw if r.get('external_record_id')==MARKER),None)
        if not record:
            scope=workspace()['case']['scope']
            response=contexts['demo_analyst'].request.post(BASE+'/api/v1/quality-data/events',headers=headers['demo_analyst'],data={
                'record_type':'inspection_report','external_record_id':MARKER,'origin_label':'阶段五本地验收：模拟文字，非真实检测报告',
                'content':{'title':MARKER+'【模拟验证文字】','text':'【模拟验证资料】补充产品使用条件描述。没有真实温升读数，未核对正式标准，不是有效检测报告。'},
                'product_ref':{'product_id':scope['product_id'],'category_id':scope['category_id']},
                'enterprise_ref':{'enterprise_id':scope['enterprise_id']},'occurred_at':None,'data_nature':'synthetic',
                'provenance':{'simulation':True,'validation_link_id':progress['lab_id']}})
            assert response.status==201,response.status;record=response.json()['data']
        progress['returned_record_id']=record['id'];checkpoint()
        panel.get_by_role('button',name='刷新关联与资料',exact=True).click()
        block=panel.locator('.lab-return');expect(block).to_be_visible()
        block.locator('.el-form-item').filter(has=author.locator('label',has_text='已接入且确认同一对象的模拟检测资料')).locator('.el-select').click()
        author.get_by_role('option',name=re.compile(MARKER)).click();author.keyboard.press('Escape')
        field(author,block,'回流说明').fill(RETURN);block.get_by_role('button',name='关联资料并返回原事项',exact=True).click()
        expect(panel).to_contain_text('演示资料已回流')
        w=workspace();assert w['latest_assessment']['effective_status']=='needs_reassessment'
        assert len(w['records'])==len(progress['base_record_ids'])+1 and len(w['assessment_versions'])==5
        progress['returned']=True;checkpoint()
        author.screenshot(path=str(OUT/'phase5-returned-evidence-desktop.png'),full_page=True)
    author.goto(BASE+f'/app/risk-assessments?case_id={CASE}',wait_until='networkidle');flow=author.locator('.demo-risk-workflow')
    current=workspace()['latest_assessment']
    if current['id']==progress['base_assessment_id']:
        flow.get_by_role('button',name='创建新版演示草稿',exact=True).click();expect(flow.locator('.demo-draft-form')).to_be_visible();current=workspace()['latest_assessment']
    assert current['version']==6
    progress['new_assessment_id']=current['id'];checkpoint()
    if current['status']=='demo_draft':
        field(author,flow,'演示结论').fill('【演示】补充模拟验证资料后，温升线索仍待真实测量核实。')
        field(author,flow,'判断依据').fill('引用原投诉、舆情与阶段五模拟验证文字。新增材料仅补充使用条件描述，不能证明温升数值或标准符合性。')
        if not flow.get_by_role('checkbox',name=re.compile(MARKER)).is_checked():
            flow.locator('label.el-checkbox').filter(has_text=MARKER).click()
        flow.get_by_role('button',name='保存演示草稿',exact=True).click();expect(flow.get_by_role('button',name='提交本版演示复核',exact=True)).to_be_enabled()
        flow.get_by_role('button',name='提交本版演示复核',exact=True).click();expect(flow).to_contain_text('提交后内容锁定')
    peer.goto(BASE+f'/app/risk-assessments?case_id={CASE}',wait_until='networkidle');peer_flow=peer.locator('.demo-risk-workflow')
    if workspace()['latest_assessment']['status']=='demo_submitted':
        field(peer,peer_flow,'本版复核意见').fill('【演示】独立核对第 6 版引用的模拟验证资料，真实测量及标准适用性仍未知；仅通过演示流程复核。')
        peer_flow.get_by_role('button',name='演示复核通过',exact=True).click();expect(peer_flow).to_contain_text('第 6 版复核意见')
    current=workspace()['latest_assessment'];assert current['status']=='demo_reviewed' and current['probability'] is None and progress['returned_record_id'] in current['demo_workflow']['content']['cited_record_ids']
    author.goto(BASE+f'/app/risk-reports?case_id={CASE}',wait_until='networkidle')
    if not progress.get('new_report_id'):
        author.get_by_role('button',name='生成本版演示研判报告',exact=True).click();expect(author.locator('.report-preview')).to_be_visible()
        progress['new_report_id']=get('/risk-reports?case_id='+CASE)[0]['id'];checkpoint()
    else:author.goto(BASE+f"/app/risk-reports?case_id={CASE}&report={progress['new_report_id']}",wait_until='networkidle')
    report=get('/risk-reports/'+progress['new_report_id']);assert report['effective_status']=='demo_frozen'
    expect(author.locator('.report-preview')).to_contain_text('原研判第 5 版')
    if progress.get('followthrough_completed'):
        assert any(s['snapshot']['assessment_id']==current['id'] and s['effective_status']=='demo_confirmed' for s in report['snapshot']['sampling'])
    else:expect(author.locator('.report-preview')).to_contain_text('本研判版本尚无当前有效的已固定抽查建议')
    download(author,'pdf','导出 PDF','reviewed');download(author,'docx','导出 Word','reviewed')
    author.reload(wait_until='networkidle');expect(author.locator('.report-preview')).to_contain_text(MARKER)
    author.screenshot(path=str(OUT/'phase5-new-report-desktop.png'),full_page=True)
    author.set_viewport_size({'width':390,'height':844});author.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    assert author.evaluate('document.documentElement.scrollWidth<=innerWidth')
    author.locator('.report-preview h2').scroll_into_view_if_needed();author.screenshot(path=str(OUT/'phase5-report-mobile.png'),full_page=True)
    author.goto(BASE+f'/app/laboratory?case_id={CASE}',wait_until='networkidle');expect(author.locator('.risk-lab-panel')).to_contain_text('演示资料已回流')
    expect(author.locator('.demo-lab-workspace')).to_contain_text('可选验证');assert author.evaluate('document.documentElement.scrollWidth<=innerWidth')
    author.locator('.lab-history').scroll_into_view_if_needed();author.screenshot(path=str(OUT/'phase5-lab-mobile.png'),full_page=True)
    peer.goto(BASE+f"/app/risk-reports?case_id={CASE}&report={progress['new_report_id']}",wait_until='networkidle');expect(peer.locator('.report-preview')).to_contain_text('独立复核')
    peer.locator('.report-preview').get_by_role('button',name='查看原研判版本',exact=True).click();peer.wait_for_url('**/app/risk-assessments?case_id=**');expect(peer_flow).to_contain_text('第 6 版复核意见')
    old=get('/risk-assessments/'+progress['base_assessment_id']);assert old['demo_workflow']['content']==progress['base_content'] and old['review_comment']==progress['base_review']
    assert get('/risk-reports/'+progress['skip_report_id'])['effective_status']=='historical_snapshot'
    assert not get('/quality-supervision/sampling-candidates')['items']
    assert not errors and not failures,(errors,failures)
    result={'stage':5,'passed':True,'api_mode':'real_local_mysql','case_id':CASE,**{k:progress[k] for k in ['base_assessment_id','new_assessment_id','skip_report_id','new_report_id','lab_id','returned_record_id']},
        'skip_validation_report_exported':True,'optional_task_not_created':True,'same_case_evidence_return':True,'new_version_independently_reviewed':True,
        'historical_reports_fixed':True,'pdf_docx_downloaded':True,'desktop_mobile_verified':True,'formal_candidates_empty':True,'real_model_called':False,'page_errors':errors,'http_5xx':failures}
    (OUT/'phase5-browser-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));browser.close()
