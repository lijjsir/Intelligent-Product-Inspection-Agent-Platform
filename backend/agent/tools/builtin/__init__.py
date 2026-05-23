"""Built-in tool registration — register_all() populates the global ToolRegistry."""

from __future__ import annotations

from agent.tools.contracts import ToolSpec
from agent.tools.registry import ToolRegistry


def register_all(registry: ToolRegistry) -> None:
    """Register all builtin tools into the given registry."""

    # ── RAG tools ──
    from agent.tools.builtin.rag_tools import standard_search as _rag_search
    async def _rag_retrieve(args: dict, ctx) -> dict:
        return await _rag_search(
            query=args.get("query", ""),
            rag_space_id=args.get("rag_space_id"),
            top_k=args.get("top_k", 5),
        )
    registry.register(
        ToolSpec(
            name="rag.retrieve", title="知识库检索",
            description="从选中的 RAG 空间中检索与查询相关的证据片段，支持语义匹配和基础过滤。",
            agent_scope=["chat", "inspection_task"], surfaces=["chat", "quality_task"],
            mode="read", risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询"},
                    "rag_space_id": {"type": "string", "description": "RAG 空间 ID"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            output_schema={"type": "object", "properties": {"documents": {"type": "array"}, "total": {"type": "integer"}}},
        ),
        handler=_rag_retrieve,
    )

    # ── File tools ──
    from agent.tools.builtin.file_tools import parse as _file_parse
    async def _file_parse_wrapper(args: dict, ctx) -> dict:
        return _file_parse(file_path=args.get("file_path", ""), file_type=args.get("file_type"))
    registry.register(
        ToolSpec(
            name="file.parse", title="文件内容解析",
            description="解析 PDF、Word、Excel、CSV、JSON 等文件内容，提取结构化文本和表格信息。",
            agent_scope=["chat", "inspection_task"], surfaces=["chat", "quality_task"],
            mode="read", risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "file_type": {"type": "string", "description": "文件类型，可选覆盖后缀判断"},
                },
                "required": ["file_path"],
            },
            output_schema={"type": "object", "properties": {"content": {"type": "string"}, "tables": {"type": "array"}}},
        ),
        handler=_file_parse_wrapper,
    )

    # ── Inspection tools ──
    from agent.tools.builtin.inspection_tools import calc_score as _calc_score
    from agent.tools.builtin.inspection_tools import compare as _std_compare
    async def _calc_score_wrapper(args: dict, ctx) -> dict:
        return _calc_score(
            standard_id=args.get("standard_id", ""),
            evidence_ids=args.get("evidence_ids", []),
        )
    registry.register(
        ToolSpec(
            name="calc.inspection_score", title="检测评分计算",
            description="根据检测标准评估规则结果，计算产品检测的总体得分和等级。",
            agent_scope=["inspection_task"], surfaces=["quality_task"],
            mode="read", risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "standard_id": {"type": "string", "description": "检测标准 ID"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}, "description": "证据 ID 列表"},
                },
                "required": ["standard_id", "evidence_ids"],
            },
            output_schema={"type": "object", "properties": {"score": {"type": "number"}, "grade": {"type": "string"}}},
        ),
        handler=_calc_score_wrapper,
    )
    async def _compare_wrapper(args: dict, ctx) -> dict:
        return _std_compare(
            result_data=args.get("result_data", {}),
            standard_values=args.get("standard_values", {}),
        )
    registry.register(
        ToolSpec(
            name="calc.standard_compare", title="标准对比评估",
            description="将检测数据与标准规范进行逐项对比，生成偏差分析结果。",
            agent_scope=["inspection_task"], surfaces=["quality_task"],
            mode="read", risk_level="medium",
            input_schema={
                "type": "object",
                "properties": {
                    "result_data": {"type": "object", "description": "检测结果数据"},
                    "standard_values": {"type": "object", "description": "标准值"},
                },
                "required": ["result_data", "standard_values"],
            },
            output_schema={"type": "object", "properties": {"comparisons": {"type": "array"}, "pass_count": {"type": "integer"}, "fail_count": {"type": "integer"}}},
        ),
        handler=_compare_wrapper,
    )

    # ── Report tools ──
    from agent.tools.builtin.report_tools import generate as _report_gen
    async def _report_gen_wrapper(args: dict, ctx) -> dict:
        return await _report_gen(
            inspection_id=args.get("inspection_id", ""),
            format=args.get("format", "pdf"),
            template=args.get("template"),
        )
    registry.register(
        ToolSpec(
            name="report.generate", title="检测报告生成",
            description="根据检测结果和评估数据，生成结构化的检测报告。",
            agent_scope=["inspection_task"], surfaces=["quality_task"],
            mode="write", risk_level="medium",
            input_schema={
                "type": "object",
                "properties": {
                    "inspection_id": {"type": "string", "description": "检测任务 ID"},
                    "format": {"type": "string", "default": "pdf"},
                    "template": {"type": "string", "description": "报告模板（可选）"},
                },
                "required": ["inspection_id"],
            },
            output_schema={"type": "object", "properties": {"report": {"type": "string"}, "format": {"type": "string"}}},
        ),
        handler=_report_gen_wrapper,
    )

    # ── Quality tools ──
    registry.register(
        ToolSpec(
            name="quality.task.status",
            title="检测任务状态查询",
            description="查询质量检测任务的当前状态、进度和基本信息。",
            agent_scope=["chat", "inspection_task"],
            surfaces=["chat", "quality_task"],
            mode="read",
            risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID"},
                },
                "required": ["task_id"],
            },
            output_schema={"type": "object", "properties": {"status": {"type": "string"}, "progress": {"type": "integer"}}},
        ),
        handler=_quality_task_status,
    )
    registry.register(
        ToolSpec(
            name="quality.report.query",
            title="历史报告查询",
            description="查询历史检测报告和结果，支持按产品、批次、时间范围过滤。",
            agent_scope=["chat", "inspection_task"],
            surfaces=["chat", "quality_task"],
            mode="read",
            risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "产品 ID"},
                    "batch_no": {"type": "string", "description": "批次号"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
            output_schema={"type": "object", "properties": {"reports": {"type": "array"}, "total": {"type": "integer"}}},
        ),
        handler=_quality_report_query,
    )
    registry.register(
        ToolSpec(
            name="quality.inspection.execute",
            title="正式质量检测执行",
            description="正式执行质量检测任务，创建任务、运行检测流程、生成结果。仅质量任务页面可调用。",
            agent_scope=["inspection_task"],
            surfaces=["quality_task"],
            mode="action",
            risk_level="high",
            requires_confirmation=True,
            timeout_ms=60_000,
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "产品 ID"},
                    "spec_code": {"type": "string", "description": "检测标准编码"},
                    "image_urls": {"type": "array", "description": "图片 URL 列表"},
                    "priority": {"type": "integer", "default": 5},
                },
                "required": ["product_id", "spec_code"],
            },
            output_schema={"type": "object", "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}}},
        ),
        handler=_quality_inspection_execute,
    )

    # ── Search tools ──
    from agent.tools.builtin.search_tools import search as _web_search
    async def _web_search_wrapper(args: dict, ctx) -> dict:
        return await _web_search(
            query=args.get("query", ""),
            max_results=args.get("max_results", 5),
            region=args.get("region", "cn-zh"),
        )
    registry.register(
        ToolSpec(
            name="web.search", title="联网搜索",
            description="提取核心关键词（仅名词/实体名），通过 DuckDuckGo 检索互联网信息。query 参数只传空格分隔的关键词，不要传完整问句。",
            agent_scope=["chat", "inspection_task"], surfaces=["chat", "quality_task"],
            mode="read", risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "default": 5},
                    "region": {"type": "string", "default": "cn-zh"},
                },
                "required": ["query"],
            },
            output_schema={"type": "object", "properties": {"results": {"type": "array"}, "query": {"type": "string"}, "total": {"type": "integer"}}},
        ),
        handler=_web_search_wrapper,
    )

    # ── Data tools ──
    registry.register(
        ToolSpec(
            name="data.analysis",
            title="数据分析",
            description="查询检测统计数据、趋势、合格率汇总等分析结果。",
            agent_scope=["chat", "inspection_task"],
            surfaces=["chat", "quality_task"],
            mode="read",
            risk_level="low",
            input_schema={
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "分析指标：pass_rate, defect_trend, inspection_volume"},
                    "product_id": {"type": "string", "description": "产品 ID（可选）"},
                    "days": {"type": "integer", "default": 30},
                },
                "required": ["metric"],
            },
            output_schema={"type": "object", "properties": {"data": {"type": "array"}, "summary": {"type": "string"}}},
        ),
        handler=_data_analysis,
    )


