"""Quality supervision records, authorization and measurement input."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BINARY

revision = "0100_quality_supervision"
down_revision = "0099_memory_transfer_knowledge_tunnel"
branch_labels = depends_on = None

# Frozen column definitions; no imports from mutable application models.
TABLES = {
    "supervision_records": [
        ("kind", "s32"),
        ("code", "s128"),
        ("name", "s255"),
        ("status", "s32"),
        ("version", "i"),
        ("created_by", "u"),
        ("assigned_to", "u?"),
        ("data", "j"),
        ("created_at", "d"),
        ("updated_at", "d"),
    ],
    "supervision_revisions": [
        ("record_id", "u"),
        ("version", "b"),
        ("actor_id", "u"),
        ("action", "s64"),
        ("snapshot", "j"),
        ("created_at", "d"),
    ],
    "device_connections": [
        ("device_id", "u"),
        ("token_hash", "s64"),
        ("status", "s16"),
        ("created_at", "d"),
    ],
    "measurement_batches": [
        ("session_id", "u"),
        ("source_key", "s128"),
        ("content_hash", "s64"),
        ("raw", "j"),
        ("created_at", "d"),
    ],
    "measurement_records": [
        ("session_id", "u"),
        ("sample_id", "u"),
        ("device_id", "u"),
        ("event_id", "s128"),
        ("content_hash", "s64"),
        ("data", "j"),
        ("created_at", "d"),
    ],
    "supervision_runs": [
        ("record_id", "u"),
        ("input_version", "i"),
        ("request_key", "s128"),
        ("agent", "s40"),
        ("status", "s32"),
        ("iteration", "i"),
        ("snapshot", "j"),
        ("output", "j?"),
        ("error", "t?"),
        ("created_by", "u"),
        ("created_at", "d"),
        ("updated_at", "d"),
    ],
    "business_reviews": [
        ("record_id", "u"),
        ("version", "i"),
        ("operation", "s32"),
        ("status", "s32"),
        ("requester_id", "u"),
        ("reviewer_id", "u?"),
        ("comment", "t?"),
        ("created_at", "d"),
        ("reviewed_at", "d?"),
    ],
    "supervision_dependencies": [
        ("source_id", "u"),
        ("source_version", "i"),
        ("target_id", "u"),
        ("target_version", "i"),
    ],
}
UNIQUES = {
    "supervision_records": ("uq_supervision_code", ["org_id", "kind", "code"]),
    "supervision_revisions": ("uq_supervision_revision", ["record_id", "version"]),
    "device_connections": ("uq_device_token", ["token_hash"]),
    "measurement_batches": ("uq_measurement_source", ["org_id", "session_id", "source_key"]),
    "measurement_records": ("uq_measurement_event", ["org_id", "session_id", "event_id"]),
    "supervision_runs": ("uq_supervision_run_key", ["org_id", "request_key"]),
    "business_reviews": ("uq_business_review", ["org_id", "record_id", "version", "operation"]),
    "supervision_dependencies": (
        "uq_supervision_dependency",
        ["org_id", "source_id", "source_version", "target_id", "target_version"],
    ),
}


def upgrade():
    for table, fields in TABLES.items():
        columns = [
            sa.Column("id", BINARY(16), primary_key=True),
            sa.Column("org_id", BINARY(16), nullable=False),
        ]
        for name, spec in fields:
            nullable = spec.endswith("?")
            code = spec.rstrip("?")
            type_ = (
                sa.String(int(code[1:]))
                if code.startswith("s")
                else {
                    "u": BINARY(16),
                    "i": sa.Integer(),
                    "b": sa.BigInteger(),
                    "j": sa.JSON(),
                    "d": sa.DateTime(),
                    "t": sa.Text(),
                }[code]
            )
            columns.append(sa.Column(name, type_, nullable=nullable))
        uname, keys = UNIQUES[table]
        op.create_table(table, *columns, sa.UniqueConstraint(*keys, name=uname))
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        indexes = {
            "supervision_records": ["kind", "status"],
            "supervision_revisions": ["record_id"],
            "device_connections": ["device_id"],
            "measurement_batches": ["session_id"],
            "measurement_records": ["session_id", "sample_id", "device_id"],
            "supervision_runs": ["record_id", "status"],
            "business_reviews": ["record_id", "status"],
            "supervision_dependencies": ["source_id", "target_id"],
        }
        for column in indexes[table]:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.add_column("product_skus", sa.Column("supervision_data", sa.JSON(), nullable=True))
    op.add_column("product_batches", sa.Column("quantity", sa.Integer(), nullable=True))
    op.add_column(
        "inspection_standard_libraries", sa.Column("applicability", sa.JSON(), nullable=True)
    )


def downgrade():
    op.drop_column("inspection_standard_libraries", "applicability")
    op.drop_column("product_batches", "quantity")
    op.drop_column("product_skus", "supervision_data")
    for table in reversed(TABLES):
        op.drop_table(table)
