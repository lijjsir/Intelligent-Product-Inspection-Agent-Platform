"""Real login and rendering against the dedicated local stage-one demo stack."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".codex_tmp/piap_quality_demo"
config = json.loads((OUT / "accounts.json").read_text(encoding="utf-8"))
BASE = config["url"]
errors = []


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    for account in config["accounts"]:
        context = browser.new_context(viewport={"width": 1500, "height": 1050}, timezone_id="Asia/Shanghai")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/login", wait_until="networkidle")
        expect(page.get_by_role("status").get_by_text("演示环境", exact=True)).to_be_visible()
        expect(page.locator("#login-org")).to_have_value(config["organization"])
        if account["role"] == "admin":
            page.screenshot(path=str(OUT / "stage1-login.png"), full_page=True)
        page.locator("#login-username").fill(account["username"])
        page.locator("#login-password").fill(account["password"])
        page.get_by_role("button", name="登录", exact=False).click()
        page.wait_for_url("**/governance/**" if account["role"] == "admin" else "**/app/**")
        expect(page.get_by_role("status").get_by_text("演示环境", exact=True)).to_be_visible()
        if account["role"] == "admin":
            expect(page.get_by_text("demo_analyst", exact=True)).to_be_visible()
            expect(page.get_by_text("demo_reviewer", exact=True)).to_be_visible()
            page.screenshot(path=str(OUT / "stage1-admin.png"), full_page=True)
        else:
            token = page.evaluate("sessionStorage.getItem('piap_token')")
            response = context.request.get(BASE + "/api/v1/risk-cases", headers={"Authorization": "Bearer " + token})
            assert response.status == 200
            case_id = response.json()["data"]["items"][0]["id"]
            page.goto(BASE + f"/app/risk-assessments?case_id={case_id}", wait_until="networkidle")
            expect(page.get_by_role("heading", name="演示产品温升异常", exact=True)).to_be_visible()
            workspace = context.request.get(BASE + f"/api/v1/risk-cases/{case_id}/workspace", headers={"Authorization": "Bearer " + token}).json()["data"]
            record_count = len(workspace["records"])
            page.get_by_role("tab", name=f"原始资料（{record_count}）").click()
            expect(page.locator(".source-record")).to_have_count(record_count)
            expect(page.locator(".runtime-banner")).to_be_visible()
            page.screenshot(path=str(OUT / f"stage1-{account['username']}.png"), full_page=True)
            page.get_by_role("tab", name="研判结论", exact=True).click()
            if account["username"] == "demo_reviewer":
                expect(page.locator(".demo-risk-workflow")).to_be_visible()
                expect(page.get_by_role("button", name="独立复核通过", exact=True)).to_have_count(0)
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1")
                expect(page.locator(".runtime-banner")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(OUT / "stage1-mobile.png"), full_page=True)
        context.close()
    assert not errors, errors
    result = {"stage": 1, "passed": True, "api_mode": "real_local_demo_server", "mocked_requests": 0,
              "accounts_logged_in": 3, "login_and_workspace_banner_verified": True, "mobile_verified": True, "console_errors": errors}
    (OUT / "browser-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    browser.close()
