"""bind standard libraries to quality thresholds

Revision ID: 0091_bind_standard_libraries_to_thresholds
Revises: 0090_default_auto_pass_enabled
Create Date: 2026-06-26
"""

from __future__ import annotations

import re
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0091_bind_standard_libraries_to_thresholds"
down_revision = "0090_default_auto_pass_enabled"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _uuid_bin() -> bytes:
    return uuid.uuid4().bytes


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-")
    return text.upper() or "GENERAL"


def _spec_code(product_family: str) -> str:
    return f"STD-{_slug(product_family)}-V1"


def upgrade() -> None:
    if not (_has_table("inspection_standard_libraries") and _has_table("inspection_specs")):
        return

    bind = op.get_bind()
    libraries = bind.execute(
        sa.text(
            """
            SELECT id, org_id, name, product_family, domain
            FROM inspection_standard_libraries
            WHERE deleted_at IS NULL
              AND (inspection_spec_id IS NULL OR spec_code IS NULL)
            """
        )
    ).mappings().all()

    for library in libraries:
        org_id = library["org_id"]
        product_family = str(library["product_family"] or "").strip()
        if not org_id or not product_family:
            continue
        spec_code = _spec_code(product_family)
        spec = bind.execute(
            sa.text(
                """
                SELECT id
                FROM inspection_specs
                WHERE deleted_at IS NULL
                  AND org_id = :org_id
                  AND spec_code = :spec_code
                LIMIT 1
                """
            ),
            {"org_id": org_id, "spec_code": spec_code},
        ).mappings().first()
        if spec:
            spec_id = spec["id"]
        else:
            spec_id = _uuid_bin()
            domain = str(library["domain"] or product_family).strip() or "通用质检"
            bind.execute(
                sa.text(
                    """
                    INSERT INTO inspection_specs (
                        id, org_id, spec_code, name, version, product_id, product_family,
                        applicable_skus, required_views, required_image_count,
                        ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold,
                        aggregation_rules, ai_gate_rules, manual_review_policies,
                        auto_pass_enabled, is_active, created_at, updated_at
                    )
                    VALUES (
                        :id, :org_id, :spec_code, :name, '2026.1', :product_id, :product_family,
                        :applicable_skus, :required_views, 1,
                        0.7200, 0.5000, 0.5000,
                        :aggregation_rules, :ai_gate_rules, :manual_review_policies,
                        1, 1, CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {
                    "id": spec_id,
                    "org_id": org_id,
                    "spec_code": spec_code,
                    "name": f"{domain}质检门槛",
                    "product_id": product_family,
                    "product_family": product_family,
                    "applicable_skus": f'["{product_family}"]',
                    "required_views": '["overview"]',
                    "aggregation_rules": '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
                    "ai_gate_rules": '{"confidence": 0.72, "evidence": 0.5, "traceability": 0.5, "faithfulness": 0.85, "physical_hallucination": 0.2}',
                    "manual_review_policies": '{"missing_required_views": "manual_required", "unmapped_defect": "manual_required", "low_evidence": "manual_required"}',
                },
            )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO inspection_spec_items (
                        id, spec_row_id, defect_type, severity, disposition,
                        confidence_threshold, zone_name, max_count, description,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :spec_row_id, :defect_type, 'critical', 'fail',
                        0.5500, 'overview', 1, 'Critical defects fail the inspection.',
                        CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {
                    "id": _uuid_bin(),
                    "spec_row_id": spec_id,
                    "defect_type": f"{product_family}.critical_defect",
                },
            )
        bind.execute(
            sa.text(
                """
                UPDATE inspection_standard_libraries
                SET inspection_spec_id = :spec_id,
                    spec_code = :spec_code
                WHERE id = :library_id
                """
            ),
            {"spec_id": spec_id, "spec_code": spec_code, "library_id": library["id"]},
        )


def downgrade() -> None:
    pass
