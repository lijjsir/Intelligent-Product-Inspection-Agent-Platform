"""Read-only real local API/UI verification; never approves or creates business data."""
import hashlib
import json
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/runtime/real_quality_case_20261023"
OUT = ROOT / "frontend/test-results/real-quality-public-case"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:5173"
index = json.loads((DATA / "case-index.json").read_text(encoding="utf-8"))
auth = json.loads((DATA / "private-browser-session.json").read_text(encoding="utf-8"))
errors, forbidden_writes = [], []


def guard(route):
    request = route.request
    path = request.url.split("/api/v1/", 1)[-1].split("?",1)[0]
    if request.method not in {"GET", "HEAD", "OPTIONS"} and path not in {"market-monitoring/scan", "streams/session"}:
        forbidden_writes.append({"method": request.method, "path": path})
        route.abort(); return
    route.continue_()


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width":1440,"height":1000}, timezone_id="Asia/Shanghai")
    context.add_init_script("for(const[key,value]of Object.entries(" + json.dumps(auth) + "))sessionStorage.setItem(key,value)")
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/v1/**", guard)
    headers = {"Authorization": "Bearer " + auth["piap_token"]}
    download = context.request.get(BASE + "/api/v1/quality-data/attachments/" + index["report_attachment"] + "/download", headers=headers)
    assert download.status == 200
    assert hashlib.sha256(download.body()).hexdigest() == "94ee5414e93c79d0d8c80c8a318204365ad1b1aab06de15ca46fb5e8034df0e2"
    food = context.request.get(BASE + "/api/v1/quality-data/records", params={"keyword":"过期食品售卖","page":1,"size":20}, headers=headers)
    assert food.status == 200 and food.json()["data"]["total"] == 0
    page.goto(BASE + "/app/quality-data?record=" + index["records"]["report"], wait_until="networkidle")
    expect(page.get_by_role("dialog", name="原始资料详情", exact=True)).to_be_visible()
    expect(page.locator(".raw-text")).to_contain_text("30.8")
    page.screenshot(path=str(OUT / "official-report-intake.png"), full_page=True)
    page.goto(BASE + "/app/risk-assessments?case_id=" + index["cases"]["main"], wait_until="networkidle")
    expect(page.locator(".case-detail")).to_contain_text("JG2128520085")
    expect(page.locator(".case-detail")).to_contain_text("30.8")
    expect(page.locator('.scope-card')).to_contain_text('历史资料复盘')
    expect(page.get_by_role('tab', name='抽查建议', exact=True)).to_have_count(0)
    expect(page.locator('.historical-sources')).to_contain_text('73 dB(A)')
    page.screenshot(path=str(OUT / "real-historical-assessment.png"), full_page=True)
    page.set_viewport_size({"width":390,"height":844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 0")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(OUT / "real-historical-assessment-mobile.png"), full_page=True)
    page.set_viewport_size({"width":1440,"height":1000})
    page.goto(BASE + "/app/quality-analytics?as_of=2022-04-25&object_type=product", wait_until="networkidle")
    expect(page.get_by_role("textbox", name="统计截止日", exact=True)).to_have_value("2022-04-25")
    expect(page.locator(".market-monitor")).to_contain_text("无法比较")
    page.screenshot(path=str(OUT / "real-historical-monitoring.png"), full_page=True)
    page.goto(BASE + "/app/laboratory?view=validation&case_id=" + index["cases"]["main"], wait_until="networkidle")
    expect(page.locator(".demo-lab-workspace")).to_contain_text("资料已回流")
    expect(page.get_by_role('radio', name='组织新的检测', exact=True)).to_be_disabled()
    page.screenshot(path=str(OUT / "real-report-return.png"), full_page=True)
    page.goto(BASE + "/app/sampling-plans", wait_until="networkidle")
    expect(page.locator(".records-table")).not_to_contain_text("测试")
    page.goto(BASE + "/app/risk-reports?case_id=" + index["cases"]["main"], wait_until="networkidle")
    expect(page.get_by_role('button', name='生成历史资料复盘报告', exact=True)).to_be_disabled()
    page.screenshot(path=str(OUT / "real-report-review-gate.png"), full_page=True)
    assert not errors and not forbidden_writes, {"page_errors":errors,"forbidden_writes":forbidden_writes}
    result = {"passed":True,"mode":"real local API and object storage; no fixture responses","real_original_pdf_sha256_verified":True,"case_id":index["cases"]["main"],"human_approvals_performed":False,"new_physical_tests_performed":False,"page_errors":errors,"forbidden_writes":forbidden_writes}
    (OUT / "checks.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    context.close(); browser.close()
