from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright


API_BASE = os.getenv("QDL_E2E_API_BASE", "http://127.0.0.1:8000/api/v1")
WEB_BASE = os.getenv("QDL_E2E_WEB_BASE", "http://127.0.0.1:5173")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


def api(method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))["data"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def storage_script(session: dict) -> str:
    values = {
        "piap_token": session["access_token"],
        "piap_org_id": session["org_id"],
        "piap_role": session["role"],
        "piap_user_id": session["user_id"],
        "piap_username": session["username"],
        "piap_roles": json.dumps(session.get("roles") or [session["role"]]),
        "piap_plan_tier": session.get("plan_tier") or "standard",
        "piap_capabilities": json.dumps(session.get("capabilities") or []),
    }
    return "for (const [key, value] of Object.entries(%s)) sessionStorage.setItem(key, value);" % json.dumps(values)


def wait_for_network_idle(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = str(int(time.time() * 1000))
    session = api(
        "POST",
        "/auth/register",
        {
            "create_org": True,
            "org_name": "QDL 工作台验收组织",
            "org_slug": f"qdl-workbench-{suffix}",
            "username": f"qdl-owner-{suffix}",
            "email": f"qdl-owner-{suffix}@example.com",
            "password": "QdlE2e!2026",
            "role": "expert",
        },
    )
    room = api(
        "POST",
        "/meetings/rooms",
        {"title": "QDL v2 验收会议", "visibility": "team", "auto_participation_mode": "off"},
        session["access_token"],
    )
    message = api(
        "POST",
        f"/meetings/rooms/{room['id']}/messages",
        {
            "content": "产品 P001 的 B001 批次连续不合格，需要在明天复测并记录稳定性。",
            "skip_agent_trigger": True,
        },
        session["access_token"],
    )
    candidates = api(
        "POST",
        f"/meetings/rooms/{room['id']}/memories/extract",
        {"topic": "复测安排", "max_items": 3},
        session["access_token"],
    )
    assert candidates, "manual extraction did not create a candidate"
    candidate = candidates[0]
    assert candidate["qdl_json"]["version"] == "qdl-v2"
    assert candidate["qdl_validation_status"] == "valid"
    assert candidate["qdl_json"]["governance"]["status"] == "candidate"
    assert candidate["qdl_json"]["provenance"]["message_ids"] == [message["id"]]
    duplicate_candidates = api(
        "POST",
        f"/meetings/rooms/{room['id']}/memories/extract",
        {"topic": "复测安排", "max_items": 3},
        session["access_token"],
    )
    assert duplicate_candidates == [], "same source messages created duplicate candidates"

    console_errors: list[str] = []
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=EDGE_PATH)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.add_init_script(storage_script(session))
        page = context.new_page()
        page.on("console", lambda event: console_errors.append(event.text) if event.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        page.goto(f"{WEB_BASE}/app/meetings", wait_until="domcontentloaded", timeout=30_000)
        wait_for_network_idle(page)
        page.get_by_text("QDL v2 验收会议", exact=True).first.wait_for(timeout=30_000)
        page.get_by_role("tab", name=re.compile(r"^记忆")).click()
        qdl_section = page.locator(".workspace-memory-qdl-section")
        expect(qdl_section).to_be_visible(timeout=20_000)
        expect(qdl_section).to_contain_text("Schema 已通过")
        expect(qdl_section).to_contain_text("规则兜底提取")
        expect(qdl_section.locator(".qdl-property-row")).to_have_count(8)
        expect(qdl_section).to_contain_text("P001")
        expect(qdl_section).to_contain_text("B001")
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        page.screenshot(path=str(ARTIFACT_DIR / "qdl-workbench-desktop.png"), full_page=True)

        locate_button = qdl_section.get_by_role("button", name="定位消息").first
        locate_button.click()
        source = page.locator(f"#meeting-message-{message['id']}")
        expect(source).to_be_visible()
        assert source.evaluate("element => document.activeElement === element")

        page.get_by_role("tab", name=re.compile(r"^记忆")).click()
        page.set_viewport_size({"width": 375, "height": 812})
        qdl_section.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        meeting_page = page.locator(".meeting-page")
        assert meeting_page.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
        expect(qdl_section).to_be_visible()
        expect(qdl_section.locator(".workspace-memory-qdl-head")).to_be_visible()
        assert page.locator(".workspace-memory-review-actions").evaluate(
            "element => getComputedStyle(element).position === 'static'"
        )
        page.screenshot(path=str(ARTIFACT_DIR / "qdl-workbench-mobile.png"), full_page=True)

        context.close()
        browser.close()

    confirmed = api(
        "POST",
        f"/meetings/memories/{candidate['memory_id']}/confirm",
        {
            "scope": "meeting_room",
            "scope_id": room["id"],
            "title": candidate["title"],
            "content": candidate["content"],
        },
        session["access_token"],
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["qdl_validation_status"] == "valid"
    assert confirmed["qdl_json"]["governance"]["status"] == "confirmed"
    assert confirmed["qdl_json"]["consensus"]["status"] == "confirmed"

    assert not console_errors, console_errors
    assert not page_errors, page_errors
    print(
        json.dumps(
            {
                "candidate_id": candidate["memory_id"],
                "qdl_version": candidate["qdl_json"]["version"],
                "extraction_method": candidate["extraction_method"],
                "viewports": ["1440x1000", "375x812"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
