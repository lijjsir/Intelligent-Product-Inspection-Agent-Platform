from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class RolePermission(Base):
    __tablename__ = "role_permissions"

    org_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    resources: Mapped[list] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class UserPermission(Base):
    __tablename__ = "user_permissions"

    org_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    overrides: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
