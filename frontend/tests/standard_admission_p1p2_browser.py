"""P1/P2 browser workflows on API fixtures; no live approvals or data writes."""
import copy
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import expect, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
OUTPUT=Path(__file__).resolve().parents[1]/"test-results"/"standard-admission-p1p2"
OUTPUT.mkdir(parents=True,exist_ok=True)
errors=[]
checks=[]
all_actions=[]


def candidate():
    return {"id":"candidate-fixture","clause_no":"6.1.1","page_number":1,"source_text":"浏览器测试候选：最高车速不得大于25 km/h，应按7.1试验。",
        "indicator":"最高车速","method":"","conditions":"","unit":"","requirement":"","operator":"unresolved",
        "measurement_key":"","applicability":"","status":"pending","missing_fields":["方法","单位"],"warning":"测试数据，核对原PDF","reviewed_by":None}


def revision(publication="unpublished",owner="admin-fixture"):
    return {"id":"revision-fixture","document_id":"doc-fixture","revision_no":1,"row_version":1,
        "snapshot":{"standard_no":"GB 17761-2018","standard_name":"浏览器隔离测试资料","standard_level":"GB","standard_status":"被代替",
            "product_category":"电动自行车","domain":"电动自行车","resource_type":"standard","source_url":"https://example.invalid/fixture",
            "publisher":"测试机构","effective_from":"2019-04-15","effective_to":"2025-08-31","production_from":"2019-04-15",
            "production_to":"2025-08-31","scope_notes":"隔离测试历史范围","file_name":"fixture.pdf","legacy":False},
        "file_hash":"fixture-hash","processing_status":"parsed","review_status":"approved" if publication=="published" else "pending",
        "publication_status":publication,"extraction_status":"needs_review","created_by":owner,"reviewed_by":None,"created_at":"2026-10-05",
        "published_by":None,"published_at":None,"page_count":1,"candidate_count":1,"confirmed_count":0,"issues":[],
        "pages":[{"page_number":1,"text":"测试页 GB 17761-2018"}],"candidates":[candidate()],"reviews":[],"jobs":[]}


