"""Isolated UI fixtures: record-owned review actions, with no live business writes."""
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("PIAP_BASE", "http://127.0.0.1:5174")
OUT = Path(__file__).resolve().parents[1] / "test-results/supervision-record-actions"
OUT.mkdir(parents=True, exist_ok=True)
records = {}
reviews = {}
mutations = []
errors = []
reads = []

for kind, name, operation in [
    ("sampling-plans", "抽查方案审批示例", "sampling.approve"),
    ("inspection-sessions", "检测结果确认示例", "result.signoff"),
    ("legacy-risk-cases", "历史风险补证示例", None),
]:
    record_id = kind + "-record"
    records[kind] = {"id": record_id, "org_id": "fixture-org", "kind": "risk-cases" if kind == "legacy-risk-cases" else kind,
        "code": "RECORD-001", "display_no": "001", "name": name,
        "status": "awaiting_review" if operation else "awaiting_evidence", "version": 1,
        "created_by": "author", "created_at": "2026-10-20T08:00:00Z", "updated_at": "2026-10-20T08:00:00Z",
        "data": {"analysis": {"status": "completed", "summary": "浏览器隔离流程数据", "selected": []},
            "description": "待补充来源资料", "occurred_at": "2026-10-20T08:00:00Z", "evidence": []}}
    reviews[record_id] = [] if not operation else [{"id": kind + "-review", "record_id": record_id,
        "version": 1, "operation": operation, "status": "pending", "requester_id": "author", "can_decide": True}]


def envelope(route, data):
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"code": "ok", "success": True, "message": "", "data": data}))


def guard(route):
    request = route.request
    parsed = urlparse(request.url)
    path = parsed.path.removeprefix("/api/v1/")
    if request.method == "GET":
        reads.append(path)
    if path == "users/me":
        envelope(route, {"id": "reviewer", "org_id": "fixture-org", "username": "reviewer", "role": "expert", "is_active": True,
            "effective_permissions": ["quality", "chat"]}); return
    if path == "runtime-context":
        envelope(route, {"execution_mode": "business", "label": "业务环境", "case_code": None}); return
    if path == "quality-supervision/settings":
        envelope(route, {"enabled": True, "laboratory_validation_enabled": True, "permissions": []}); return
    if path.startswith("quality-supervision/options/"):
        envelope(route, {"items": [], "selected": [], "unavailable_selected_ids": [], "total": 0, "has_more": False, "page": 1, "size": 20}); return
    if path in {"quality-supervision/assignees", "quality-supervision/dataset-enrollments"}:
        envelope(route, []); return
    if path == "business-reviews":
        raise AssertionError("Removed standalone todo API must not be requested")
    if path.startswith("business-reviews/"):
        assert request.method == "POST"
        review_id = path.split("/")[1]
        payload = request.post_data_json
        mutations.append({"review": review_id, **payload})
        for kind, record in records.items():
            for review in reviews[record["id"]]:
                if review["id"] == review_id:
                    review["status"] = "accepted"; review["can_decide"] = False
                    record["status"] = "approved" if kind == "sampling-plans" else "signed"
        envelope(route, {}); return
    parts = path.split("/")
    if parts[0] in records:
        record = records[parts[0]]
        if len(parts) == 3 and parts[2] == "reviews":
            envelope(route, reviews[record["id"]]); return
        if len(parts) == 1:
            status = parse_qs(parsed.query).get("status", [None])[0]
            items = [record] if status in {None, record["status"]} else []
            envelope(route, {"items": items, "total": len(items), "page": 1, "size": 20}); return
        if request.method == "PATCH":
            payload = request.post_data_json
            record.update(name=payload["name"], data=payload["data"], version=record["version"] + 1)
            mutations.append({"record": record["id"], "action": "evidence-update"})
        envelope(route, record); return
    assert request.method == "GET", f"Unexpected mutation: {path}"
    envelope(route, [])


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    storage = {"piap_token": "isolated-fixture", "piap_role": "expert", "piap_roles": '["expert"]',
        "piap_user_id": "reviewer", "piap_org_id": "fixture-org", "piap_username": "reviewer"}
    context.add_init_script("for(const [key,value] of Object.entries(" + json.dumps(storage) + "))sessionStorage.setItem(key,value)")
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/api/v1/**", guard)
    page.goto(BASE + "/app/workbench", wait_until="networkidle")
    expect(page).to_have_url(re.compile(r"/app/quality-analytics$"))
    expect(page.locator(".app-sidebar").get_by_text("质监工作台", exact=True)).to_have_count(0)
    expect(page.locator(".todo-panel")).to_have_count(0)

    for kind, label in [("sampling-plans", "批准抽查方案"), ("inspection-sessions", "确认正式结果")]:
        page.goto(BASE + "/app/" + kind, wait_until="networkidle")
        page.locator(".records-table .el-table__row").click()
        expect(page.locator(".record-detail")).to_be_visible()
        expect(page.get_by_role("button", name=label, exact=True)).to_be_visible()
        expect(page.locator(".records-table .el-tag")).to_have_text("待批准" if kind == "sampling-plans" else "待复核")
        expect(page.locator(".todo-panel")).to_have_count(0)
        page.screenshot(path=str(OUT / (kind + "-record.png")), full_page=True)
        page.get_by_role("button", name=label, exact=True).click()
        prompt = page.locator(".el-message-box")
        prompt.locator("textarea").fill("已核对当前版本和来源依据")
        prompt.get_by_role("button", name="确定", exact=True).click()
        expect(page.get_by_role("button", name=label, exact=True)).to_have_count(0)
        expect(page.locator(".record-detail")).to_be_visible()

    page.goto(BASE + "/app/risk-assessments/records/risk-cases", wait_until="networkidle")
    page.locator(".records-table .el-table__row").click()
    page.get_by_role("button", name="编辑与补证", exact=True).click()
    dialog = page.get_by_role("dialog")
    dialog.locator(".el-form-item").filter(has=page.locator("label", has_text="名称")).locator("input").fill("历史风险来源已补充")
    dialog.get_by_role("button", name="保存", exact=True).click()
    expect(page.locator(".record-detail h2")).to_have_text("历史风险来源已补充")
    expect(page.locator(".record-detail")).to_contain_text("版本 2")
    page.screenshot(path=str(OUT / "risk-evidence-record.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 0")
    expect(page.locator(".el-message")).to_have_count(0)
    page.screenshot(path=str(OUT / "risk-evidence-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflow"
    assert not errors, errors
    assert len(mutations) == 3, mutations
    result = {"passed": True, "mode": "isolated API fixtures", "live_business_writes": False,
        "checks": ["old workbench redirect", "no standalone todo panels or queue reads", "plan approval inside record",
            "formal result confirmation inside record", "historical risk evidence editing", "mobile width"],
        "page_errors": errors}
    (OUT / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    browser.close()
