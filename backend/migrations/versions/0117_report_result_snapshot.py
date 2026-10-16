"""Allow immutable report evidence bundles without TEXT truncation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision='0117_report_result_snapshot'
down_revision='0116_execution_review_evidence'
branch_labels=None
depends_on=None

def upgrade():
    op.alter_column('export_jobs','config_json',existing_type=sa.Text(),type_=LONGTEXT(),existing_nullable=True)

def downgrade():
    count=op.get_bind().execute(sa.text('SELECT COUNT(*) FROM export_jobs WHERE OCTET_LENGTH(config_json)>65535')).scalar_one()
    if count:raise RuntimeError('Large report snapshots exist; preserve them instead of truncating to TEXT')
    op.alter_column('export_jobs','config_json',existing_type=LONGTEXT(),type_=sa.Text(),existing_nullable=True)
