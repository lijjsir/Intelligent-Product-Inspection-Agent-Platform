"""API + UI regression against an isolated supervision QA server (test data, no browser mocks)."""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

API=os.getenv("SUPERVISION_QA_API","http://127.0.0.1:8123")
WEB=os.getenv("SUPERVISION_QA_WEB","http://127.0.0.1:5174")
manifest=json.load(urllib.request.urlopen(API+"/qa/manifest"))
artifacts=Path(os.getenv("SUPERVISION_QA_ARTIFACTS",str(Path(__file__).resolve().parent/"artifacts")))
artifacts.mkdir(parents=True,exist_ok=True)

def api(role,method,path,body=None,expected=200,token=None):
    headers={"Content-Type":"application/json"}
    if token:headers["X-Device-Token"]=token
    else:headers["Authorization"]="Bearer "+manifest["roles"][role]["token"]
    request=urllib.request.Request(API+"/api/v1"+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(request,timeout=60) as response:
            status=response.status;result=json.load(response)
    except urllib.error.HTTPError as exc:
        status=exc.code;result=json.load(exc)
    assert status==expected,(method,path,status,result.get("message"))
    return result.get("data")

def record(role,kind,code,data):return api(role,"POST","/"+kind,{"code":code,"name":code,"data":data})
def run(role,kind,record,operation):
    queued=api(role,"POST",f"/{kind}/{record['id']}/runs",{"version":record["version"],"request_key":f"qa:{operation}:{record['id']}:{record['version']}","operation":operation})
    for _ in range(60):
        current=api(role,"GET","/supervision-runs/"+queued["id"])
        if current["status"] not in {"queued","running"}:
            assert current["status"]=="completed",current
            return current
        time.sleep(0.5)
    raise AssertionError("运行未完成，请检查QA工作者")
def submit(role,kind,record,operation):return api(role,"POST",f"/{kind}/{record['id']}/reviews",{"version":record["version"],"operation":operation})
def accept(role,review,expected=200):return api(role,"POST",f"/business-reviews/{review['id']}/decision",{"decision":"accept","comment":"核对测试来源与本版本完整结果"},expected)

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(channel="msedge",headless=True)
    errors=[]
    def context(role,width=1440):
        actor=manifest["roles"][role]
        session={"piap_token":actor["token"],"piap_org_id":manifest["org_id"],"piap_user_id":actor["user_id"],"piap_role":actor["role"],"piap_roles":json.dumps([actor["role"]]),"piap_username":role}
        result=browser.new_context(viewport={"width":width,"height":1000})
        result.add_init_script("const data="+json.dumps(session)+";for(const[key,value]of Object.entries(data))sessionStorage.setItem(key,value);")
        return result
    ctx=context("user");page=ctx.new_page();page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto(WEB+"/app/risk-cases");page.wait_for_load_state("domcontentloaded")
    page.get_by_role("button",name="新增舆情监测",exact=True).click()
    page.get_by_label("编号",exact=True).fill("QA-续航线索")
    page.get_by_label("名称",exact=True).fill("QA-电动自行车续航下降")
    page.get_by_label("问题描述",exact=True).fill("测试线索：续航下降，需要依据标准和完整检测核验。")
    page.get_by_role("button",name="保存",exact=True).click()
    page.get_by_role("dialog").wait_for(state="hidden")
    case=api("user","GET","/risk-cases?size=200")["items"][0]
    cq=record("admin","regions","QA-重庆",{})
    district=record("admin","regions","QA-渝北",{"parent_id":cq["id"]})
    company=record("admin","enterprises","QA-测试企业",{"credit_code":"QA-TEST","region_id":cq["id"],"product_sku_ids":[manifest["sku_id"]]})
    device=record("admin","devices","QA-温升设备",{"device_type":"温升检测","capabilities":["温升"],"capacity":5,"calibration_status":"valid","region_id":district["id"]})
    now=datetime.utcnow().isoformat()
    data={"product_sku_id":manifest["sku_id"],"batch_id":manifest["batch_id"],"enterprise_id":company["id"],
        "inspection_standard_id":manifest["standard_id"],"product_category":"电动自行车（测试）","production_region_id":cq["id"],
        "complaint_region_id":district["id"],"sales_region_ids":[cq["id"]],"evidence":[{"evidence_id":"qa-complaint","source_id":"QA-C-1","source_type":"complaint","occurred_at":now,"text":"续航下降的测试记录","nature":"observed"}]}
    case=api("user","PATCH","/risk-cases/"+case["id"],{"version":case["version"],"data":data})
    run("user","risk-cases",case,"risk_monitoring")
    case=api("user","GET","/risk-cases/"+case["id"])
    assert case["data"]["analysis"]["probability"] is None
    case=api("expert","POST",f"/risk-cases/{case['id']}/manual-assessment",{"version":case["version"],"risk_level":"medium","evidence_ids":["qa-complaint"],"reason":"测试专家判断：需对实物抽检，未推断内部缺陷。"})
    accept("expert2",submit("user","risk-cases",case,"risk.review"))
    case=api("user","GET","/risk-cases/"+case["id"])
    assert case["status"]=="risk_assessed"
    test={"item":"温升","unit":"C","method":"测试方法","upper_limit":45,"standard_ref":"QA-001 测试条款"}
    plan=record("expert","sampling-plans","QA-抽查计划",{"budget":100,"max_samples":1,"max_staff_hours":2,"hours_per_sample":1,
        "required_categories":["电动自行车（测试）"],"candidates":[{"case_id":case["id"],"sample_count":1,"unit_cost":20,"device_id":device["id"],"region_id":district["id"],"test_items":[test]}]})
    run("expert","sampling-plans",plan,"sampling")
    plan=api("expert","GET","/sampling-plans/"+plan["id"])
    approval=submit("expert","sampling-plans",plan,"sampling.approve")
    accept("admin",approval,403)
    accept("expert2",approval)
    plan=api("user","GET","/sampling-plans/"+plan["id"])
    task_id=plan["data"]["task_ids"][0]
    session=next(s for s in api("user","GET","/inspection-sessions?size=200")["items"] if s["data"]["task_id"]==task_id)
    sample_id=session["data"]["sample_ids"][0]
    sample=api("user","GET","/samples/"+sample_id)
    assert sample["status"]=="planned"
    api("user","PATCH","/samples/"+sample_id,{"version":sample["version"],"data":{"sampled_at":now}})
    token=api("app_developer","POST",f"/devices/{device['id']}/connection",{})["token"]
    reading={"event_id":"qa-reading-1","sample_id":sample_id,"device_id":device["id"],"item":"温升","measured_at":now,"value":55,"unit":"C","method":"测试方法"}
    req={"session_id":session["id"],"source_key":"QA-device-1","measurements":[reading]}
    assert api("user","POST","/device-ingest/measurements",req,token=token)["accepted"]==1
    assert api("user","POST","/device-ingest/measurements",req,token=token)["accepted"]==0
    api("user","POST","/device-ingest/measurements",{**req,"source_key":"QA-device-conflict","measurements":[{**reading,"value":40}]},409,token)
    session=api("user","GET","/inspection-sessions/"+session["id"])
    run("user","inspection-sessions",session,"laboratory")
    session=api("user","GET","/inspection-sessions/"+session["id"])
    assert session["data"]["analysis"]["early_warning"]
    accept("expert",submit("user","inspection-sessions",session,"result.review"))
    sign=submit("user","inspection-sessions",session,"result.signoff")
    accept("expert2",sign)
    assert api("user","GET","/inspection-sessions/"+session["id"])["status"]=="signed"
    assert api("user","GET","/tasks/"+task_id)["status"]=="done"
    formal=api("user","GET","/results/by-task/"+task_id)
    assert formal["verdict"]=="fail" and formal["score_status"]=="not_calibrated"
    api("expert","PATCH",f"/results/{formal['id']}/review",{"verdict":"pass"},409)
    api("user","DELETE","/tasks/"+task_id,expected=409)
    api("algorithm_engineer","GET","/risk-cases",expected=403)
    api("algorithm_engineer","GET","/tasks/"+task_id,expected=403)
    dataset=api("algorithm_engineer","POST","/datasets",{"name":"QA-授权测量集","modality":"text"},201)
    payload={"target":"dataset","dataset_id":dataset["id"],"mode":"candidate"}
    api("algorithm_engineer","POST",f"/tasks/{task_id}/ingest",payload,403)
    api("user","POST",f"/inspection-sessions/{session['id']}/dataset-enrollments",{"dataset_id":dataset["id"]})
    assert api("algorithm_engineer","POST",f"/tasks/{task_id}/ingest",payload)["created_sample_count"]==1
    page.goto(WEB+"/app/workbench");page.wait_for_load_state("domcontentloaded")
    for agent_name in ["市场监控 Agent","舆情监测 Agent","监督抽查 Agent","实验室检测 Agent"]:
        page.get_by_role("heading",name=agent_name,exact=True).wait_for()
    page.screenshot(path=str(artifacts/"supervision-workbench.png"),full_page=True)
    page.goto(WEB+"/app/risk-cases?record="+case["id"]);page.wait_for_load_state("domcontentloaded")
    page.get_by_role("heading",name="QA-电动自行车续航下降",exact=True).wait_for()
    page.locator(".supervision-page .el-loading-mask").wait_for(state="hidden")
    page.screenshot(path=str(artifacts/"supervision-risk-desktop.png"),full_page=True)
    page.goto(WEB+"/app/tasks/"+task_id);page.wait_for_load_state("domcontentloaded")
    page.get_by_text("检测过程与测量",exact=True).wait_for()
    page.screenshot(path=str(artifacts/"supervision-signed-task.png"),full_page=True)
    page.goto(WEB+"/app/results/"+task_id);page.wait_for_load_state("domcontentloaded")
    page.get_by_text("未校准，不作为概率展示",exact=True).wait_for()
    mobile=context("user",375);mobile_page=mobile.new_page();mobile_page.on("pageerror",lambda e:errors.append(str(e)))
    mobile_page.goto(WEB+"/app/risk-cases?record="+case["id"]);mobile_page.wait_for_load_state("domcontentloaded")
    mobile_page.get_by_role("heading",name="QA-电动自行车续航下降",exact=True).wait_for()
    mobile_page.locator(".supervision-page .el-loading-mask").wait_for(state="hidden")
    mobile_page.screenshot(path=str(artifacts/"supervision-risk-mobile.png"),full_page=True)
    assert mobile_page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"),"移动页面存在整页横向溢出"
    assert not errors,errors
    browser.close()
print("API+UI supervision flow passed (isolated SQLite and test fixtures; real model/device acceptance remains separate)")
