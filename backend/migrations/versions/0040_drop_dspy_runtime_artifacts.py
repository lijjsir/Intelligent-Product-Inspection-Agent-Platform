"""drop retired optimization tables

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    for table_name in (
        "dspy_optimization_runs",
        "dspy_optimization_configs",
        "prompt_dspy_configs",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    # Retired tables are intentionally not recreated.
    pass
