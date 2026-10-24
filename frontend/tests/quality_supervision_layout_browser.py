"""Exercise module layouts and laboratory state transitions with isolated API data."""
import copy
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("PIAP_BASE", "http://127.0.0.1:5174")
OUT = Path(__file__).resolve().parents[1] / "test-results/quality-supervision-layout"
OUT.mkdir(parents=True, exist_ok=True)
state = {"summary_error": False, "list_error": False, "mode": "business"}
reads, errors, mutations = [], [], []
stamp = "2026-10-20T08:00:00Z"
case = {"id": "case-1", "code": "RISK-001", "title": "产品温升异常待核验", "scope_type": "product", "scope": {"name": "测试产品", "product_id": "product-1"},
    "status": "awaiting_evidence", "source_record_ids": [], "evidence_ids": [], "created_at": stamp, "updated_at": stamp}
batch = {"id": "batch-1", "org_id": "org", "kind": "inspection-sessions", "code": "LAB-001", "name": "温升检测准备批次", "status": "active", "version": 1,
    "created_by": "author", "data": {"task_id": "task-1", "input_mode": "measurement", "sample_ids": ["sample-1"], "device_ids": [], "test_items": []}, "created_at": stamp, "updated_at": stamp}
plan = {**batch, "id": "plan-1", "kind": "sampling-plans", "code": "PLAN-001", "name": "重点产品抽查方案", "status": "draft", "data": {}}
market = {"execution_mode": "business", "as_of": "2026-10-20", "object_type": "product", "windows": {"previous_start": "2026-09-22", "current_start": "2026-10-06", "end": "2026-10-20", "timezone": "Asia/Shanghai"},
    "rule": {"version": 1, "algorithm": "count", "window_days": 14, "min_current": 3, "min_increase": 3, "growth_factor": 2},
    "totals": {"consumer_complaint": {"previous": 2, "current": 5}, "public_opinion": {"previous": 1, "current": 2}}, "daily": [], "groups": [], "pending_objects": [], "missing_time": [], "unavailable_sources": [], "notice": "隔离浏览器数据"}


def reply(route, data, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps({"success": status == 200, "code": "ok" if status == 200 else "unavailable", "message": "读取失败" if status != 200 else "", "data": data}))


def guard(route):
    request = route.request
    parsed = urlparse(request.url)
    path = parsed.path.removeprefix("/api/v1/")
    reads.append({"path": path, "query": parsed.query, "method": request.method})
    if request.method != "GET":
        assert path == "market-monitoring/scan", f"Unexpected business write: {path}"
        reply(route, market); return
    if path == "users/me":
        reply(route, {"id": "expert", "org_id": "org", "username": "reviewer", "role": "expert", "is_active": True,
            "effective_permissions": ["chat", "quality", "quality_material_read_business", "quality_material_submit", "task", "result"]}); return
    if path == "runtime-context":
        reply(route, {"execution_mode": state["mode"], "label": "业务环境", "case_code": None}); return
    if path == "quality-supervision/settings":
        reply(route, {"enabled": True, "laboratory_validation_enabled": True, "permissions": []}); return
    if path == "quality-supervision/laboratory-summary":
        reply(route, {"collecting": 0, "review": 0, "signed": 0, "online": 0}, 503 if state["summary_error"] else 200); return
    if path == "inspection-sessions":
        if state["list_error"]: reply(route, None, 503); return
        query = parse_qs(parsed.query)
        items = [batch] if query.get("status", [batch["status"]])[0] == batch["status"] else []
        reply(route, {"items": items, "total": len(items), "page": 1, "size": 20}); return
    if path == "inspection-sessions/batch-1": reply(route, batch); return
    if path.endswith("/reviews"): reply(route, []); return
    if path == "sampling-plans": reply(route, {"items": [plan], "total": 1, "page": 1, "size": 20}); return
    if path == "risk-cases": reply(route, {"items": [case], "total": 1, "page": 1, "size": 20}); return
    if path == "risk-cases/case-1/workspace":
        reply(route, {"case": case, "records": [], "latest_assessment": None, "assessment_versions": [], "workflow_context": {"execution_mode": state["mode"], "eligible": False, "can_author": True, "basis_hash": None}}); return
    if path == "risk-cases/case-1/laboratory-verifications": reply(route, []); return
    if path == "quality-data/records": reply(route, {"items": [], "total": 0, "page": 1, "size": 20}); return
    if path == "quality-data/reference-options": reply(route, {"products": [], "categories": [], "enterprises": []}); return
    if path in {"quality-products/options", "quality-products/catalog"}: reply(route, {"products": [], "categories": []}); return
    if path.startswith("quality-supervision/options/"): reply(route, {"items": [], "selected": [], "unavailable_selected_ids": [], "total": 0, "has_more": False, "page": 1, "size": 20}); return
    reply(route, [])


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Page horizontal overflow"


