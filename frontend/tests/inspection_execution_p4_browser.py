import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:5173", wait_until="networkidle")
    page.screenshot(path="frontend/test-results/p4-home.png", full_page=True)
    print("title:", page.title())
    print("url:", page.url)
    print("body:", page.locator("body").inner_text()[:500])
    browser.close()
