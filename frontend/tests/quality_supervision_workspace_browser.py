"""Isolated UI regression; fixture APIs never connect to a deployed database."""
import copy
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("PIAP_UI_BASE", "http://127.0.0.1:5173")
OUT = Path(__file__).resolve().parents[2] / ".codex_tmp" / "quality-supervision-workspace"
OUT.mkdir(parents=True, exist_ok=True)
STAMP = "2026-10-17T01:00:00Z"
CASE = "case-outside-first-page"
record = {"id": "source-1", "source_id": "source", "record_type": "public_opinion", "display_no": "ZL-0001",
    "external_record_id": "EXT-1", "occurred_at": STAMP, "received_at": STAMP, "content": {"text": "某产品使用时出现异常温升"},
    "content_hash": "fixture", "enterprise_ref": {"name": "企业A"}, "product_ref": {}, "location": {},
    "attachment_ids": [], "provenance": {"origin_label": "原始公开记录"}, "data_nature": "observed",
    "authorization_scope": "org", "normalization_status": "normalized", "normalization_errors": [], "created_by": "submitter"}
extra = {**copy.deepcopy(record), "id": "source-2", "display_no": "ZL-0002", "content": {"text": "新接入检测报告，供补充研判"}}
case = {"id": CASE, "org_id": "org", "code": "RISK-001", "title": "温升风险研判事项", "scope_type": "product",
    "scope": {"name": "产品A"}, "status": "risk_assessed", "evidence_ids": ["ev-1"], "source_record_ids": [record["id"]],
    "created_by": "submitter", "created_at": STAMP, "updated_at": STAMP}
assessment = {"id": "assessment-2", "risk_case_id": CASE, "version": 2, "risk_type": "温升异常", "risk_level": "high",
    "scope": case["scope"], "evidence_ids": ["ev-1"], "standard_matches": [{"standard_no": "引用标准A", "clause_ref": "4.2"}],
    "conflicts": [], "missing_inputs": [], "possible_causes": ["需进一步验证散热条件"], "recommendations": ["建议补充代表性实物验证"],
    "trust_status": "verified", "probability": None, "policy_version": None, "status": "accepted", "effective_status": "accepted",
    "review_comment": "专家已核对来源和证据范围", "reviewed_at": STAMP, "submitted_by": "submitter", "reviewed_by": "reviewer",
    "created_at": STAMP, "source_validation": {"blockers": [], "uncertainties": []}}
old = {**copy.deepcopy(assessment), "id": "assessment-1", "version": 1, "status": "draft", "effective_status": "draft", "review_comment": None}
state = {"case": copy.deepcopy(case), "assessments": [copy.deepcopy(assessment), old], "fail_workspace": False}
requests, unexpected, errors = [], [], []


def paged(items):
    return {"items": items, "total": len(items), "page": 1, "size": 20}


