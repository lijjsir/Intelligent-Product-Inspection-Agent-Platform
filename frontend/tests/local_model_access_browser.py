"""Browser checks with synthetic API fixtures; no deployed server or model required."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


BASE = os.environ.get("PIAP_TEST_FRONTEND_URL", "http://127.0.0.1:15174")
OUT = Path(__file__).resolve().parent / "artifacts" / "local-model-access"
OUT.mkdir(parents=True, exist_ok=True)
MODEL = {
    "id": "local-test", "org_id": "test-org", "provider": "local_openai",
    "model_key": "test-vlm", "display_name": "本地多模态测试模型", "source_type": "local",
    "source_uri": "test-vlm", "endpoint": "http://host.docker.internal:11434/v1",
    "model_type": "multimodal", "priority": 1, "rpm_limit": 10, "is_active": True,
    "health_status": "unknown", "health_message": None, "has_api_key": False,
}


def main():
    requests = []
    errors = []

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        requests.append({"path": path, "method": request.method, "payload": request.post_data_json if request.post_data else None})
        if path.endswith("/runtime-context"):
            data = {"execution_mode": "business", "label": "本地测试", "notice": None, "organization_slug": "test-org", "case_code": None}
        elif path.endswith("/users/me"):
            data = {"id": "test-user", "org_id": "test-org", "username": "算法工程师", "role": "algorithm_engineer",
                    "effective_permissions": ["model_config", "model_config_read"], "capabilities": []}
        elif path.endswith("/model-configs"):
            data = [MODEL, {**MODEL, "id": "cloud-test", "provider": "deepseek", "display_name": "外部测试模型"}]
        elif path.endswith("/verify"):
            assert request.post_data_json == {"capabilities": ["text", "json", "vision", "tools"]}
            data = {"model_config_id": MODEL["id"], "model_key": MODEL["model_key"], "results": [
                {"capability": capability, "status": "healthy" if capability != "tools" else "unsupported",
                 "message": "测试接口通过" if capability != "tools" else "接口未接受工具调用", "latency_ms": 10}
                for capability in request.post_data_json["capabilities"]
            ]}
        elif path.endswith("/health-check"):
            data = {"health_status": "healthy", "health_message": "图片输入及文字响应通过"}
        else:
            data = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"code": 0, "message": "OK", "data": data}, ensure_ascii=False))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1000})
        context.add_init_script("""sessionStorage.setItem('piap_token','synthetic-browser-token');
            sessionStorage.setItem('piap_org_id','test-org'); sessionStorage.setItem('piap_role','algorithm_engineer');
            sessionStorage.setItem('piap_user_id','test-user');""")
        context.route("**/api/v1/**", api)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(BASE + "/governance/admin/models", wait_until="networkidle")
            expect(page.get_by_text(MODEL["display_name"], exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="接入验证", exact=True)).to_have_count(1)
            page.get_by_role("button", name="接入验证", exact=True).click()
            dialog = page.get_by_role("dialog", name="本地模型接入验证")
            expect(dialog.get_by_role("checkbox", checked=True)).to_have_count(4)
            dialog.get_by_role("button", name="开始验证", exact=True).click()
            expect(dialog.get_by_text("接口未接受工具调用", exact=True)).to_be_visible()
            expect(dialog.get_by_text("通过", exact=True)).to_have_count(3)
            expect(dialog.get_by_text("通过", exact=True).first).to_be_visible()
            page.screenshot(path=str(OUT / "capabilities.png"), full_page=True, animations="disabled")
            dialog.get_by_role("button", name="关闭", exact=True).click()
            page.get_by_role("button", name="新增 Base Model", exact=True).click()
            drawer = page.get_by_role("dialog", name="新增 Base Model")
            provider = drawer.locator(".el-form-item").filter(has=page.locator("label", has_text="提供方")).locator(".el-select__wrapper")
            provider.click()
            page.get_by_role("option", name="本地 OpenAI 兼容服务（Ollama / vLLM）").click()
            expect(drawer.get_by_text("本地服务未启用鉴权时可留空", exact=False)).to_be_visible()
            expect(drawer.get_by_placeholder("http://host.docker.internal:11434/v1")).to_be_visible()
            page.keyboard.press("Escape")
            page.screenshot(path=str(OUT / "local-model-form.png"), full_page=True, animations="disabled")
            assert not errors, errors
            assert not any(r["method"] == "POST" and r["path"].endswith("/model-configs") for r in requests)
            (OUT / "result.json").write_text(json.dumps({"passed": True, "api_mode": "synthetic fixtures", "page_errors": errors, "requests": requests}, ensure_ascii=False, indent=2), encoding="utf-8")
            print("PASS: local model form, capability selection/results, local-only action and no automatic writes")
        except Exception:
            page.screenshot(path=str(OUT / "failure.png"), full_page=True)
            (OUT / "failure.json").write_text(json.dumps({"url": page.url, "errors": errors, "requests": requests, "text": page.locator("body").inner_text()}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"url": page.url, "errors": errors, "requests": requests}, ensure_ascii=True))
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