# ── Handler implementations for quality/data tools ──

async def _quality_task_status(arguments: dict, context) -> dict:
    """Query real task status from inspection_tasks table."""
    session = context.metadata.get("__db_session__")
    task_id = arguments.get("task_id", "")
    if not session or not task_id:
        return {"task_id": task_id, "status": "unknown", "reason": "missing session or task_id"}

    from sqlalchemy import select
    from app.models.task import InspectionTask
    result = await session.execute(
        select(InspectionTask).where(InspectionTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        return {"task_id": task_id, "status": "not_found"}
    return {
        "task_id": str(task.id),
        "status": task.status,
        "product_id": task.product_id,
        "spec_code": task.spec_code,
        "priority": task.priority,
        "started_at": task.started_at.isoformat() if hasattr(task, "started_at") and task.started_at else None,
        "finished_at": task.finished_at.isoformat() if hasattr(task, "finished_at") and task.finished_at else None,
    }


async def _quality_report_query(arguments: dict, context) -> dict:
    """Query real inspection results from inspection_results table."""
    session = context.metadata.get("__db_session__")
    if not session:
        return {"reports": [], "total": 0, "reason": "missing session"}

    from sqlalchemy import select, func
    from app.models.result import InspectionResult

    product_id = arguments.get("product_id", "")
    limit = min(arguments.get("limit", 10), 50)

    filters = [InspectionResult.deleted_at.is_(None)]
    if product_id:
        from app.models.task import InspectionTask
        stmt = (
            select(InspectionResult)
            .join(InspectionTask, InspectionResult.task_id == InspectionTask.id)
            .where(InspectionTask.product_id == product_id, InspectionResult.deleted_at.is_(None))
            .order_by(InspectionResult.created_at.desc())
            .limit(limit)
        )
    else:
        stmt = (
            select(InspectionResult)
            .where(*filters)
            .order_by(InspectionResult.created_at.desc())
            .limit(limit)
        )

    rows = (await session.execute(stmt)).scalars().all()
    reports = [{
        "result_id": str(r.id),
        "task_id": str(r.task_id),
        "verdict": r.verdict,
        "overall_score": float(r.overall_score) if r.overall_score else 0,
        "latency_ms": r.latency_ms,
        "llm_model": r.llm_model,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]

    count_stmt = select(func.count()).select_from(InspectionResult).where(InspectionResult.deleted_at.is_(None))
    total = (await session.execute(count_stmt)).scalar() or 0

    return {"reports": reports, "total": total}


async def _quality_inspection_execute(arguments: dict, context) -> dict:
    """Execute formal quality inspection via InspectionTaskGraph."""
    session = context.metadata.get("__db_session__")
    product_id = arguments.get("product_id", "")
    spec_code = arguments.get("spec_code", "")
    image_urls = arguments.get("image_urls", [])
    priority = arguments.get("priority", 5)

    if not session:
        return {"task_id": "", "status": "blocked", "reason": "missing db session"}

    from agent.subgraphs.inspection_task.graph import InspectionTaskGraph
    from agent.contracts.quality_contracts import NormalizedRequest

    request = NormalizedRequest(
        request_id=context.request_id,
        query=product_id + " " + spec_code,
        attachments=[],
        image_urls=image_urls,
        org_id=context.org_id,
        user_id=context.user_id or "",
        session_id=context.session_id,
        ext={
            "action_intent": "quality_inspection_execute",
            "product_id": product_id,
            "spec_code": spec_code,
            "priority": priority,
        },
    )
    graph = InspectionTaskGraph()
    result = await graph.run(request, db_session=session)
    return {
        "task_id": result.get("task_id", ""),
        "status": result.get("status", "executed"),
        "verdict": result.get("verdict"),
        "overall_score": result.get("overall_score"),
    }


async def _data_analysis(arguments: dict, context) -> dict:
    """Query real inspection statistics aggregations."""
    session = context.metadata.get("__db_session__")
    metric = arguments.get("metric", "pass_rate")
    days = min(arguments.get("days", 30), 365)

    if not session:
        return {"data": [], "summary": "missing session", "metric": metric}

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func
    from app.models.result import InspectionResult

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [InspectionResult.deleted_at.is_(None), InspectionResult.created_at >= cutoff]

    data = []
    summary = ""

    if metric == "pass_rate":
        total_stmt = select(func.count()).select_from(InspectionResult).where(*filters)
        total = (await session.execute(total_stmt)).scalar() or 1
        pass_stmt = select(func.count()).select_from(InspectionResult).where(
            *filters, InspectionResult.verdict.in_(["pass", "合格"])
        )
        passed = (await session.execute(pass_stmt)).scalar() or 0
        data.append({"label": "pass_rate", "value": round(passed / total * 100, 1)})
        data.append({"label": "total_inspections", "value": total})
        summary = f"近 {days} 天共 {total} 次检测，合格率 {round(passed / total * 100, 1)}%"

    elif metric == "defect_trend":
        from sqlalchemy import cast, Date
        date_stmt = (
            select(
                func.date(InspectionResult.created_at).label("date"),
                func.count().label("total"),
                func.sum(func.if_(InspectionResult.verdict.in_(["fail", "不合格"]), 1, 0)).label("failed"),
            )
            .where(*filters)
            .group_by(func.date(InspectionResult.created_at))
            .order_by(func.date(InspectionResult.created_at))
            .limit(days)
        )
        rows = (await session.execute(date_stmt)).all()
        for row in rows:
            data.append({
                "date": str(row.date),
                "total": int(row.total),
                "failed": int(row.failed or 0),
            })
        summary = f"近 {days} 天缺陷趋势，{len(data)} 天有记录"

    elif metric == "inspection_volume":
        stmt = select(func.count()).select_from(InspectionResult).where(*filters)
        total = (await session.execute(stmt)).scalar() or 0
        data.append({"label": "total", "value": total})
        summary = f"近 {days} 天共 {total} 次检测"

    return {"data": data, "summary": summary, "metric": metric, "days": days}
