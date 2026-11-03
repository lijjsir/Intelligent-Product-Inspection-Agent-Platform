"""Explicit local acceptance: retry one failed image task and inspect result layout.

Run with --task-id for a task the operator wants to retry. Uses short-lived
tokens for existing users in that task's organization; never saves tokens.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--skip-retry", action="store_true", help="Inspect the completed result of a prior acceptance retry")
    args = parser.parse_args()
    bootstrap = '''import asyncio,json
from sqlalchemy import select
from infra.database.session import create_session,reset_async_engine_pool
from app.models.task import InspectionTask
from app.models.user import User
from app.core.security import create_access_token
async def main():
 async with create_session() as s:
  task=await s.get(InspectionTask,TASK_ID)
  assert task and task.status==EXPECTED_STATUS, 'Choose a failed task explicitly, or a completed task with --skip-retry'
  owner=await s.get(User,task.created_by)
  manager=(await s.execute(select(User).where(User.org_id==task.org_id,User.role.in_(['algorithm_engineer','admin']),User.is_active.is_(True)))).scalars().first()
  def session(user):return {'user_id':user.id,'org_id':user.org_id,'role':user.role,'username':user.username,'token':create_access_token(user.id,{'org_id':user.org_id,'role':user.role,'roles':[user.role]})}
  print(json.dumps({'owner':session(owner),'manager':session(manager)}))
 await reset_async_engine_pool()
asyncio.run(main())
'''.replace("TASK_ID", repr(args.task_id)).replace("EXPECTED_STATUS", repr("done" if args.skip_retry else "failed"))
    completed = subprocess.run(["docker", "exec", "-i", "piap-backend", "python", "-"],
                               input=bootstrap, text=True, capture_output=True, check=True)
    identities = json.loads(completed.stdout.strip().splitlines()[-1])
    output = Path(__file__).parent / "artifacts" / "model-retry-result"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        errors = []
        def context_for(identity):
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            state = {"piap_token": identity["token"], "piap_org_id": identity["org_id"],
                     "piap_user_id": identity["user_id"], "piap_username": identity["username"],
                     "piap_role": identity["role"], "piap_roles": json.dumps([identity["role"]])}
            context.add_init_script("for(const [key,value] of Object.entries(" + json.dumps(state) + ")) sessionStorage.setItem(key,value)")
            # The long-lived stream is independent of this retry/layout check.
            context.route("**/agent/tasks/*/stream?*", lambda route: route.fulfill(
                status=200, content_type="text/event-stream", body=": browser acceptance\n\n"))
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            return context, page
        owner, page = context_for(identities["owner"])
        headers = {"Authorization": "Bearer " + identities["owner"]["token"]}
        api = pw.request.new_context(base_url="http://127.0.0.1:8000", extra_http_headers=headers)
        before = api.get(f"/api/v1/tasks/{args.task_id}").json()["data"]
        digest = hashlib.sha256(json.dumps(before["image_urls"]).encode()).hexdigest()
        if not args.skip_retry:
            page.goto(f"http://127.0.0.1:5173/app/tasks/{args.task_id}", wait_until="networkidle")
            expect(page.get_by_test_id("task-outcome")).to_contain_text("检测未完成")
            expect(page.get_by_role("button", name="重新检测", exact=True)).to_be_visible()
            expect(page.get_by_text("本任务还没有标准执行记录", exact=False)).not_to_be_visible()
            page.screenshot(path=str(output / "failed-task.png"))
            with page.expect_response(lambda response: response.url.endswith(f"/tasks/{args.task_id}/retry")) as response:
                page.get_by_role("button", name="重新检测", exact=True).click()
            assert response.value.status == 200
            expect(page.get_by_role("dialog", name="新建标准执行记录")).not_to_be_visible()
        after = before
        for _ in range(300):
            after = api.get(f"/api/v1/tasks/{args.task_id}").json()["data"]
            if after["status"] not in {"queued", "running"}:
                break
            time.sleep(1)
        assert hashlib.sha256(json.dumps(after["image_urls"]).encode()).hexdigest() == digest
        assert after["status"] == "done", after.get("execution", {}).get("error")
        page.goto(f"http://127.0.0.1:5173/app/results/{args.task_id}", wait_until="networkidle")
        expect(page.get_by_test_id("result-overview")).to_be_visible()
        assert page.get_by_test_id("result-overview").bounding_box()["y"] < 600
        expect(page.get_by_text("读取版本", exact=True)).not_to_be_visible()
        page.screenshot(path=str(output / "result-first.png"))
        manager, models = context_for(identities["manager"])
        models.goto("http://127.0.0.1:5173/governance/admin/models", wait_until="networkidle")
        expect(models.get_by_role("button", name="能力验证", exact=True)).to_have_count(5)
        expect(models.get_by_role("button", name="检测", exact=True)).to_have_count(0)
        models.screenshot(path=str(output / "model-capabilities.png"))
        assert not errors, errors
        (output / "acceptance.json").write_text(json.dumps({"task_id": args.task_id,
            "status": after["status"], "retry_submitted": not args.skip_retry, "original_images_preserved": True,
            "result_first": True, "capability_buttons": 5, "page_errors": errors}, indent=2), encoding="utf-8")
        print(json.dumps({"status": after["status"], "retry_submitted": not args.skip_retry, "original_images_preserved": True, "page_errors": errors}))
        manager.close()
        owner.close()
        api.dispose()
        browser.close()


if __name__ == "__main__":
    main()
