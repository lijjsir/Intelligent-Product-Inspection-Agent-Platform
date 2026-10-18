"""Explainable counts over canonical intake records. Signals are not risk decisions.

Durability uses the existing tenant/kind/code unique journal. No parallel master
objects or copied intake payloads are created. Organization locks serialize scans,
rule updates, focus changes and conversion mappings across workers.
"""
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.organization import Organization
from app.models.quality_risk import ProductCategory, QualityDataSource, QualityProduct, QualityRiskCase, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.market_monitoring import MarketRule
from app.schemas.quality_risk import RiskCaseCreate
from app.services.quality_risk_service import QualityRiskService, stable_hash
from app.services.supervision_service import SupervisionService

TZ = ZoneInfo("Asia/Shanghai")
KINDS = ("consumer_complaint", "public_opinion")
LABELS = {"consumer_complaint": "投诉", "public_opinion": "舆情"}
RULE_VERSION = "count-growth-v1"


def utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def windows(as_of: date | None = None, now: datetime | None = None):
    today = (now or datetime.now(timezone.utc)).astimezone(TZ).date()
    day = as_of or today
    if day > today:
        raise ValidationError("统计截止日不能晚于北京时间今天")
    end = datetime.combine(day, time.min, tzinfo=TZ)
    return tuple(utc(x) for x in (end - timedelta(days=14), end - timedelta(days=7), end))


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def classify(previous, current, covered, rule):
    if not covered:
        return "insufficient_coverage", None
    qualifying = current >= rule["min_current"] and current - previous >= rule["min_increase"] and current >= previous * rule["growth_factor"]
    status = ("new_cluster" if previous == 0 else "quantity_growth") if qualifying else "normal"
    return status, ((current - previous) / previous * 100 if previous else None)


