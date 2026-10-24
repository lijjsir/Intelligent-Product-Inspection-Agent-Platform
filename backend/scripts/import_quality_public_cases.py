"""Import verifiable public material and prepare historical cases without approvals.

Stages are explicit so external inference is not repeated on import retries.
All historical facts retain dates, source URLs and documentary limitations.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.models.organization import Organization
from app.models.user import User
from app.models.quality_risk import ProductCategory, QualityProduct, QualityRiskCase
from app.schemas.user import CurrentUser
from app.schemas.quality_risk import ProductCategoryCreate, QualityEventCreate, RiskAnalyzeRequest, RiskCaseCreate
from app.schemas.risk_completion import LabDecision, LabReturn
from app.services.quality_risk_service import QualityRiskService, stable_hash
from app.services.risk_lab_service import RiskLabService
from app.services.risk_workflow_context_service import RiskWorkflowContextService
from infra.database.session import get_session, reset_async_engine_pool

REPORT_URL = "https://www.qzlc.gov.cn/zwgk/qzbm/qscjdglj/zljg/202110/P020211028350036974001.pdf"
REPORT_SHA256 = "94ee5414e93c79d0d8c80c8a318204365ad1b1aab06de15ca46fb5e8034df0e2"
CQ_URL = "https://scjgj.cq.gov.cn/zfxxgk_225/gsgg/qtgg/202512/t20251219_15256568.html"
CHARGER_URL = "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/zljds/art/2025/art_d75bb5a15c794893bca6cf8baf9f5155.html"
NEWS_URL = "https://www.cqn.com.cn/ms/content/2022-04/24/content_8811952.htm"
PACKAGE_KEY = "verified-public-history-20261023"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def actors(db):
    org = await db.scalar(select(Organization).where(Organization.slug == "cqupt"))
    if not org or (org.settings or {}).get("execution_mode") == "demo":
        raise RuntimeError("Expected the existing non-demo cqupt organization")
    users = {}
    for role, username in (("expert", "expert"), ("admin", "admin")):
        user = await db.scalar(select(User).where(User.org_id == org.id, User.username == username, User.role == role, User.is_active.is_(True)))
        if not user:
            raise RuntimeError(f"Existing {username} account not found")
        users[role] = CurrentUser(user_id=user.id, org_id=org.id, role=role)
    return org, users


async def category(service, name, basis):
    row = await service.db.scalar(select(ProductCategory).where(ProductCategory.org_id == service.org_id, ProductCategory.name == name, ProductCategory.deleted_at.is_(None)))
    return row.id if row else (await service.create_category(ProductCategoryCreate(name=name, classification_basis=basis)))["id"]


async def attachment(service, path, filename):
    response = await service.upload_attachment(UploadFile(file=io.BytesIO(path.read_bytes()), filename=filename))
    return response["id"]


async def make_record(service, *, key, kind, text, url, content=None, attachments=None, product_id=None, category_id=None, occurred_at=None, provenance=None):
    payload = QualityEventCreate(
        record_type=kind, external_record_id=f"{PACKAGE_KEY}:{key}", origin_label=url,
        occurred_at=occurred_at,
        content={"text": text, **(content or {})},
        attachment_ids=attachments or [],
        product_ref={"product_id": product_id, "category_id": category_id},
        provenance={"package_key": PACKAGE_KEY, "source_url": url, "collected_on": "2026-10-23", "preparation": "用户授权下自动整理公开资料，未代替专业复核", "historical_material": True, **(provenance or {})},
        authorization_scope="organization", data_nature="observed",
    )
    return await service.create_event(payload)


async def make_case(service, *, key, title, scope, record_ids, scope_type):
    row = await service.db.scalar(select(QualityRiskCase).where(QualityRiskCase.org_id == service.org_id, QualityRiskCase.deleted_at.is_(None), QualityRiskCase.scope["public_case_key"].as_string() == key))
    if row:
        return service.risk_case_response(row)
    return await service.create_risk_case(RiskCaseCreate(title=title, scope_type=scope_type,
        scope={**scope, "public_case_key": key, "case_mode": "public_historical_review", "package_key": PACKAGE_KEY,
            "boundary": "公开历史资料复盘；平台当前操作不等于重新抽样、实物检测、历史行政处置或专家审批。"},
        source_record_ids=record_ids))


async def prepare(db, root, org, users):
    service, admin = QualityRiskService(db, users["expert"]), QualityRiskService(db, users["admin"])
    source_dir = root / "sources"
    if sha(source_dir / "report.pdf") != REPORT_SHA256:
        raise RuntimeError("Official original report digest changed; verify the document before import")
    product = await db.scalar(select(QualityProduct).where(QualityProduct.org_id == org.id, QualityProduct.model == "TDR009Z-2Z", QualityProduct.deleted_at.is_(None)))
    if not product:
        raise RuntimeError("The preserved historical report product must be audited before creating another master")
    ebike_category = product.category_id
    charger_category = await category(admin, "电动自行车充电器", CHARGER_URL)
    report_attachment = await attachment(service, source_dir / "report.pdf", "JG2128520085-政府公开原报告.pdf")
    sampling = await make_record(service, key="ebike-sampling-facts", kind="supervision_inspection", url=REPORT_URL,
        text="历史公开报告的抽样事实摘录，尚未进行本平台重新检测。报告JG2128520085记载：速珂电动自行车TDR009Z-2Z，标称生产单位江苏速珂智能科技有限公司，生产日期2019-08-01；受检单位泉州市永富通商贸有限公司。抽样日期2021-07-30，抽样单编号01010590730114622，样品2辆（1辆检测、1辆备样），样品2021-08-13到达检验机构。原件PDF第2页。本条与后续检验结果摘录来自同一份报告，不能作为两个独立样本或两次独立检测。",
        attachments=[report_attachment], product_id=product.id, category_id=ebike_category, occurred_at=datetime(2021, 7, 30),
        content={"report_no": "JG2128520085", "sampling_date": "2021-07-30", "sample_count": 2, "tested_sample_count": 1, "reserve_sample_count": 1, "sampling_form_no": "01010590730114622"},
        provenance={"original_sha256": REPORT_SHA256, "original_pdf_page": 2, "event_time_precision": "date_only", "independent_document_key": REPORT_SHA256})
    news = await make_record(service, key="ebike-public-news", kind="public_opinion", url=NEWS_URL,
        text="2022年4月24日，中国质量新闻网发布道路交通产品国家监督抽查报道，附表列明江苏速珂智能科技有限公司TDR009Z-2Z、生产日期2019-08-01，受检单位泉州市永富通商贸有限公司，不合格项目为鸣号装置和车速限值。这里只记录该历史报道，不能据此判断2026年在售产品状态；同一公开抽查事件的转载不计为新增检测或独立消费者投诉。",
        product_id=product.id, category_id=ebike_category, occurred_at=datetime(2022, 4, 24),
        provenance={"event_time_precision": "publication_date_only", "publisher": "中国质量新闻网", "retrieval": "网页检索核验并与政府公开原报告核对；本地直连返回405，未冒充取得网页原件", "independent_document_key": REPORT_SHA256})
    report = await make_record(service, key="ebike-report-facts", kind="inspection_report", url=REPORT_URL,
        text="政府网站公开原报告JG2128520085的核对摘录，签发日期2021-09-03，承检机构上海市质量监督检验技术研究院。对象：江苏速珂智能科技有限公司速珂TDR009Z-2Z，生产日期2019-08-01；受检单位泉州市永富通商贸有限公司。原报告依据GB17761-2018，所检项目结论为不合格，涉及车速限值和鸣号装置。PDF第3页：最高设计车速24km/h，实测30.8km/h，原文要求不超过设计车速且不超过25km/h，原报告该项不合格；整车质量51.4kg，对应上限55kg，原报告该项合格。PDF第5页：鸣号声压级73dB(A)，要求75至100dB(A)，原报告该项不合格。上述数值是报告汇总值，不是本平台采集的仪器原始观测；三次鸣号原始读数、仪器校准档案、后续整改复检和现售批次状态未公开，不补造。结论仅用于该历史样品和原报告所检范围。",
        attachments=[report_attachment], product_id=product.id, category_id=ebike_category, occurred_at=datetime(2021, 9, 3),
        content={"report_no": "JG2128520085", "issued_date": "2021-09-03", "documentary_verdict": "原报告所检项目不合格", "transcribed_values": [
            {"indicator": "车速限值", "value": 30.8, "unit": "km/h", "designed_max": 24, "regulatory_max": 25, "original_pdf_page": 3, "documentary_verdict": "不合格"},
            {"indicator": "整车质量", "value": 51.4, "unit": "kg", "limit": 55, "original_pdf_page": 3, "documentary_verdict": "合格"},
            {"indicator": "鸣号声压级", "value": 73, "unit": "dB(A)", "lower_limit": 75, "upper_limit": 100, "original_pdf_page": 5, "documentary_verdict": "不合格"}],
            "limitations": ["历史样品复盘，不是新实物检测", "每个报告汇总值只计一条来源，不补造三次原始读数", "当前标准适用性和现售产品状态未据此判定", "摘录尚需独立人工核对"]},
        provenance={"original_sha256": REPORT_SHA256, "original_pdf_pages": [2, 3, 5], "event_time_precision": "report_issue_date_only", "independent_document_key": REPORT_SHA256, "transcription_status": "awaiting_independent_review"})
    main_case = await make_case(service, key="SOCO-JG2128520085", title="真实历史资料复盘｜速珂TDR009Z-2Z国家监督抽查与报告核对", scope_type="product",
        scope={"name": product.name, "product_id": product.id, "category_id": ebike_category, "product_category": "电动自行车", "production_date": "2019-08-01", "report_no": "JG2128520085", "historical_period": "2021-2022"}, record_ids=[sampling["id"], news["id"]])
    cq_attachment = await attachment(service, source_dir / "cq_cases.txt", "重庆市市场监管局-电动自行车典型案例-20251219.txt")
    enforcement = await make_record(service, key="cq-wanzhou-enforcement", kind="enforcement_case", url=CQ_URL,
        text="重庆市市场监管局于2025-12-19公布的第三起历史案例：2024年7月，万州区市场监管局检查发现某经营部销售的10个型号28辆电动自行车鞍座超长，经抽样检验不符合GB17761-2018规定要求。公告披露责令改正、没收不合格电动自行车28辆、罚款5.5万元。经营部、品牌型号、原始报告编号、具体鞍座测量值、仪器和校准资料未公开，不能补造。不能把28辆处置数量直接当作28次独立检验；公告也没有证明罚款履行或整改复检已经完成。",
        attachments=[cq_attachment], category_id=ebike_category,
        content={"publication_date": "2025-12-19", "event_period": "2024-07", "area": "重庆市万州区", "documentary_outcome": "公告披露的历史行政处罚", "vehicle_quantity": 28, "model_quantity": 10, "fine_yuan": 55000, "enterprise_identity": "公告匿名，未虚构企业名称"},
        provenance={"publisher": "重庆市市场监督管理局", "original_html_sha256": sha(source_dir / "cq_cases.html"), "event_time_precision": "month_only"})
    cq_case = await make_case(service, key="CQ-WANZHOU-202407", title="真实公开执法复盘｜万州电动自行车鞍座超长案", scope_type="category",
        scope={"name": "电动自行车", "category_id": ebike_category, "area": "重庆市万州区", "historical_period": "2024-07", "source_publication_date": "2025-12-19"}, record_ids=[enforcement["id"]])
    samr_attachment = await attachment(service, source_dir / "samr_2024.txt", "市场监管总局-2024年度产品质量抽查通报-20250407.txt")
    charger = await make_record(service, key="samr-charger-2024", kind="supervision_inspection", url=CHARGER_URL,
        text="市场监管总局2025-04-07发布2024年电子产品用锂离子电池和电池组等27种产品质量国家监督抽查情况通报。其中电动自行车充电器在6个省份80家生产单位抽查80批次，发现4批次不合格，涉及3批次过充切断不合格、1批次超温保护不合格。80和4是该次抽查的批次数，不是市场保有量、日投诉数或产品故障概率。此处是类别级公开监管信息；本条正文未列具体厂家型号及原始检测值，不据此创建虚构产品、样品或仪器测量。",
        attachments=[samr_attachment], category_id=charger_category,
        content={"publication_date": "2025-04-07", "document_date": "2025-03-12", "inspection_period": "2024", "sampled_batches": 80, "nonconforming_batches": 4, "overcharge_cutoff_nonconforming_batches": 3, "overtemperature_protection_nonconforming_batches": 1},
        provenance={"publisher": "国家市场监督管理总局", "original_html_sha256": sha(source_dir / "samr_2024.html"), "event_time_precision": "year_only"})
    charger_case = await make_case(service, key="SAMR-CHARGER-2024", title="真实公开抽查复盘｜电动自行车充电器安全项目", scope_type="category",
        scope={"name": "电动自行车充电器", "category_id": charger_category, "historical_period": "2024", "source_publication_date": "2025-04-07"}, record_ids=[charger["id"]])
    await db.commit()
    result = {"organization": {"id": org.id, "slug": org.slug}, "package_key": PACKAGE_KEY,
        "cases": {"main": main_case["id"], "cq_enforcement": cq_case["id"], "charger": charger_case["id"]},
        "records": {"sampling": sampling["id"], "news": news["id"], "report": report["id"], "cq_enforcement": enforcement["id"], "charger": charger["id"]},
        "report_attachment": report_attachment, "product_id": product.id,
        "human_approvals_performed": False, "new_physical_tests_performed": False}
    save(root / "case-index.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


async def analyze(db, root, users, stage):
    index = json.loads((root / "case-index.json").read_text(encoding="utf-8"))
    service = QualityRiskService(db, users["expert"])
    keys = ["main"] if stage == "analyze-first" else list(index["cases"])
    results = []
    for key in keys:
        print(json.dumps({"analyzing": key, "case_id": index["cases"][key]}, ensure_ascii=False), flush=True)
        row = await service.analyze_risk(index["cases"][key], RiskAnalyzeRequest())
        await db.commit()
        result = {"key": key, "case_id": index["cases"][key], "assessment_id": row["id"], "version": row["version"], "status": row["status"], "risk_level": row["risk_level"], "missing_inputs": row["missing_inputs"], "model_versions": row["model_versions"], "reviewed_by": row.get("reviewed_by")}
        results.append(result)
        save(root / f"{stage}-results.json", results)
        print(json.dumps({k: v for k, v in result.items() if k != "model_versions"}, ensure_ascii=False), flush=True)


async def return_report(db, root, users):
    index = json.loads((root / "case-index.json").read_text(encoding="utf-8"))
    service = QualityRiskService(db, users["expert"])
    case = await service.risk_case(index["cases"]["main"])
    workflow = RiskWorkflowContextService(db, users["expert"])
    latest = await workflow.latest(case)
    if not latest:
        raise RuntimeError("Generate the initial assessment before recording validation")
    basis, issues = await workflow.capture(case)
    if issues:
        raise RuntimeError(f"Current source access needs correction: {issues}")
    lab = RiskLabService(db, users["expert"])
    link = await lab.decide(case.id, LabDecision(assessment_id=latest.id, expected_basis_hash=stable_hash(basis), verification_path="report", mode="verify", purpose="核对同一历史样品的政府公开原报告，不补建实物任务或虚构仪器观测；回流后形成新版研判，待人工独立复核。"))
    await db.commit()
    returned = await lab.return_records(link["id"], LabReturn(expected_revision=link["revision"], record_ids=[index["records"]["report"]], note="关联政府公开原报告的核对摘录和原件，保留30.8km/h、51.4kg、73dB(A)对应原页码与历史范围；未补造原始重复测量、校准或新的检测结果。"))
    await db.commit()
    save(root / "report-return.json", returned)
    print(json.dumps({"verification_id": returned["id"], "status": returned["status"], "record_ids": returned["record_ids"], "new_physical_tests_performed": False}, ensure_ascii=False), flush=True)


async def refresh_requirements(db, root, users):
    index = json.loads((root / "case-index.json").read_text(encoding="utf-8"))
    from app.models.quality_risk import QualityRiskAssessment
    service = QualityRiskService(db, users['expert'])
    results = []
    for key, case_id in index['cases'].items():
        versions = list(await db.scalars(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id == service.org_id,
            QualityRiskAssessment.risk_case_id == case_id, QualityRiskAssessment.deleted_at.is_(None)).order_by(QualityRiskAssessment.version.desc())))
        prior = next((row for row in versions if (row.model_versions or {}).get('model_success') and
            (row.model_versions or {}).get('analysis_summary', {}).get('summary')), None)
        if not prior:raise RuntimeError(f'No completed analysis to carry forward for {key}')
        row = await service.refresh_historical_requirements(case_id, prior.id)
        await db.commit()
        results.append({field:row.get(field) for field in ['id','version','risk_level','status','missing_inputs','purpose_review','analysis_origin','reviewed_by']})
        print(json.dumps({'key':key,'version':row['version'],'status':row['status'],'source_version':prior.version,
            'new_model_calls':0,'reviewed_by':row['reviewed_by']},ensure_ascii=False),flush=True)
    save(root / 'purpose-refresh-results.json', results)


async def main(args):
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        async with get_session() as db:
            org, users = await actors(db)
            if args.stage == "prepare":
                await prepare(db, root, org, users)
            elif args.stage == "return-report":
                await return_report(db, root, users)
            elif args.stage == 'refresh-requirements':
                await refresh_requirements(db, root, users)
            else:
                await analyze(db, root, users, args.stage)
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="runtime/real_quality_case_20261023")
    parser.add_argument("--stage", choices=["prepare", "analyze-first", "return-report", "analyze-latest", "refresh-requirements"], required=True)
    asyncio.run(main(parser.parse_args()))
