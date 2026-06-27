"""product batch standard closure

Revision ID: 0078_product_batch_standard_closure
Revises: 0077_remove_meeting_room_type
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary


revision = "0078_product_batch_standard_closure"
down_revision = "0077_remove_meeting_room_type"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return index_name in {index["name"] for index in _inspector().get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("product_lines"):
        op.create_table(
            "product_lines",
            sa.Column("id", UUIDBinary(length=16), nullable=False),
            sa.Column("org_id", UUIDBinary(length=16), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_product_lines_org_id", "product_lines", ["org_id"])
    _create_index_if_missing("ix_product_lines_code", "product_lines", ["code"])
    _create_index_if_missing("ux_product_lines_org_code_active", "product_lines", ["org_id", "code", "deleted_at"], unique=True)

    if not _has_table("product_skus"):
        op.create_table(
            "product_skus",
            sa.Column("id", UUIDBinary(length=16), nullable=False),
            sa.Column("org_id", UUIDBinary(length=16), nullable=False),
            sa.Column("product_line_id", UUIDBinary(length=16), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_product_skus_org_id", "product_skus", ["org_id"])
    _create_index_if_missing("ix_product_skus_product_line_id", "product_skus", ["product_line_id"])
    _create_index_if_missing("ix_product_skus_code", "product_skus", ["code"])
    _create_index_if_missing("ux_product_skus_org_code_active", "product_skus", ["org_id", "code", "deleted_at"], unique=True)

    if not _has_table("product_batches"):
        op.create_table(
            "product_batches",
            sa.Column("id", UUIDBinary(length=16), nullable=False),
            sa.Column("org_id", UUIDBinary(length=16), nullable=False),
            sa.Column("product_sku_id", UUIDBinary(length=16), nullable=False),
            sa.Column("batch_no", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("production_date", sa.Date(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_product_batches_org_id", "product_batches", ["org_id"])
    _create_index_if_missing("ix_product_batches_product_sku_id", "product_batches", ["product_sku_id"])
    _create_index_if_missing("ix_product_batches_batch_no", "product_batches", ["batch_no"])
    _create_index_if_missing("ux_product_batches_sku_batch_active", "product_batches", ["product_sku_id", "batch_no", "deleted_at"], unique=True)

    _add_column_if_missing("inspection_standard_libraries", sa.Column("inspection_spec_id", UUIDBinary(length=16), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("spec_code", sa.String(length=64), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("applicable_product_line_ids", mysql.JSON(), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("applicable_product_sku_ids", mysql.JSON(), nullable=True))
    _create_index_if_missing(
        "ix_inspection_standard_libraries_inspection_spec_id",
        "inspection_standard_libraries",
        ["inspection_spec_id"],
        unique=False,
    )
    _create_index_if_missing("ix_inspection_standard_libraries_spec_code", "inspection_standard_libraries", ["spec_code"])

    _add_column_if_missing("inspection_tasks", sa.Column("product_sku_id", UUIDBinary(length=16), nullable=True))
    _add_column_if_missing("inspection_tasks", sa.Column("batch_id", UUIDBinary(length=16), nullable=True))
    _add_column_if_missing("inspection_tasks", sa.Column("inspection_standard_id", UUIDBinary(length=16), nullable=True))
    _create_index_if_missing("ix_inspection_tasks_product_sku_id", "inspection_tasks", ["product_sku_id"])
    _create_index_if_missing("ix_inspection_tasks_batch_id", "inspection_tasks", ["batch_id"])
    _create_index_if_missing("ix_inspection_tasks_inspection_standard_id", "inspection_tasks", ["inspection_standard_id"])

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT IGNORE INTO product_lines
          (id, org_id, code, name, description, is_active, created_at, updated_at)
        SELECT UNHEX(REPLACE(UUID(), '-', '')), t.org_id, t.product_id, t.product_id,
               '由历史检测任务的产品编号自动创建。', 1, NOW(3), NOW(3)
        FROM inspection_tasks t
        WHERE t.deleted_at IS NULL AND COALESCE(t.product_id, '') <> ''
        GROUP BY t.org_id, t.product_id
        """
    ))
    conn.execute(sa.text(
        """
        INSERT IGNORE INTO product_skus
          (id, org_id, product_line_id, code, name, description, is_active, created_at, updated_at)
        SELECT UNHEX(REPLACE(UUID(), '-', '')), t.org_id, pl.id, t.product_id, t.product_id,
               '由历史检测任务的产品编号自动创建。', 1, NOW(3), NOW(3)
        FROM inspection_tasks t
        JOIN product_lines pl
          ON pl.org_id = t.org_id
         AND CONVERT(pl.code USING utf8mb4) COLLATE utf8mb4_unicode_ci
             = CONVERT(t.product_id USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND pl.deleted_at IS NULL
        WHERE t.deleted_at IS NULL AND COALESCE(t.product_id, '') <> ''
        GROUP BY t.org_id, pl.id, t.product_id
        """
    ))
    conn.execute(sa.text(
        """
        INSERT IGNORE INTO product_batches
          (id, org_id, product_sku_id, batch_no, name, description, is_active, created_at, updated_at)
        SELECT UNHEX(REPLACE(UUID(), '-', '')), ps.org_id, ps.id, 'UNSPECIFIED', '未指定批次',
               '为没有批次号的历史任务自动创建的兼容批次。', 1, NOW(3), NOW(3)
        FROM product_skus ps
        WHERE ps.deleted_at IS NULL
        GROUP BY ps.org_id, ps.id
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE inspection_tasks t
        JOIN product_skus ps
          ON ps.org_id = t.org_id
         AND CONVERT(ps.code USING utf8mb4) COLLATE utf8mb4_unicode_ci
             = CONVERT(t.product_id USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND ps.deleted_at IS NULL
        JOIN product_batches pb
          ON pb.org_id = t.org_id AND pb.product_sku_id = ps.id AND pb.batch_no = 'UNSPECIFIED' AND pb.deleted_at IS NULL
        SET t.product_sku_id = ps.id, t.batch_id = pb.id
        WHERE t.deleted_at IS NULL AND t.product_sku_id IS NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE inspection_standard_libraries isl
        JOIN inspection_specs spec
          ON spec.org_id = isl.org_id
         AND spec.deleted_at IS NULL
         AND spec.is_active = 1
         AND (
              CONVERT(spec.spec_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
              = CONVERT(isl.product_family USING utf8mb4) COLLATE utf8mb4_unicode_ci
           OR CONVERT(spec.product_family USING utf8mb4) COLLATE utf8mb4_unicode_ci
              = CONVERT(isl.product_family USING utf8mb4) COLLATE utf8mb4_unicode_ci
           OR CONVERT(spec.product_id USING utf8mb4) COLLATE utf8mb4_unicode_ci
              = CONVERT(isl.product_family USING utf8mb4) COLLATE utf8mb4_unicode_ci
         )
        SET isl.inspection_spec_id = spec.id,
            isl.spec_code = spec.spec_code
        WHERE isl.deleted_at IS NULL
          AND isl.inspection_spec_id IS NULL
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO inspection_standard_libraries
          (id, org_id, name, product_family, inspection_spec_id, spec_code,
           applicable_product_line_ids, applicable_product_sku_ids,
           description, rag_space_ids, is_active, created_at, updated_at)
        SELECT UNHEX(REPLACE(UUID(), '-', '')),
               spec.org_id,
               spec.name,
               COALESCE(NULLIF(spec.product_family, ''), NULLIF(spec.product_id, ''), spec.spec_code),
               spec.id,
               spec.spec_code,
               JSON_ARRAY(),
               JSON_ARRAY(),
               'Auto-created from existing inspection spec during product/batch/standard closure migration.',
               JSON_ARRAY(),
               spec.is_active,
               NOW(3),
               NOW(3)
        FROM inspection_specs spec
        LEFT JOIN inspection_standard_libraries isl
          ON isl.org_id = spec.org_id
         AND isl.deleted_at IS NULL
         AND (
              isl.inspection_spec_id = spec.id
           OR CONVERT(isl.spec_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
              = CONVERT(spec.spec_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
         )
        WHERE spec.deleted_at IS NULL
          AND spec.org_id IS NOT NULL
          AND isl.id IS NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE inspection_tasks t
        JOIN inspection_standard_libraries isl
          ON isl.org_id = t.org_id
         AND (
              CONVERT(isl.spec_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
              = CONVERT(t.spec_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
           OR CONVERT(isl.product_family USING utf8mb4) COLLATE utf8mb4_unicode_ci
              = CONVERT(t.product_id USING utf8mb4) COLLATE utf8mb4_unicode_ci
         )
         AND isl.deleted_at IS NULL
         AND isl.is_active = 1
        SET t.inspection_standard_id = isl.id
        WHERE t.deleted_at IS NULL AND t.inspection_standard_id IS NULL
        """
    ))


