"""add inspection specs and seed baseline screw standard

Revision ID: 0008_inspection_specs
Revises: 0007_harden_core_timestamps
Create Date: 2026-03-24
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0008_inspection_specs"
down_revision = "0007_harden_core_timestamps"
branch_labels = None
depends_on = None


SPEC_ROW_ID = uuid.UUID("7f947c59-1f5f-4cf3-9e1f-d7997cc0ca11")
ITEM_IDS = [
    uuid.UUID("f7bceca8-a687-41ad-99a3-4cf984040001"),
    uuid.UUID("f7bceca8-a687-41ad-99a3-4cf984040002"),
    uuid.UUID("f7bceca8-a687-41ad-99a3-4cf984040003"),
]


def upgrade() -> None:
    op.create_table(
        "inspection_specs",
        sa.Column("id", mysql.BINARY(16), primary_key=True, nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=True),
        sa.Column("spec_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("product_id", sa.String(length=64), nullable=True),
        sa.Column("required_image_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ai_gate_confidence_threshold", sa.Numeric(5, 4), nullable=False, server_default="0.7200"),
        sa.Column("ai_gate_evidence_threshold", sa.Numeric(5, 4), nullable=False, server_default="0.5000"),
        sa.Column("ai_gate_traceability_threshold", sa.Numeric(5, 4), nullable=False, server_default="0.5000"),
        sa.Column("auto_pass_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    op.create_index("ix_inspection_specs_org_id", "inspection_specs", ["org_id"])
    op.create_index("ix_inspection_specs_spec_code", "inspection_specs", ["spec_code"])
    op.create_index("idx_spec_org_code_active", "inspection_specs", ["org_id", "spec_code", "is_active"])

    op.create_table(
        "inspection_spec_items",
        sa.Column("id", mysql.BINARY(16), primary_key=True, nullable=False),
        sa.Column("spec_row_id", mysql.BINARY(16), nullable=False),
        sa.Column("defect_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="major"),
        sa.Column("disposition", sa.String(length=32), nullable=False, server_default="fail"),
        sa.Column("confidence_threshold", sa.Numeric(5, 4), nullable=False, server_default="0.5500"),
        sa.Column("zone_name", sa.String(length=64), nullable=True),
        sa.Column("max_count", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    op.create_index("ix_inspection_spec_items_spec_row_id", "inspection_spec_items", ["spec_row_id"])
    op.create_index("ix_inspection_spec_items_defect_type", "inspection_spec_items", ["defect_type"])

    spec_table = sa.table(
        "inspection_specs",
        sa.column("id", mysql.BINARY(16)),
        sa.column("org_id", mysql.BINARY(16)),
        sa.column("spec_code", sa.String(64)),
        sa.column("name", sa.String(128)),
        sa.column("version", sa.String(32)),
        sa.column("product_id", sa.String(64)),
        sa.column("required_image_count", sa.Integer()),
        sa.column("ai_gate_confidence_threshold", sa.Numeric(5, 4)),
        sa.column("ai_gate_evidence_threshold", sa.Numeric(5, 4)),
        sa.column("ai_gate_traceability_threshold", sa.Numeric(5, 4)),
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

    op.bulk_insert(
        spec_table,
        [
            {
                "id": SPEC_ROW_ID.bytes,
                "org_id": None,
                "spec_code": "SCREW-A-2026-V1",
                "name": "螺钉外观检测基线标准",
                "version": "2026.1",
                "product_id": "screw",
                "required_image_count": 1,
                "ai_gate_confidence_threshold": 0.72,
                "ai_gate_evidence_threshold": 0.5,
                "ai_gate_traceability_threshold": 0.5,
                "auto_pass_enabled": False,
                "is_active": True,
            }
        ],
    )
    op.bulk_insert(
        item_table,
        [
            {
                "id": ITEM_IDS[0].bytes,
                "spec_row_id": SPEC_ROW_ID.bytes,
                "defect_type": "crack",
                "severity": "critical",
                "disposition": "fail",
                "confidence_threshold": 0.45,
                "zone_name": "body",
                "max_count": 1,
                "description": "裂纹属于关键缺陷，命中即拒收。",
            },
            {
                "id": ITEM_IDS[1].bytes,
                "spec_row_id": SPEC_ROW_ID.bytes,
                "defect_type": "surface_scratch",
                "severity": "major",
                "disposition": "fail",
                "confidence_threshold": 0.62,
                "zone_name": "body",
                "max_count": 1,
                "description": "表面划伤达到显著置信度时判定为拒收。",
            },
            {
                "id": ITEM_IDS[2].bytes,
                "spec_row_id": SPEC_ROW_ID.bytes,
                "defect_type": "coating_defect",
                "severity": "minor",
                "disposition": "manual_required",
                "confidence_threshold": 0.55,
                "zone_name": "body",
                "max_count": 2,
                "description": "镀层异常先人工复核，不自动放行。",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_inspection_spec_items_defect_type", table_name="inspection_spec_items")
    op.drop_index("ix_inspection_spec_items_spec_row_id", table_name="inspection_spec_items")
    op.drop_table("inspection_spec_items")
    op.drop_index("idx_spec_org_code_active", table_name="inspection_specs")
    op.drop_index("ix_inspection_specs_spec_code", table_name="inspection_specs")
    op.drop_index("ix_inspection_specs_org_id", table_name="inspection_specs")
    op.drop_table("inspection_specs")
