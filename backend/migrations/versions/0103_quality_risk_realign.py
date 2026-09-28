"""Risk-first quality data foundation and simplified product model.

Revision ID: 0103_quality_risk_realign
Revises: 0102_adaptive_quality_supervision
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY

revision = "0103_quality_risk_realign"
down_revision = "0102_adaptive_quality_supervision"
branch_labels = depends_on = None


U = BINARY(16)


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    ]


def create(name, *columns, uniques=(), indexes=()):
    op.create_table(
        name,
        sa.Column("id", U, primary_key=True),
        sa.Column("org_id", U, nullable=False),
        *columns,
        *timestamps(),
        *(sa.UniqueConstraint(*fields, name=constraint) for constraint, fields in uniques),
    )
    op.create_index(f"ix_{name}_org_id", name, ["org_id"])
    for index in indexes:
        op.create_index(f"ix_{name}_{index}", name, [index])


def upgrade():
    create(
        "product_categories",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("parent_id", U, nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        uniques=(("uq_product_category_code", ("org_id", "code")),),
        indexes=("code", "parent_id"),
    )
    create(
        "quality_products",
        sa.Column("category_id", U, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("brand", sa.String(128), nullable=True),
        sa.Column("manufacturer_enterprise_id", U, nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        uniques=(("uq_quality_product_identity", ("org_id", "category_id", "name", "model")),),
        indexes=("category_id", "name", "model", "brand", "manufacturer_enterprise_id"),
    )
    create(
        "product_identifiers",
        sa.Column("product_id", U, nullable=False),
        sa.Column("identifier_type", sa.String(32), nullable=False),
        sa.Column("identifier_value", sa.String(255), nullable=False),
        sa.Column("source_id", U, nullable=True),
        uniques=(("uq_product_identifier_source", ("org_id", "identifier_type", "identifier_value", "source_id")),),
        indexes=("product_id", "identifier_type", "identifier_value", "source_id"),
    )
    create(
        "enterprise_product_relations",
        sa.Column("enterprise_id", U, nullable=False),
        sa.Column("product_id", U, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=True),
        sa.Column("effective_to", sa.DateTime(), nullable=True),
        sa.Column("source_record_id", U, nullable=True),
        uniques=(("uq_enterprise_product_role", ("org_id", "enterprise_id", "product_id", "role", "effective_from")),),
        indexes=("enterprise_id", "product_id", "role", "source_record_id"),
    )
    create(
        "quality_data_sources",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("connector_type", sa.String(32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", U, nullable=False),
        uniques=(("uq_quality_source_code", ("org_id", "code")),),
        indexes=("source_type", "connector_type", "status"),
    )
    create(
        "quality_ingestion_jobs",
        sa.Column("source_id", U, nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("import_batch_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_by", U, nullable=False),
        uniques=(("uq_quality_ingestion_key", ("org_id", "request_key")),),
        indexes=("source_id", "import_batch_code", "status"),
    )
    create(
        "quality_attachments",
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("bucket", sa.String(128), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("uploaded_by", U, nullable=False),
        indexes=("sha256",),
    )
    create(
        "quality_source_records",
        sa.Column("source_id", U, nullable=False),
        sa.Column("ingestion_job_id", U, nullable=True),
        sa.Column("external_record_id", sa.String(255), nullable=True),
        sa.Column("record_type", sa.String(48), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("enterprise_ref", sa.JSON(), nullable=False),
        sa.Column("product_ref", sa.JSON(), nullable=False),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column("attachment_ids", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("authorization_scope", sa.String(64), nullable=False),
        sa.Column("data_nature", sa.String(32), nullable=False),
        sa.Column("normalization_status", sa.String(32), nullable=False),
        sa.Column("normalization_errors", sa.JSON(), nullable=False),
        sa.Column("created_by", U, nullable=False),
        uniques=(("uq_quality_source_content", ("org_id", "source_id", "content_hash")),),
        indexes=("source_id", "ingestion_job_id", "external_record_id", "record_type", "occurred_at", "content_hash", "normalization_status"),
    )
    create(
        "quality_evidence_items",
        sa.Column("evidence_code", sa.String(128), nullable=False),
        sa.Column("source_record_id", U, nullable=False),
        sa.Column("evidence_type", sa.String(48), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("structured_data", sa.JSON(), nullable=False),
        sa.Column("attachment_id", U, nullable=True),
        sa.Column("nature", sa.String(32), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        uniques=(("uq_quality_evidence_code", ("org_id", "evidence_code")),),
        indexes=("evidence_code", "source_record_id", "evidence_type", "attachment_id", "content_hash"),
    )
    create(
        "quality_risk_cases",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("source_record_ids", sa.JSON(), nullable=False),
        sa.Column("assigned_to", U, nullable=True),
        sa.Column("created_by", U, nullable=False),
        indexes=("code", "scope_type", "status", "assigned_to"),
    )
    create(
        "quality_risk_assessments",
        sa.Column("risk_case_id", U, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("risk_type", sa.String(128), nullable=True),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("standard_matches", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("possible_causes", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("trust_status", sa.String(32), nullable=False),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("model_versions", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=True),
        sa.Column("knowledge_snapshot_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("submitted_by", U, nullable=True),
        sa.Column("reviewed_by", U, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        uniques=(("uq_quality_risk_assessment_version", ("org_id", "risk_case_id", "version")),),
        indexes=("risk_case_id", "risk_type", "risk_level", "trust_status", "status"),
    )
    create(
        "quality_risk_policies",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", U, nullable=False),
        sa.Column("published_by", U, nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        uniques=(("uq_quality_risk_policy_version", ("org_id", "code", "version")),),
        indexes=("code", "status"),
    )
    create(
        "standard_execution_rules",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("standard_id", U, nullable=False),
        sa.Column("clause_ref", sa.String(255), nullable=False),
        sa.Column("page_ref", sa.String(64), nullable=True),
        sa.Column("category_id", U, nullable=True),
        sa.Column("product_id", U, nullable=True),
        sa.Column("indicator", sa.String(128), nullable=False),
        sa.Column("method", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("decision_action", sa.String(64), nullable=False),
        sa.Column("review_policy", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", U, nullable=False),
        sa.Column("reviewed_by", U, nullable=True),
        sa.Column("published_by", U, nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        uniques=(("uq_standard_execution_rule_version", ("org_id", "code", "version")),),
        indexes=("code", "standard_id", "category_id", "product_id", "status"),
    )
    create(
        "physical_samples",
        sa.Column("sampling_plan_id", U, nullable=False),
        sa.Column("product_id", U, nullable=True),
        sa.Column("production_batch_ref", sa.String(128), nullable=True),
        sa.Column("external_sample_code", sa.String(128), nullable=True),
        sa.Column("unit_serial_ref", sa.String(255), nullable=True),
        sa.Column("sampled_at", sa.DateTime(), nullable=True),
        sa.Column("sampling_location", sa.JSON(), nullable=False),
        sa.Column("custody_status", sa.String(32), nullable=False),
        indexes=("sampling_plan_id", "product_id", "external_sample_code", "custody_status"),
    )
    create(
        "quality_market_monitoring_reports",
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("input_versions", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_by", U, nullable=False),
    )
    create(
        "quality_public_opinion_reports",
        sa.Column("risk_case_id", U, nullable=True),
        sa.Column("input_versions", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_by", U, nullable=False),
        indexes=("risk_case_id",),
    )

    op.add_column("inspection_tasks", sa.Column("product_category_id", U, nullable=True))
    op.add_column("inspection_tasks", sa.Column("quality_product_id", U, nullable=True))
    op.create_index("ix_inspection_tasks_product_category_id", "inspection_tasks", ["product_category_id"])
    op.create_index("ix_inspection_tasks_quality_product_id", "inspection_tasks", ["quality_product_id"])
    op.add_column(
        "inspection_standard_libraries",
        sa.Column("applicable_category_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "inspection_standard_libraries",
        sa.Column("applicable_product_ids", sa.JSON(), nullable=True),
    )

def downgrade():
    op.drop_index("ix_inspection_tasks_quality_product_id", table_name="inspection_tasks")
    op.drop_index("ix_inspection_tasks_product_category_id", table_name="inspection_tasks")
    op.drop_column("inspection_tasks", "quality_product_id")
    op.drop_column("inspection_tasks", "product_category_id")
    op.drop_column("inspection_standard_libraries", "applicable_product_ids")
    op.drop_column("inspection_standard_libraries", "applicable_category_ids")
    for name in reversed((
        "quality_public_opinion_reports",
        "quality_market_monitoring_reports",
        "physical_samples",
        "standard_execution_rules",
        "quality_risk_policies",
        "quality_risk_assessments",
        "quality_risk_cases",
        "quality_evidence_items",
        "quality_source_records",
        "quality_attachments",
        "quality_ingestion_jobs",
        "quality_data_sources",
        "enterprise_product_relations",
        "product_identifiers",
        "quality_products",
        "product_categories",
    )):
        op.drop_table(name)
