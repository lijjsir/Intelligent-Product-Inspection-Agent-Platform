from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture all network requests related to meetings
    meeting_requests = []
    page.on("request", lambda req: meeting_requests.append(f"REQ {req.method} {req.url}") if "meeting" in req.url.lower() or "v1/meetings" in req.url.lower() else None)
    page.on("response", lambda resp: meeting_requests.append(f"RES {resp.status} {resp.url}") if "meeting" in resp.url.lower() or "v1/meetings" in resp.url.lower() else None)

    # Capture console errors
    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

    # Navigate to login page
    page.goto("http://localhost:5175/login")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Fill login form
    inputs = page.locator("input").all()
    # Org ID input
    inputs[0].fill("admin")
    # Username input
    inputs[1].fill("admin")
    # Password input
    inputs[2].fill("admin123")

    # Click login
    page.locator("button", has_text="登录").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    print("=== After login URL ===")
    print(page.url)

    # Now navigate to meeting page
    page.goto("http://localhost:5175/meeting")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)

    print("\n=== Meeting page URL ===")
    print(page.url)

    # Take screenshot
    page.screenshot(path="meeting_page.png", full_page=True)

    print("\n=== Meeting API Requests ===")
    for r in meeting_requests:
        print(r)

    print("\n=== Console Errors ===")
    for e in console_errors:
        print(e)

    browser.close()
