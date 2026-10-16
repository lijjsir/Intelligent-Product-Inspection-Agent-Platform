"""Read-only live assignment checks plus isolated API fixtures for pagination and failures."""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:5173"
OUT = ROOT / "frontend/test-results/quality-supervision-start"
OUT.mkdir(parents=True, exist_ok=True)
inventory = json.loads((ROOT / "backend/runtime/industrial_case_20261014/runtime_inventory.json").read_text(encoding="utf-8"))
actor = next(u for u in inventory["users"] if u["username"] == "expert")
code = "from app.core.security import create_access_token; print(create_access_token(" + repr(actor["id"]) + ", " + repr({"org_id": inventory["org_id"], "role": "expert"}) + "))"
token = subprocess.run(["docker", "exec", "piap-backend", "python", "-c", code], capture_output=True, check=True).stdout.decode().strip()
checks, errors, unexpected_http = [], [], []
fixture = [{"id": f"browser-{i}", "source_id": "browser-source", "record_type": "consumer_complaint" if i < 201 else "public_opinion",
    "occurred_at": None, "received_at": "2026-10-14T00:00:00Z", "content": {"text": f"browser signal {i}"},
    "enterprise_ref": {}, "product_ref": {}, "location": {}, "normalization_status": "stored"} for i in range(406)]
state = {"workbench_failure": False, "fixture": False, "opinion_failure": False}


def envelope(route, data, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps({"success": status == 200,
        "code": "ok" if status == 200 else "unavailable", "message": "" if status == 200 else "浏览器隔离接口暂不可用", "data": data}))


