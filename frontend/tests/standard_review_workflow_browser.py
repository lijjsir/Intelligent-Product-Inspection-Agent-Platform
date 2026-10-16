"""New review workspace against actual isolated API services, never production APIs."""
import json,sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
sys.stdout.reconfigure(encoding="utf-8")
BASE="http://127.0.0.1:5173"
API="http://127.0.0.1:8015"
OUTPUT=Path(__file__).resolve().parents[1]/"test-results"/"standard-review-20261013"
OUTPUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,channel="chromium")
    request=pw.request.new_context();ids=request.get(API+"/_fixture/info").json()
    assert ids["isolated"] is True
    actions=[];errors=[];checks=[]
    def new_page(token,role,uid):
        ctx=browser.new_context(viewport={"width":1680,"height":1080})
        page=ctx.new_page()
        state={"piap_token":token,"piap_role":role,"piap_roles":json.dumps([role]),"piap_user_id":uid,"piap_org_id":ids["org_id"],"piap_username":"isolated test"}
        page.add_init_script("try { if(location.origin==='http://127.0.0.1:5173' && window.sessionStorage) { for(const [k,v] of Object.entries("+json.dumps(state)+"))sessionStorage.setItem(k,v); } } catch (_) {}")
        page.on("pageerror",lambda e:errors.append(str(e)))
        def forward(route):
            parsed=urlparse(route.request.url)
            if parsed.path=="/api/v1/streams/session":
                body=route.request.post_data_json
                route.fulfill(status=200,content_type="application/json",body=json.dumps({"success":True,"data":{
                    "stream_token":"isolated-no-events","expires_at":"2027-01-01T00:00:00Z","resource":body["resource"],"resource_id":body["resource_id"]}}))
                return
            if parsed.path.endswith("/collab/stream"):
                route.fulfill(status=200,content_type="text/event-stream",body="retry: 60000\n\n: isolated no events\n\n")
                return
            if parsed.path in {"/api/v1/quality-products/catalog","/api/v1/quality-products/options"}:
                route.fulfill(status=200,content_type="application/json",body=json.dumps({"success":True,"data":{"categories":[],"products":[]}}))
                return
            target=API+parsed.path+("?"+parsed.query if parsed.query else "")
            response=route.fetch(url=target)
            if route.request.method=="POST" and parsed.path.startswith("/api/v1/standard-documents/"):
                actions.append({"role":token,"path":parsed.path,"status":response.status})
            route.fulfill(status=response.status,headers={**response.headers,"access-control-allow-origin":"*"},body=response.body())
        page.route("**/api/v1/**",forward)
        return ctx,page
    def field(dialog,label):return dialog.locator(".el-form-item").filter(has_text=label).locator("input,textarea").first

    ctx,a=new_page("fixture-admin","admin",ids["admin_id"])
    a.goto(BASE+"/governance/admin/inspection-standards",wait_until="networkidle")
    expect(a.get_by_role("heading",name="检测标准库",exact=True)).to_be_visible()
    a.screenshot(path=str(OUTPUT/"00-admin-library.png"),full_page=True)
    a.get_by_role("button",name="审核分派与发布",exact=True).click()
    a.get_by_role("button",name="分派",exact=True).click()
    dialog=a.get_by_role("dialog",name="分派标准审核")
    dialog.locator(".el-select").click();a.get_by_role("option",name="隔离核验专家A",exact=True).click()
    field(dialog,"分派依据与说明").fill("工业标准隔离流程验收，分派给核验专家A")
    dialog.get_by_role("button",name="记录并分派",exact=True).click()
    expect(dialog).not_to_be_visible();checks.append("管理员通过真实隔离API分派修订")
    a.screenshot(path=str(OUTPUT/"01-admin-assignment.png"),full_page=True)

    ctx1,p=new_page("fixture-expert","expert",ids["expert_id"])
    p.goto(BASE+"/app/standard-reviews",wait_until="networkidle")
    expect(p.get_by_role("heading",name="标准审核工作台")).to_be_visible()
    p.get_by_role("button",name="进入审核",exact=True).click()
    expect(p.get_by_role("button",name="发布标准",exact=True)).to_have_count(0)
    p.get_by_role("button",name="打开原PDF核对",exact=True).first.click()
    expect(p.locator('iframe[title="标准审核原PDF"]')).to_be_visible()
    p.get_by_role("button",name="编辑整理稿",exact=True).click()
    edit=p.get_by_role("dialog",name="核对检测项目与要求")
    field(edit,"试验条件与规格分支").fill("dry road")
    field(edit,"核对说明").fill("按原文补充干燥道路试验条件")
    edit.get_by_role("button",name="保存整理稿",exact=True).click()
    expect(edit).not_to_be_visible()
    expect(p.get_by_text("本人整理，须交其他专家确认",exact=True)).to_be_visible()
    expect(p.get_by_role("button",name="逐项专业核对",exact=True)).to_have_count(0)
    checks.append("专家A修改整理后不能确认本人要求，也无默认发布按钮")
    p.screenshot(path=str(OUTPUT/"02-expert-preparation.png"),full_page=True)

    a.get_by_role("button",name="刷新",exact=True).last.click()
    a.get_by_role("button",name="分派",exact=True).click()
    dialog=a.get_by_role("dialog",name="分派标准审核")
    dialog.locator(".el-select").click();a.get_by_role("option",name="隔离核验专家B",exact=True).click()
    field(dialog,"分派依据与说明").fill("由另一位专家独立核对整理后的要求")
    dialog.get_by_role("button",name="记录并分派",exact=True).click();expect(dialog).not_to_be_visible()

    ctx2,q=new_page("fixture-expert2","expert",ids["expert2_id"])
    q.goto(BASE+"/app/standard-reviews",wait_until="networkidle")
    q.get_by_role("button",name="进入审核",exact=True).click()
    q.get_by_role("button",name="逐项专业核对",exact=True).click()
    review=q.get_by_role("dialog",name="逐项专业核对")
    field(review,"专业核对意见").fill("已对照隔离PDF，要求和干燥道路条件与原文一致")
    field(review,"核对依据（每行一条）").fill("隔离PDF第1页，6.1与7.1条款")
    review.get_by_role("button",name="记录逐项决定",exact=True).click();expect(review).not_to_be_visible()
    q.get_by_role("button",name="专业核验",exact=True).click()
    review=q.get_by_role("dialog",name="专业核验",exact=True)
    field(review,"核对说明 / 操作原因").fill("隔离原文来源版本和类型已核对")
    field(review,"核对依据（每行一条，批准时必填）").fill("隔离PDF第1页，测试来源登记")
    review.get_by_role("button",name="确认并记录",exact=True).click();expect(review).not_to_be_visible()
    expect(q.get_by_text("1 项已确认",exact=True)).to_be_visible()
    checks.append("专家B逐项确认并完成原文核验，依据真实持久化")
    q.screenshot(path=str(OUTPUT/"03-expert-independent-review.png"),full_page=True)

    a.get_by_role("button",name="刷新",exact=True).last.click()
    a.get_by_text("待发布",exact=True).click()
    a.get_by_role("button",name="核对并发布",exact=True).click()
    expect(a.get_by_role("button",name="专业核验",exact=True)).to_have_count(0)
    a.get_by_role("button",name="发布标准",exact=True).click()
    publish=a.get_by_role("dialog",name="发布标准",exact=True)
    field(publish,"核对说明 / 操作原因").fill("独立审核完成，隔离流程验证发布请求")
    publish.get_by_role("button",name="确认并记录",exact=True).click();expect(publish).not_to_be_visible()
    expect(a.locator(".admission-stages").get_by_text("发布处理中",exact=True)).to_be_visible()
    checks.append("管理员提交发布至outbox，专家与管理员职责分开")
    a.screenshot(path=str(OUTPUT/"04-admin-publication.png"),full_page=True)

    original=request.get(API+f'/api/v1/standard-documents/{ids["document_id"]}/revisions/{ids["revision_id"]}',headers={"Authorization":"Bearer fixture-admin"}).json()["data"]
    assert original["candidates"][0]["prepared_by"]==ids["expert_id"]
    assert original["candidates"][0]["reviewed_by"]==ids["expert2_id"]
    assert original["candidates"][0]["review_evidence_refs"]
    assert original["published_by"]==ids["admin_id"]
    assert all(x["status"]==200 for x in actions),actions
    assert not errors,errors
    for context in [ctx,ctx1,ctx2]:context.close()
    browser.close();request.dispose()
    report={"checks":checks,"actions":actions,"page_errors":errors,"mode":"actual API services + disposable SQLite + synthetic identities; zero production writes"}
    (OUTPUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
