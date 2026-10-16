"""Distinguish products with the same name/model but different brands or manufacturers."""
from alembic import op
import sqlalchemy as sa

revision = "0108_quality_product_identity"
down_revision = "0107_quality_production_batches"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint("uq_quality_product_identity", "quality_products", type_="unique")
    op.create_unique_constraint("uq_quality_product_identity", "quality_products",
        ["org_id", "category_id", "name", "model", "brand", "manufacturer_enterprise_id"])


def downgrade():
    duplicates = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM (SELECT 1 FROM quality_products WHERE model IS NOT NULL GROUP BY org_id, category_id, name, model HAVING COUNT(*) > 1) AS conflicts"))
    if duplicates:
        raise RuntimeError("不同品牌或企业存在同名同型号产品，不能回退为原产品唯一约束")
    op.drop_constraint("uq_quality_product_identity", "quality_products", type_="unique")
    op.create_unique_constraint("uq_quality_product_identity", "quality_products", ["org_id", "category_id", "name", "model"])
