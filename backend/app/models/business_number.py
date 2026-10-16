from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class BusinessNumberSequence(Base):
    __tablename__ = "business_number_sequences"

    org_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(2), primary_key=True)
    business_date: Mapped[object] = mapped_column(Date, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class BusinessIdentifier(Base):
    __tablename__ = "business_identifiers"
    __table_args__ = (UniqueConstraint("org_id", "display_no", name="uq_business_display_no"),)

    org_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    entity_kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    display_no: Mapped[str] = mapped_column(String(20), nullable=False)