def context_for(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    storage = {"piap_token": "isolated", "piap_role": "expert", "piap_roles": '["expert"]', "piap_user_id": "expert", "piap_org_id": "org", "piap_username": "reviewer"}
    context.add_init_script("for(const [key,value] of Object.entries(" + json.dumps(storage) + "))sessionStorage.setItem(key,value)")
    context.route("**/api/v1/**", guard)
    return context


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = context_for(browser)
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/app/laboratory", wait_until="networkidle")
    nav = page.locator(".app-sidebar nav")
    expect(nav.locator("#nav-group-质量监督").get_by_role("link", name="实验室检测", exact=True)).to_be_visible()
    expect(nav.locator(".nav-link-active")).to_have_text("实验室检测")
    expect(page.locator(".module-header h1")).to_have_text("实验室检测")
    expect(page.locator(".demo-lab-workspace")).to_have_count(0)
    expect(page.locator(".session-row")).to_contain_text("待准备")
    expect(page.locator(".configuration-notice")).to_contain_text("关联检测设备")
    expect(page.locator(".configuration-notice")).to_contain_text("配置检测项目")
    expect(page.get_by_role("button", name="完善配置与执行", exact=True)).to_be_enabled()
    no_overflow(page)
    page.screenshot(path=str(OUT / "laboratory-batches-desktop.png"), full_page=True)
    page.get_by_role("button", name="待复核", exact=True).click()
    expect(page.locator(".session-row")).to_have_count(0)
    assert any("status=awaiting_review" in row["query"] for row in reads if row["path"] == "inspection-sessions")
    page.get_by_role("button", name="全部", exact=True).click()
    expect(page.locator(".session-row")).to_have_count(1)
    page.get_by_role("button", name="批次详情", exact=True).click()
    expect(page).to_have_url(__import__('re').compile(r"/app/inspection-sessions\?record=batch-1$"))
    expect(page.locator(".record-detail h2")).to_have_text(batch["name"])
    expect(nav.locator(".nav-link-active")).to_have_text("实验室检测")
    page.goto(BASE + "/app/laboratory", wait_until="networkidle")
    page.get_by_role("button", name="从风险事项发起验证", exact=True).click()
    expect(page.locator(".demo-lab-workspace")).to_be_visible()
    expect(page.locator(".laboratory-board")).to_have_count(0)
    page.locator("#lab-case").select_option(case["id"])
    expect(page.locator(".risk-lab-panel")).to_be_visible()
    expect(page.locator(".verification-paths")).to_contain_text("引用已有报告")
    page.screenshot(path=str(OUT / "laboratory-validation-desktop.png"), full_page=True)

    state["summary_error"] = True
    page.goto(BASE + "/app/laboratory", wait_until="networkidle")
    expect(page.locator(".session-row")).to_have_count(1)
    expect(page.locator(".batch-summary")).to_contain_text("—")
    expect(page.get_by_text("批次统计暂不可用，已加载的批次仍可查看。", exact=True)).to_be_visible()
    state["summary_error"] = False
    state["list_error"] = True
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("button", name="重试批次列表", exact=True)).to_be_visible()
    expect(page.get_by_text("当前条件下没有检测批次", exact=True)).to_have_count(0)
    state["list_error"] = False
    page.get_by_role("button", name="重试批次列表", exact=True).click()
    expect(page.locator(".session-row")).to_have_count(1)

    for path, title in [("quality-data", "数据采集"), ("quality-analytics", "市场监控"), ("risk-assessments", "风险研判"), ("sampling-plans", "监督抽查"), ("laboratory", "实验室检测")]:
        page.goto(BASE + "/app/" + path, wait_until="networkidle")
        expect(page.locator(".module-header h1")).to_have_text(title)
        expect(page.locator(".todo-panel")).to_have_count(0)
        assert page.locator(".module-header").bounding_box()["height"] < 220
        no_overflow(page)
        page.screenshot(path=str(OUT / (path + "-desktop.png")), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 0")
        no_overflow(page)
        page.screenshot(path=str(OUT / (path + "-mobile.png")), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
    context.close()

    state["mode"] = "demo"
    demo = context_for(browser)
    demo_page = demo.new_page()
    demo_page.on("pageerror", lambda e: errors.append(str(e)))
    start = len(reads)
    demo_page.goto(BASE + "/app/laboratory", wait_until="networkidle")
    expect(demo_page.locator(".demo-lab-workspace")).to_be_visible()
    expect(demo_page.get_by_role("button", name="检测批次 样品、设备与执行", exact=True)).to_be_disabled()
    assert not any(row["path"] == "inspection-sessions" for row in reads[start:])
    demo.close()
    browser.close()
    assert not errors, errors
    result = {"passed": True, "mode": "isolated API fixtures", "live_business_writes": False,
        "checks": ["nested laboratory navigation", "separate batch and validation views", "missing-configuration guidance", "batch detail and task context", "status filtering", "partial statistics failure", "list failure and recovery", "five module desktop/mobile layouts", "demo execution boundary"], "page_errors": errors}
    (OUT / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