def handle(route):
    request = route.request
    url = urlparse(request.url)
    path = url.path.removeprefix("/api/v1")
    query = parse_qs(url.query)
    requests.append((request.method, path))
    data, status = None, 200
    if path == "/runtime-context":
        data = {"execution_mode": "business", "label": "业务环境", "notice": None, "organization_slug": None, "case_code": None}
    elif path == "/users/me":
        data = {"id": "reviewer", "org_id": "org", "username": "expert", "email": "expert@example.com", "role": "expert",
            "is_active": True, "effective_permissions": ["quality", "quality_material_submit", "quality_material_read_business", "quality_ingestion_manage", "task", "result", "inspection_standard_library_read", "report_read", "report_generate"]}
    elif path == "/risk-cases" and request.method == "GET":
        data = paged([])  # The requested case is deliberately outside this list page.
    elif path == f"/risk-cases/{CASE}/workspace":
        status = 503 if state["fail_workspace"] else 200
        data = {"case": state["case"], "records": [record, extra] if len(state["case"]["source_record_ids"]) > 1 else [record],
            "unavailable_source_ids": [], "latest_assessment": state["assessments"][0],
            "assessment_versions": [{k: item.get(k) for k in ["id", "version", "status", "risk_level", "created_at", "reviewed_at"]} for item in state["assessments"]]}
        if state.get('formal_completion'):
            data['workflow_context'] = {'enabled':True, 'execution_mode':'business', 'can_author':True, 'eligible':True,
                'assessment_id':state['assessments'][0]['id'], 'basis_hash':'a'*64, 'blockers':[], 'boundary':'隔离正式业务界面契约'}
    elif path == f'/risk-cases/{CASE}/collaborations':
        data = []
    elif path == f'/risk-cases/{CASE}/laboratory-options':
        data = {'tasks':[], 'records':[]}
    elif path in [f'/risk-cases/{CASE}/laboratory-tasks-options', f'/risk-cases/{CASE}/laboratory-records-options']:
        chosen = [{'id':'task-formal','label':'隔离检测任务','status':'pending'}] if 'tasks-options' in path and query.get('selected_ids') else []
        data = {'items':[], 'selected':chosen, 'unavailable_selected_ids':[], 'total':0, 'page':1, 'size':20}
    elif path == f'/risk-cases/{CASE}/laboratory-verifications':
        if request.method == 'POST':
            payload = request.post_data_json
            assert payload['expected_basis_hash'] == 'a'*64 and payload['mode'] == 'skip'
            state['lab'] = {'id':'lab-formal', 'status':'skipped', 'revision':1, 'created_by':'reviewer',
                'case_id':CASE, 'case_code':'RISK-001', 'assessment_id':payload['assessment_id'], 'assessment_version':3,
                'mode':'skip', 'purpose':payload['purpose'], 'task_id':None, 'record_ids':[], 'is_latest_assessment':True,
                'issues':[], 'boundary':'隔离正式业务验证关联', 'events':[]}
            data = state['lab']
        else: data = [state['lab']] if state.get('lab') else []
    elif path == f'/risk-cases/{CASE}/reports':
        payload = request.post_data_json
        assert payload == {'assessment_id':state['assessments'][0]['id'], 'expected_basis_hash':'a'*64}
        state['report'] = {'id':'report-formal', 'title':'【研判报告】RISK-001', 'frozen_at':STAMP, 'effective_status':'frozen',
            'source_issues':[], 'snapshot_hash':'fixture', 'snapshot':{'case_id':CASE, 'assessment_id':payload['assessment_id'], 'assessment_version':3, 'source_refs':[]},
            'sections':[{'title':'独立复核', 'paragraphs':['隔离正式界面核验；真实来源和复核由后端另行集成测试。']}]}
        data = state['report']
    elif path == '/risk-reports':
        data = [state['report']] if state.get('report') else []
    elif path == '/risk-report-pages':
        data = {'items':[state['report']] if state.get('report') else [], 'next_cursor':None, 'has_more':False, 'size':20, 'notice':'打开报告核对当前依据'}
    elif path == '/risk-reports/report-formal':
        data = state['report']
    elif path == '/risk-sampling/suggestions':
        data = []
    elif path == '/risk-sampling/candidates':
        data = {'items':[], 'blockers':[], 'boundary':'隔离业务建议'}
    elif path == '/risk-laboratory-verifications/lab-formal/execution-results':
        if request.method == 'GET':
            number = int(query.get('page', ['1'])[0])
            data = {'page':number, 'size':20, 'total':21, 'items':[
                {'id':'run-blocked', 'row_version':2, 'reviewed_at':STAMP, 'eligible':False, 'issues':['原报告尚未明确共享'], 'summary':None, 'definition_hash':None, 'already_returned':False},
                {'id':'run-valid' if number == 1 else 'run-next-page', 'row_version':2, 'reviewed_at':STAMP, 'eligible':True,
                    'issues':[], 'summary':{'item_verdict':'fail', 'product_verdict':'not_assessed'}, 'definition_hash':'c'*64,
                    'already_returned':bool(state['lab'].get('execution_returns'))}]}
        else:
            payload = request.post_data_json
            assert payload['expected_revision'] == state['lab']['revision'] and payload['run_id'] == 'run-valid' and payload['expected_run_hash'] == 'c'*64
            if state.get('return_conflict'):
                route.fulfill(status=409, content_type='application/json', body=json.dumps({'error':{'code':'conflict', 'message':'检测结果已变化，请刷新后重试'}}))
                return
            state['lab'] = {**state['lab'], 'revision':state['lab']['revision']+1, 'status':'returned', 'execution_returns':[
                {'id':'return-1', 'ref':{'run_id':'run-valid', 'task_id':'task-formal', 'row_version':2, 'definition_hash':'c'*64},
                 'note':payload['note'], 'summary':{'item_verdict':'fail', 'product_verdict':'not_assessed'}, 'returned_by':'reviewer',
                 'returned_at':STAMP, 'withdrawn_at':None, 'issues':[]}]}
            data = state['lab']
    elif path == '/risk-laboratory-verifications/lab-formal/execution-results/return-1/withdraw':
        payload = request.post_data_json
        assert payload['expected_revision'] == state['lab']['revision'] and payload['note'].strip()
        state['lab']['execution_returns'][0].update(withdrawn_at=STAMP, withdrawal_note=payload['note'])
        state['lab']['revision'] += 1
        data = state['lab']
    elif path.startswith("/risk-assessments/"):
        data = next(item for item in state["assessments"] if item["id"] == path.split("/")[-1])
    elif path == f"/risk-cases/{CASE}/sources":
        assert request.post_data_json == {"source_record_ids": [extra["id"]]}
        state["case"] = {**state["case"], "source_record_ids": [record["id"], extra["id"]], "status": "awaiting_evidence"}
        state["assessments"][0] = {**state["assessments"][0], "effective_status": "needs_reassessment",
            "source_validation": {"blockers": [{"code": "risk_evidence_set_changed", "message": "本案关联证据已更新，请生成新版草稿后重新复核"}], "uncertainties": []}}
        data = state["case"]
    elif path == f"/risk-cases/{CASE}/reviews":
        payload = request.post_data_json
        assert payload["assessment_id"] == state["assessments"][0]["id"]
        state["assessments"][0] = {**state["assessments"][0], "status": "accepted", "effective_status": "accepted", "review_comment": payload["comment"]}
        state["case"]["status"] = "risk_assessed"
        data = state["assessments"][0]
    elif path == "/risk-policies":
        data = []
    elif path == "/quality-data/records":
        items = [record, extra] if "keyword" in query else [record]
        if query.get("record_type") == ["consumer_complaint"]:
            items = []
        data = paged(items)
    elif path == "/quality-data/records/source-1":
        data = record
    elif path == "/quality-data/records/source-1/evidence":
        data = []
    elif path == "/quality-data/sources":
        data = [{"id": "source", "name": "公开来源", "status": "active"}]
    elif path in ["/quality-products/options", "/quality-products/catalog"]:
        data = {"categories": [], "products": []}
    elif path == "/quality-data/reference-options":
        data = {"categories": [], "products": [], "enterprises": []}
    elif path == "/quality-data/records/source-1/context":
        data = {"record":record,"objects":{key:{"id":None,"name":None,"status":"unlinked"} for key in ["enterprise","product","category"]},
            "source":{"id":"source","name":"公开来源","status":"active"},"attachments":[],"unavailable_attachment_ids":[],"related_cases":[]}
    elif path == "/quality-data/events" and request.method == "POST":
        assert request.post_data_json["record_type"] == "public_opinion"
        data = record
    elif path == "/quality-supervision/settings":
        data = {"enabled": True, "laboratory_validation_enabled": True}
    elif path == "/quality-supervision/analytics":
        data = {"summary": "隔离态势", "confirmed_categories": [], "plans": [], "sessions": [], "dimensions": {}, "metric_status": "分母不足", "limitations": []}
    elif path == "/quality-supervision/sampling-candidates":
        data = {"items": [{"id": CASE, "code": "RISK-001", "title": case["title"], "assessment_version": 2}], "excluded_count": 0}
    elif path in ["/sampling-plans", "/inspection-sessions", "/devices", "/enterprises"]:
        data = paged([])
    elif path == "/users/assignees":
        data = []
    else:
        unexpected.append((request.method, path))
        status = 404
    route.fulfill(status=status, content_type="application/json", body=json.dumps({"data": data, "message": "测试响应"}))


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1500, "height": 1050}, timezone_id="Asia/Shanghai")
    stored = {"piap_token": "isolated-ui-token", "piap_role": "expert", "piap_roles": '["expert"]',
        "piap_user_id": "reviewer", "piap_org_id": "org", "piap_username": "expert"}
    context.add_init_script("for(const [key,value] of Object.entries("+json.dumps(stored)+"))sessionStorage.setItem(key,value)")
    context.route("**/api/v1/**", handle)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE+f"/app/risk-assessments?case_id={CASE}", wait_until="networkidle")
    expect(page.get_by_role("heading", name=case["title"], exact=True)).to_be_visible()
    expect(page.get_by_text(assessment["review_comment"], exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="查看抽查候选", exact=True)).to_be_enabled()
    expect(page.locator(".agent-rail")).to_have_count(0)
    page.reload(wait_until="networkidle")
    expect(page.get_by_text(assessment["review_comment"], exact=True)).to_be_visible()
    page.get_by_role("tab", name="原始资料（1）").click()
    expect(page.locator(".source-record").get_by_text(record["content"]["text"], exact=True)).to_be_visible()
    page.get_by_role("button", name="查看原件与附件").click()
    expect(page.get_by_role("heading", name="原始资料详情", exact=True)).to_be_visible()
    page.goto(BASE+f"/app/risk-assessments?case_id={CASE}", wait_until="networkidle")
    page.get_by_role("tab", name="版本与复核（2）").click()
    page.get_by_role("button", name="第 1 版", exact=False).click()
    expect(page.get_by_text("历史版本，仅供查阅", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="独立复核通过", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="查看抽查候选", exact=True)).to_be_disabled()
    page.get_by_role("tab", name="版本与复核（2）").click()
    page.get_by_role("button", name="第 2 版", exact=False).click()
    expect(page.get_by_role("button", name="查看抽查候选", exact=True)).to_be_enabled()
    page.screenshot(path=str(OUT/"risk-workspace-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("heading", name=case["title"], exact=True)).to_be_visible()
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows"
    page.screenshot(path=str(OUT/"risk-workspace-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1500, "height": 1050})
    page.get_by_role("button", name="查看抽查候选", exact=True).click()
    expect(page.get_by_text("已带入来源研判事项。", exact=False)).to_be_visible()
    expect(page.locator(".agent-rail")).to_have_count(0)
    page.goto(BASE+"/app/risk-cases", wait_until="networkidle")
    page.get_by_role("button", name="公开舆情", exact=False).click()
    page.get_by_role("button", name="接入投诉或舆情", exact=True).click()
    expect(page.get_by_role("dialog", name="提交质量资料")).to_be_visible()
    expect(page.locator(".quality-intake-form").get_by_text("舆情信息", exact=True)).to_be_visible()
    page.get_by_role("textbox", name="原始内容或附件（至少一种）").fill("统一入口测试原文")
    page.get_by_role("button", name="提交", exact=True).click()
    expect(page.get_by_role("dialog", name="提交质量资料")).not_to_be_visible()
    assert sum(method == "POST" and path == "/quality-data/events" for method, path in requests) == 1
    page.goto(BASE+f"/app/risk-assessments?case_id={CASE}", wait_until="networkidle")
    page.get_by_role("button", name="关联补充资料", exact=True).click()
    source_select = page.get_by_role("dialog", name="关联补充资料").get_by_role("combobox")
    source_select.fill("新接入")
    page.get_by_role("option", name="新接入检测报告", exact=False).click()
    page.get_by_role("dialog", name="关联补充资料").get_by_role("heading", name="关联补充资料", exact=True).click()
    page.get_by_role("button", name="关联到本事项", exact=True).click()
    expect(page.get_by_text("来源变化，待重新研判", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="查看抽查候选", exact=True)).to_be_disabled()
    expect(page.get_by_text(assessment["review_comment"], exact=True)).to_be_visible()
    page.get_by_role("tab", name="原始资料（2）").click()
    expect(page.locator(".source-record")).to_have_count(2)
    state["fail_workspace"] = True
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("button", name="重试详情", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name=case["title"], exact=True)).to_have_count(0)
    state["fail_workspace"] = False
    page.get_by_role("button", name="重试详情", exact=True).click()
    expect(page.get_by_role("heading", name=case["title"], exact=True)).to_be_visible()
    page.goto(BASE+"/app/laboratory", wait_until="networkidle")
    expect(page.locator(".task-relationship")).to_be_visible()
    expect(page.locator(".agent-rail")).to_have_count(0)
    draft = {**copy.deepcopy(assessment), "id": "assessment-3", "version": 3, "status": "awaiting_review", "effective_status": "awaiting_review", "review_comment": None}
    state["assessments"].insert(0, draft)
    page.goto(BASE+f"/app/risk-assessments?case_id={CASE}", wait_until="networkidle")
    page.get_by_role("button", name="独立复核通过", exact=True).click()
    page.locator(".el-message-box textarea").fill("复核当前版本及新增证据")
    page.locator(".el-message-box").get_by_role("button", name="确定", exact=True).click()
    expect(page.get_by_text("复核当前版本及新增证据", exact=True)).to_be_visible()
    # These are fixture UI contracts; actual evidence and independent-review gates
    # are exercised separately in test_formal_risk_completion.py.
    state['formal_completion'] = True
    page.reload(wait_until='networkidle')
    page.get_by_role('tab', name='协同讨论', exact=True).click()
    expect(page.get_by_role('button', name='发起本版同单位协同', exact=True)).to_be_enabled()
    expect(page.locator('.risk-collaboration-panel')).not_to_contain_text('演示')
    page.get_by_role('tab', name='可选验证', exact=True).click()
    lab = page.locator('.risk-lab-panel')
    lab.locator('textarea').first.fill('当前仅形成核查方向，跳过实验室验证')
    lab.get_by_role('button', name='保存本版验证选择', exact=True).click()
    expect(lab).to_contain_text('已跳过')
    page.goto(BASE+f'/app/risk-reports?case_id={CASE}', wait_until='networkidle')
    page.get_by_role('button', name='生成本版研判报告', exact=True).click()
    expect(page.locator('.report-preview')).to_contain_text('独立复核')
    expect(page.locator('.report-preview')).not_to_contain_text('演示')
    page.set_viewport_size({'width':390, 'height':844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(OUT/'formal-report-mobile.png'), full_page=True)
    page.goto(BASE+f'/app/risk-sampling?case_id={CASE}', wait_until='networkidle')
    expect(page.get_by_role('heading', name='抽查建议', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='查看正式抽查计划', exact=True)).to_be_visible()
    # Inspect the actual rendered result-return controls before exercising them.
    state['lab'].update(mode='verify', task_id='task-formal', status='requested', purpose='隔离检测结果回流', revision=2)
    page.goto(BASE+f'/app/risk-assessments?case_id={CASE}&tab=laboratory', wait_until='networkidle')
    panel = page.get_by_role('region', name='已复核检测结果回流')
    expect(panel.get_by_role('heading', name='从检测任务返回已复核结果')).to_be_visible()
    assert '选择检测结果' in panel.locator('fieldset').inner_text()
    expect(panel.get_by_role('radio', name='检测执行 run-blocked', exact=False)).to_be_disabled()
    panel.get_by_role('button', name='下一页', exact=True).click()
    expect(panel).to_contain_text('run-next-page')
    panel.get_by_role('button', name='上一页', exact=True).click()
    panel.get_by_role('radio', name='检测执行 run-valid', exact=False).check()
    panel.get_by_role('textbox', name='检测结果回流说明', exact=True).fill('隔离已复核结果回流界面核验')
    state['return_conflict'] = True
    panel.get_by_role('button', name='将已复核结果返回原事项', exact=True).click()
    expect(panel).to_contain_text('检测结果已变化，请刷新后重试')
    state['return_conflict'] = False
    panel.get_by_role('button', name='将已复核结果返回原事项', exact=True).click()
    expect(panel).to_contain_text('检测结果已返回')
    expect(panel.get_by_role('radio', name='检测执行 run-valid', exact=False)).to_be_disabled()
    expect(panel.get_by_role('button', name='返回事项创建新版研判', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    panel.get_by_role('heading', name='从检测任务返回已复核结果').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'execution-return-mobile.png'))
    panel.get_by_role('heading', name='检测结果回流记录').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'execution-return-history-mobile.png'))
    panel.get_by_role('textbox', name='撤回引用说明（需要撤回时填写）', exact=True).fill('来源需要补证，明确撤回本次引用')
    panel.get_by_role('button', name='撤回本次结果引用', exact=True).click()
    expect(panel).to_contain_text('本次引用已撤回')
    assert not errors, errors
    assert not unexpected, unexpected
    browser.close()
    result = {"passed": True, "api_mode": "isolated fixtures", "console_errors": errors, "unexpected_requests": unexpected,
        "checks": ["deep link outside current list", "refresh restores review", "source provenance link", "history cannot be reviewed", "sampling carries case", "unified opinion intake", "supplement requires reassessment", "mobile layout", "retry clears stale case", "lab navigation and task relationship", "formal collaboration eligibility", "formal optional validation", "formal report generation and mobile layout", "formal suggestion route", "execution return permission and conflict display", "execution return pagination", "execution return duplicate disabled", "execution return withdrawal and mobile layout"]}
    (OUT/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
