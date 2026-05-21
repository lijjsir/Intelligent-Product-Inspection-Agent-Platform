from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class AlgoResourceMixin:
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AlgoExecutionMixin:
    execution_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    executor_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class DatasetKnowledgeGraph(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "dataset_knowledge_graphs"

    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)


class DatasetKgEntity(Base, TimestampMixin):
    __tablename__ = "dataset_kg_entities"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    knowledge_graph_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="Entity")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class DatasetKgRelation(Base, TimestampMixin):
    __tablename__ = "dataset_kg_relations"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    knowledge_graph_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    source_entity_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_entity_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="RELATED_TO")
    properties_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class DatasetAlignment(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "dataset_alignments"

    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)


class DatasetAlignmentPair(Base, TimestampMixin):
    __tablename__ = "dataset_alignment_pairs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    alignment_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    source_sample_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    target_sample_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="describes")
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="suggested")


class DatasetAugmentationBatch(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "dataset_augmentation_batches"

    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    history_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DatasetAugmentationProposal(Base, TimestampMixin):
    __tablename__ = "dataset_augmentation_proposals"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    batch_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_sample_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    augmentation_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    augmentation_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DatasetExport(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "dataset_exports"

    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)


class EvaluationDataset(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "evaluation_datasets"

    source_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)


class EvaluationDatasetItem(Base, TimestampMixin):
    __tablename__ = "evaluation_dataset_items"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    evaluation_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_sample_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    item_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TrainingJob(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "training_jobs"

    source_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    model_config_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    eval_set_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class FineTuneRun(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "fine_tune_runs"

    training_job_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    model_config_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class OfflineEvaluation(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "offline_evaluations"

    eval_set_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, default="training_job")
    target_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class OnlineValidation(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "online_validations"

    deployment_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class Experiment(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "experiments"

    pass


class ModelDeployment(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "model_deployments"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="fine_tune")
    source_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
