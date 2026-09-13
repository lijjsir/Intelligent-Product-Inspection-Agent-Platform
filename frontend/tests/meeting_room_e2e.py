from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright


API_BASE = "http://127.0.0.1:8000/api/v1"
WEB_BASE = "http://127.0.0.1:5173"
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


def register(payload: dict) -> dict:
    return api("POST", "/auth/register", payload)


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
        # The meeting SSE connection can keep the network active indefinitely.
        pass


def open_meeting(page, title: str) -> list[dict]:
    predicate = lambda response: (
        "/api/v1/meetings/rooms/" in response.url
        and "/messages?" in response.url
        and "after_seq=" not in response.url
        and "before_seq=" not in response.url
        and response.request.method == "GET"
    )
    with page.expect_response(predicate, timeout=30_000) as response_info:
        page.goto(f"{WEB_BASE}/app/meetings", wait_until="domcontentloaded", timeout=30_000)
    wait_for_network_idle(page)
    page.get_by_text(title, exact=True).first.wait_for(timeout=30_000)
    return response_info.value.json()["data"]


def assert_minimum_size(locator, width: float = 44, height: float = 44) -> None:
    box = locator.bounding_box()
    assert box is not None, "interactive element is not visible"
    assert box["width"] >= width - 0.5, box
    assert box["height"] >= height - 0.5, box


def send_public(page, content: str) -> None:
    composer = page.locator(".composer")
    composer.get_by_label("公共消息").fill(content)
    composer.get_by_role("button", name="发送", exact=True).click()
    page.locator("article.message-row", has_text=content).wait_for(timeout=20_000)


def fulfill_private_agent(route, owner: dict, room_id: str) -> None:
    payload = route.request.post_data_json
    now = datetime.now(timezone.utc).isoformat()
    message = {
        "id": str(uuid.uuid4()),
        "room_id": room_id,
        "user_id": owner["user_id"],
        "username": "会议Agent",
        "seq_no": 20_000,
        "content": "这是仅当前用户可见的会议Agent验收回答。",
        "message_type": "agent",
        "agent_id": "general_agent",
        "mentions": None,
        "quote_message_id": None,
        "metadata_json": {
            "query": payload["query"],
            "visibility": "private",
            "response_visibility": "private",
            "interaction_mode": "private_chat",
            "private_recipient_user_id": owner["user_id"],
            "question_message_id": payload.get("question_message_id"),
            "question_sources": payload.get("question_sources") or [],
            "confirmation_status": "unconfirmed_ai_suggestion",
        },
        "private_recipient_user_id": owner["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "code": 0,
            "message": "ok",
            "data": {
                "selected_subgraph": "general_chat",
                "answer": message["content"],
                "message": message,
                "memory_sources": [],
                "candidate_memories": [],
                "response_visibility": "private",
                "escalation_required": False,
            },
        }, ensure_ascii=False),
    )


