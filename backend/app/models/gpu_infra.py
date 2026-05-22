from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


class GpuComputeNode(Base, TimestampMixin):
    __tablename__ = "gpu_compute_nodes"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_username: Mapped[str] = mapped_column(String(128), nullable=False)
    ssh_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_private_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    available_gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gpu_bitmap: Mapped[str] = mapped_column(String(255), nullable=False, default="0")
    cpu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="offline")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    load_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GpuJobLease(Base, TimestampMixin):
    __tablename__ = "gpu_job_leases"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    node_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    gpu_indices: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="leased")
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