class MarketMonitoringService:
    def __init__(self, db, current):
        self.db, self.current = db, current
        self.org_id, self.actor = str(current.org_id), str(current.user_id)
        self.mode = "demo" if settings.quality_demo_enabled else "business"
        self.locked = False

    async def guard(self, lock=False):
        svc = SupervisionService(self.db, self.current)
        await svc.permissions()
        # The first rollout is the expert workspace. Do not widen raw-material
        # visibility for operational roles that can read legacy aggregates.
        svc.require_role({"admin", "expert"})
        require_role("quality_material_read_business", self.current.role)
        await svc.require_enabled()
        stmt = select(Organization).where(Organization.id == self.org_id).execution_options(populate_existing=True)
        org = await self.db.scalar(stmt.with_for_update() if lock else stmt)
        self.locked = self.locked or lock
        if (org.settings or {}).get("execution_mode") == "demo" and self.mode != "demo":
            raise ForbiddenError("演示组织仅能在服务端启用的隔离演示环境使用")
        return org

    def row_query(self, kind, code=None):
        stmt = select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == kind)
        stmt = stmt.where(SupervisionRecord.code == code) if code else stmt
        return self.current_read(stmt)

    def current_read(self, stmt):
        # Authentication can establish an older MySQL REPEATABLE READ snapshot
        # before a request waits for the organization lock. Mutations must use
        # current locking reads to see another worker's committed conversion.
        return stmt.with_for_update().execution_options(populate_existing=True) if self.locked else stmt

    async def rules(self):
        row = await self.db.scalar(self.row_query("market-rule", self.mode))
        rule = MarketRule.model_validate((row.data or {}).get("thresholds", {}) if row else {}).model_dump()
        return {"version": row.version if row else 1, "algorithm": RULE_VERSION, "window_days": 7, **rule}

    async def update_rule(self, payload):
        await self.guard(lock=True)
        rule = await self.rules()
        if payload.expected_version != rule["version"]:
            raise ConflictError("规则已更新，请刷新后重试")
        row = await self.db.scalar(self.row_query("market-rule", self.mode))
        if not row:
            row = self.new_row("market-rule", self.mode, "数量增长线索规则", {})
        old = dict(row.data or {})
        row.version = rule["version"] + 1
        row.data = {"thresholds": payload.model_dump(include={"min_current", "min_increase", "growth_factor"}),
                    "history": [*old.get("history", []), {"before": rule, "actor_id": self.actor, "reason": payload.reason, "at": iso(datetime.utcnow())}]}
        await self.db.flush()
        return await self.rules()

    def new_row(self, kind, code, name, data):
        row = SupervisionRecord(id=str(uuid5(NAMESPACE_URL, f"market:{self.org_id}:{kind}:{code}")),
                                org_id=self.org_id, kind=kind, code=code, name=name[:255],
                                status="active", version=1, created_by=self.actor, data=data)
        self.db.add(row)
        return row

    async def coverage(self):
        await self.guard()
        sources = list(await self.db.scalars(self.current_read(select(QualityDataSource).where(QualityDataSource.org_id == self.org_id,
                            QualityDataSource.deleted_at.is_(None), QualityDataSource.status == "active"))))
        rows = list(await self.db.scalars(self.row_query("market-coverage")))
        data = {(r.data["source_id"], r.data["record_type"]): r.data for r in rows if r.data.get("execution_mode") == self.mode}
        return [{"source_id": s.id, "source_name": s.name, "record_type": k,
                 "coverage": data.get((s.id, k))} for s in sources for k in KINDS]

    async def set_coverage(self, payload):
        await self.guard(lock=True)
        source = await self.db.scalar(select(QualityDataSource).where(QualityDataSource.id == str(payload.source_id),
                    QualityDataSource.org_id == self.org_id, QualityDataSource.deleted_at.is_(None), QualityDataSource.status == "active"))
        if not source:
            raise NotFoundError("数据来源不可用")
        if utc(payload.end_at) > datetime.utcnow():
            raise ValidationError("不能声明未来资料已完整覆盖")
        code = f"{self.mode}:{source.id}:{payload.record_type}"
        row = await self.db.scalar(self.row_query("market-coverage", code))
        if not row:
            row = self.new_row("market-coverage", code, "资料覆盖声明", {})
        previous = {k: v for k, v in (row.data or {}).items() if k != "history"}
        row.version += 1
        row.data = {"source_id": source.id, "record_type": payload.record_type, "start_at": iso(utc(payload.start_at)),
                    "end_at": iso(utc(payload.end_at)), "reason": payload.reason, "actor_id": self.actor,
                    "at": iso(datetime.utcnow()), "execution_mode": self.mode,
                    "history": [*(row.data or {}).get("history", []), previous] if previous else []}
        await self.db.flush()
        return {k: v for k, v in row.data.items() if k != "history"}

    async def objects(self, object_type):
        if object_type == "product":
            rows = await self.db.scalars(self.current_read(select(QualityProduct).join(ProductCategory, ProductCategory.id == QualityProduct.category_id).where(
                QualityProduct.org_id == self.org_id, QualityProduct.deleted_at.is_(None), QualityProduct.is_active.is_(True),
                ProductCategory.org_id == self.org_id, ProductCategory.deleted_at.is_(None), ProductCategory.is_active.is_(True))))
        else:
            rows = await self.db.scalars(self.current_read(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
                               SupervisionRecord.kind == "enterprises", SupervisionRecord.status == "active")))
        return {x.id: x for x in rows}

    @staticmethod
    def object_id(row, object_type):
        ref = (row.product_ref if object_type == "product" else row.enterprise_ref) or {}
        return str(ref.get("product_id") or "") if object_type == "product" else str(ref.get("enterprise_id") or ref.get("id") or "")

    async def report(self, payload, *, persist=False, lock_records=False):
        org = await self.guard(lock=persist)
        selected_day = payload.as_of
        demo_day = None
        if self.mode == 'demo' and (org.settings or {}).get('anchor_at'):
            try:
                anchor = datetime.fromisoformat(org.settings['anchor_at'])
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                demo_day = anchor.astimezone(TZ).date()
            except (TypeError, ValueError):
                raise ValidationError('演示统计日期配置无效，请核对演示初始化记录') from None
            if selected_day is None:
                selected_day = demo_day
        start, middle, end = windows(selected_day)
        rule = await self.rules()
        objects = await self.objects(payload.object_type)
        source_rows = list(await self.db.scalars(self.current_read(select(QualityDataSource).where(QualityDataSource.org_id == self.org_id))))
        sources = {s.id: s for s in source_rows if s.deleted_at is None and s.status == "active"}
        coverage = {(c["source_id"], c["record_type"]): c["coverage"] for c in await self.coverage()}
        stmt = select(QualitySourceRecord).where(QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.deleted_at.is_(None),
                QualitySourceRecord.record_type.in_(KINDS),
                QualitySourceRecord.data_nature == ("synthetic" if self.mode == "demo" else "observed"),
                or_(QualitySourceRecord.occurred_at.is_(None),
                    (QualitySourceRecord.occurred_at >= start) & (QualitySourceRecord.occurred_at < end))).order_by(QualitySourceRecord.id)
        rows = list(await self.db.scalars(stmt.with_for_update().execution_options(populate_existing=True) if lock_records or persist else stmt))
        pending, missing, unavailable, groups = [], [], [], {}
        totals = {k: {"previous": 0, "current": 0} for k in KINDS}
        daily = [{"day": (start.replace(tzinfo=timezone.utc).astimezone(TZ) + timedelta(days=i)).date().isoformat(),
                  **{k: 0 for k in KINDS}} for i in range(14)]
        for row in rows:
            summary = self.source_summary(row)
            if row.source_id not in sources:
                unavailable.append(summary)
                continue
            object_id = self.object_id(row, payload.object_type)
            if object_id not in objects:
                pending.append(summary)
            if row.occurred_at is None:
                missing.append(summary)
                continue
            period = "previous" if row.occurred_at < middle else "current"
            totals[row.record_type][period] += 1
            daily[(row.occurred_at - start).days][row.record_type] += 1
            if object_id not in objects:
                continue
            groups.setdefault((object_id, row.record_type), []).append(row)

        results = []
        for (object_id, kind), records in sorted(groups.items()):
            previous = [r for r in records if r.occurred_at < middle]
            current = [r for r in records if r.occurred_at >= middle]
            declarations, uncovered = [], []
            for source_id in sorted({r.source_id for r in records}):
                c = coverage.get((source_id, kind))
                covered = c and utc(datetime.fromisoformat(c["start_at"])) <= start and utc(datetime.fromisoformat(c["end_at"])) >= end
                if not covered:
                    uncovered.append(sources[source_id].name)
                declarations.append({"source_id": source_id, "coverage": {k: v for k, v in c.items() if k != "history"} if c else None})
            status, percent = classify(len(previous), len(current), not uncovered, rule)
            basis = {"execution_mode": self.mode, "as_of": end.replace(tzinfo=timezone.utc).astimezone(TZ).date().isoformat(),
                     "object_type": payload.object_type, "object_id": object_id, "record_type": kind,
                     "windows": {"previous_start": iso(start), "current_start": iso(middle), "end": iso(end), "timezone": "Asia/Shanghai"},
                     "rule": rule, "previous_count": len(previous), "current_count": len(current), "status": status,
                     "growth_percent": percent, "coverage": declarations,
                     "source_record_ids": [r.id for r in records],
                     "source_fingerprints": {r.id: stable_hash({"content_hash": r.content_hash, "product_ref": r.product_ref,
                        "enterprise_ref": r.enterprise_ref, "occurred_at": r.occurred_at, "source_id": r.source_id,
                        "authorization_scope": r.authorization_scope, "provenance": r.provenance}) for r in records}}
            code = stable_hash(basis)
            stored = await self.db.scalar(self.row_query("market-signal", code))
            if persist and status in {"quantity_growth", "new_cluster"} and not stored:
                stored = self.new_row("market-signal", code, f"{objects[object_id].name} · {LABELS[kind]}数量线索", basis)
                await self.db.flush()
            results.append({**basis, "object_name": objects[object_id].name,
                            "signal_id": stored.id if stored else None,
                            "case_id": (stored.data or {}).get("case_id") if stored else None,
                            "uncovered_sources": uncovered})
        return {"execution_mode": self.mode, "as_of": end.replace(tzinfo=timezone.utc).astimezone(TZ).date().isoformat(),
                "date_basis": 'explicit' if payload.as_of else 'demo_anchor' if demo_day else 'current_day',
                "demo_anchor_as_of": demo_day.isoformat() if demo_day else None,
                "windows": {"previous_start": iso(start), "current_start": iso(middle), "end": iso(end), "timezone": "Asia/Shanghai"},
                "object_type": payload.object_type, "rule": rule, "totals": totals, "daily": daily,
                "groups": results, "pending_objects": pending, "missing_time": missing, "unavailable_sources": unavailable,
                "notice": "规则仅识别数量变化，不代表风险结论；本日及未来发生的资料不参与完整窗口比较。"}

    @staticmethod
    def source_summary(row):
        return {"id": row.id, "record_type": row.record_type, "occurred_at": iso(row.occurred_at) if row.occurred_at else None,
                "external_record_id": row.external_record_id, "text": str((row.content or {}).get("text", ""))[:200]}

    async def signal(self, signal_id):
        row = await self.db.scalar(self.row_query("market-signal").where(SupervisionRecord.id == signal_id))
        if not row or row.data.get("execution_mode") != self.mode:
            raise NotFoundError("线索不存在")
        return row

    async def detail(self, signal_id):
        await self.guard()
        row = await self.signal(signal_id)
        from app.schemas.market_monitoring import MarketScan
        report = await self.report(MarketScan(as_of=date.fromisoformat(row.data["as_of"]), object_type=row.data["object_type"]))
        fresh = next((g for g in report["groups"] if g.get("signal_id") == row.id), None)
        rows = await self.db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id == self.org_id,
                    QualitySourceRecord.id.in_(row.data["source_record_ids"]), QualitySourceRecord.deleted_at.is_(None)))
        return {"id": row.id, "name": row.name, "snapshot": row.data, "is_current": bool(fresh),
                "records": [self.source_summary(r) for r in rows]}

    async def convert(self, signal_id, payload):
        await self.guard(lock=True)
        row = await self.signal(signal_id)
        data = dict(row.data)
        # Return the original mapping even if evidence has since changed; the
        # case's normal evidence validator controls any later conclusion.
        risk = QualityRiskService(self.db, self.current)
        if data.get("case_id"):
            if payload.target_case_id and str(payload.target_case_id) != data["case_id"]:
                raise ConflictError("该线索已经关联另一研判事项")
            case = await risk.risk_case(data["case_id"], lock=True)
            return {"case": risk.risk_case_response(case), "reused": True}
        from app.schemas.market_monitoring import MarketScan
        report = await self.report(MarketScan(as_of=date.fromisoformat(data["as_of"]), object_type=data["object_type"]), lock_records=True)
        candidate = next((g for g in report["groups"] if g.get("signal_id") == row.id and g["status"] in {"quantity_growth", "new_cluster"}), None)
        if not candidate:
            raise ConflictError("资料、对象、覆盖声明或规则已变化，请重新扫描并核对线索")
        if len(data["source_record_ids"]) > 500:
            raise ValidationError("该线索超过研判事项的 500 条来源上限，请先由专家整理资料范围；原始线索快照已保留")
        if payload.target_case_id:
            target = await risk.risk_case(str(payload.target_case_id), lock=True)
            if (target.scope or {}).get(f"{data['object_type']}_id") != data["object_id"]:
                raise ValidationError("只能关联同一已确认对象的研判事项")
            if ((target.scope or {}).get("execution_mode") == "demo") != (self.mode == "demo"):
                raise ValidationError("演示线索与正式研判事项不能混用")
            case = await risk.append_risk_sources(target.id, data["source_record_ids"])
            target.scope = {**target.scope, "market_signal_ids": list(dict.fromkeys([*target.scope.get("market_signal_ids", []), row.id]))}
        else:
            case = await risk.create_risk_case(RiskCaseCreate(title=("【演示】" if self.mode == "demo" else "") + row.name,
                scope_type=data["object_type"], scope={"name": candidate["object_name"], f"{data['object_type']}_id": data["object_id"], "execution_mode": self.mode,
                                                     "market_signal_ids": [row.id]}, source_record_ids=data["source_record_ids"], assigned_to=self.actor))
        data["case_id"], data["converted_by"], data["converted_at"] = case["id"], self.actor, iso(datetime.utcnow())
        row.data = data
        await self.db.flush()
        return {"case": case, "reused": False}

    async def focus_list(self):
        await self.guard()
        maps = {k: await self.objects(k) for k in ("product", "enterprise")}
        rows = list(await self.db.scalars(self.row_query("market-focus").where(SupervisionRecord.status == "active")))
        return [{"id": r.id, **{k: v for k, v in r.data.items() if k != "history"},
                 "object_name": getattr(maps[r.data["object_type"]].get(r.data["object_id"]), "name", "对象已不可用"),
                 "available": r.data["object_id"] in maps[r.data["object_type"]]} for r in rows if r.data.get("execution_mode") == self.mode]

    async def add_focus(self, payload):
        await self.guard(lock=True)
        objects = await self.objects(payload.object_type)
        object_id = str(payload.object_id)
        if object_id not in objects:
            raise NotFoundError("对象不可用，请在资料接入中确认对象")
        code = f"{self.mode}:{payload.object_type}:{object_id}"
        row = await self.db.scalar(self.row_query("market-focus", code))
        if row and row.status == "active":
            return {"id": row.id, "reused": True}
        if not row:
            row = self.new_row("market-focus", code, objects[object_id].name, {})
        old = dict(row.data or {})
        row.status = "active"
        row.version += 1
        row.data = {"object_type": payload.object_type, "object_id": object_id, "reason": payload.reason,
                    "execution_mode": self.mode, "actor_id": self.actor, "at": iso(datetime.utcnow()),
                    "history": [*old.get("history", []), {"action": "add", "reason": payload.reason, "actor_id": self.actor, "at": iso(datetime.utcnow())}]}
        await self.db.flush()
        return {"id": row.id, "reused": False}

    async def remove_focus(self, record_id, reason):
        await self.guard(lock=True)
        row = await self.db.scalar(self.row_query("market-focus").where(SupervisionRecord.id == record_id))
        if not row or row.data.get("execution_mode") != self.mode:
            raise NotFoundError("关注记录不存在")
        if row.status != "archived":
            row.status = "archived"
            row.version += 1
            row.data = {**row.data, "history": [*row.data.get("history", []), {"action": "remove", "reason": reason,
                        "actor_id": self.actor, "at": iso(datetime.utcnow())}]}
            await self.db.flush()
        return {"removed": True}
