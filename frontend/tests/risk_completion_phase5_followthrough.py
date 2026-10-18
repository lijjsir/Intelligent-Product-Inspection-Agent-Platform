"""Carry the reviewed sixth version through collaboration and a fresh suggestion."""
import json
from pathlib import Path
from playwright.sync_api import expect,sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'.codex_tmp/piap_quality_demo'
config=json.loads((OUT/'accounts.json').read_text(encoding='utf-8'));BASE=config['url']
progress_file=OUT/'phase5-browser-progress.json';progress=json.loads(progress_file.read_text(encoding='utf-8'));CASE='90daba62-f80d-55b5-9d25-f05d0c0ffdfe'
PUBLIC='【演示第6版协同】已核对模拟验证文字，仍缺少真实测量和标准适用性核对，抽查数量与安排保持未知。'
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);contexts,pages,headers={},{},{}
    for name in ['demo_analyst','demo_reviewer']:
        a=next(a for a in config['accounts'] if a['username']==name);ctx=browser.new_context(viewport={'width':1500,'height':1050},timezone_id='Asia/Shanghai');page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE+'/login',wait_until='networkidle');page.locator('#login-username').fill(name);page.locator('#login-password').fill(a['password']);page.get_by_role('button',name='登录',exact=False).click();page.wait_for_url('**/app/**')
        contexts[name],pages[name],headers[name]=ctx,page,{'Authorization':'Bearer '+page.evaluate("sessionStorage.getItem('piap_token')")}
    author,peer=pages.values()
    def get(path,name='demo_analyst'):
        r=contexts[name].request.get(BASE+'/api/v1'+path,headers=headers[name]);assert r.status==200,(path,r.status);return r.json()['data']
    w=get(f'/risk-cases/{CASE}/workspace');assessment=w['latest_assessment'];assert assessment['version']==6 and assessment['status']=='demo_reviewed'
    author.goto(BASE+f'/app/risk-assessments?case_id={CASE}&tab=collaboration',wait_until='networkidle');panel=author.locator('.risk-collaboration-panel');expect(panel).to_be_visible()
    links=get(f'/risk-cases/{CASE}/collaborations');link=next((r for r in links if r['assessment_id']==assessment['id']),None)
    if not link:
        panel.get_by_role('button',name='发起本版同单位协同',exact=True).click();dialog=author.get_by_role('dialog',name='发起同单位研判协同',exact=True)
        dialog.locator('.el-select').first.click();author.get_by_role('option',name='demo_reviewer',exact=True).click();dialog.get_by_role('textbox',name='协同问题',exact=True).fill('【演示】基于第6版及模拟验证资料，重新核对证据缺口、建议范围和限制。')
        dialog.get_by_role('button',name='创建协同并关联本版',exact=True).click();expect(dialog).not_to_be_visible()
        link=next(r for r in get(f'/risk-cases/{CASE}/collaborations') if r['assessment_id']==assessment['id'])
    panel.get_by_role('button',name='进入会议讨论',exact=True).click();author.wait_for_url('**/app/meetings?room_id='+link['room_id']);expect(author.locator('.risk-meeting-context')).to_contain_text('固定第 6 版')
    if not any(m['content']==PUBLIC for m in get('/risk-collaborations/'+link['id']).get('discussion',[])):
        author.get_by_role('textbox',name='公共消息',exact=True).fill(PUBLIC);author.locator('.composer-actions').get_by_role('button',name='发送',exact=True).click();expect(author.get_by_text(PUBLIC,exact=True)).to_be_visible()
    current=get('/risk-collaborations/'+link['id']);view='pending' if current['status']=='pending' else 'processed'
    peer.goto(BASE+f"/app/collab?view={view}&work_item=action_request:{link['message_id']}",wait_until='networkidle');expect(peer.locator('.risk-collab-notice')).to_contain_text('固定第 6 版')
    if current['status']=='pending':
        peer.get_by_role('button',name='接受',exact=True).click();dialog=peer.get_by_role('dialog',name='接受工作项',exact=True);dialog.locator('textarea').fill('【演示】接收第6版协同');dialog.get_by_role('button',name='确认接受',exact=True).click();expect(dialog).not_to_be_visible();peer.goto(BASE+f"/app/collab?view=processed&work_item=action_request:{link['message_id']}",wait_until='networkidle')
    if get('/risk-collaborations/'+link['id'])['status']=='accepted':
        peer.get_by_role('button',name='完成',exact=True).click();dialog=peer.get_by_role('dialog',name='完成工作项',exact=True);dialog.locator('textarea').fill('【演示】第6版仍保留真实测量缺口，建议按明确对象继续核查，数量、地点、批次和时间未知。');dialog.get_by_role('button',name='确认完成',exact=True).click();expect(dialog).not_to_be_visible()
    assert get('/risk-collaborations/'+link['id'])['status']=='done'
    author.goto(BASE+f'/app/sampling-plans?case_id={CASE}',wait_until='networkidle');expect(author.locator('.candidate-card')).to_have_count(1)
    author.locator('.candidate-card').get_by_role('button').click();detail=author.locator('.suggestion-detail');expect(detail).to_be_visible()
    row=next(r for r in get('/demo-sampling/suggestions?case_id='+CASE) if r['snapshot']['assessment_id']==assessment['id'])
    if row['status']=='demo_draft':
        for index,text in enumerate(['【演示】补充模拟验证资料后，温升线索仍有真实证据缺口，建议对同一产品进一步核查。','核对产品型号与使用条件，取得真实温升测量和标准适用依据后，再确定抽样数量与安排。','全部模拟资料；数量、批次、地点、时间及资源可用性未知；不构成正式抽查或检测指令。']):detail.locator('textarea').nth(index).fill(text)
        detail.get_by_role('button',name='保存演示草稿',exact=True).click();expect(detail.get_by_role('button',name='确认并固定演示建议',exact=True)).to_be_enabled();detail.get_by_role('button',name='确认并固定演示建议',exact=True).click();expect(detail).to_contain_text('演示建议已固定')
    row=get('/demo-sampling/suggestions/'+row['id']);assert row['is_current'] and row['status']=='demo_confirmed' and any(m['content']==PUBLIC for m in row['snapshot']['opinions'])
    author.screenshot(path=str(OUT/'phase5-current-suggestion.png'),full_page=True)
    author.goto(BASE+f'/app/risk-reports?case_id={CASE}',wait_until='networkidle');author.get_by_role('button',name='生成本版演示研判报告',exact=True).click();expect(author.locator('.report-preview')).to_be_visible()
    report=get('/risk-reports?case_id='+CASE)[0];frozen=get('/risk-reports/'+report['id']);assert frozen['effective_status']=='demo_frozen'
    assert any(s['snapshot']['assessment_id']==assessment['id'] and s['effective_status']=='demo_confirmed' for s in frozen['snapshot']['sampling'])
    assert not errors,errors
    if progress['new_report_id']!=report['id']:progress.setdefault('before_followthrough_report_id',progress['new_report_id'])
    progress.update(new_report_id=report['id'],current_collaboration_id=link['id'],current_suggestion_id=row['id'],followthrough_completed=True)
    progress_file.write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
    result={'stage':5,'passed':True,'case_id':CASE,'assessment_version':6,'collaboration_id':link['id'],'suggestion_id':row['id'],'report_id':report['id'],'new_version_collaboration_and_suggestion_completed':True,'real_model_called':False}
    (OUT/'phase5-followthrough-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));browser.close()
