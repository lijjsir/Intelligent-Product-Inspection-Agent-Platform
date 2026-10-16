"""Capture the isolated standards and governance design preview."""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend/test-results/standards-governance-preview"
OUT.mkdir(parents=True, exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    desktop = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    errors = []
    desktop.on("pageerror", lambda error: errors.append(str(error)))
    desktop.goto("http://127.0.0.1:5174/standards-governance-preview.html")
    desktop.wait_for_load_state("networkidle")
    expect(desktop.get_by_role("heading", name="标准库工作台", exact=True)).to_be_visible()
    desktop.screenshot(path=str(OUT / "01-standard-library.png"), full_page=True)

    desktop.locator('[data-screen="requirements"]').click()
    expect(desktop.get_by_role("heading", name="检测要求总览", exact=True)).to_be_visible()
    desktop.locator('[data-req="distance"]').click()
    desktop.screenshot(path=str(OUT / "02-requirements.png"), full_page=True)

    desktop.locator('[data-screen="strategy"]').click()
    expect(desktop.get_by_role("heading", name="检测执行策略", exact=True)).to_be_visible()
    desktop.screenshot(path=str(OUT / "03-execution-strategy.png"), full_page=True)

    desktop.locator('[data-screen="governance"]').click()
    expect(desktop.get_by_role("heading", name="风险与知识治理", exact=True)).to_be_visible()
    desktop.screenshot(path=str(OUT / "04-governance.png"), full_page=True)

    mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    mobile.goto("http://127.0.0.1:5174/standards-governance-preview.html")
    mobile.wait_for_load_state("networkidle")
    mobile.screenshot(path=str(OUT / "05-mobile-library.png"), full_page=True)

    assert not errors, errors
    browser.close()
    print(f"captured {len(list(OUT.glob('*.png')))} screenshots; page errors={errors}")
