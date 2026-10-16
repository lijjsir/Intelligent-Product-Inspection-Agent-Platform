from sqlalchemy import DateTime,ForeignKey,Integer,JSON,String,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.core.ids import uuid7
from app.core.datetime import utcnow
from app.models.base import Base,UUIDBinary


class InspectionPolicyPublication(Base):
    __tablename__="inspection_policy_publications"
    __table_args__=(UniqueConstraint("org_id","request_key"),)
    id:Mapped[str]=mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id:Mapped[str]=mapped_column(UUIDBinary,index=True)
    spec_id:Mapped[str]=mapped_column(UUIDBinary,index=True)
    request_key:Mapped[str]=mapped_column(String(128))
    payload_hash:Mapped[str]=mapped_column(String(64))
    snapshot:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(32),default="published")
    published_by:Mapped[str]=mapped_column(UUIDBinary)
    created_at:Mapped[object]=mapped_column(DateTime,default=utcnow)


class InspectionExecutionRun(Base):
    __tablename__="inspection_execution_runs"
    __table_args__=(UniqueConstraint("org_id","request_key"),)
    id:Mapped[str]=mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id:Mapped[str]=mapped_column(UUIDBinary,index=True)
    task_id:Mapped[str]=mapped_column(UUIDBinary,ForeignKey("inspection_tasks.id"),index=True)
    session_id:Mapped[str|None]=mapped_column(UUIDBinary,nullable=True)
    request_key:Mapped[str]=mapped_column(String(128))
    payload_hash:Mapped[str]=mapped_column(String(64))
    snapshot:Mapped[dict]=mapped_column(JSON)
    evaluation:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(32),default="draft")
    row_version:Mapped[int]=mapped_column(Integer,default=1)
    created_by:Mapped[str]=mapped_column(UUIDBinary)
    reviewed_by:Mapped[str|None]=mapped_column(UUIDBinary,nullable=True)
    created_at:Mapped[object]=mapped_column(DateTime,default=utcnow)
    reviewed_at:Mapped[object|None]=mapped_column(DateTime,nullable=True)


class InspectionExecutionAction(Base):
    __tablename__="inspection_execution_actions"
    __table_args__=(UniqueConstraint("org_id","request_key"),)
    id:Mapped[str]=mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id:Mapped[str]=mapped_column(UUIDBinary,index=True)
    run_id:Mapped[str]=mapped_column(UUIDBinary,ForeignKey("inspection_execution_runs.id"),index=True)
    actor_id:Mapped[str]=mapped_column(UUIDBinary)
    request_key:Mapped[str]=mapped_column(String(128))
    payload_hash:Mapped[str]=mapped_column(String(64))
    action:Mapped[str]=mapped_column(String(32))
    reason:Mapped[str]=mapped_column(Text)
    evidence_refs:Mapped[list|None]=mapped_column(JSON(none_as_null=True),nullable=True)
    verification_snapshot:Mapped[dict|None]=mapped_column(JSON(none_as_null=True),nullable=True)
    created_at:Mapped[object]=mapped_column(DateTime,default=utcnow)
