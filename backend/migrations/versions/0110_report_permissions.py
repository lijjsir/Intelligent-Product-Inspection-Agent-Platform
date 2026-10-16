"""Give report operations their own permissions while preserving old access."""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY

revision = "0110_report_permissions"
down_revision = "0109_category_basis"
branch_labels = depends_on = None
REPORT_KEYS = {"report_generate", "report_read"}
REPORT_ROLES = {"admin", "user", "expert", "platform_operator"}


def _decode(value):
    return json.loads(value) if isinstance(value, str) else value


def _update(upgrading):
    connection = op.get_bind()
    roles = sa.table("role_permissions", sa.column("org_id", BINARY(16)), sa.column("role", sa.String(32)),
                     sa.column("resources", sa.JSON()), sa.column("version", sa.Integer()))
    personal = sa.table("user_permissions", sa.column("org_id", BINARY(16)), sa.column("user_id", BINARY(16)),
                        sa.column("overrides", sa.JSON()), sa.column("version", sa.Integer()))
    users = sa.table("users", sa.column("id", BINARY(16)), sa.column("org_id", BINARY(16)), sa.column("role", sa.String(32)))
    for row in connection.execute(sa.select(roles).with_for_update()).mappings():
        old = set(_decode(row["resources"]) or [])
        new = set(old)
        if upgrading and row["role"] in REPORT_ROLES and {"feedback", "task", "result"} <= old:
            new |= REPORT_KEYS
        elif not upgrading:
            new -= REPORT_KEYS
        if new != old:
            connection.execute(roles.update().where(roles.c.org_id == row["org_id"], roles.c.role == row["role"]).values(
                resources=sorted(new), version=row["version"] + 1))
    statement = sa.select(personal, users.c.role.label("assigned_role")).join(users,
        sa.and_(users.c.id == personal.c.user_id, users.c.org_id == personal.c.org_id)).with_for_update()
    for row in connection.execute(statement).mappings():
        old = dict(_decode(row["overrides"]) or {})
        new = dict(old)
        if upgrading and row["assigned_role"] in REPORT_ROLES and old.get("feedback") in {"grant", "deny"}:
            for key in REPORT_KEYS:
                new.setdefault(key, old["feedback"])
        elif not upgrading:
            new = {key: value for key, value in old.items() if key not in REPORT_KEYS}
        if new != old:
            connection.execute(personal.update().where(personal.c.org_id == row["org_id"], personal.c.user_id == row["user_id"]).values(
                overrides=new, version=row["version"] + 1))


def upgrade():
    _update(True)


def downgrade():
    _update(False)
