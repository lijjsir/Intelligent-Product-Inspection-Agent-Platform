import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, Column, Integer, LargeBinary, MetaData, String, Table, create_engine, select


def test_report_migration_preserves_legacy_role_and_personal_access():
    path = Path(__file__).parents[1] / "migrations/versions/0110_report_permissions.py"
    spec = importlib.util.spec_from_file_location("report_permission_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    metadata = MetaData()
    roles = Table("role_permissions", metadata, Column("org_id", LargeBinary(16)), Column("role", String), Column("resources", JSON), Column("version", Integer))
    personal = Table("user_permissions", metadata, Column("org_id", LargeBinary(16)), Column("user_id", LargeBinary(16)), Column("overrides", JSON), Column("version", Integer))
    users = Table("users", metadata, Column("id", LargeBinary(16)), Column("org_id", LargeBinary(16)), Column("role", String))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(roles.insert(), [
            {"org_id": b"o" * 16, "role": "user", "resources": ["task", "result", "feedback"], "version": 1},
            {"org_id": b"o" * 16, "role": "expert", "resources": ["task", "result"], "version": 1},
        ])
        connection.execute(users.insert(), {"id": b"u" * 16, "org_id": b"o" * 16, "role": "user"})
        connection.execute(personal.insert(), {"user_id": b"u" * 16, "org_id": b"o" * 16, "overrides": {"feedback": "deny"}, "version": 1})
        module.op = SimpleNamespace(get_bind=lambda: connection)
        module.upgrade()
        records = {row.role: row.resources for row in connection.execute(select(roles))}
        assert {"report_generate", "report_read"} <= set(records["user"])
        assert "report_read" not in records["expert"]
        overrides = connection.execute(select(personal.c.overrides)).scalar_one()
        assert overrides == {"feedback": "deny", "report_generate": "deny", "report_read": "deny"}
        module.downgrade()
        assert connection.execute(select(personal.c.overrides)).scalar_one() == {"feedback": "deny"}
    engine.dispose()