def guard(route):
    request = route.request
    url = urlparse(request.url)
    path = url.path
    if path == "/api/v1/chat/sessions" or path.endswith("/events"):
        envelope(route, []); return
    if path == "/api/v1/collab/summary":
        envelope(route, {"pending_count": 0, "initiated_count": 0, "processed_count": 0}); return
    if path == "/api/v1/streams/session":
        data = request.post_data_json
        envelope(route, {"stream_token": "isolated-browser", "expires_at": "2027-01-01T00:00:00Z",
            "resource": data["resource"], "resource_id": data["resource_id"]}); return
    if path.endswith("/stream"):
        route.fulfill(status=200, content_type="text/event-stream", body=": isolated browser\n\n"); return
    assert request.method == "GET", "Browser checks must not modify live business records"
    if state["workbench_failure"] and path in {"/api/v1/quality-data/records", "/api/v1/business-reviews"}:
        envelope(route, None, 503); return
    if state["fixture"] and path == "/api/v1/quality-data/records":
        if state["opinion_failure"]:
            envelope(route, None, 503); return
        params = parse_qs(url.query)
        types = params.get("record_types") or params.get("record_type")
        assert types, "Multi-type request must use repeated record_types without brackets"
        rows = [r for r in fixture if r["record_type"] in types]
        if params.get("keyword"):
            rows = [r for r in rows if params["keyword"][0] in r["content"]["text"]]
        page, size = int(params.get("page", [1])[0]), int(params.get("size", [20])[0])
        envelope(route, {"items": rows[(page-1)*size:page*size], "total": len(rows), "page": page, "size": size}); return
    response = route.fetch()
    if response.status >= 400:
        unexpected_http.append({"path": path, "status": response.status})
    route.fulfill(response=response)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1050}, timezone_id="Asia/Shanghai")
    storage = {"piap_token": token, "piap_role": "expert", "piap_roles": '["expert"]',
        "piap_user_id": actor["id"], "piap_org_id": inventory["org_id"], "piap_username": "expert"}
    context.add_init_script("try{if(location.origin===" + json.dumps(BASE) + ")for(const[k,v]of Object.entries(" + json.dumps(storage) + "))sessionStorage.setItem(k,v);}catch(_){}")
    response = context.request.get(BASE + "/api/v1/quality-data/records?record_types=consumer_complaint&record_types=public_opinion&page=1&size=20",
        headers={"Authorization": "Bearer " + token})
    assert response.status == 200
    actual = response.json()["data"]
    assert all(r["record_type"] in {"consumer_complaint", "public_opinion"} for r in actual["items"])
    checks.append("Live API accepts repeated record types and excludes inspection reports")
    queue = context.request.get(BASE + "/api/v1/standards/review-queue?scope=mine&page=1&size=100",
        headers={"Authorization": "Bearer " + token})
    assert queue.status == 200
    case = next(r for r in queue.json()["data"]["items"] if r["revision_id"] == "01a13879-073c-7a70-a8bf-0b496c8328d9")
    assert case["assigned_to_me"] and case["can_review"] and case["review_status"] == "pending" and case["publication_status"] == "unpublished"
    checks.append("Live expert queue contains the assigned R4 case without professional approval")
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/v1/**", guard)
    page.goto(BASE + "/app/workbench", wait_until="networkidle")
    expect(page.locator(".metric-grid > div").nth(1).locator("strong")).not_to_have_text("—")
    page.screenshot(path=str(OUT / "workbench-normal.png"), full_page=True)
    state["workbench_failure"] = True
    page.reload(wait_until="networkidle")
    expect(page.locator(".metric-grid > div").nth(1).locator("strong")).to_have_text("—")
    expect(page.locator(".overview-error")).to_contain_text("未能加载")
    expect(page.locator(".todo-panel .el-alert")).to_be_visible()
    expect(page.get_by_text("当前队列已处理完", exact=True)).to_have_count(0)
    page.screenshot(path=str(OUT / "workbench-failed.png"), full_page=True)
    state["workbench_failure"] = False
    page.get_by_role("button", name="刷新工作台数据", exact=True).click()
    page.locator(".todo-panel").get_by_role("button", name="刷新", exact=True).click()
    expect(page.locator(".overview-error")).to_have_count(0)
    expect(page.locator(".metric-grid > div").nth(1).locator("strong")).not_to_have_text("—")
    checks.append("Workbench failures are unknown values; todo failures do not appear completed; refresh recovers")

    state["fixture"] = True
    page.goto(BASE + "/app/risk-cases", wait_until="networkidle")
    expect(page.locator(".signal-card")).to_have_count(20)
    expect(page.locator(".signal-overview button").nth(0).locator("strong")).to_have_text("406")
    expect(page.locator(".signal-card").first).to_contain_text("未提供")
    page.locator(".el-pager .number").filter(has_text=re.compile("^21$")).click()
    expect(page.locator(".signal-card")).to_have_count(6)
    expect(page.get_by_text("browser signal 405", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "opinion-page-21.png"), full_page=True)
    checks.append("406 mixed signals remain accessible beyond the old per-type 200 cap; unknown times remain unknown")
    page.locator(".signal-overview button").nth(1).click()
    expect(page.locator(".signal-card")).to_have_count(20)
    expect(page.get_by_text("browser signal 0", exact=True)).to_be_visible()
    expect(page.locator(".el-pagination")).to_contain_text("201")
    page.locator(".el-pager .number").filter(has_text=re.compile("^11$")).click()
    expect(page.locator(".signal-card")).to_have_count(1)
    expect(page.get_by_text("browser signal 200", exact=True)).to_be_visible()
    page.locator(".signal-overview button").nth(0).click()
    page.get_by_placeholder("搜索投诉、舆情原文或外部编号").fill("browser signal 405")
    page.get_by_role("button", name="查询", exact=True).click()
    expect(page.locator(".signal-card")).to_have_count(1)
    expect(page.locator(".signal-overview button").nth(0).locator("strong")).to_have_text("1")
    checks.append("Type changes and searches reset server pages while preserving accurate totals")
    state["opinion_failure"] = True
    page.get_by_role("button", name="刷新", exact=True).click()
    expect(page.locator(".signals-panel .el-alert")).to_be_visible()
    expect(page.get_by_text("暂无投诉或舆情线索", exact=True)).to_have_count(0)
    expect(page.locator(".signal-overview button").nth(0).locator("strong")).to_have_text("—")
    state["opinion_failure"] = False
    page.get_by_role("button", name="刷新", exact=True).click()
    expect(page.locator(".signal-card")).to_have_count(1)
    checks.append("Opinion request failures do not appear empty and recover on refresh")
    page.set_viewport_size({"width": 430, "height": 950})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    page.get_by_placeholder("搜索投诉、舆情原文或外部编号").clear()
    page.get_by_role("button", name="查询", exact=True).click()
    expect(page.locator(".signal-card")).to_have_count(20)
    expect(page.get_by_text("浏览器隔离接口暂不可用", exact=True)).to_have_count(0)
    page.screenshot(path=str(OUT / "opinion-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    checks.append("430px opinion layout has no horizontal document overflow")

    state["fixture"] = False
    page.set_viewport_size({"width": 1600, "height": 1050})
    page.goto(BASE + "/app/standard-reviews", wait_until="networkidle")
    page.locator(".review-filters").get_by_text("我的待审", exact=True).click()
    expect(page.locator(".review-table")).to_contain_text("GB 17761-2018")
    page.screenshot(path=str(OUT / "expert-assigned-review.png"), full_page=True)
    assert not errors and not unexpected_http, (errors, unexpected_http)
    browser.close()

result = {"checks": checks, "page_errors": errors, "unexpected_http_errors": unexpected_http,
    "live_business_writes": 0, "fixture_signals": 406}
(OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
