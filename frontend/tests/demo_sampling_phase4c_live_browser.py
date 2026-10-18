"""Real local author/save/refresh/confirm and invited peer traceability. No mocks."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/quality-demo"))
from verify import request  # noqa: E402

OUT = ROOT / ".codex_tmp/piap_quality_demo"
config = json.loads((OUT / "accounts.json").read_text(encoding="utf-8"))
BASE = config["url"]
CASE = "90daba62-f80d-55b5-9d25-f05d0c0ffdfe"
URL = BASE + "/app/sampling-plans?case_id=" + CASE
TEXT = ["【演示】同一产品的投诉与舆情集中出现温升描述，建议补充核查。",
        "核对产品型号、使用条件及温升线索，关注是否需要后续实验室验证。",
        "全部为模拟资料；缺少真实测量及适用标准核对。数量、批次、地点、时间和资源可用性保持未知。"]
errors, failures = [], []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    contexts, pages, headers, tokens = {}, {}, {}, {}
    for name in ("demo_analyst", "demo_reviewer"):
        account = next(a for a in config["accounts"] if a["username"] == name)
        ctx = browser.new_context(viewport={"width":1500,"height":1050}, timezone_id="Asia/Shanghai")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: failures.append(r.status) if r.status >= 500 else None)
        page.goto(BASE + "/login", wait_until="networkidle")
        page.locator("#login-username").fill(name); page.locator("#login-password").fill(account["password"])
        page.get_by_role("button", name="登录", exact=False).click(); page.wait_for_url("**/app/**")
        token = page.evaluate("sessionStorage.getItem('piap_token')")
        contexts[name], pages[name], headers[name], tokens[name] = ctx, page, {"Authorization":"Bearer " + token}, token
    author, peer = pages.values()
    def get(path, name="demo_analyst"):
        response = contexts[name].request.get(BASE + "/api/v1" + path, headers=headers[name])
        assert response.status == 200, (path, response.status)
        return response.json()["data"]
    before = get(f"/risk-cases/{CASE}/workspace")
    author.goto(URL, wait_until="networkidle")
    expect(author.locator(".candidate-card")).to_have_count(1)
    author.locator(".candidate-card").get_by_role("button").click()
    detail = author.locator(".suggestion-detail")
    expect(detail).to_be_visible()
    row = get("/demo-sampling/suggestions?case_id=" + CASE)[0]
    assert row["snapshot"]["assessment_version"] == 5 and row["is_current"]
    if row["status"] == "demo_draft":
        # Inspect the rendered form, then use its labelled controls.
        assert detail.locator(".el-form-item__label").all_text_contents()[:3] == ["抽查理由", "关注内容", "资源假设、限制与待核实事项"]
        for label, value in zip(("抽查理由", "关注内容", "资源假设、限制与待核实事项"), TEXT):
            detail.locator(".el-form-item").filter(has=author.locator("label", has_text=label)).locator("textarea").fill(value)
        expect(detail.get_by_role("button", name="确认并固定演示建议", exact=True)).to_be_disabled()
        detail.get_by_role("button", name="保存演示草稿", exact=True).click()
        expect(detail.get_by_role("button", name="确认并固定演示建议", exact=True)).to_be_enabled()
        author.reload(wait_until="networkidle")
        for index, value in enumerate(TEXT): expect(detail.locator("textarea").nth(index)).to_have_value(value)
        row = get("/demo-sampling/suggestions/" + row["id"])
        # Real MySQL two-writer collision; identical authored content avoids
        # introducing arbitrary changes into the approved demo case.
        body = {"expected_revision": row["revision"], "content": row["content"]}
        def save(_): return request("/demo-sampling/suggestions/" + row["id"], token=tokens["demo_analyst"], body=body, method="PATCH")[0]
        with ThreadPoolExecutor(max_workers=2) as pool: codes = sorted(pool.map(save, range(2)))
        assert codes == [200,409], codes
        (OUT / "phase4c-concurrency.json").write_text(json.dumps({"save_statuses":codes}),encoding="utf-8")
        author.reload(wait_until="networkidle")
        detail.get_by_role("button", name="确认并固定演示建议", exact=True).click()
        expect(detail).to_contain_text("演示建议已固定")
    row = get("/demo-sampling/suggestions/" + row["id"])
    assert row["status"] == "demo_confirmed" and row["is_current"] and not row["can_edit"]
    assert all(row["content"][key] is None for key in ("sample_quantity","batch","location","proposed_time"))
    expect(detail.locator("textarea")).to_have_count(0)
    expect(detail.locator(".fixed-suggestion")).to_contain_text(TEXT[2])
    expect(detail).to_contain_text("【演示公开意见】")
    expect(detail).not_to_contain_text("【演示私聊】")
    author.screenshot(path=str(OUT / "phase4c-confirmed-desktop.png"), full_page=True)
    detail.locator(".fixed-suggestion").scroll_into_view_if_needed()
    author.screenshot(path=str(OUT / "phase4c-fixed-content-desktop.png"), full_page=True)
    author.reload(wait_until="networkidle"); expect(detail).to_contain_text("演示建议已固定")
    author.set_viewport_size({"width":390,"height":844})
    author.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    expect(detail).to_be_visible()
    assert author.evaluate("document.documentElement.scrollWidth <= innerWidth")
    author.screenshot(path=str(OUT / "phase4c-confirmed-mobile.png"), full_page=True)
    detail.locator("h2").scroll_into_view_if_needed()
    author.screenshot(path=str(OUT / "phase4c-sources-mobile.png"), full_page=True)
    detail.locator(".fixed-suggestion").scroll_into_view_if_needed()
    author.screenshot(path=str(OUT / "phase4c-fixed-content-mobile.png"), full_page=True)
    peer.goto(URL + "&suggestion=" + row["id"], wait_until="networkidle")
    expect(peer.locator(".suggestion-detail textarea")).to_have_count(0)
    expect(peer.locator(".fixed-suggestion")).to_contain_text(TEXT[0])
    peer.locator(".suggestion-detail").get_by_role("button", name="查看本版研判与协同", exact=True).click()
    peer.wait_for_url("**/app/risk-assessments?case_id=**")
    expect(peer.locator(".risk-collaboration-panel")).to_contain_text("协同已完成")
    assert "assessment_id=" + row["snapshot"]["assessment_id"] in peer.url
    peer.get_by_role("tab", name="抽查建议", exact=True).click()
    peer.get_by_role("button", name="查看本事项演示抽查建议", exact=True).click()
    peer.wait_for_url("**/app/sampling-plans?case_id=" + CASE)
    expect(peer.locator(".suggestion-row")).to_have_count(1)
    after = get(f"/risk-cases/{CASE}/workspace")
    assert before["case"] == after["case"] and before["assessment_versions"] == after["assessment_versions"]
    assert not get("/quality-supervision/sampling-candidates")["items"]
    assert not errors and not failures, (errors,failures)
    result = {"stage":"4c", "passed":True, "api_mode":"real_local_mysql", "case_id":CASE,
        "suggestion_id":row["id"], "assessment_id":row["snapshot"]["assessment_id"],
        "collaboration_id":row["snapshot"]["collaboration_id"], "status":row["status"],
        "saved_refresh_recovered":True, "unknown_fields_remain_null":True,
        "private_messages_excluded":True, "source_version_navigation":True,
        "desktop_mobile_no_overflow":True, "assessment_unchanged":True,
        "formal_candidates_empty":True, "real_model_called":False, "page_errors":errors,"http_5xx":failures}
    (OUT / "phase4c-browser-acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    browser.close()