def new_page(browser,role,initial=None,permissions=None):
    context=browser.new_context(viewport={"width":1600,"height":1050})
    page=context.new_page()
    perms=permissions or ["inspection_standard_library_read","standard_admission_submit","standard_admission_review","standard_admission_publish","quality"]
    if role=="admin": perms+=["inspection_standard_library","inspection_spec_read","user"]
    user_id=f"{role}-fixture"
    state={"revisions":[initial or revision()],"actions":[]}
    session={"piap_token":"fixture","piap_role":role,"piap_roles":json.dumps([role]),"piap_user_id":user_id,"piap_org_id":"fixture-org","piap_username":role}
    page.add_init_script("for(const [k,v] of Object.entries("+json.dumps(session)+"))sessionStorage.setItem(k,v);")
    page.on("pageerror",lambda e:errors.append(str(e)))
    lib={"id":"lib-fixture","org_id":"fixture-org","name":"工业标准测试分组","product_family":"电动自行车","domain":"电动自行车","product_category":"电动自行车",
        "rag_space_ids":[],"rag_spaces":[],"pdf_count":1,"document_count":1,"chunk_count":1,"total_document_count":1,
        "import_status":"pending_review","is_active":True,"has_quality_threshold":False}

    def handle(route):
        path=urlparse(route.request.url).path.removeprefix("/api")
        method=route.request.method
        if method not in {"GET","HEAD","OPTIONS"}:
            body=route.request.post_data_json
            state["actions"].append({"path":path,"body":body});all_actions.append({"role":role,"path":path})
        active=state["revisions"][0]
        if path=="/v1/users/me":
            data={"id":user_id,"org_id":"fixture-org","username":role,"email":"fixture@example.com","role":role,"roles":[role],"is_active":True,"effective_permissions":perms}
        elif path in {"/v1/standard-libraries","/v1/inspection-standards"}:data={"items":[lib],"total":1,"page":1,"size":50}
        elif path.endswith("/documents"):
            data={"items":[{"id":"doc-fixture","library_id":"lib-fixture","standard_no":"GB 17761-2018","standard_name":"浏览器隔离测试资料",
                "domain":"电动自行车","standard_level":"GB","standard_status":"被代替","file_name":"fixture.pdf","file_path":"fixture.pdf",
                "chunk_count":1,"page_count":1,"import_status":"parsed","processing_status":"parsed","review_status":active["review_status"],
                "publication_status":active["publication_status"],"current_revision_id":active["id"],"published_revision_id":active["id"] if active["publication_status"]=="published" else None}],"total":1,"page":1,"size":50}
        elif path=="/v1/standard-documents/doc-fixture/revisions" and method=="GET":data=state["revisions"]
        elif path=="/v1/standard-documents/doc-fixture/revisions" and method=="POST":
            fresh=copy.deepcopy(active);fresh["id"]="revision-fixture-2";fresh["revision_no"]+=1;fresh["row_version"]=1
            fresh["snapshot"].update({k:v for k,v in route.request.post_data_json.items() if k not in {"expected_version","base_revision_id"}})
            state["revisions"].insert(0,fresh);data=fresh
        elif "/revisions/" in path:
            rid=path.split("/revisions/")[1].split("/")[0]
            rev=next(v for v in state["revisions"] if v["id"]==rid)
            body=route.request.post_data_json if method=="POST" else {}
            if path.endswith("/candidates"):
                item=rev["candidates"][0];item.update({k:v for k,v in body.items() if k in item});rev["confirmed_count"]=int(item["status"]=="confirmed")
            elif path.endswith("/candidate-review"):
                rev["candidates"][0]["status"]="confirmed" if body["decision"]=="confirm" else "rejected" if body["decision"]=="reject" else "pending"
                rev["confirmed_count"]=int(rev["candidates"][0]["status"]=="confirmed")
            elif path.endswith("/review"):rev["review_status"]="approved"
            elif path.endswith("/publish"):rev["publication_status"]="publishing"
            elif path.endswith("/withdraw"):rev["publication_status"]="withdrawn"
            elif path.endswith("/applicability"):
                data={"status":"needs_information","missing_fields":["需提供产品生产日期"],"mismatches":[],"scope_notes":"历史范围","notice":"测试反馈"}
                route.fulfill(status=200,content_type="application/json",body=json.dumps({"data":data}));return
            if method=="POST":rev["row_version"]+=1
            data=rev
        elif path=="/v1/standards/requirements":data=[]
        elif "catalog" in path or ("products" in path and "options" in path):data={"categories":[],"products":[]}
        else:data=[]
        route.fulfill(status=200,content_type="application/json",body=json.dumps({"success":True,"data":data}))
    page.route("**/api/v1/**",handle)
    page.goto("http://127.0.0.1:5173/governance/admin/inspection-standards?library=lib-fixture&document=doc-fixture")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading",name="GB 17761-2018",exact=True)).to_be_visible()
    return context,page,state


def form_field(page,label):
    return page.locator(".el-form-item").filter(has_text=re.compile(r"^\s*"+re.escape(label))).get_by_role("textbox")