def fulfill_share(route, owner: dict, room_id: str) -> None:
    payload = route.request.post_data_json
    now = datetime.now(timezone.utc).isoformat()
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "code": 0,
            "message": "ok",
            "data": {
                "id": str(uuid.uuid4()),
                "room_id": room_id,
                "user_id": owner["user_id"],
                "username": owner["username"],
                "seq_no": 20_001,
                "content": payload["content"],
                "message_type": "user",
                "agent_id": None,
                "mentions": None,
                "quote_message_id": None,
                "metadata_json": {
                    "shared_agent_answer": True,
                    "visibility": "room",
                    "answer_message_id": payload["answer_message_id"],
                    "source_message_ids": payload.get("source_message_ids") or [],
                    "confirmation_status": "unconfirmed_ai_suggestion",
                },
                "private_recipient_user_id": None,
                "created_at": now,
                "updated_at": now,
            },
        }, ensure_ascii=False),
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = str(int(time.time() * 1000))
    org_slug = f"meeting-plan-e2e-{suffix}"
    password = "MeetingE2e!2026"
    owner = register({
        "create_org": True,
        "org_name": "会议完整改进验收组织",
        "org_slug": org_slug,
        "username": f"owner-{suffix}",
        "email": f"owner-{suffix}@example.com",
        "password": password,
        "role": "expert",
    })
    member = register({
        "create_org": False,
        "org_name": "",
        "org_slug": org_slug,
        "username": f"member-{suffix}",
        "email": f"member-{suffix}@example.com",
        "password": password,
        "role": "expert",
    })
    room = api("POST", "/meetings/rooms", {
        "title": "会议完整改进验收",
        "visibility": "team",
        "auto_participation_mode": "off",
    }, owner["access_token"])
    room_id = room["id"]
    api("POST", "/meetings/rooms/join", {"access_code": room["access_code"]}, member["access_token"])

    for index in range(1, 106):
        api("POST", f"/meetings/rooms/{room_id}/messages", {
            "content": "",
            "skip_agent_trigger": True,
            "quote_snapshot": {
                "source": "user",
                "author": "历史记录",
                "content": f"分页验收历史消息 {index}",
            },
        }, owner["access_token"])

    seeded_messages = []
    for content in (
        "A：建议按 A17 放行，请核对依据。",
        "B：我正在补充本批次检测记录。",
        "C：标准条款可能要求先完成复核。",
    ):
        seeded_messages.append(api("POST", f"/meetings/rooms/{room_id}/messages", {
            "content": content,
            "skip_agent_trigger": True,
        }, owner["access_token"]))

    deadline = time.time() + 15
    business_objects = []
    while time.time() < deadline:
        business_objects = api("GET", f"/meetings/rooms/{room_id}/business-objects", token=owner["access_token"])
        if any(item["object_value"].upper() == "A17" for item in business_objects):
            break
        time.sleep(0.4)
    assert any(item["object_value"].upper() == "A17" for item in business_objects)

    console_errors: list[str] = []
    page_errors: list[str] = []
    results: dict[str, object] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=EDGE_PATH)
        owner_context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            reduced_motion="reduce",
        )
        owner_context.add_init_script(storage_script(owner))
        page = owner_context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("**/api/v1/meetings/rooms/*/agent/run", lambda route: fulfill_private_agent(route, owner, room_id))
        page.route("**/api/v1/meetings/rooms/*/agent/share", lambda route: fulfill_share(route, owner, room_id))

        latest_page = open_meeting(page, "会议完整改进验收")
        assert len(latest_page) == 100
        assert latest_page[0]["seq_no"] > 1
        assert latest_page[-1]["id"] == seeded_messages[-1]["id"]
        message_list = page.locator(".meeting-message-pane .message-list")
        message_pane = page.locator(".meeting-message-pane")
        load_older = message_list.get_by_role("button", name="加载更早消息")
        expect(load_older).to_be_visible()
        page.wait_for_timeout(300)
        bottom_distance = message_list.evaluate("el => el.scrollHeight - el.scrollTop - el.clientHeight")
        assert bottom_distance <= 24, bottom_distance

        message_list.evaluate("el => { el.scrollTop = 0; }")
        first_loaded = message_list.locator("article.message-row").first
        first_id = first_loaded.get_attribute("id")
        first_top_before = first_loaded.bounding_box()["y"]
        pagination_before = message_list.evaluate(
            "el => ({ scrollHeight: el.scrollHeight, scrollTop: el.scrollTop, "
            "clientHeight: el.clientHeight, buttonHeight: el.querySelector('.load-older-messages')?.offsetHeight || 0 })"
        )
        with page.expect_response(lambda response: "before_seq=" in response.url and response.request.method == "GET"):
            load_older.click()
        pagination_timeline = []
        elapsed = 0
        for checkpoint in (0, 20, 60, 120, 220, 320):
            page.wait_for_timeout(checkpoint - elapsed)
            elapsed = checkpoint
            pagination_timeline.append({
                "ms": checkpoint,
                "top": page.locator(f"#{first_id}").bounding_box()["y"],
                **message_list.evaluate(
                    "el => ({ scrollHeight: el.scrollHeight, scrollTop: el.scrollTop, clientHeight: el.clientHeight })"
                ),
            })
        first_top_after = page.locator(f"#{first_id}").bounding_box()["y"]
        pagination_after = message_list.evaluate(
            "el => ({ scrollHeight: el.scrollHeight, scrollTop: el.scrollTop, "
            "clientHeight: el.clientHeight, buttonHeight: el.querySelector('.load-older-messages')?.offsetHeight || 0 })"
        )
        assert abs(first_top_after - first_top_before) <= 3, {
            "top_before": first_top_before,
            "top_after": first_top_after,
            "before": pagination_before,
            "after": pagination_after,
            "timeline": pagination_timeline,
        }
        expect(load_older).to_be_hidden()

        message_list.evaluate("el => { el.scrollTop = 160; }")
        scroll_before_remote = message_list.evaluate("el => el.scrollTop")
        api("POST", f"/meetings/rooms/{room_id}/messages", {
            "content": "远端成员新增消息，不应抢走历史阅读位置。",
            "skip_agent_trigger": True,
        }, member["access_token"])
        new_message_button = message_pane.get_by_role("button", name=re.compile(r"有 1 条新消息"))
        expect(new_message_button).to_be_visible(timeout=15_000)
        scroll_after_remote = message_list.evaluate("el => el.scrollTop")
        assert abs(scroll_after_remote - scroll_before_remote) <= 3
        jump_box = new_message_button.bounding_box()
        pane_box = message_pane.bounding_box()
        assert jump_box and pane_box
        assert pane_box["y"] <= jump_box["y"] <= pane_box["y"] + pane_box["height"] - jump_box["height"]
        assert_minimum_size(new_message_button, width=80)
        new_message_button.click()
        expect(new_message_button).to_be_hidden()
        assert message_list.evaluate("el => el.scrollHeight - el.scrollTop - el.clientHeight") <= 24

        a2 = "A2：@会议Agent 请核对 A17 放行是否违反当前标准。"
        b2 = "B2：检测记录仍在补充，请先保留分歧。"
        c2 = "C2：同时请比较复核与重新抽检两个方案。"
        send_public(page, a2)
        send_public(page, b2)
        send_public(page, c2)
        a_article = page.locator("article.message-row", has_text=a2)
        b_article = page.locator("article.message-row", has_text=b2)
        c_article = page.locator("article.message-row", has_text=c2)
        anchor = a_article.locator(".anchored-agent-reply").first
        expect(anchor).to_be_visible(timeout=30_000)
        assert b_article.locator(".anchored-agent-reply").count() == 0
        assert c_article.locator(".anchored-agent-reply").count() == 0
        anchor_reply_id = anchor.get_attribute("data-reply-id")
        assert anchor_reply_id
        anchor.get_by_role("button", name="查看完整回复").click()
        targeted_reply = page.locator(f"#agent-reply-{anchor_reply_id}")
        expect(targeted_reply).to_be_visible()
        expect(targeted_reply).to_have_class(re.compile(r"agent-thread-reply-targeted"))
        target_id = targeted_reply.get_attribute("id")
        assert target_id and target_id.startswith("agent-reply-")
        agent_list = page.locator(".agent-thread-list")
        target_box = targeted_reply.bounding_box()
        list_box = agent_list.bounding_box()
        assert target_box and list_box
        assert list_box["y"] <= target_box["y"] < list_box["y"] + list_box["height"]
        assert a2 in page.locator(".agent-qa-group", has=targeted_reply).inner_text()
        private_agent_tab = page.get_by_role("tab", name="我的对话", exact=True)
        public_agent_tab = page.get_by_role("tab", name="公开问答", exact=True)
        auto_agent_tab = page.get_by_role("tab", name="主动介入", exact=True)
        for tab in (private_agent_tab, public_agent_tab, auto_agent_tab):
            expect(tab).to_be_visible()
            assert_minimum_size(tab)
        expect(public_agent_tab).to_have_attribute("aria-selected", "true")
        auto_agent_tab.click()
        expect(page.locator(".agent-empty")).to_have_text("暂无 Agent 主动介入")
        expect(page.locator(f"#agent-reply-{anchor_reply_id}")).to_have_count(0)
        public_agent_tab.click()
        expect(page.locator(f"#agent-reply-{anchor_reply_id}")).to_be_visible()
        page.get_by_role("tab", name="会场", exact=True).click()

        duplicate_question = "重复定位验收：@会议Agent 当前会议室作用范围是什么？"
        first_duplicate = api("POST", f"/meetings/rooms/{room_id}/messages", {
            "content": duplicate_question,
        }, owner["access_token"])
        second_duplicate = api("POST", f"/meetings/rooms/{room_id}/messages", {
            "content": duplicate_question,
        }, owner["access_token"])
        first_duplicate_article = page.locator(f"#meeting-message-{first_duplicate['id']}")
        second_duplicate_article = page.locator(f"#meeting-message-{second_duplicate['id']}")
        first_duplicate_anchor = first_duplicate_article.locator(".anchored-agent-reply").first
        second_duplicate_anchor = second_duplicate_article.locator(".anchored-agent-reply").first
        expect(first_duplicate_anchor).to_be_visible(timeout=45_000)
        expect(second_duplicate_anchor).to_be_visible(timeout=45_000)

        first_duplicate_reply_id = first_duplicate_anchor.get_attribute("data-reply-id")
        assert first_duplicate_reply_id
        first_duplicate_anchor.get_by_role("button", name="查看完整回复").click()
        first_targeted_reply = page.locator(f"#agent-reply-{first_duplicate_reply_id}")
        expect(first_targeted_reply).to_be_visible()
        expect(first_targeted_reply).to_have_class(re.compile(r"agent-thread-reply-targeted"))
        expect(page.locator(".agent-thread-reply-targeted")).to_have_count(1)
        first_group = page.locator(".agent-qa-group", has=first_targeted_reply)
        expect(first_group.locator(f"#agent-question-{first_duplicate['id']}")).to_be_visible()
        expect(first_group.locator(f"#agent-question-{second_duplicate['id']}")).to_have_count(0)
        assert first_targeted_reply.evaluate("element => document.activeElement === element")

        agent_list.evaluate(
            "el => { el.style.height = '240px'; el.style.flex = '0 0 240px'; el.scrollTop = 0; }"
        )
        assert agent_list.evaluate("el => el.scrollHeight > el.clientHeight")
        page.get_by_role("tab", name="会场", exact=True).click()
        page.get_by_role("tab", name=re.compile(r"^AI(?:\s+\d+)?$")).click()
        page.wait_for_function(
            "el => el.scrollHeight - el.scrollTop - el.clientHeight <= 24",
            arg=agent_list.element_handle(),
        )
        page.get_by_role("tab", name="会场", exact=True).click()
        recent_texts = page.locator("article.message-row").all_inner_texts()
        positions = [next(index for index, text in enumerate(recent_texts) if value in text) for value in (a2, b2, c2)]
        assert positions == sorted(positions), positions

        ask_button = b_article.get_by_role("button", name="问会议Agent")
        assert_minimum_size(ask_button)
        ask_button.click()
        expect(page.get_by_role("tab", name="我的对话")).to_be_visible()
        expect(page.get_by_role("tab", name="公开问答")).to_be_visible()
        expect(page.get_by_role("tab", name="主动介入")).to_be_visible()
        assert_minimum_size(page.get_by_role("tab", name="我的对话"))
        assert_minimum_size(page.get_by_role("tab", name="公开问答"))
        assert_minimum_size(page.get_by_role("tab", name="主动介入"))
        expect(page.locator(".agent-source-chips")).to_contain_text("消息 #")

        page.get_by_role("tab", name="会场", exact=True).click()
        c_article = page.locator("article.message-row", has_text=c2)
        selected_span = c_article.locator(".message-bubble span")
        box = selected_span.bounding_box()
        assert box
        selected_span.evaluate(
            """el => {
              const node = el.firstChild;
              const text = node.textContent || '';
              const start = Math.max(0, text.indexOf('比较'));
              const range = document.createRange();
              range.setStart(node, start);
              range.setEnd(node, Math.min(text.length, start + 10));
              const selection = window.getSelection();
              selection.removeAllRanges();
              selection.addRange(range);
            }"""
        )
        c_article.dispatch_event("mouseup", {"clientX": box["x"] + 40, "clientY": box["y"] + 12})
        selection_toolbar = page.get_by_role("toolbar", name="所选文字操作")
        expect(selection_toolbar).to_be_visible()
        for label in ("复制", "问会议Agent", "加入当前提问"):
            assert_minimum_size(selection_toolbar.get_by_role("button", name=label), width=40)
        selection_toolbar.get_by_role("button", name="加入当前提问").click()
        expect(page.locator(".agent-source-chips > span")).to_have_count(2)

        discussion_entry = page.get_by_role("button", name=re.compile(r"讨论对象 \d+"))
        assert_minimum_size(discussion_entry, width=80)
        discussion_entry.click()
        drawer = page.locator(".el-drawer", has_text="纠正讨论对象")
        expect(drawer).to_be_visible()
        expect(drawer).to_contain_text("A17")
        drawer.locator("#business-object-correction").fill("不是A17，是A18")
        drawer.get_by_role("button", name="提交纠正").click()
        expect(drawer).to_contain_text("A18", timeout=15_000)
        page.keyboard.press("Escape")
        expect(drawer).to_be_hidden()

        page.get_by_role("tab", name=re.compile(r"^AI(?:\s+\d+)?$")).click()
        page.get_by_role("tab", name="我的对话").click()
        agent_input = page.get_by_label("询问会议Agent")
        agent_input.fill("请对刚才的方案比较给出一个简短建议。")
        agent_send = page.get_by_role("button", name="发送给会议Agent")
        assert_minimum_size(agent_send)
        agent_send.click()
        private_answer = page.get_by_text("这是仅当前用户可见的会议Agent验收回答。", exact=True)
        expect(private_answer).to_be_visible(timeout=20_000)
        private_reply = page.locator("article.agent-thread-reply", has_text="这是仅当前用户可见")
        share_button = private_reply.get_by_role("button", name="分享到会场")
        assert_minimum_size(share_button)
        share_button.click()
        share_dialog = page.locator(".el-dialog", has_text="会场全体成员可见")
        expect(share_dialog).to_be_visible()
        expect(share_dialog).to_contain_text("不会公开你的其他私人问答")
        share_dialog.get_by_role("button", name="确认公开").click()
        expect(share_dialog).to_be_hidden()
        page.get_by_role("tab", name="会场", exact=True).click()
        expect(page.locator("article.message-row", has_text="这是仅当前用户可见的会议Agent验收回答。")) .to_be_visible()

        page.screenshot(path=str(ARTIFACT_DIR / "meeting-room-e2e-desktop.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        assert page.evaluate("window.matchMedia('(prefers-reduced-motion: reduce)').matches")
        transition_ms = anchor.evaluate(
            """el => Math.max(...getComputedStyle(el).transitionDuration.split(',').map(value => {
              const number = Number.parseFloat(value) || 0;
              return value.trim().endsWith('ms') ? number : number * 1000;
            }))"""
        )
        assert transition_ms <= 1, transition_ms

        page.set_viewport_size({"width": 1024, "height": 900})
        page.wait_for_timeout(500)
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        workspace_tabs = page.locator(".meeting-workspace-tabs")
        audit_tab = workspace_tabs.get_by_role("tab", name=re.compile(r"^审计"))
        audit_tab.scroll_into_view_if_needed()
        expect(audit_tab).to_be_visible()
        tabs_box = workspace_tabs.bounding_box()
        audit_box = audit_tab.bounding_box()
        assert tabs_box and audit_box
        assert audit_box["x"] >= tabs_box["x"] - 1
        assert audit_box["x"] + audit_box["width"] <= tabs_box["x"] + tabs_box["width"] + 1
        workspace_tabs.evaluate("el => { el.scrollLeft = 0; }")
        page.screenshot(path=str(ARTIFACT_DIR / "meeting-room-e2e-tablet.png"), full_page=True)

        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(500)
        meeting_page = page.locator(".meeting-page")
        assert meeting_page.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        meeting_page.evaluate("el => { el.scrollTop = el.scrollHeight; }")
        page.wait_for_timeout(300)
        page.screenshot(path=str(ARTIFACT_DIR / "meeting-room-e2e-mobile.png"))

        member_context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
        member_context.add_init_script(storage_script(member))
        member_page = member_context.new_page()
        open_meeting(member_page, "会议完整改进验收")
        expect(member_page.get_by_text("请对刚才的方案比较给出一个简短建议。", exact=False)).to_have_count(0)
        expect(member_page.get_by_text(c2, exact=True)).to_be_visible()
        member_context.close()

        results = {
            "latest_page_count": len(latest_page),
            "latest_page_first_seq": latest_page[0]["seq_no"],
            "anchor_text": anchor.inner_text(),
            "business_object": "A17 -> A18",
            "private_question_hidden_from_member": True,
            "viewports": ["1440x1000", "1024x900", "375x812"],
            "console_errors": console_errors,
            "page_errors": page_errors,
        }
        owner_context.close()
        browser.close()

    assert not console_errors, console_errors
    assert not page_errors, page_errors
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
