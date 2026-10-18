"""Stage-two interaction acceptance against real isolated APIs; no route mocks."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".codex_tmp/piap_quality_demo"
config = json.loads((OUT / "accounts.json").read_text(encoding="utf-8"))
accepted = json.loads((OUT / "phase2-api-acceptance.json").read_text(encoding="utf-8"))
BASE, RECORD, CASE = config["url"], accepted["source_record_id"], accepted["scenario_case_id"]
errors, server_errors = [], []


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width":1500,"height":1050},timezone_id="Asia/Shanghai",accept_downloads=True)
    account = next(item for item in config["accounts"] if item["username"]=="demo_analyst")
    session = context.request.post(BASE+"/api/v1/auth/token", headers={"X-Org-Id":config["organization"]},
        data={"username":account["username"],"password":account["password"]}).json()["data"]
    headers = {"Authorization":"Bearer "+session["access_token"]}
    def record_context():
        response = context.request.get(BASE+f"/api/v1/quality-data/records/{RECORD}/context",headers=headers)
        assert response.status==200
        return response.json()["data"]
    initial = record_context()
    original = initial["record"]
    company_name = initial["objects"]["enterprise"]["name"]
    attachment = initial["attachments"][0]
    file_bytes = context.request.get(BASE+attachment["download_url"],headers=headers).body()
    stored = {"piap_token":session["access_token"],"piap_org_id":session["org_id"],"piap_user_id":session["user_id"],
        "piap_role":"expert","piap_roles":'["expert"]',"piap_username":account["username"]}
    context.add_init_script("for(const[k,v]of Object.entries("+json.dumps(stored)+"))sessionStorage.setItem(k,v)")
    page = context.new_page()
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.on("response",lambda response:server_errors.append(response.url) if "/api/v1/" in response.url and response.status>=500 else None)
    page.goto(BASE+"/app/quality-data",wait_until="networkidle")
    expect(page.get_by_role("heading",name="数据采集",exact=True)).to_be_visible()
    page.get_by_role("button",name="投诉资料",exact=True).click()
    page.get_by_role("button",name="提交资料",exact=True).click()
    dialog = page.get_by_role("dialog",name="提交质量资料",exact=True)
    dialog.get_by_role("textbox",name="原始内容或附件（至少一种）",exact=True).fill(original["content"]["text"])
    dialog.get_by_role("textbox",name="原始出处（选填）",exact=True).fill(original["provenance"]["origin_label"])
    dialog.locator('input[type="file"]').set_input_files({"name":attachment["file_name"],"mimeType":"text/plain","buffer":file_bytes})
    dialog.get_by_text("对象与发生时间（已有信息再填）",exact=True).click()
    dialog.get_by_role("textbox",name="产品原始描述",exact=True).fill(original["content"]["product_description"])
    dialog.get_by_role("textbox",name="原始企业描述",exact=True).fill(original["enterprise_ref"]["name"])
    dialog.get_by_role("textbox",name="外部报告／投诉编号",exact=True).fill(original["external_record_id"])
    dialog.get_by_role("button",name="提交",exact=True).click()
    expect(page.get_by_text("资料已存在，复用受理记录",exact=False)).to_be_visible()
    expect(dialog).not_to_be_visible()
    source_row = page.locator(".el-table__row").filter(has_text=original["content"]["text"])
    expect(source_row).to_have_count(1)
    source_row.click()
    page.wait_for_function("([record]) => { const u = new URL(location.href); return u.pathname === '/app/quality-data' && u.searchParams.get('record') === record && u.searchParams.get('record_type') === 'consumer_complaint'; }", arg=[RECORD])
    drawer = page.get_by_role("dialog",name="原始资料详情",exact=True)
    expect(drawer.locator(".object-links")).to_contain_text(company_name)
    expect(drawer.locator("tr").filter(has_text="发生时间").get_by_text("未知",exact=True)).to_be_visible()
    expect(drawer.get_by_text("原资料称某厂",exact=True)).to_be_visible()
    page.reload(wait_until="networkidle")
    expect(drawer.locator(".object-links")).to_contain_text(company_name)
    drawer.get_by_role("button",name="确认或调整关联",exact=True).click()
    binding_dialog = page.get_by_role("dialog",name="确认资料对象关联",exact=True)
    enterprise_field = binding_dialog.locator(".el-form-item").filter(has_text="关联企业")
    enterprise_field.locator(".el-select").hover()
    enterprise_field.locator(".el-select__clear").click()
    binding_dialog.get_by_role("textbox",name="关联依据",exact=False).fill("【演示验收】暂不确认企业，保留原始描述")
    binding_dialog.get_by_role("heading",name="确认资料对象关联",exact=True).click()
    binding_dialog.get_by_role("button",name="保存关联",exact=True).click()
    expect(binding_dialog).not_to_be_visible()
    expect(drawer.locator(".object-links dd").first).to_have_text("待确认")
    assert record_context()["objects"]["enterprise"]["status"]=="unlinked"
    drawer.get_by_role("button",name="确认或调整关联",exact=True).click()
    binding_dialog.get_by_role("combobox",name="关联企业",exact=True).fill(company_name)
    page.get_by_role("option",name=company_name,exact=True).click()
    binding_dialog.get_by_role("heading",name="确认资料对象关联",exact=True).click()
    binding_dialog.get_by_role("textbox",name="关联依据",exact=False).fill("【演示验收】对照原件重新确认企业档案")
    binding_dialog.get_by_role("button",name="保存关联",exact=True).click()
    expect(binding_dialog).not_to_be_visible()
    expect(drawer.locator(".object-links")).to_contain_text(company_name)
    expect(drawer.locator(".binding-history")).to_contain_text("对照原件重新确认企业档案")
    # A second expert changes the reference while this editor holds an old version.
    drawer.get_by_role("button",name="确认或调整关联",exact=True).click()
    current = record_context()["record"]
    peer = next(item for item in config["accounts"] if item["username"]=="demo_reviewer")
    peer_login = context.request.post(BASE+"/api/v1/auth/token",headers={"X-Org-Id":config["organization"]},
        data={"username":peer["username"],"password":peer["password"]}).json()["data"]
    peer_change=context.request.patch(BASE+f"/api/v1/quality-data/records/{RECORD}/objects",headers={"Authorization":"Bearer "+peer_login["access_token"]},data={
        "enterprise_id":None,"product_id":current["product_ref"]["product_id"],"category_id":current["product_ref"]["category_id"],
        "expected_version":current["provenance"]["object_binding_version"],"reason":"【演示并发验收】另一位专家调整关联"})
    assert peer_change.status==200
    binding_dialog.get_by_role("textbox",name="关联依据",exact=False).fill("【演示并发验收】重新核对后保存")
    binding_dialog.get_by_role("button",name="保存关联",exact=True).click()
    expect(binding_dialog.locator(".el-alert").filter(has_text="资料关联版本已变化")).to_be_visible()
    binding_dialog.get_by_role("button",name="重新核对最新关联",exact=True).click()
    expect(binding_dialog.get_by_role("textbox",name="关联依据",exact=False)).to_have_value("【演示并发验收】重新核对后保存")
    binding_dialog.get_by_role("combobox",name="关联企业",exact=True).fill(company_name)
    page.get_by_role("option",name=company_name,exact=True).click()
    binding_dialog.get_by_role("heading",name="确认资料对象关联",exact=True).click()
    binding_dialog.get_by_role("button",name="保存关联",exact=True).click()
    expect(binding_dialog).not_to_be_visible()
    expect(drawer.locator(".object-links")).to_contain_text(company_name)
    final = record_context()
    for key in ["id","content","content_hash","occurred_at","received_at","attachment_ids"]:
        assert original[key]==final["record"][key]
    assert final["record"]["provenance"]["object_binding_version"]>=initial["record"]["provenance"]["object_binding_version"]+2
    drawer.locator(".object-links").scroll_into_view_if_needed()
    expect(page.locator(".el-message")).to_have_count(0,timeout=15000)
    assert page.locator(".el-drawer").bounding_box()["y"] >= page.locator(".runtime-banner").bounding_box()["height"]
    page.screenshot(path=str(OUT/"phase2-source-context.png"),full_page=True)
    with page.expect_download() as download:
        drawer.get_by_role("button",name="下载 "+attachment["file_name"],exact=True).click()
    assert Path(download.value.path()).read_bytes()==file_bytes
    drawer.locator(".related-cases").get_by_role("button",name="DEMO-QS-001",exact=False).click()
    expect(page).to_have_url(BASE+f"/app/risk-assessments?case_id={CASE}")
    workspace = context.request.get(BASE+f"/api/v1/risk-cases/{CASE}/workspace",headers=headers).json()["data"]
    page.get_by_role("tab",name=f"原始资料（{len(workspace['records'])}）",exact=True).click()
    source = page.locator(".source-record").filter(has_text=original["content"]["text"])
    expect(source).to_have_count(1)
    source.get_by_role("button",name="查看原件与附件",exact=True).click()
    expect(drawer.locator(".object-links")).to_contain_text(company_name)
    page.set_viewport_size({"width":390,"height":844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
    drawer.locator(".object-links").scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    page.screenshot(path=str(OUT/"phase2-source-mobile.png"),full_page=True)
    drawer.locator(".el-drawer__close-btn").click()
    page.set_viewport_size({"width":1500,"height":1050})
    page.goto(BASE+"/app/quality-data",wait_until="networkidle")
    page.get_by_role("button",name="查看标准资料",exact=True).click()
    expect(page).to_have_url(BASE+"/governance/admin/inspection-standards")
    page.wait_for_load_state("networkidle")
    page.goto(BASE+"/app/quality-data",wait_until="networkidle")
    page.get_by_role("button",name="查看知识资料",exact=True).click()
    expect(page).to_have_url(BASE+"/app/rag-spaces")
    expect(page.get_by_role("heading",name="知识资料",exact=True)).to_be_visible()
    assert not errors, errors
    assert not server_errors, server_errors
    result={"stage":2,"passed":True,"api_mode":"real_local_demo_server","mocked_requests":0,"duplicate_upload_and_submission_verified":True,
        "source_identity_preserved":True,"manual_binding_audited":True,"concurrent_binding_recovery_verified":True,"source_risk_roundtrip_verified":True,"original_download_verified":True,
        "mobile_verified":True,"standard_and_knowledge_entries_reused":True,"console_errors":errors,"server_errors":server_errors}
    (OUT/"phase2-browser-acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    browser.close()