def downgrade() -> None:
    op.drop_index("ix_inspection_tasks_inspection_standard_id", table_name="inspection_tasks")
    op.drop_index("ix_inspection_tasks_batch_id", table_name="inspection_tasks")
    op.drop_index("ix_inspection_tasks_product_sku_id", table_name="inspection_tasks")
    op.drop_column("inspection_tasks", "inspection_standard_id")
    op.drop_column("inspection_tasks", "batch_id")
    op.drop_column("inspection_tasks", "product_sku_id")

    op.drop_index("ix_inspection_standard_libraries_spec_code", table_name="inspection_standard_libraries")
    op.drop_index("ix_inspection_standard_libraries_inspection_spec_id", table_name="inspection_standard_libraries")
    op.drop_column("inspection_standard_libraries", "applicable_product_sku_ids")
    op.drop_column("inspection_standard_libraries", "applicable_product_line_ids")
    op.drop_column("inspection_standard_libraries", "spec_code")
    op.drop_column("inspection_standard_libraries", "inspection_spec_id")

    op.drop_index("ux_product_batches_sku_batch_active", table_name="product_batches")
    op.drop_index("ix_product_batches_batch_no", table_name="product_batches")
    op.drop_index("ix_product_batches_product_sku_id", table_name="product_batches")
    op.drop_index("ix_product_batches_org_id", table_name="product_batches")
    op.drop_table("product_batches")

    op.drop_index("ux_product_skus_org_code_active", table_name="product_skus")
    op.drop_index("ix_product_skus_code", table_name="product_skus")
    op.drop_index("ix_product_skus_product_line_id", table_name="product_skus")
    op.drop_index("ix_product_skus_org_id", table_name="product_skus")
    op.drop_table("product_skus")

    op.drop_index("ux_product_lines_org_code_active", table_name="product_lines")
    op.drop_index("ix_product_lines_code", table_name="product_lines")
    op.drop_index("ix_product_lines_org_id", table_name="product_lines")
    op.drop_table("product_lines")
