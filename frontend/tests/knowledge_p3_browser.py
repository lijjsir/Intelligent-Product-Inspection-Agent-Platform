"""P3 UI workflows with explicit API fixtures; no live sharing or approval."""
import copy,json,re,sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

sys.stdout.reconfigure(encoding="utf-8")
OUT=Path(__file__).resolve().parents[1]/"test-results"/"knowledge-p3";OUT.mkdir(parents=True,exist_ok=True)
errors=[];checks=[];mutations=[]


def item():return {"id":"admission-fixture","memory_id":"memory-fixture","created_by":"owner-fixture","row_version":1,
    "review_status":"pending","sharing_status":"pending","publication_status":"unpublished","created_at":"2026-10-05",
    "snapshot":{"claim":"续航变化应先核对条件","product_category":"电动自行车","applicability":"相同试验场景",
        "limitations":"不作为合格判定依据","requested_scope":"organization","consent_to_review":True,"consent_to_share":True},
    "source_refs":[{"kind":"rag_document","id":"doc-fixture","quote":"不能仅凭投诉认定不合格","authority":"reference_only","metadata":{"title":"测试专家笔记"}}],"actions":[],"jobs":[]}


def page_for(browser,role):
    context=browser.new_context(viewport={"width":1600,"height":1080});page=context.new_page()
    actor=f"{role}-fixture";perms=["knowledge_read","knowledge_candidate_submit","knowledge_publish","inspection_standard_library_read","quality","chat"]
    perms+= ["knowledge_share_decide","memory_governance","user"] if role=="admin" else ["knowledge_review"]
    session={"piap_token":"fixture","piap_role":role,"piap_roles":json.dumps([role]),"piap_user_id":actor,"piap_org_id":"org-fixture","piap_username":role}
    page.add_init_script("for(const [k,v] of Object.entries("+json.dumps(session)+"))sessionStorage.setItem(k,v);")
    page.on("pageerror",lambda e:errors.append(str(e)))
    state={"admission":item(),"grants":[]}
    def route(request_route):
        req=request_route.request;path=urlparse(req.url).path.removeprefix("/api");method=req.method
        if method not in {"GET","HEAD","OPTIONS"}:mutations.append({"role":role,"path":path})
        if path=="/v1/users/me":data={"id":actor,"org_id":"org-fixture","username":role,"role":role,"roles":[role],"is_active":True,"email":"fixture@example.com","effective_permissions":perms}
        elif path=="/v1/standard-libraries":data={"items":[{"id":"standard-fixture","name":"工业标准专题","published_document_count":0,"pending_review_document_count":1}],"total":1,"page":1,"size":50}
        elif path=="/v1/rag-spaces":
            data=[{"id":sid,"org_id":"org-fixture","created_by":owner,"name":name,"resource_domain":"workspace","file_count":1,"folder_count":0,"chunk_count":1,"status":"ready","index_status":"ready","selected_count":0,"can_submit_knowledge":can} for sid,owner,name,can in [
                ("mine",actor,"P3我的资料",True),("shared","peer-fixture","P3同事共享资料",False)]]
        elif path.endswith("/tree"):
            sid=path.split("/")[-2]
            data=[{"id":"node-"+sid,"org_id":"org-fixture","rag_space_id":sid,"node_type":"file","name":"expert-note.md","full_path":"expert-note.md","depth":0,"status":"ready","children_count":0,"children":[],"document":{"id":"doc-fixture","file_name":"expert-note.md","parse_status":"parsed","index_status":"ready","chunk_count":1,"size_bytes":10}}]
        elif path=="/v1/knowledge/share-targets":data=[{"id":"peer-fixture","name":"同组织专家","role":"expert"}]
        elif path.endswith("/grants"):data=state["grants"]
        elif path.endswith("/share"):
            body=req.post_data_json;state["grants"]=[{"id":"grant-fixture","user_id":body["user_id"],"status":"active","row_version":1,"reason":body["reason"],"allow_knowledge_submission":body["allow_knowledge_submission"]}];data=state["grants"]
        elif path=="/v1/knowledge/source-preview":data={"kind":"rag_document","id":"doc-fixture","quote":"","available_excerpt":"不能仅凭投诉认定不合格","authority":"reference_only","metadata":{"title":"测试专家笔记"}}
        elif path=="/v1/knowledge/candidates" and method=="POST":
            data=copy.deepcopy(state["admission"]);data["snapshot"].update(req.post_data_json);data["created_by"]=actor;state["submitted"]=req.post_data_json
        elif path=="/v1/knowledge/candidates":data=[state["admission"]]
        elif path=="/v1/knowledge/published":data=[]
        elif path.startswith("/v1/knowledge/candidates/"):
            row=state["admission"]
            if method=="POST":
                if path.endswith("/sharing"):row["sharing_status"]="approved"
                if path.endswith("/review"):row["review_status"]="approved"
                if path.endswith("/publish"):row["publication_status"]="publishing"
                row["row_version"]+=1
            data=row
        else:data=[]
        request_route.fulfill(status=200,content_type="application/json",body=json.dumps({"success":True,"data":data}))
    page.route("**/api/v1/**",route)
    return context,page,state


