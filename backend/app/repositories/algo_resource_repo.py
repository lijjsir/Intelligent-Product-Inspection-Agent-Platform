from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.algo_resources import (
    DatasetAlignment,
    DatasetAlignmentPair,
    DatasetAugmentationBatch,
    DatasetAugmentationProposal,
    DatasetExport,
    DatasetKgEntity,
    DatasetKgRelation,
    DatasetKnowledgeGraph,
    EvaluationDataset,
    EvaluationDatasetItem,
    Experiment,
    FineTuneRun,
    ModelDeployment,
    OfflineEvaluation,
    OnlineValidation,
    TrainingJob,
)


RESOURCE_MODEL_MAP: dict[str, Any] = {
    "evaluation_dataset": EvaluationDataset,
    "training_job": TrainingJob,
    "fine_tune": FineTuneRun,
    "offline_evaluation": OfflineEvaluation,
    "online_validation": OnlineValidation,
    "experiment": Experiment,
    "deployment": ModelDeployment,
}

PROCESSING_MODEL_MAP: dict[str, Any] = {
    "kg": DatasetKnowledgeGraph,
    "alignment": DatasetAlignment,
    "augmentation": DatasetAugmentationBatch,
    "export": DatasetExport,
}


class AlgoResourceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, model, payload: dict):
        obj = model(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def list_for_owner(
        self,
        *,
        model,
        org_id: str,
        owner_user_id: str,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
        extra_filters: list[Any] | None = None,
    ):
        conditions = [
            model.org_id == org_id,
            model.created_by == owner_user_id,
            model.deleted_at.is_(None),
        ]
        if keyword:
            like = f"%{keyword}%"
            conditions.append(model.name.ilike(like))
        if status:
            conditions.append(model.status == status)
        if extra_filters:
            conditions.extend(extra_filters)

        total = int(
            (
                await self._session.execute(
                    select(func.count(model.id)).where(*conditions)
                )
            ).scalar_one()
            or 0
        )

        rows = (
            (
                await self._session.execute(
                    select(model)
                    .where(*conditions)
                    .order_by(model.updated_at.desc(), model.created_at.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def get(self, *, model, org_id: str, resource_id: str, owner_user_id: str):
        result = await self._session.execute(
            select(model).where(
                model.id == resource_id,
                model.org_id == org_id,
                model.created_by == owner_user_id,
                model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def save(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def soft_delete(self, obj):
        obj.deleted_at = func.now()
        await self._session.flush()
        return obj

    async def count(self, *, model, org_id: str, owner_user_id: str, extra_filters: list[Any] | None = None) -> int:
        conditions = [
            model.org_id == org_id,
            model.created_by == owner_user_id,
            model.deleted_at.is_(None),
        ]
        if extra_filters:
            conditions.extend(extra_filters)
        total = await self._session.execute(select(func.count(model.id)).where(*conditions))
        return int(total.scalar_one() or 0)


class EvaluationDatasetItemRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_items(
        self,
        *,
        org_id: str,
        evaluation_dataset_id: str,
        created_by: str,
        page: int,
        size: int,
        sample_type: str | None = None,
    ):
        conditions = [
            EvaluationDatasetItem.org_id == org_id,
            EvaluationDatasetItem.evaluation_dataset_id == evaluation_dataset_id,
            EvaluationDatasetItem.created_by == created_by,
            EvaluationDatasetItem.deleted_at.is_(None),
        ]
        if sample_type:
            conditions.append(
                func.json_unquote(func.json_extract(EvaluationDatasetItem.payload_json, "$.sample_type")) == sample_type
            )

        total = await self._session.execute(select(func.count(EvaluationDatasetItem.id)).where(*conditions))
        rows = (
            (
                await self._session.execute(
                    select(EvaluationDatasetItem)
                    .where(*conditions)
                    .order_by(EvaluationDatasetItem.item_order.asc(), EvaluationDatasetItem.created_at.asc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total.scalar_one() or 0)

    async def list_items_all(
        self,
        *,
        org_id: str,
        evaluation_dataset_id: str,
        created_by: str,
    ) -> list[EvaluationDatasetItem]:
        rows = (
            (
                await self._session.execute(
                    select(EvaluationDatasetItem).where(
                        EvaluationDatasetItem.org_id == org_id,
                        EvaluationDatasetItem.evaluation_dataset_id == evaluation_dataset_id,
                        EvaluationDatasetItem.created_by == created_by,
                        EvaluationDatasetItem.deleted_at.is_(None),
                    ).order_by(EvaluationDatasetItem.item_order.asc(), EvaluationDatasetItem.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def get_item(
        self,
        *,
        org_id: str,
        evaluation_dataset_id: str,
        item_id: str,
        created_by: str,
    ) -> EvaluationDatasetItem | None:
        result = await self._session.execute(
            select(EvaluationDatasetItem).where(
                EvaluationDatasetItem.id == item_id,
                EvaluationDatasetItem.org_id == org_id,
                EvaluationDatasetItem.evaluation_dataset_id == evaluation_dataset_id,
                EvaluationDatasetItem.created_by == created_by,
                EvaluationDatasetItem.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def replace_items(
        self,
        *,
        org_id: str,
        evaluation_dataset_id: str,
        source_dataset_id: str,
        created_by: str,
        items: list[dict[str, Any]],
    ) -> None:
        existing = (
            (
                await self._session.execute(
                    select(EvaluationDatasetItem).where(
                        EvaluationDatasetItem.org_id == org_id,
                        EvaluationDatasetItem.evaluation_dataset_id == evaluation_dataset_id,
                        EvaluationDatasetItem.created_by == created_by,
                        EvaluationDatasetItem.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in existing:
            row.deleted_at = func.now()
        for index, item_payload in enumerate(items):
            item = EvaluationDatasetItem(
                org_id=org_id,
                evaluation_dataset_id=evaluation_dataset_id,
                source_dataset_id=source_dataset_id,
                dataset_sample_id=item_payload.get("dataset_sample_id"),
                created_by=created_by,
                item_order=index,
                payload_json=item_payload.get("payload_json") or {},
            )
            self._session.add(item)
        await self._session.flush()

    async def append_items(
        self,
        *,
        org_id: str,
        evaluation_dataset_id: str,
        source_dataset_id: str,
        created_by: str,
        items: list[dict[str, Any]],
    ) -> None:
        existing = await self.list_items_all(
            org_id=org_id,
            evaluation_dataset_id=evaluation_dataset_id,
            created_by=created_by,
        )
        max_order = max((row.item_order for row in existing), default=-1)
        for offset, item_payload in enumerate(items, start=1):
            self._session.add(
                EvaluationDatasetItem(
                    org_id=org_id,
                    evaluation_dataset_id=evaluation_dataset_id,
                    source_dataset_id=source_dataset_id,
                    dataset_sample_id=item_payload.get("dataset_sample_id"),
                    created_by=created_by,
                    item_order=max_order + offset,
                    payload_json=item_payload.get("payload_json") or {},
                )
            )
        await self._session.flush()

    async def count_items(self, *, org_id: str, evaluation_dataset_id: str, created_by: str) -> int:
        total = await self._session.execute(
            select(func.count(EvaluationDatasetItem.id)).where(
                EvaluationDatasetItem.org_id == org_id,
                EvaluationDatasetItem.evaluation_dataset_id == evaluation_dataset_id,
                EvaluationDatasetItem.created_by == created_by,
                EvaluationDatasetItem.deleted_at.is_(None),
            )
        )
        return int(total.scalar_one() or 0)

    async def soft_delete(self, obj: EvaluationDatasetItem) -> None:
        obj.deleted_at = func.now()
        await self._session.flush()

    async def soft_delete_many(self, *, org_id: str, evaluation_dataset_id: str, created_by: str) -> None:
        rows = await self.list_items_all(
            org_id=org_id,
            evaluation_dataset_id=evaluation_dataset_id,
            created_by=created_by,
        )
        for row in rows:
            row.deleted_at = func.now()
        await self._session.flush()


class DatasetProcessingEntityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_entities(self, *, org_id: str, knowledge_graph_id: str, created_by: str):
        rows = (
            (
                await self._session.execute(
                    select(DatasetKgEntity).where(
                        DatasetKgEntity.org_id == org_id,
                        DatasetKgEntity.knowledge_graph_id == knowledge_graph_id,
                        DatasetKgEntity.created_by == created_by,
                        DatasetKgEntity.deleted_at.is_(None),
                    ).order_by(DatasetKgEntity.updated_at.desc(), DatasetKgEntity.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_entity(self, payload: dict):
        obj = DatasetKgEntity(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get_entity(self, *, org_id: str, entity_id: str, created_by: str):
        result = await self._session.execute(
            select(DatasetKgEntity).where(
                DatasetKgEntity.id == entity_id,
                DatasetKgEntity.org_id == org_id,
                DatasetKgEntity.created_by == created_by,
                DatasetKgEntity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete_entity(self, obj):
        obj.deleted_at = func.now()
        await self._session.flush()

    async def list_relations(self, *, org_id: str, knowledge_graph_id: str, created_by: str):
        rows = (
            (
                await self._session.execute(
                    select(DatasetKgRelation).where(
                        DatasetKgRelation.org_id == org_id,
                        DatasetKgRelation.knowledge_graph_id == knowledge_graph_id,
                        DatasetKgRelation.created_by == created_by,
                        DatasetKgRelation.deleted_at.is_(None),
                    ).order_by(DatasetKgRelation.updated_at.desc(), DatasetKgRelation.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_relation(self, payload: dict):
        obj = DatasetKgRelation(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get_relation(self, *, org_id: str, relation_id: str, created_by: str):
        result = await self._session.execute(
            select(DatasetKgRelation).where(
                DatasetKgRelation.id == relation_id,
                DatasetKgRelation.org_id == org_id,
                DatasetKgRelation.created_by == created_by,
                DatasetKgRelation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete_relation(self, obj):
        obj.deleted_at = func.now()
        await self._session.flush()


class DatasetAlignmentPairRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_pairs(self, *, org_id: str, alignment_id: str, created_by: str):
        rows = (
            (
                await self._session.execute(
                    select(DatasetAlignmentPair).where(
                        DatasetAlignmentPair.org_id == org_id,
                        DatasetAlignmentPair.alignment_id == alignment_id,
                        DatasetAlignmentPair.created_by == created_by,
                        DatasetAlignmentPair.deleted_at.is_(None),
                    ).order_by(DatasetAlignmentPair.updated_at.desc(), DatasetAlignmentPair.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def list_pairs_filtered(
        self,
        *,
        org_id: str,
        alignment_id: str,
        created_by: str,
        min_score: float | None = None,
        only_confirmed: bool | None = None,
        sample_id: str | None = None,
    ):
        conditions = [
            DatasetAlignmentPair.org_id == org_id,
            DatasetAlignmentPair.alignment_id == alignment_id,
            DatasetAlignmentPair.created_by == created_by,
            DatasetAlignmentPair.deleted_at.is_(None),
        ]
        if min_score is not None:
            conditions.append(DatasetAlignmentPair.similarity_score >= min_score)
        if only_confirmed:
            conditions.append(DatasetAlignmentPair.confirmation_status == "confirmed")
        if sample_id:
            conditions.append(
                (DatasetAlignmentPair.source_sample_id == sample_id)
                | (DatasetAlignmentPair.target_sample_id == sample_id)
            )
        rows = (
            (
                await self._session.execute(
                    select(DatasetAlignmentPair).where(*conditions).order_by(DatasetAlignmentPair.updated_at.desc(), DatasetAlignmentPair.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_pair(self, payload: dict):
        obj = DatasetAlignmentPair(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def update_pair(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get_pair(self, *, org_id: str, pair_id: str, created_by: str):
        result = await self._session.execute(
            select(DatasetAlignmentPair).where(
                DatasetAlignmentPair.id == pair_id,
                DatasetAlignmentPair.org_id == org_id,
                DatasetAlignmentPair.created_by == created_by,
                DatasetAlignmentPair.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete_pair(self, obj):
        obj.deleted_at = func.now()
        await self._session.flush()


class DatasetAugmentationProposalRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_proposals(self, *, org_id: str, batch_id: str, created_by: str):
        rows = (
            (
                await self._session.execute(
                    select(DatasetAugmentationProposal).where(
                        DatasetAugmentationProposal.org_id == org_id,
                        DatasetAugmentationProposal.batch_id == batch_id,
                        DatasetAugmentationProposal.created_by == created_by,
                        DatasetAugmentationProposal.deleted_at.is_(None),
                    ).order_by(DatasetAugmentationProposal.updated_at.desc(), DatasetAugmentationProposal.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def list_history(self, *, org_id: str, dataset_id: str, created_by: str):
        rows = (
            (
                await self._session.execute(
                    select(DatasetAugmentationProposal).where(
                        DatasetAugmentationProposal.org_id == org_id,
                        DatasetAugmentationProposal.dataset_id == dataset_id,
                        DatasetAugmentationProposal.created_by == created_by,
                        DatasetAugmentationProposal.deleted_at.is_(None),
                    ).order_by(DatasetAugmentationProposal.updated_at.desc(), DatasetAugmentationProposal.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_proposal(self, payload: dict):
        obj = DatasetAugmentationProposal(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def update_proposal(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get_proposal(self, *, org_id: str, proposal_id: str, created_by: str):
        result = await self._session.execute(
            select(DatasetAugmentationProposal).where(
                DatasetAugmentationProposal.id == proposal_id,
                DatasetAugmentationProposal.org_id == org_id,
                DatasetAugmentationProposal.created_by == created_by,
                DatasetAugmentationProposal.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete_proposal(self, obj):
        obj.deleted_at = func.now()
        await self._session.flush()
