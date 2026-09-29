"""Risk-first quality supervision API + browser regression on the isolated QA server."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

API = os.getenv("SUPERVISION_QA_API", "http://127.0.0.1:8123")
WEB = os.getenv("SUPERVISION_QA_WEB", "http://127.0.0.1:5174")
manifest = json.load(urllib.request.urlopen(API + "/qa/manifest"))
artifacts = Path(os.getenv("SUPERVISION_QA_ARTIFACTS", str(Path(__file__).resolve().parent / "artifacts")))
artifacts.mkdir(parents=True, exist_ok=True)

def api(role, method, path, body=None, expected=200):
    request = urllib.request.Request(
        API + "/api/v1" + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + manifest["roles"][role]["token"]},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status, result = response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        status, result = exc.code, json.load(exc)
    assert status == expected, (method, path, status, result.get("message"))
    return result.get("data")

source = api("admin", "POST", "/quality-data/sources", {
    "code": "QA-INSPECTION-E2E", "name": "监督抽查报告（测试）",
    "source_type": "supervision_inspection", "connector_type": "api", "config": {},
}, expected=201)
record = api("user", "POST", "/quality-data/events", {
    "source_id": source["id"], "record_type": "supervision_inspection",
    "occurred_at": "2026-09-27T10:00:00",
    "content": {"text": "电动自行车充电温升超过标准限值", "risk_type": "过热风险", "risk_level": "high", "possible_causes": ["充电控制或电池热管理异常"], "recommendations": ["纳入重点监督抽查"]},
    "product_ref": {"category_id": manifest["category_id"]},
}, expected=201)
risk = api("user", "POST", "/risk-cases", {
    "title": "电动自行车充电温升风险", "scope_type": "category",
    "scope": {"name": "电动自行车", "category_id": manifest["category_id"]},
    "source_record_ids": [record["id"]],
}, expected=201)
assessment = api("user", "POST", f"/risk-cases/{risk['id']}/analyze", {})
assert assessment["risk_level"] == "high" and assessment["probability"] is None
reviewed = api("expert2", "POST", f"/risk-cases/{risk['id']}/reviews", {
    "decision": "accept", "comment": "原始抽查记录、风险类型和范围一致",
    "risk_type": "过热风险", "risk_level": "high",
})
assert reviewed["trust_status"] == "verified"
api("algorithm_engineer", "GET", "/risk-cases", expected=403)

def session_values(role):
    account = manifest["roles"][role]
    return {"piap_token": account["token"], "piap_org_id": manifest["org_id"], "piap_role": account["role"], "piap_user_id": account["user_id"], "piap_username": role, "piap_roles": json.dumps([account["role"]]), "piap_plan_tier": "enterprise", "piap_capabilities": "[]"}

def browser_context(browser, role, width=1440, height=960):
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_init_script("(() => { const values = " + json.dumps(session_values(role)) + "; for (const [key,value] of Object.entries(values)) sessionStorage.setItem(key,value); })()")
    return context

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    errors = []
    expert = browser_context(browser, "expert")
    page = expert.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(WEB + "/app/quality-data"); page.wait_for_load_state("networkidle")
    page.get_by_role("heading", name="质量数据接入", exact=True).wait_for()
    page.get_by_text("电动自行车充电温升超过标准限值", exact=True).wait_for()
    assert page.get_by_text("实验室检测", exact=True).count() == 0
    page.screenshot(path=str(artifacts / "quality-data-v4.png"), full_page=True)
    page.goto(WEB + "/app/risk-assessments"); page.wait_for_load_state("networkidle")
    page.get_by_text("电动自行车充电温升风险", exact=True).wait_for()
    page.screenshot(path=str(artifacts / "risk-assessment-v4.png"), full_page=True)
    admin = browser_context(browser, "admin"); admin_page = admin.new_page()
    admin_page.goto(WEB + "/governance/admin/quality-products"); admin_page.wait_for_load_state("networkidle")
    admin_page.get_by_role("heading", name="产品类别与具体产品", exact=True).wait_for()
    assert admin_page.get_by_text("地区字典", exact=True).count() == 0
    developer = browser_context(browser, "app_developer"); developer_page = developer.new_page()
    developer_page.goto(WEB + "/ops/agents"); developer_page.wait_for_load_state("networkidle")
    assert developer_page.get_by_text("四类质监 Agent 的运行设置", exact=True).count() == 0
    mobile = browser_context(browser, "expert", 375, 812); mobile_page = mobile.new_page()
    mobile_page.goto(WEB + "/app/quality-data"); mobile_page.wait_for_load_state("networkidle")
    assert mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    mobile_page.screenshot(path=str(artifacts / "quality-data-v4-mobile.png"), full_page=True)
    assert not errors, errors
    browser.close()
print("quality risk v4 API + browser flow passed")
