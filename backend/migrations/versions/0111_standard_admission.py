"""Versioned admission; legacy indexed resources remain unapproved."""
import json
import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY

revision = "0111_standard_admission"
down_revision = "0110_report_permissions"
branch_labels = depends_on = None


def upgrade():
    uid = BINARY(16)
    op.add_column("standard_documents", sa.Column("current_revision_id", uid, nullable=True))
    op.add_column("standard_documents", sa.Column("published_revision_id", uid, nullable=True))
    for name, default in [("processing_status", "pending"), ("review_status", "pending"), ("publication_status", "unpublished")]:
        op.add_column("standard_documents", sa.Column(name, sa.String(32), nullable=False, server_default=default))
    op.create_table("standard_document_revisions",
        sa.Column("id", uid, primary_key=True), sa.Column("document_id", uid, sa.ForeignKey("standard_documents.id"), nullable=False),
        sa.Column("org_id", uid, nullable=False), sa.Column("revision_no", sa.Integer, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False), sa.Column("file_hash", sa.String(64)),
        *[sa.Column(name, sa.String(32), nullable=False) for name in ["processing_status", "review_status", "publication_status", "extraction_status"]],
        *[sa.Column(name, sa.JSON, nullable=False) for name in ["pages_json", "candidates_json", "issues_json"]],
        sa.Column("row_version", sa.Integer, nullable=False), sa.Column("index_generation", sa.String(64)),
        *[sa.Column(name, uid) for name in ["created_by", "reviewed_by", "published_by"]],
        *[sa.Column(name, sa.DateTime) for name in ["created_at", "reviewed_at", "published_at"]],
        sa.UniqueConstraint("document_id", "revision_no"))
    op.create_index("ix_standard_revision_org", "standard_document_revisions", ["org_id"])
    op.create_index("ix_standard_revision_doc", "standard_document_revisions", ["document_id"])
    op.create_table("standard_admission_reviews",
        sa.Column("id", uid, primary_key=True), sa.Column("org_id", uid, nullable=False),
        sa.Column("revision_id", uid, sa.ForeignKey("standard_document_revisions.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False), sa.Column("actor_id", uid, nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False), sa.Column("evidence_refs", sa.JSON, nullable=False),
        sa.Column("detail_json", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("org_id", "request_key"))
    op.create_index("ix_standard_review_revision", "standard_admission_reviews", ["revision_id"])
    op.create_index("ix_standard_review_org", "standard_admission_reviews", ["org_id"])
    op.create_table("standard_sync_outbox",
        sa.Column("id", uid, primary_key=True), sa.Column("org_id", uid, nullable=False),
        sa.Column("revision_id", uid, sa.ForeignKey("standard_document_revisions.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False), sa.Column("generation", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error_message", sa.Text), sa.Column("next_attempt_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False), sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("revision_id", "action", "generation"))
    op.create_index("ix_standard_outbox_org", "standard_sync_outbox", ["org_id"])
    op.create_index("ix_standard_outbox_status", "standard_sync_outbox", ["status"])
    connection = op.get_bind()
    op.add_column("rag_spaces", sa.Column("resource_domain", sa.String(32), nullable=False, server_default="workspace"))
    libraries = connection.execute(sa.text("SELECT org_id, rag_space_ids FROM inspection_standard_libraries WHERE deleted_at IS NULL")).mappings()
    for library in list(libraries):
        space_ids = json.loads(library["rag_space_ids"]) if isinstance(library["rag_space_ids"], str) else library["rag_space_ids"]
        for space_id in space_ids or []:
            connection.execute(sa.text("UPDATE rag_spaces SET resource_domain='formal_standard' WHERE id=:id AND org_id=:org AND created_by IS NULL"),
                {"id":uuid.UUID(space_id).bytes,"org":library["org_id"]})
    # Keep original PDFs, chunks and vector IDs. Their old 'completed' is not admission.
    rows = connection.execute(sa.text("SELECT * FROM standard_documents WHERE deleted_at IS NULL")).mappings()
    revisions = sa.table("standard_document_revisions", *[
        sa.column(n, t) for n, t in [("id", uid), ("document_id", uid), ("org_id", uid), ("revision_no", sa.Integer),
        ("snapshot", sa.JSON), ("file_hash", sa.String), ("processing_status", sa.String), ("review_status", sa.String),
        ("publication_status", sa.String), ("extraction_status", sa.String), ("pages_json", sa.JSON),
        ("candidates_json", sa.JSON), ("issues_json", sa.JSON), ("row_version", sa.Integer), ("created_at", sa.DateTime)]])
    for row in list(rows):
        if row["org_id"] is None:
            continue  # Unknown namespace never becomes an unrestricted resource.
        rid = uuid.uuid4().bytes
        snapshot = {k: row[k] for k in ["standard_no", "standard_name", "domain", "product_category", "standard_level",
            "standard_status", "file_name", "file_path", "file_hash", "file_size"]}
        snapshot.update(resource_type="unverified", source_url="", publisher="", applicability={}, legacy=True)
        connection.execute(revisions.insert().values(id=rid, document_id=row["id"], org_id=row["org_id"], revision_no=1,
            snapshot=snapshot, file_hash=row["file_hash"], processing_status="pending", review_status="pending",
            publication_status="unpublished", extraction_status="pending", pages_json=[], candidates_json=[],
            issues_json=["历史资料须重新核对来源、类型与适用状态；旧索引不代表正式发布。"], row_version=1, created_at=row["created_at"]))
        connection.execute(sa.text("UPDATE standard_documents SET current_revision_id=:rid WHERE id=:id"), {"rid":rid,"id":row["id"]})
    roles = sa.table("role_permissions", sa.column("org_id", uid), sa.column("role", sa.String), sa.column("resources", sa.JSON), sa.column("version", sa.Integer))
    for row in connection.execute(sa.select(roles).where(roles.c.role == "expert")).mappings():
        resources = json.loads(row["resources"]) if isinstance(row["resources"], str) else list(row["resources"])
        if "inspection_standard_library_read" in resources:
            connection.execute(roles.update().where(roles.c.org_id==row["org_id"], roles.c.role=="expert").values(
                resources=sorted(set(resources) | {"standard_admission_submit", "standard_admission_review", "standard_admission_publish"}), version=row["version"]+1))


def downgrade():
    connection = op.get_bind()
    count = connection.execute(sa.text("SELECT COUNT(*) FROM standard_admission_reviews")).scalar()
    if count:
        raise RuntimeError("Admission history exists; preserve it and roll back application routing instead of dropping history.")
    for table in ["standard_sync_outbox", "standard_admission_reviews", "standard_document_revisions"]:
        op.drop_table(table)
    op.drop_column("rag_spaces", "resource_domain")
    for name in ["current_revision_id", "published_revision_id", "processing_status", "review_status", "publication_status"]:
        op.drop_column("standard_documents", name)