with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    context,page,state=new_page(browser,"admin")
    expect(page.get_by_role("button",name="专业核验",exact=True)).to_have_count(0)
    expect(page.get_by_role("button",name="发布标准",exact=True)).to_have_count(0)
    form_field(page,"标准名称").fill("核对后的测试名称")
    page.get_by_role("button",name="保存为新修订",exact=True).click()
    expect(page.locator(".document-heading").get_by_text("核对后的测试名称",exact=True)).to_be_visible()
    assert state["revisions"][1]["snapshot"]["standard_name"]=="浏览器隔离测试资料"
    assert state["actions"][0]["body"]["expected_version"]==1
    checks.append("管理员补来源形成新修订；无自审或直接发布按钮")
    page.screenshot(path=str(OUTPUT/"admin-new-revision.png"),full_page=True)
    context.close()

    prepared=revision()
    prepared["candidates"][0].update(method="试验方法7.1",conditions="隔离条件",unit="km/h",requirement="不得超过25",operator="le",measurement_key="maximum_speed",applicability="电动自行车",prepared_by="admin-fixture")
    context,page,state=new_page(browser,"expert",initial=prepared)
    page.locator(".el-tabs__item").nth(2).click()
    page.get_by_role("button",name="逐项专业核对",exact=True).click()
    dialog=page.get_by_role("dialog",name="逐项专业核对")
    expect(dialog.get_by_text("6.1.1 · PDF第 1 页",exact=True)).to_be_visible()
    form_field(dialog,"专业核对意见").fill("隔离测试核对记录")
    form_field(dialog,"核对依据（每行一条）").fill("fixture.pdf 第1页")
    dialog.get_by_role("button",name="记录逐项决定",exact=True).click()
    expect(page.get_by_text("1 项已确认",exact=True)).to_be_visible()
    page.get_by_role("button",name="专业核验",exact=True).click()
    review=page.get_by_role("dialog",name="专业核验")
    form_field(review,"核对说明 / 操作原因").fill("浏览器隔离核验测试")
    form_field(review,"核对依据（每行一条，批准时必填）").fill("隔离API测试依据")
    review.get_by_role("button",name="确认并记录",exact=True).click()
    expect(page.get_by_role("button",name="发布标准",exact=True)).to_be_visible()
    page.get_by_role("button",name="发布标准",exact=True).click()
    publish=page.get_by_role("dialog",name="发布标准")
    form_field(publish,"核对说明 / 操作原因").fill("隔离发布请求")
    publish.get_by_role("button",name="确认并记录",exact=True).click()
    expect(publish).not_to_be_visible()
    expect(page.locator(".admission-stages").get_by_text("发布处理中",exact=True)).to_be_visible()
    assert [a["path"].split("/")[-1] for a in state["actions"]]==["candidate-review","review","publish"]
    checks.append("专家在原文旁确认检测要求；核验后发布仍显示处理中")
    page.screenshot(path=str(OUTPUT/"expert-requirement-review.png"),full_page=True)
    context.close()

    context,page,state=new_page(browser,"admin",revision(publication="published"))
    page.locator(".el-tabs__item").nth(2).click()
    expect(page.get_by_role("button",name="编辑整理稿",exact=True)).to_have_count(0)
    page.get_by_role("button",name="撤回本修订",exact=True).click()
    dialog=page.get_by_role("dialog",name="撤回修订")
    form_field(dialog,"核对说明 / 操作原因").fill("错误资料撤回测试")
    dialog.get_by_role("button",name="确认并记录",exact=True).click()
    expect(page.locator(".admission-stages").get_by_text("已撤回",exact=True)).to_be_visible()
    checks.append("已发布要求不可原位编辑；撤回记录可见")
    context.close()

    context,page,state=new_page(browser,"expert",permissions=["inspection_standard_library_read"])
    expect(page.get_by_role("button",name="保存为新修订",exact=True)).to_have_count(0)
    expect(page.get_by_role("button",name="专业核验",exact=True)).to_have_count(0)
    page.locator(".el-tabs__item").nth(4).click()
    page.get_by_role("button",name="核对当前修订适用范围",exact=True).click()
    expect(page.get_by_text("需提供产品生产日期",exact=True)).to_be_visible()
    checks.append("只读专家没有写入动作；适用核对明确提示缺项")
    context.close()
    browser.close()

assert not errors,errors
report={"checks":checks,"page_errors":errors,"actions":all_actions,"mode":"API fixtures; zero live resource mutations or professional approvals"}
(OUTPUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
