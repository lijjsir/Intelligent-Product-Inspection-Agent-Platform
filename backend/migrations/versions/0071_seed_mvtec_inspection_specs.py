"""seed MVTec anomaly detection inspection specs

Revision ID: 0071
Revises: 0070
Create Date: 2026-05-26
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


SPEC_ROWS = [
    {
        "product_id": "bottle",
        "family": "瓶子",
        "name": "瓶子外观缺陷检测门槛",
        "rules": [
            ("bottle.exterior.crack", "critical", "fail", 0.45, "瓶身", 1, "瓶身裂缝命中即拒收。"),
            ("bottle.opening.deformation", "major", "fail", 0.58, "瓶口", 1, "瓶口变形会影响密封，需拒收。"),
            ("bottle.label.print_blur", "minor", "manual_required", 0.60, "标签", 1, "标签印刷模糊进入人工复核。"),
            ("bottle.bottom.foreign_body", "major", "fail", 0.55, "瓶底", 1, "瓶底异物或沉淀判定为高风险缺陷。"),
        ],
    },
    {
        "product_id": "cable",
        "family": "电缆",
        "name": "电缆外观与连接缺陷检测门槛",
        "rules": [
            ("cable.exterior.insulation_damage", "critical", "fail", 0.46, "外护层", 1, "绝缘层破损存在安全风险，命中即拒收。"),
            ("cable.cross_section.diameter_deviation", "major", "manual_required", 0.62, "截面", 1, "线径偏差需人工复核尺寸。"),
            ("cable.connector.loose", "major", "fail", 0.58, "接头", 1, "接头松动会影响连接可靠性。"),
            ("cable.marking.illegible", "minor", "manual_required", 0.60, "标识", 1, "标识不清需要确认批次和规格。"),
        ],
    },
    {
        "product_id": "capsule",
        "family": "胶囊",
        "name": "胶囊表面与封口缺陷检测门槛",
        "rules": [
            ("capsule.exterior.crack", "critical", "fail", 0.45, "外壳", 1, "胶囊壳破裂直接拒收。"),
            ("capsule.exterior.deformation", "major", "fail", 0.56, "外壳", 1, "胶囊变形影响灌装与包装稳定性。"),
            ("capsule.exterior.color_spot", "major", "manual_required", 0.58, "表面", 1, "色斑需人工确认是否为污染。"),
            ("capsule.seal.leak", "critical", "fail", 0.48, "封口", 1, "封口泄漏属于关键缺陷。"),
        ],
    },
    {
        "product_id": "carpet",
        "family": "地毯",
        "name": "地毯织面缺陷检测门槛",
        "rules": [
            ("carpet.front.stain", "major", "fail", 0.55, "正面", 1, "正面污渍达到阈值时拒收。"),
            ("carpet.front.color_deviation", "major", "manual_required", 0.62, "正面", 1, "明显色差进入人工复核。"),
            ("carpet.edge.fraying", "major", "fail", 0.58, "边缘", 1, "边缘脱线影响耐用性。"),
            ("carpet.back.thickness_uneven", "minor", "manual_required", 0.63, "背面", 2, "厚度不均累计超限需复核。"),
        ],
    },
    {
        "product_id": "grid",
        "family": "网格",
        "name": "网格结构缺陷检测门槛",
        "rules": [
            ("grid.structure.breakage", "critical", "fail", 0.48, "网格结构", 1, "网格断裂命中即拒收。"),
            ("grid.structure.deformation", "major", "fail", 0.56, "网格结构", 1, "结构形变会影响装配精度。"),
            ("grid.hole.blocked", "major", "manual_required", 0.60, "孔位", 1, "孔洞堵塞需人工确认可用性。"),
            ("grid.surface.contamination", "minor", "manual_required", 0.62, "表面", 2, "表面污染累计超限需复核。"),
        ],
    },
    {
        "product_id": "hazelnut",
        "family": "榛子",
        "name": "榛子外观缺陷检测门槛",
        "rules": [
            ("hazelnut.shell.crack", "major", "fail", 0.52, "外壳", 1, "外壳裂纹可能暴露内部组织。"),
            ("hazelnut.surface.mold", "critical", "fail", 0.45, "表面", 1, "霉斑属于食品安全关键缺陷。"),
            ("hazelnut.surface.insect_damage", "critical", "fail", 0.48, "表面", 1, "虫蛀痕迹直接拒收。"),
            ("hazelnut.surface.foreign_body", "major", "manual_required", 0.58, "表面", 1, "异物附着需人工确认。"),
        ],
    },
    {
        "product_id": "leather",
        "family": "皮革",
        "name": "皮革表面缺陷检测门槛",
        "rules": [
            ("leather.surface.scratch", "major", "fail", 0.55, "表面", 1, "明显划痕影响外观等级。"),
            ("leather.surface.stain", "major", "fail", 0.56, "表面", 1, "污渍达到阈值时拒收。"),
            ("leather.surface.wrinkle", "minor", "manual_required", 0.62, "表面", 2, "褶皱累计超限需复核。"),
            ("leather.surface.hole", "critical", "fail", 0.46, "表面", 1, "破洞属于关键缺陷。"),
        ],
    },
    {
        "product_id": "metal_nut",
        "family": "金属螺母",
        "name": "金属螺母结构缺陷检测门槛",
        "rules": [
            ("metal_nut.thread.damage", "critical", "fail", 0.48, "螺纹", 1, "螺纹损伤影响装配强度。"),
            ("metal_nut.edge.chip", "major", "fail", 0.54, "边缘", 1, "边缘缺口达到阈值时拒收。"),
            ("metal_nut.surface.rust", "major", "manual_required", 0.58, "表面", 1, "锈蚀需人工确认等级。"),
            ("metal_nut.body.crack", "critical", "fail", 0.45, "本体", 1, "本体裂纹命中即拒收。"),
        ],
    },
    {
        "product_id": "pill",
        "family": "药片",
        "name": "药片外观缺陷检测门槛",
        "rules": [
            ("pill.body.crack", "critical", "fail", 0.46, "片体", 1, "药片裂纹直接拒收。"),
            ("pill.body.chip", "major", "fail", 0.54, "边缘", 1, "缺角影响剂量和外观。"),
            ("pill.color.abnormal", "major", "manual_required", 0.58, "表面", 1, "颜色异常需人工确认污染风险。"),
            ("pill.surface.foreign_body", "critical", "fail", 0.48, "表面", 1, "异物附着属于关键缺陷。"),
        ],
    },
    {
        "product_id": "screw",
        "family": "螺丝",
        "name": "MVTec 螺丝结构缺陷检测门槛",
        "rules": [
            ("screw.thread.damage", "critical", "fail", 0.48, "螺纹", 1, "螺纹损伤影响锁付强度。"),
            ("screw.body.bent", "critical", "fail", 0.46, "杆身", 1, "杆身弯曲命中即拒收。"),
            ("screw.surface.rust", "major", "manual_required", 0.58, "表面", 1, "锈蚀需人工确认等级。"),
            ("screw.head.chip", "major", "fail", 0.55, "头部", 1, "头部缺口会影响装配工具咬合。"),
        ],
    },
    {
        "product_id": "tile",
        "family": "瓷砖",
        "name": "瓷砖表面与边角缺陷检测门槛",
        "rules": [
            ("tile.surface.crack", "critical", "fail", 0.46, "表面", 1, "瓷砖裂纹命中即拒收。"),
            ("tile.edge.chip", "major", "fail", 0.54, "边角", 1, "边角缺损影响铺装质量。"),
            ("tile.surface.scratch", "minor", "manual_required", 0.60, "釉面", 1, "釉面划痕需人工确认等级。"),
            ("tile.color.deviation", "major", "manual_required", 0.62, "表面", 1, "明显色差进入人工复核。"),
        ],
    },
    {
        "product_id": "toothbrush",
        "family": "牙刷",
        "name": "牙刷刷头与手柄缺陷检测门槛",
        "rules": [
            ("toothbrush.bristle.missing", "major", "fail", 0.54, "刷毛", 1, "刷毛缺失影响清洁效果。"),
            ("toothbrush.head.deformation", "major", "fail", 0.55, "刷头", 1, "刷头变形影响使用安全。"),
            ("toothbrush.surface.contamination", "critical", "fail", 0.48, "表面", 1, "污染属于卫生关键缺陷。"),
            ("toothbrush.handle.crack", "major", "manual_required", 0.58, "手柄", 1, "手柄裂纹需人工确认强度。"),
        ],
    },
    {
        "product_id": "transistor",
        "family": "晶体管",
        "name": "晶体管引脚与封装缺陷检测门槛",
        "rules": [
            ("transistor.pin.bent", "critical", "fail", 0.48, "引脚", 1, "引脚弯曲会影响焊接和导通。"),
            ("transistor.pin.missing", "critical", "fail", 0.45, "引脚", 1, "引脚缺失命中即拒收。"),
            ("transistor.package.crack", "critical", "fail", 0.46, "封装", 1, "封装裂纹存在可靠性风险。"),
            ("transistor.marking.missing", "minor", "manual_required", 0.60, "标识", 1, "标识缺失需人工确认批次。"),
        ],
    },
    {
        "product_id": "wood",
        "family": "木材",
        "name": "木材表面缺陷检测门槛",
        "rules": [
            ("wood.surface.crack", "major", "fail", 0.52, "表面", 1, "表面裂纹影响结构强度。"),
            ("wood.knot.oversize", "minor", "manual_required", 0.62, "节疤", 1, "节疤超限需人工判级。"),
            ("wood.surface.insect_hole", "critical", "fail", 0.48, "表面", 1, "虫孔属于关键缺陷。"),
            ("wood.surface.mold", "critical", "fail", 0.47, "表面", 1, "霉斑存在质量与卫生风险。"),
        ],
    },
    {
        "product_id": "zipper",
        "family": "拉链",
        "name": "拉链齿带与拉头缺陷检测门槛",
        "rules": [
            ("zipper.teeth.missing", "critical", "fail", 0.48, "链齿", 1, "链齿缺失会导致拉合失效。"),
            ("zipper.teeth.misaligned", "major", "fail", 0.55, "链齿", 1, "错齿影响顺滑度和闭合可靠性。"),
            ("zipper.slider.damage", "major", "fail", 0.54, "拉头", 1, "拉头损坏直接影响使用。"),
            ("zipper.tape.fraying", "minor", "manual_required", 0.60, "布带", 1, "布带破损需人工确认等级。"),
        ],
    },
]


def _uuid_bytes(seed: str) -> bytes:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"piap.mvtec.{seed}").bytes


def _spec_code(product_id: str) -> str:
    return f"MVTEC-{product_id.upper().replace('_', '-')}-2026-V1"


def upgrade() -> None:
    bind = op.get_bind()
    spec_table = sa.table(
        "inspection_specs",
        sa.column("id", mysql.BINARY(16)),
        sa.column("org_id", mysql.BINARY(16)),
        sa.column("spec_code", sa.String(64)),
        sa.column("name", sa.String(128)),
        sa.column("version", sa.String(32)),
        sa.column("product_id", sa.String(64)),
        sa.column("product_family", sa.String(128)),
        sa.column("applicable_skus", mysql.JSON),
        sa.column("required_views", mysql.JSON),
        sa.column("required_image_count", sa.Integer()),
        sa.column("ai_gate_confidence_threshold", sa.Numeric(5, 4)),
        sa.column("ai_gate_evidence_threshold", sa.Numeric(5, 4)),
        sa.column("ai_gate_traceability_threshold", sa.Numeric(5, 4)),
        sa.column("aggregation_rules", mysql.JSON),
        sa.column("ai_gate_rules", mysql.JSON),
        sa.column("manual_review_policies", mysql.JSON),
        sa.column("auto_pass_enabled", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )
    item_table = sa.table(
        "inspection_spec_items",
        sa.column("id", mysql.BINARY(16)),
        sa.column("spec_row_id", mysql.BINARY(16)),
        sa.column("defect_type", sa.String(64)),
        sa.column("severity", sa.String(16)),
        sa.column("disposition", sa.String(32)),
        sa.column("confidence_threshold", sa.Numeric(5, 4)),
        sa.column("zone_name", sa.String(64)),
        sa.column("max_count", sa.Integer()),
        sa.column("description", sa.Text()),
    )

    for spec in SPEC_ROWS:
        product_id = spec["product_id"]
        spec_code = _spec_code(product_id)
        existing = bind.execute(
            sa.select(spec_table.c.id).where(spec_table.c.spec_code == spec_code)
        ).first()
        if existing:
            continue

        spec_id = _uuid_bytes(f"spec.{product_id}")
        bind.execute(
            spec_table.insert().values(
                id=spec_id,
                org_id=None,
                spec_code=spec_code,
                name=spec["name"],
                version="MVTec-2026.1",
                product_id=product_id,
                product_family=spec["family"],
                applicable_skus=[product_id],
                required_views=["正面", "局部细节"],
                required_image_count=1,
                ai_gate_confidence_threshold=0.72,
                ai_gate_evidence_threshold=0.50,
                ai_gate_traceability_threshold=0.50,
                aggregation_rules={"strategy": "任一严重或致命缺陷命中则不放行"},
                ai_gate_rules={"dataset": "MVTec Anomaly Detection", "language": "zh-CN"},
                manual_review_policies={"uncertain": "置信度不足或轻微缺陷累计超限时进入人工复核"},
                auto_pass_enabled=False,
                is_active=True,
            )
        )
        for index, (defect_type, severity, disposition, threshold, zone, max_count, description) in enumerate(spec["rules"], 1):
            bind.execute(
                item_table.insert().values(
                    id=_uuid_bytes(f"item.{product_id}.{index}"),
                    spec_row_id=spec_id,
                    defect_type=defect_type,
                    severity=severity,
                    disposition=disposition,
                    confidence_threshold=threshold,
                    zone_name=zone,
                    max_count=max_count,
                    description=description,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    spec_table = sa.table(
        "inspection_specs",
        sa.column("id", mysql.BINARY(16)),
        sa.column("spec_code", sa.String(64)),
    )
    item_table = sa.table(
        "inspection_spec_items",
        sa.column("spec_row_id", mysql.BINARY(16)),
    )
    codes = [_spec_code(spec["product_id"]) for spec in SPEC_ROWS]
    ids = [
        row[0]
        for row in bind.execute(sa.select(spec_table.c.id).where(spec_table.c.spec_code.in_(codes))).all()
    ]
    if ids:
        bind.execute(item_table.delete().where(item_table.c.spec_row_id.in_(ids)))
        bind.execute(spec_table.delete().where(spec_table.c.id.in_(ids)))
