"""Real local expert workflow: case -> invitation/meeting -> case/version feedback."""
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".codex_tmp/piap_quality_demo"
config = json.loads((OUT / "accounts.json").read_text(encoding="utf-8"))
BASE = config["url"]
CASE = str(uuid5(NAMESPACE_URL, "piap-quality-demo:case"))
URL = BASE + f"/app/risk-assessments?case_id={CASE}&tab=collaboration"
PURPOSE = "【演示】请同单位专家核对温升线索的证据缺口与结论限制。"
PUBLIC = "【演示公开意见】仍缺少真实温升测量和适用标准核对，请保留概率未知。"
PRIVATE = "【演示私聊】这条文字只供私聊，不应返回事项公开意见。"
errors, failures = [], []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    contexts, pages, headers, sessions = {}, {}, {}, {}
    for name in ("demo_analyst", "demo_reviewer"):
        account = next(a for a in config["accounts"] if a["username"] == name)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1050}, timezone_id="Asia/Shanghai")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: failures.append(r.status) if r.status >= 500 else None)
        page.goto(BASE + "/login", wait_until="networkidle")
        page.locator("#login-username").fill(name); page.locator("#login-password").fill(account["password"])
        page.get_by_role("button", name="登录", exact=False).click(); page.wait_for_url("**/app/**")
        token = page.evaluate("sessionStorage.getItem('piap_token')")
        contexts[name], pages[name], headers[name] = ctx, page, {"Authorization": "Bearer " + token}
        sessions[name] = ctx.request.get(BASE + "/api/v1/users/me", headers=headers[name]).json()["data"]
    author, peer = pages.values()
    def get(path, name="demo_analyst"):
        r = contexts[name].request.get(BASE + "/api/v1" + path, headers=headers[name]); assert r.status == 200, (path, r.status)
        return r.json()["data"]
    def workspace(): return get(f"/risk-cases/{CASE}/workspace")
    def panel(page): return page.locator(".risk-collaboration-panel")
    before = workspace(); original = before["latest_assessment"]
    author.goto(URL, wait_until="networkidle")
    expect(panel(author)).to_be_visible()
    rows = get(f"/risk-cases/{CASE}/collaborations")
    if not rows:
        panel(author).get_by_role("button", name="发起本版同单位协同", exact=True).click()
        dialog = author.get_by_role("dialog", name="发起同单位研判协同", exact=True)
        dialog.get_by_role("button", name="创建协同并关联本版", exact=True).click()
        expect(dialog).to_contain_text("请选择同单位协同负责人")
        dialog.locator(".el-select").first.click()
        author.get_by_role("option", name="demo_reviewer", exact=True).click()
        dialog.get_by_role("textbox", name="协同问题", exact=True).fill(PURPOSE)
        dialog.get_by_role("button", name="创建协同并关联本版", exact=True).click()
        expect(dialog).not_to_be_visible()
    expect(panel(author).locator(".collaboration-card")).to_have_count(1)
    link = get(f"/risk-cases/{CASE}/collaborations")[0]
    assert link["assessment_id"] == original["id"]
    (OUT / "phase4b-browser-progress.json").write_text(json.dumps({"collaboration_id": link["id"]}), encoding="utf-8")
    author.screenshot(path=str(OUT / "phase4b-case-collaboration.png"), full_page=True)
    panel(author).get_by_role("button", name="进入会议讨论", exact=True).click()
    author.wait_for_url("**/app/meetings?room_id=" + link["room_id"])
    expect(author.locator(".risk-meeting-context")).to_contain_text("固定第 5 版")
    expect(author.get_by_role("textbox", name="公共消息", exact=True)).to_be_visible()
    existing = get("/risk-collaborations/" + link["id"])
    if not any(m["content"] == PUBLIC for m in existing.get("discussion", [])):
        author.get_by_role("textbox", name="公共消息", exact=True).fill(PUBLIC)
        author.locator(".composer-actions").get_by_role("button", name="发送", exact=True).click()
        expect(author.get_by_text(PUBLIC, exact=True)).to_be_visible()
    # Real private message: verify it never appears in the case's public feedback.
    stored_private = OUT / "phase4b-private-tested.json"
    if not stored_private.exists():
        r = contexts["demo_reviewer"].request.post(BASE + f"/api/v1/meetings/rooms/{link['room_id']}/messages", headers=headers["demo_reviewer"],
            data={"content": PRIVATE, "private_recipient_user_id": sessions["demo_analyst"]["id"]})
        assert r.status == 200
        stored_private.write_text(json.dumps({"message_id": r.json()["data"]["id"]}), encoding="utf-8")
    author.screenshot(path=str(OUT / "phase4b-pinned-meeting.png"), full_page=True)
    author.set_viewport_size({"width":390,"height":844})
    author.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    expect(author.locator(".risk-meeting-context")).to_be_visible()
    author.wait_for_function("() => { const a=document.querySelector('.risk-meeting-context').getBoundingClientRect(); const b=document.querySelector('.meeting-workspace-nav').getBoundingClientRect(); return a.bottom <= b.top + 1; }")
    assert author.evaluate("document.documentElement.scrollWidth <= innerWidth")
    author.screenshot(path=str(OUT / "phase4b-pinned-meeting-mobile.png"), full_page=True)
    author.set_viewport_size({"width":1500,"height":1050})
    author.get_by_role("button", name="返回事项与本版协同意见", exact=True).click()
    author.wait_for_url("**/app/risk-assessments?case_id=**")
    expect(panel(author).locator(".collaboration-card")).to_have_count(1)
    panel(author).get_by_role("button", name="查看返回意见", exact=True).click()
    expect(panel(author).locator(".collaboration-feedback")).to_contain_text(PUBLIC)
    expect(panel(author).locator(".collaboration-feedback")).not_to_contain_text(PRIVATE)
    # Coordinator receives the native work item and completes it through the
    # existing collaboration center; this does not accept a risk assessment.
    current = get("/risk-collaborations/" + link["id"])
    view = "pending" if current["status"] == "pending" else "processed"
    peer.goto(BASE + f"/app/collab?view={view}&work_item=action_request:{link['message_id']}", wait_until="networkidle")
    expect(peer.locator(".risk-collab-notice")).to_contain_text("固定第 5 版")
    if current["status"] == "pending":
        peer.get_by_role("button", name="接受", exact=True).click()
        dialog = peer.get_by_role("dialog", name="接受工作项", exact=True)
        dialog.locator("textarea").fill("【演示】接收本版本协同请求")
        dialog.get_by_role("button", name="确认接受", exact=True).click()
        expect(dialog).not_to_be_visible()
        peer.goto(BASE + f"/app/collab?view=processed&work_item=action_request:{link['message_id']}", wait_until="networkidle")
    current = get("/risk-collaborations/" + link["id"])
    if current["status"] == "accepted":
        peer.get_by_role("button", name="完成", exact=True).click()
        dialog = peer.get_by_role("dialog", name="完成工作项", exact=True)
        dialog.locator("textarea").fill("【演示】已讨论资料缺口，意见已返回原事项，独立复核结论保持原记录。")
        dialog.get_by_role("button", name="确认完成", exact=True).click()
        expect(dialog).not_to_be_visible()
    expect(peer.locator(".risk-collab-notice")).to_be_visible()
    peer.screenshot(path=str(OUT / "phase4b-completed-work-item.png"), full_page=True)
    peer.get_by_role("link", name="查看来源", exact=True).click()
    expect(panel(peer)).to_be_visible()
    expect(panel(peer)).to_contain_text("协同已完成")
    panel(peer).get_by_role("button", name="查看返回意见", exact=True).click()
    expect(panel(peer).locator(".collaboration-feedback")).to_contain_text(PUBLIC)
    peer.reload(wait_until="networkidle")
    expect(panel(peer)).to_be_visible()
    after = workspace()
    assert after["latest_assessment"]["id"] == original["id"]
    assert after["latest_assessment"]["demo_workflow"] == original["demo_workflow"]
    assert len(after["assessment_versions"]) == len(before["assessment_versions"])
    assert after["case"]["source_record_ids"] == before["case"]["source_record_ids"]
    peer.set_viewport_size({"width": 390, "height": 844})
    peer.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    panel(peer).get_by_role("button", name="查看返回意见", exact=True).click()
    panel(peer).locator(".collaboration-feedback").scroll_into_view_if_needed()
    expect(peer.locator(".runtime-banner")).to_be_visible()
    assert peer.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(peer.locator(".el-message")).to_have_count(0, timeout=15000)
    peer.screenshot(path=str(OUT / "phase4b-feedback-mobile.png"), full_page=True)
    assert not errors, errors
    assert not failures, failures
    result = {"stage": "4b", "passed": True, "api_mode": "real_local_demo_server", "mocked_requests": 0,
        "case_id": CASE, "assessment_id": original["id"], "collaboration_id": link["id"], "room_id": link["room_id"],
        "two_browser_accounts": True, "version_pinned": True, "public_feedback_returned": True,
        "private_messages_excluded": True, "native_work_item_completed": True, "assessment_unchanged": True,
        "desktop_mobile_verified": True, "page_errors": errors, "http_5xx": failures, "real_model_called": False}
    (OUT / "phase4b-browser-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    for ctx in contexts.values(): ctx.close()
    browser.close()
