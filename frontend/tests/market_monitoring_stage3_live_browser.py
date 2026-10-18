"""Real local stage-three interactions. No intercepted or mocked API requests."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".codex_tmp/piap_quality_demo"
config = json.loads((OUT / "accounts.json").read_text(encoding="utf-8"))
accepted = json.loads((OUT / "phase3-api-acceptance.json").read_text(encoding="utf-8"))
BASE, DAY, CASE = config["url"], accepted["as_of"], accepted["scenario_case_id"]
errors, server_errors = [], []


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1100}, timezone_id="Asia/Shanghai")
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("response", lambda response: server_errors.append(response.status) if response.status >= 500 else None)
    analyst = next(a for a in config["accounts"] if a["username"] == "demo_analyst")
    page.goto(BASE + "/login", wait_until="networkidle")
    page.locator("#login-username").fill(analyst["username"])
    page.locator("#login-password").fill(analyst["password"])
    page.get_by_role("button", name="登录", exact=False).click()
    page.wait_for_url("**/app/**")
    market_url = BASE + f"/app/quality-analytics?as_of={DAY}"
    page.goto(market_url, wait_until="networkidle")
    monitor = page.locator(".market-monitor")
    expect(monitor.locator(".overview-metrics")).to_contain_text("投诉资料 · 本期")
    expect(monitor.locator(".overview-metrics article").first.locator("strong")).to_have_text("6条")
    expect(monitor.locator(".overview-metrics article").nth(2).locator("strong")).to_have_text("2条")
    expect(page.locator(".runtime-banner")).to_be_visible()
    monitor.get_by_text("查看每日数量明细", exact=True).click()
    expect(monitor.locator(".trend-data tbody tr")).to_have_count(14)
    monitor.get_by_text("查看每日数量明细", exact=True).click()
    page.screenshot(path=str(OUT / "phase3-overview.png"), full_page=True)
    monitor.get_by_role("tab", name="异常监测", exact=True).click()
    expect(monitor.locator(".signal-card")).to_have_count(2)
    expect(monitor.locator(".signal-card").filter(has_text="新增集中线索")).to_contain_text("不计算增长百分比")
    page.screenshot(path=str(OUT / "phase3-anomalies.png"), full_page=True)
    # An already focused object is reused. Empty reasons stay in the dialog.
    monitor.locator(".signal-card").first.get_by_role("button", name="关注对象").click()
    dialog = page.get_by_role("dialog", name="添加重点对象", exact=True)
    dialog.get_by_role("button", name="保存关注").click()
    expect(dialog).to_contain_text("填写关注依据")
    dialog.locator("textarea").fill("【演示】浏览器验收持续关注温升变化")
    dialog.get_by_role("button", name="保存关注").click()
    expect(dialog).not_to_be_visible()
    monitor.get_by_role("tab", name="重点对象", exact=True).click()
    expect(monitor.locator(".focus-card")).to_have_count(1)
    page.screenshot(path=str(OUT / "phase3-focus.png"), full_page=True)
    monitor.get_by_role("button", name="查看关联资料", exact=True).click()
    page.wait_for_url("**/app/quality-data?product_id=*")
    expect(page.locator('.el-select__selected-item').filter(has_text="演示产品A")).to_be_visible()
    # Deep links restore the immutable snapshot after refresh.
    signal_url = market_url + f"&tab=anomalies&signal={accepted['opinion_signal_id']}"
    page.goto(signal_url, wait_until="networkidle")
    drawer = page.get_by_role("dialog", name="数量线索依据", exact=True)
    expect(drawer).to_contain_text("模拟资料")
    expect(drawer.locator(".source-row")).to_have_count(4)
    drawer.locator(".source-row").first.get_by_role("button", name="查看原文与附件").click()
    page.wait_for_url("**/app/quality-data?record=*")
    expect(page.get_by_role("dialog", name="原始资料详情", exact=True)).to_be_visible()
    page.goto(signal_url, wait_until="networkidle")
    page.reload(wait_until="networkidle")
    expect(drawer).to_contain_text("上期 0 条 → 本期 4 条")
    page.screenshot(path=str(OUT / "phase3-signal-snapshot.png"), full_page=True)
    existing = drawer.get_by_role("button", name="进入已关联研判事项", exact=True)
    if existing.count():
        existing.click()
    else:
        drawer.get_by_role("button", name="转为研判事项", exact=True).click()
        conversion = page.get_by_role("dialog", name="关联研判事项", exact=True)
        conversion.locator(".el-select").click()
        page.get_by_role("option", name="DEMO-QS-001 · 演示产品温升异常", exact=True).click()
        conversion.get_by_role("button", name="确认关联并进入研判").click()
    page.wait_for_url(BASE + f"/app/risk-assessments?case_id={CASE}")
    expect(page.get_by_role("heading", name="演示产品温升异常", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="查看市场线索依据", exact=True)).to_have_count(2)
    page.get_by_role("button", name="查看市场线索依据", exact=True).last.click()
    expect(drawer).to_contain_text("数量线索")
    # Rule editor does not silently change thresholds without an explanation.
    page.goto(market_url, wait_until="networkidle")
    monitor.get_by_role("button", name="规则与覆盖", exact=True).click()
    editor = page.get_by_role("dialog", name="规则与资料覆盖", exact=True)
    editor.get_by_role("button", name="保存新规则版本", exact=True).click()
    expect(editor).to_contain_text("请填写规则调整依据")
    editor.get_by_role("tab", name="来源覆盖", exact=True).click()
    expect(editor).to_contain_text("覆盖不足时显示")
    editor.locator(".el-dialog__headerbtn").click()
    # A future date fails explicitly and recovers with a valid date.
    monitor.locator('input[type="date"]').fill("2100-01-01")
    monitor.get_by_role("button", name="刷新监测", exact=True).click()
    expect(monitor).to_contain_text("不能晚于北京时间今天")
    monitor.locator('input[type="date"]').fill(DAY)
    monitor.get_by_role("button", name="刷新监测", exact=True).click()
    expect(monitor.locator(".overview-metrics")).to_be_visible()
    # Mobile overflow, touch layout and persistent demo marker.
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
    monitor.get_by_role("tab", name="异常监测", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(page.locator(".el-message")).to_have_count(0, timeout=15000)
    monitor.locator(".signal-card").first.scroll_into_view_if_needed()
    page.wait_for_timeout(350)  # Element Plus tab indicator and scroll animation.
    page.screenshot(path=str(OUT / "phase3-mobile.png"), full_page=True)
    monitor.locator(".signal-card").first.get_by_role("button", name="查看线索依据", exact=True).click()
    expect(drawer).to_be_visible()
    expect(drawer.locator(".source-row")).to_have_count(7)
    page.wait_for_function("() => { const r = document.querySelector('.el-drawer').getBoundingClientRect(); return r.x <= 1 && r.width >= innerWidth - 1; }")
    assert drawer.bounding_box()["y"] >= page.locator(".runtime-banner").bounding_box()["height"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(OUT / "phase3-mobile-snapshot.png"), full_page=True)
    assert not errors, errors
    assert not server_errors, server_errors
    result = {"stage": 3, "passed": True, "api_mode": "real_local_demo_server", "mocked_requests": 0,
              "three_views": True, "raw_record_roundtrip": True, "refresh_snapshot_restored": True,
              "same_case_reused": True, "focus_deduplicated": True, "invalid_date_recovery": True,
              "desktop_mobile_verified": True, "page_errors": errors, "http_5xx": server_errors}
    (OUT / "phase3-browser-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    context.close()
    browser.close()
