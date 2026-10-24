"""Durable, idempotent background risk analysis."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BINARY

revision='0118_risk_analysis_jobs'
down_revision='0117_report_result_snapshot'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('risk_analysis_jobs',
        sa.Column('id',BINARY(16),primary_key=True),sa.Column('org_id',BINARY(16),nullable=False),
        sa.Column('case_id',BINARY(16),sa.ForeignKey('quality_risk_cases.id'),nullable=False),
        sa.Column('created_by',BINARY(16),nullable=False),sa.Column('request_key',sa.String(36),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('basis_hash',sa.String(64),nullable=False),
        sa.Column('status',sa.String(32),nullable=False),sa.Column('claim_token',sa.String(36)),
        sa.Column('assessment_id',BINARY(16)),sa.Column('error_code',sa.String(48)),sa.Column('message',sa.String(500),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('started_at',sa.DateTime()),
        sa.Column('finished_at',sa.DateTime()),sa.Column('lease_until',sa.DateTime()),
        sa.UniqueConstraint('org_id','request_key',name='uq_risk_analysis_request'))
    for field in ('org_id','case_id'):op.create_index('ix_risk_analysis_jobs_'+field,'risk_analysis_jobs',[field])
    op.create_index('ix_risk_analysis_dispatch','risk_analysis_jobs',['status','created_at'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM risk_analysis_jobs')).scalar_one():
        raise RuntimeError('Preserve analysis job history before removing this table; do not silently discard requests')
    op.drop_table('risk_analysis_jobs')
