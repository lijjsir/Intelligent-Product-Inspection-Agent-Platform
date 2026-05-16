"""Full E2E test: login, quality tracing page, delete, Langfuse link."""
from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    page.on("console", lambda msg: None)  # suppress console noise
    results = {}

    # === 1. Login ===
    print("=== 1. Login ===")
    page.goto(f"{FRONTEND}/login")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    inputs = page.locator("input:visible")
    if inputs.count() >= 3:
        inputs.nth(0).fill("admin")
        inputs.nth(1).fill("operator")
        inputs.nth(2).fill("operator")
        print("   Filled org_id=admin, user=operator, password=operator")
    else:
        print(f"   ERROR: Expected 3 inputs, got {inputs.count()}")
        page.screenshot(path="/tmp/login_error.png", full_page=True)

    login_btn = page.locator('button:has-text("登录")')
    if login_btn.count() == 0:
        login_btn = page.locator('button[type="submit"]')
    login_btn.first.click()
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")

    url = page.url
    logged_in = "/login" not in url
    results["login"] = logged_in
    print(f"   Logged in: {logged_in} → {url[:80]}")

    # === 2. Navigate to quality tracing ===
    print("\n=== 2. Quality Tracing Page ===")
    page.goto(f"{FRONTEND}/governance/quality/analysis-center?tab=tracing")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path="/tmp/qt_page.png", full_page=True)

    # Check for table rows
    table_rows = page.locator("table tbody tr, .el-table__body tr")
    row_count = table_rows.count()
    results["tracing_rows"] = row_count
    print(f"   Table rows: {row_count}")

    # Check for empty state
    empty_text = page.locator('text=暂无')
    print(f"   Empty state: {empty_text.count() > 0}")

    # === 3. Check Langfuse button ===
    print("\n=== 3. Langfuse Link ===")
    lf_btns = page.locator('button:has-text("Langfuse")')
    print(f"   Langfuse buttons: {lf_btns.count()}")

    # === 4. Check delete button ===
    print("\n=== 4. Delete Button ===")
    del_btns = page.locator('button:has-text("删除")')
    print(f"   Delete buttons: {del_btns.count()}")

    if del_btns.count() > 0:
        # Click first delete button
        del_btns.first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path="/tmp/qt_delete_dialog.png", full_page=True)

        # Check for confirmation dialog
        confirm_btn = page.locator('button:has-text("删除")')
        cancel_btn = page.locator('button:has-text("取消")')
        dialog_visible = confirm_btn.count() >= 2  # one in table, one in dialog
        results["delete_dialog"] = dialog_visible
        print(f"   Confirm dialog: {dialog_visible}")

        # Cancel the delete for safety
        if cancel_btn.count() > 0:
            cancel_btn.last.click()
            print("   Cancelled delete (safety)")
            page.wait_for_timeout(500)

    # === 5. Check Langfuse web UI ===
    print("\n=== 5. Langfuse Web UI ===")
    page2 = browser.new_page()
    page2.goto("http://127.0.0.1:3000")
    page2.wait_for_load_state("networkidle")
    page2.wait_for_timeout(2000)
    page2.screenshot(path="/tmp/langfuse_ui.png", full_page=True)
    langfuse_title = page2.title()
    results["langfuse_ui"] = "Langfuse" in langfuse_title or "Sign" in langfuse_title
    print(f"   Langfuse UI accessible: {results['langfuse_ui']} (title={langfuse_title})")

    # === 6. Check Langfuse API health ===
    print("\n=== 6. Langfuse API ===")
    api_page = browser.new_page()
    api_page.goto("http://127.0.0.1:3000/api/public/traces?limit=1")
    api_page.wait_for_timeout(1000)
    api_body = api_page.content()
    has_json = "data" in api_body and "meta" in api_body
    results["langfuse_api"] = has_json
    print(f"   API returns JSON: {has_json}")

    # === Summary ===
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    all_pass = True
    for k, v in results.items():
        status = "PASS" if v else "FAIL"
        if not v:
            all_pass = False
        print(f"  [{status}] {k}")
    print(f"\nOverall: {'ALL PASSED' if all_pass else 'SOME FAILED'}")

    browser.close()
