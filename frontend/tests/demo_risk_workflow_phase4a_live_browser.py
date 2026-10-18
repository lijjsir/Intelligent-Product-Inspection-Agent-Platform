"""Two real browser logins; manual demo submissions, revision conflict and review."""
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".codex_tmp/piap_quality_demo"
config = json.loads((OUT / "accounts.json").read_text(encoding="utf-8"))
BASE = config["url"]
CASE = str(uuid5(NAMESPACE_URL, "piap-quality-demo:case"))
SUPPLEMENT = str(uuid5(NAMESPACE_URL, "piap-quality-demo:market-record-10"))
URL = BASE + f"/app/risk-assessments?case_id={CASE}"
RESULT = OUT / "phase4a-browser-acceptance.json"
errors, server_errors = [], []


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    contexts, pages, headers = {}, {}, {}
    for name in ("demo_analyst", "demo_reviewer"):
        account = next(a for a in config["accounts"] if a["username"] == name)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1050}, timezone_id="Asia/Shanghai")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: server_errors.append(r.status) if r.status >= 500 else None)
        page.goto(BASE + "/login", wait_until="networkidle")
        page.locator("#login-username").fill(name)
        page.locator("#login-password").fill(account["password"])
        page.get_by_role("button", name="登录", exact=False).click()
        page.wait_for_url("**/app/**")
        token = page.evaluate("sessionStorage.getItem('piap_token')")
        contexts[name], pages[name], headers[name] = ctx, page, {"Authorization": "Bearer " + token}
    author, reviewer = pages.values()
    def workspace(name="demo_analyst"):
        r = contexts[name].request.get(BASE + f"/api/v1/risk-cases/{CASE}/workspace", headers=headers[name])
        assert r.status == 200
        return r.json()["data"]
    def visit(page):
        page.goto(URL, wait_until="networkidle")
        expect(page.locator(".demo-risk-workflow")).to_be_visible()
    def panel(page): return page.locator(".demo-risk-workflow")
    def field(page, label): return panel(page).get_by_role("textbox", name=label, exact=True)
    def click_version(page, number):
        page.get_by_role("tab", name="版本与复核", exact=False).click()
        page.locator(".version-item").filter(has=page.get_by_text(f"第 {number} 版", exact=True)).click()
        expect(panel(page)).to_contain_text(f"第 {number} 版")
    def save_and_submit(suffix):
        summary = "【演示浏览器验收】温升线索需进一步核查" + suffix
        field(author, "演示结论").fill(summary)
        field(author, "判断依据").fill("引用已接入的模拟投诉与舆情，结合来源原文说明数量变化；结论范围仅限流程演示。")
        field(author, "证据缺口（每行一项）").fill("真实温升测量\n标准适用条件与样本代表性")
        field(author, "适用范围与限制").fill("全部为模拟资料，真实设备测量、发生概率和正式标准适用性尚未验证。")
        panel(author).get_by_role("checkbox").first.check()
        panel(author).get_by_role("button", name="保存演示草稿", exact=True).click()
        expect(panel(author).get_by_role("button", name="提交本版演示复核", exact=True)).to_be_enabled()
        author.reload(wait_until="networkidle")
        expect(field(author, "演示结论")).to_have_value(summary)
        panel(author).get_by_role("button", name="提交本版演示复核", exact=True).click()
        expect(panel(author).get_by_role("button", name="演示复核通过", exact=True)).to_be_disabled()
        expect(panel(author).locator(".demo-draft-form")).to_have_count(0)
        return summary
    def review_version(comment):
        visit(reviewer)
        panel(reviewer).get_by_role("button", name="演示复核通过", exact=True).click()
        expect(panel(reviewer)).to_contain_text("请填写针对本版本的复核意见")
        field(reviewer, "本版复核意见").fill(comment)
        panel(reviewer).get_by_role("button", name="演示复核通过", exact=True).click()
        expect(panel(reviewer).locator(".demo-review-note")).to_contain_text(comment)
        expect(panel(reviewer).locator(".workflow-version")).to_contain_text("演示复核通过")
    visit(author)
    existing = json.loads(RESULT.read_text(encoding="utf-8")) if RESULT.exists() else None
    if existing:
        old = contexts["demo_analyst"].request.get(BASE + f"/api/v1/risk-assessments/{existing['reviewed_before_supplement_id']}", headers=headers["demo_analyst"]).json()["data"]
        latest = workspace()["latest_assessment"]
        assert old["status"] == "demo_reviewed" and old["effective_status"] == "needs_reassessment"
        assert latest["status"] == "demo_reviewed" and latest["demo_validation"]["is_current"]
        result = {**existing, "reused": True}
    else:
        pending = workspace()["latest_assessment"]
        comment1 = "【演示浏览器复核】第一个提交版本的引用、缺口和限制已核对。"
        if pending["status"] == "demo_reviewed" and pending.get("demo_workflow", {}).get("content", {}).get("summary") == "【演示浏览器验收】温升线索需进一步核查（补证前）" and pending["review_comment"] == comment1:
            first = pending
            first_summary = pending["demo_workflow"]["content"]["summary"]
        else:
            panel(author).get_by_role("button", name="创建新版演示草稿", exact=True).click()
            expect(panel(author).locator(".demo-draft-form")).to_be_visible()
            # Another expert can inspect, but cannot edit an author's current draft.
            visit(reviewer)
            expect(panel(reviewer).locator(".demo-draft-form")).to_have_count(0)
            expect(panel(reviewer).get_by_role("button", name="提交本版演示复核", exact=True)).to_have_count(0)
            field(author, "演示结论").fill("【演示浏览器验收】草稿保存恢复")
            panel(author).get_by_role("button", name="保存演示草稿", exact=True).click()
            expect(panel(author).get_by_role("button", name="提交本版演示复核", exact=True)).to_be_enabled()
            w = workspace()
            draft = w["latest_assessment"]
            # A real concurrent save advances the server revision while this page
            # retains its old revision. The ensuing UI conflict preserves typed text.
            update = contexts["demo_analyst"].request.patch(BASE + f"/api/v1/risk-cases/{CASE}/demo-drafts/{draft['id']}",
                headers=headers["demo_analyst"], data={"expected_revision": draft["demo_workflow"]["revision"], "content": draft["demo_workflow"]["content"]})
            assert update.status == 200
            field(author, "演示结论").fill("【演示】冲突时保留的未保存输入")
            panel(author).get_by_role("button", name="保存演示草稿", exact=True).click()
            expect(panel(author)).to_contain_text("草稿已被更新")
            expect(field(author, "演示结论")).to_have_value("【演示】冲突时保留的未保存输入")
            panel(author).get_by_role("button", name="重新加载（放弃未保存输入）", exact=True).click()
            expect(field(author, "演示结论")).to_have_value("【演示浏览器验收】草稿保存恢复")
            first_summary = save_and_submit("（补证前）")
            first = workspace()["latest_assessment"]
            comment1 = "【演示浏览器复核】第一个提交版本的引用、缺口和限制已核对。"
            review_version(comment1)
            panel(reviewer).locator(".demo-review-note").scroll_into_view_if_needed()
            reviewer.screenshot(path=str(OUT / "phase4a-independent-review.png"), full_page=True)
        visit(author)
        author.get_by_role("button", name="关联补充资料", exact=True).click()
        dialog = author.get_by_role("dialog", name="关联补充资料", exact=True)
        dialog.locator(".el-select").click()
        dialog.get_by_role("combobox").fill("DEMO-QS-001-MKT-10")
        author.get_by_role("option").filter(has_text="模拟资料 10").click()
        dialog.get_by_role("heading", name="关联补充资料", exact=True).click()
        dialog.get_by_role("button", name="关联到本事项", exact=True).click()
        expect(panel(author)).to_contain_text("本版依据已变化")
        assert SUPPLEMENT in workspace()["case"]["source_record_ids"]
        stale = workspace()["latest_assessment"]
        assert stale["id"] == first["id"] and stale["effective_status"] == "needs_reassessment"
        assert stale["review_comment"] == comment1
        panel(author).get_by_role("button", name="创建新版演示草稿", exact=True).click()
        expect(field(author, "演示结论")).to_have_value(first_summary)
        second_summary = save_and_submit("（补证后）")
        comment2 = "【演示浏览器复核】已核对补充资料后的新版本；旧版意见继续保留。"
        review_version(comment2)
        latest = workspace()["latest_assessment"]
        assert latest["version"] == first["version"] + 1
        result = {"stage": "4a", "passed": True, "api_mode": "real_local_demo_server", "mocked_requests": 0,
            "case_id": CASE, "reviewed_before_supplement_id": first["id"], "latest_assessment_id": latest["id"],
            "versions": [first["version"], latest["version"]], "two_browser_accounts": True,
            "draft_refresh_restored": True, "concurrent_conflict_recovered": True, "self_review_disabled": True,
            "supplement_new_version_reviewed": True, "history_preserved": True, "reused": False}
    visit(author)
    click_version(author, result["versions"][0])
    expect(panel(author)).to_contain_text("历史版本 · 仅供查阅")
    expect(panel(author).locator(".demo-review-note")).to_contain_text("第一个提交版本")
    expect(panel(author).locator(".demo-draft-form")).to_have_count(0)
    expect(panel(author).get_by_role("button", name="创建新版演示草稿", exact=True)).to_have_count(0)
    author.screenshot(path=str(OUT / "phase4a-history-preserved.png"), full_page=True)
    panel(author).get_by_role("button", name="返回最新版本", exact=True).click()
    expect(panel(author).locator(".workflow-version")).to_contain_text("演示复核通过")
    author.reload(wait_until="networkidle")
    expect(panel(author).locator(".workflow-version")).to_contain_text("演示复核通过")
    panel(author).locator(".demo-review-note").scroll_into_view_if_needed()
    author.screenshot(path=str(OUT / "phase4a-reviewed-desktop.png"), full_page=True)
    author.set_viewport_size({"width": 390, "height": 844})
    author.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    panel(author).locator(".workflow-version").scroll_into_view_if_needed()
    expect(author.locator(".el-message")).to_have_count(0, timeout=15000)
    assert author.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(author.locator(".runtime-banner")).to_be_visible()
    author.screenshot(path=str(OUT / "phase4a-reviewed-mobile.png"), full_page=True)
    snapshot = workspace()
    assert snapshot["latest_assessment"]["probability"] is None
    assert snapshot["latest_assessment"]["submitted_by"] != snapshot["latest_assessment"]["reviewed_by"]
    candidates = contexts["demo_reviewer"].request.get(BASE + "/api/v1/quality-supervision/sampling-candidates", headers=headers["demo_reviewer"]).json()["data"]
    assert not candidates["items"]
    assert not errors, errors
    assert not server_errors, server_errors
    result.update(desktop_mobile_verified=True, formal_candidates_empty=True, real_model_called=False, page_errors=errors, http_5xx=server_errors)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    for context in contexts.values(): context.close()
    browser.close()