def fill(root,label,value):root.locator(".el-form-item").filter(has_text=re.compile(r"^\s*"+re.escape(label))).get_by_role("textbox").fill(value)


with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context,page,state=page_for(browser,"expert")
    page.goto("http://127.0.0.1:5173/app/rag-spaces");page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading",name="知识资料",exact=True)).to_be_visible()
    expect(page.get_by_role("heading",name="我的资料",exact=True)).to_be_visible()
    expect(page.get_by_role("button",name="上传到当前文件夹",exact=True)).to_be_visible()
    page.get_by_role("button",name="授权共享",exact=True).click()
    dialog=page.get_by_role("dialog",name="授权共享资料")
    dialog.locator(".el-select").click();page.get_by_role("option",name="同组织专家",exact=True).click()
    fill(dialog,"共享目的","共同核对资料")
    dialog.get_by_role("button",name="保存只读授权",exact=True).click()
    expect(dialog.get_by_text("已授权",exact=True)).to_be_visible()
    assert state["grants"][0]["allow_knowledge_submission"] is False
    dialog.locator(".el-dialog__headerbtn").click()
    checks.append("共享默认只读，知识提交许可单独选择")
    page.get_by_role("tab",name="授权共享资料",exact=True).click();page.wait_for_load_state("networkidle")
    expect(page.get_by_text("已授权共享资料 · 只读",exact=True)).to_be_visible()
    expect(page.get_by_role("button",name="上传到当前文件夹",exact=True)).to_have_count(0)
    expect(page.get_by_role("button",name="授权共享",exact=True)).to_have_count(0)
    checks.append("接收者可读共享资料，不能维护或再次授权")
    page.get_by_role("tab",name="知识候选与申请",exact=True).click();page.wait_for_load_state("networkidle")
    page.get_by_role("button",name="提交知识候选",exact=True).click()
    dialog=page.get_by_role("dialog",name="从已有来源提交知识候选")
    fill(dialog,"来源记录编号","doc-fixture");dialog.get_by_role("button",name="核对来源",exact=True).click()
    fill(dialog,"选定引用片段（须与来源一致）","不能仅凭投诉认定不合格")
    dialog.get_by_role("button",name="加入来源清单",exact=True).click()
    for label,value in {"可复用的知识主张":"续航变化应结合试验条件核验","相关产品类别":"电动自行车","适用条件与场景":"相同试验条件下的分析","限制、反例与尚缺证据":"不直接判断产品合格"}.items():fill(dialog,label,value)
    expect(dialog.get_by_role("button",name="提交待核对候选",exact=True)).to_be_disabled()
    dialog.get_by_text("同意审核者读取本次主张及选定的引用片段",exact=True).click()
    dialog.get_by_role("button",name="提交待核对候选",exact=True).click()
    expect(dialog).not_to_be_visible()
    assert state["submitted"]["requested_scope"]=="private" and state["submitted"]["consent_to_share"] is False
    checks.append("选取真实片段并明确授权后提交；默认私人范围")
    page.get_by_role("button",name="出处与核对",exact=True).click()
    expect(page.get_by_role("button",name="专业核验",exact=True)).to_be_visible()
    expect(page.get_by_role("button",name="审批组织使用范围",exact=True)).to_have_count(0)
    page.screenshot(path=str(OUT/"expert-source-and-review.png"),full_page=True)
    context.close()

    context,page,state=page_for(browser,"admin")
    page.goto("http://127.0.0.1:5173/governance/memory");page.wait_for_load_state("networkidle")
    page.get_by_role("button",name="出处与核对",exact=True).click()
    expect(page.get_by_role("button",name="专业核验",exact=True)).to_have_count(0)
    expect(page.get_by_role("button",name="发布知识",exact=True)).to_have_count(0)
    page.get_by_role("button",name="审批组织使用范围",exact=True).click()
    dialog=page.get_by_role("dialog",name="审批组织使用范围")
    fill(dialog,"核对说明或操作原因","已核对组织使用范围")
    dialog.get_by_role("button",name="确认并记录",exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role("button",name="发布知识",exact=True)).to_have_count(0)
    assert state["admission"]["sharing_status"]=="approved" and state["admission"]["review_status"]=="pending"
    checks.append("管理员批准范围后仍不能替代专家核验或直接发布")
    page.screenshot(path=str(OUT/"admin-scope-separate-review.png"),full_page=True)
    context.close();browser.close()

assert not errors,errors
report={"checks":checks,"page_errors":errors,"fixture_actions":mutations,"live_resource_mutations":0}
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
