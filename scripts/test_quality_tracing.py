"""E2E test — login, navigate to quality tracing, verify UI elements."""
from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    # Step 1: Login via UI
    page.goto(f"{FRONTEND}/login")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # Check login page structure
    inputs = page.locator("input")
    input_count = inputs.count()
    print(f"1. Login inputs: {input_count}")

    # Print input placeholders for debugging
    for i in range(input_count):
        try:
            ph = inputs.nth(i).get_attribute("placeholder") or ""
            print(f"   input[{i}] placeholder='{ph}'")
        except Exception:
            pass

    # Fill login form (try common field patterns)
    all_inputs = page.locator("input:visible")
    if all_inputs.count() >= 3:
        # Organization ID, Username, Password
        all_inputs.nth(0).fill("piap-local-org")
        all_inputs.nth(1).fill("admin")
        all_inputs.nth(2).fill("admin123")
        print("2. Filled: org=piap-local-org, user=admin")

    # Find and click login button
    login_btn = page.locator('button:has-text("登录")')
    if login_btn.count() == 0:
        login_btn = page.locator('button[type="submit"]')
    if login_btn.count() > 0:
        login_btn.first.click()
        print("3. Clicked login")
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

    # Check where we landed
    current_url = page.url
    print(f"4. After login URL: {current_url}")

    # Navigate to analysis center quality tracing
    page.goto(f"{FRONTEND}/governance/quality/analysis-center?tab=tracing")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    print(f"5. Analysis center URL: {page.url}")

    # Take screenshot
    page.screenshot(path="/tmp/qt_final.png", full_page=True)

    # Check UI elements
    tabs = page.locator('[role="tab"], .el-tabs__item, [class*=tab]')
    print(f"6. Tabs: {tabs.count()}")

    table = page.locator("table, .el-table")
    print(f"7. Table: {table.count() > 0}")

    del_btns = page.locator('button:has-text("删除")')
    lf_btns = page.locator('button:has-text("Langfuse")')
    refresh_btn = page.locator('button:has-text("刷新")')
    print(f"8. Delete btn: {del_btns.count()}, Langfuse btn: {lf_btns.count()}, Refresh: {refresh_btn.count() > 0}")

    # Print all visible button texts
    all_btns = page.locator("button:visible")
    texts = []
    for i in range(min(all_btns.count(), 25)):
        try:
            t = all_btns.nth(i).text_content()
            if t and t.strip():
                texts.append(t.strip()[:30])
        except Exception:
            pass
    print(f"9. Visible buttons: {texts}")

    # Check for error messages
    error = page.locator('[class*=error], .el-message--error, .el-notification')
    if error.count() > 0:
        try:
            print(f"10. Errors: {error.first.text_content()[:100]}")
        except Exception:
            print("10. Error element found but couldn't read text")

    browser.close()
    print("\nE2E test completed")
