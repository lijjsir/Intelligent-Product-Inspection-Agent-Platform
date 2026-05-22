from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import NotFoundError
from app.core.permissions import require_role
from app.schemas.algo_resources import (
    DatasetAlignmentPairCreateRequest,
    DatasetAugmentationProposalCreateRequest,
    DatasetExportRequest,
    DatasetKgEntityCreateRequest,
    DatasetKgRelationCreateRequest,
    DatasetProcessingRunRequest,
    EvaluationDatasetCreateRequest,
    EvaluationDatasetSampleAppendRequest,
    EvaluationDatasetUpdateRequest,
    ExperimentCreateRequest,
    ExperimentUpdateRequest,
    FineTuneRunCreateRequest,
    FineTuneRunUpdateRequest,
    ModelDeploymentCreateRequest,
    ModelDeploymentUpdateRequest,
    OfflineEvaluationCreateRequest,
    OfflineEvaluationUpdateRequest,
    OnlineValidationCreateRequest,
    OnlineValidationUpdateRequest,
    TrainingJobCreateRequest,
    TrainingJobUpdateRequest,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.algo_workspace_service import AlgoWorkspaceService


router = APIRouter()


def _svc(current: CurrentUser, db):
    require_role("algo_workspace", current.role)
    return AlgoWorkspaceService(db, current.org_id, current.user_id)


@router.post("/datasets/{dataset_id}/processing/kg/start", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def start_kg_run(
    dataset_id: str,
    payload: DatasetProcessingRunRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).launch_processing_run(dataset_id=dataset_id, processing_type="kg", payload=payload))


@router.get("/datasets/{dataset_id}/processing/kg/status", response_model=ResponseEnvelope)
async def get_kg_status(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_status(dataset_id=dataset_id, processing_type="kg"))


@router.get("/datasets/{dataset_id}/processing/kg/results", response_model=ResponseEnvelope)
async def get_kg_results(
    dataset_id: str,
    entity_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_results(dataset_id=dataset_id, processing_type="kg", entity_type=entity_type, keyword=keyword))


@router.post("/datasets/{dataset_id}/processing/kg/subgraph", response_model=ResponseEnvelope)
async def get_kg_subgraph(
    dataset_id: str,
    payload: dict[str, str | None],
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_subgraph(dataset_id=dataset_id, entity_type=payload.get("entity_type"), keyword=payload.get("keyword")))


@router.post("/datasets/{dataset_id}/processing/kg/entities", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_kg_entity(
    dataset_id: str,
    payload: DatasetKgEntityCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).create_kg_entity(dataset_id=dataset_id, payload=payload))


@router.delete("/datasets/{dataset_id}/processing/kg/entities/{entity_id}", response_model=ResponseEnvelope)
async def delete_kg_entity(
    dataset_id: str,
    entity_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    await _svc(current, db).delete_kg_entity(entity_id=entity_id)
    return ResponseEnvelope(data={"deleted": True, "dataset_id": dataset_id})


@router.post("/datasets/{dataset_id}/processing/kg/relations", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_kg_relation(
    dataset_id: str,
    payload: DatasetKgRelationCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).create_kg_relation(dataset_id=dataset_id, payload=payload))


@router.delete("/datasets/{dataset_id}/processing/kg/relations/{relation_id}", response_model=ResponseEnvelope)
async def delete_kg_relation(
    dataset_id: str,
    relation_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    await _svc(current, db).delete_kg_relation(relation_id=relation_id)
    return ResponseEnvelope(data={"deleted": True, "dataset_id": dataset_id})


@router.post("/datasets/{dataset_id}/processing/alignment/start", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def start_alignment_run(
    dataset_id: str,
    payload: DatasetProcessingRunRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).launch_processing_run(dataset_id=dataset_id, processing_type="alignment", payload=payload))


@router.get("/datasets/{dataset_id}/processing/alignment/status", response_model=ResponseEnvelope)
async def get_alignment_status(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_status(dataset_id=dataset_id, processing_type="alignment"))


@router.get("/datasets/{dataset_id}/processing/alignment/results", response_model=ResponseEnvelope)
async def get_alignment_results(
    dataset_id: str,
    min_score: float | None = Query(default=None),
    only_confirmed: bool | None = Query(default=None),
    sample_id: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_results(dataset_id=dataset_id, processing_type="alignment", min_score=min_score, only_confirmed=only_confirmed, sample_id=sample_id))


@router.post("/datasets/{dataset_id}/processing/alignment/pairs", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_alignment_pair(
    dataset_id: str,
    payload: DatasetAlignmentPairCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).create_alignment_pair(dataset_id=dataset_id, payload=payload))


@router.post("/datasets/{dataset_id}/processing/alignment/pairs/{pair_id}/confirm", response_model=ResponseEnvelope)
async def confirm_alignment_pair(
    dataset_id: str,
    pair_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).confirm_alignment_pair(dataset_id=dataset_id, pair_id=pair_id))


@router.delete("/datasets/{dataset_id}/processing/alignment/pairs/{pair_id}", response_model=ResponseEnvelope)
async def delete_alignment_pair(
    dataset_id: str,
    pair_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    await _svc(current, db).delete_alignment_pair(pair_id=pair_id)
    return ResponseEnvelope(data={"deleted": True, "dataset_id": dataset_id})


@router.post("/datasets/{dataset_id}/processing/augmentation/start", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def start_augmentation_run(
    dataset_id: str,
    payload: DatasetProcessingRunRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).launch_processing_run(dataset_id=dataset_id, processing_type="augmentation", payload=payload))


@router.get("/datasets/{dataset_id}/processing/augmentation/status", response_model=ResponseEnvelope)
async def get_augmentation_status(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_status(dataset_id=dataset_id, processing_type="augmentation"))


@router.get("/datasets/{dataset_id}/processing/augmentation/results", response_model=ResponseEnvelope)
async def get_augmentation_results(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_results(dataset_id=dataset_id, processing_type="augmentation"))


@router.post("/datasets/{dataset_id}/processing/augmentation/proposals", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_augmentation_proposal(
    dataset_id: str,
    payload: DatasetAugmentationProposalCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).create_augmentation_proposal(dataset_id=dataset_id, payload=payload))


@router.delete("/datasets/{dataset_id}/processing/augmentation/proposals/{proposal_id}", response_model=ResponseEnvelope)
async def delete_augmentation_proposal(
    dataset_id: str,
    proposal_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    await _svc(current, db).delete_augmentation_proposal(proposal_id=proposal_id)
    return ResponseEnvelope(data={"deleted": True, "dataset_id": dataset_id})


@router.post("/datasets/{dataset_id}/processing/augmentation/apply", response_model=ResponseEnvelope)
async def apply_augmentation(
    dataset_id: str,
    payload: dict[str, list[str]],
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).apply_augmentation(dataset_id=dataset_id, proposal_ids=list(payload.get("proposal_ids") or [])))


@router.get("/datasets/{dataset_id}/processing/augmentation/history", response_model=ResponseEnvelope)
async def get_augmentation_history(
    dataset_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).get_augmentation_history(dataset_id=dataset_id))


@router.post("/datasets/{dataset_id}/exports", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_dataset_export(
    dataset_id: str,
    payload: DatasetExportRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).create_export(dataset_id=dataset_id, payload=payload))


@router.get("/datasets/{dataset_id}/exports/status", response_model=ResponseEnvelope)
async def get_dataset_export_status(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_status(dataset_id=dataset_id, processing_type="export"))


@router.get("/datasets/{dataset_id}/exports/results", response_model=ResponseEnvelope)
async def get_dataset_export_results(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_processing_results(dataset_id=dataset_id, processing_type="export"))


@router.get("/datasets/{dataset_id}/exports/download")
async def download_dataset_export(dataset_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    service = _svc(current, db)
    artifact = await service.get_export_artifact_download(dataset_id=dataset_id)
    payload = service.get_export_artifact_payload(
        bucket=artifact["bucket"],
        object_key=artifact["object_key"],
        storage_backend=artifact.get("storage_backend"),
    )
    if payload is None:
        raise NotFoundError("export artifact payload not found")
    content, content_type = payload
    return Response(
        content=content,
        media_type=content_type or "application/json",
        headers={"Content-Disposition": f'attachment; filename="{artifact["file_name"]}"'},
    )


@router.get("/eval-datasets", response_model=ResponseEnvelope)
async def list_eval_datasets(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="evaluation_dataset", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/eval-datasets", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_eval_dataset(payload: EvaluationDatasetCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_evaluation_dataset(payload))


@router.get("/eval-datasets/{resource_id}", response_model=ResponseEnvelope)
async def get_eval_dataset(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="evaluation_dataset", resource_id=resource_id))


@router.get("/eval-datasets/{resource_id}/samples", response_model=ResponseEnvelope)
async def list_eval_dataset_samples(
    resource_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=24, ge=1, le=100),
    sample_type: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_evaluation_dataset_items(resource_id=resource_id, page=page, size=size, sample_type=sample_type))


@router.post("/eval-datasets/{resource_id}/samples", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def append_eval_dataset_samples(
    resource_id: str,
    payload: EvaluationDatasetSampleAppendRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).append_evaluation_dataset_items(resource_id=resource_id, payload=payload))


@router.delete("/eval-datasets/{resource_id}/samples/{item_id}", response_model=ResponseEnvelope)
async def delete_eval_dataset_sample_item(
    resource_id: str,
    item_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    await _svc(current, db).delete_evaluation_dataset_item(resource_id=resource_id, item_id=item_id)
    return ResponseEnvelope(data={"deleted": True})


@router.patch("/eval-datasets/{resource_id}", response_model=ResponseEnvelope)
async def update_eval_dataset(resource_id: str, payload: EvaluationDatasetUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_evaluation_dataset(resource_id, payload))


@router.delete("/eval-datasets/{resource_id}", response_model=ResponseEnvelope)
async def delete_eval_dataset(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_generic_resource(resource_type="evaluation_dataset", resource_id=resource_id)
    return ResponseEnvelope(data={"deleted": True})


@router.get("/training-jobs", response_model=ResponseEnvelope)
async def list_training_jobs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="training_job", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/training-jobs", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_training_job(payload: TrainingJobCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_training_job(payload))


@router.get("/training-jobs/{resource_id}", response_model=ResponseEnvelope)
async def get_training_job(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="training_job", resource_id=resource_id))


@router.patch("/training-jobs/{resource_id}", response_model=ResponseEnvelope)
async def update_training_job(resource_id: str, payload: TrainingJobUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_training_job(resource_id, payload))


@router.post("/training-jobs/{resource_id}/launch", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def launch_training_job(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).launch_training_job(resource_id))


@router.post("/training-jobs/{resource_id}/cancel", response_model=ResponseEnvelope)
async def cancel_training_job(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).cancel_training_job(resource_id))


@router.delete("/training-jobs/{resource_id}", response_model=ResponseEnvelope)
async def delete_training_job(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_training_job(resource_id)
    return ResponseEnvelope(data={"deleted": True})


@router.get("/fine-tunes", response_model=ResponseEnvelope)
async def list_fine_tunes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="fine_tune", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/fine-tunes", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_fine_tune(payload: FineTuneRunCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_fine_tune(payload))


@router.get("/fine-tunes/{resource_id}", response_model=ResponseEnvelope)
async def get_fine_tune(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="fine_tune", resource_id=resource_id))


@router.patch("/fine-tunes/{resource_id}", response_model=ResponseEnvelope)
async def update_fine_tune(resource_id: str, payload: FineTuneRunUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_fine_tune(resource_id, payload))


@router.post("/fine-tunes/{resource_id}/launch", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def launch_fine_tune(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).launch_generic_resource(resource_type="fine_tune", resource_id=resource_id))


@router.post("/fine-tunes/{resource_id}/cancel", response_model=ResponseEnvelope)
async def cancel_fine_tune(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).cancel_generic_resource(resource_type="fine_tune", resource_id=resource_id))


@router.delete("/fine-tunes/{resource_id}", response_model=ResponseEnvelope)
async def delete_fine_tune(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_generic_resource(resource_type="fine_tune", resource_id=resource_id)
    return ResponseEnvelope(data={"deleted": True})


@router.get("/offline-evaluations", response_model=ResponseEnvelope)
async def list_offline_evaluations(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="offline_evaluation", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/offline-evaluations", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_offline_evaluation(payload: OfflineEvaluationCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_offline_evaluation(payload))


@router.get("/offline-evaluations/{resource_id}", response_model=ResponseEnvelope)
async def get_offline_evaluation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="offline_evaluation", resource_id=resource_id))


@router.patch("/offline-evaluations/{resource_id}", response_model=ResponseEnvelope)
async def update_offline_evaluation(resource_id: str, payload: OfflineEvaluationUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_offline_evaluation(resource_id, payload))


@router.post("/offline-evaluations/{resource_id}/launch", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def launch_offline_evaluation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).launch_generic_resource(resource_type="offline_evaluation", resource_id=resource_id))


@router.post("/offline-evaluations/{resource_id}/cancel", response_model=ResponseEnvelope)
async def cancel_offline_evaluation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).cancel_generic_resource(resource_type="offline_evaluation", resource_id=resource_id))


@router.delete("/offline-evaluations/{resource_id}", response_model=ResponseEnvelope)
async def delete_offline_evaluation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_generic_resource(resource_type="offline_evaluation", resource_id=resource_id)
    return ResponseEnvelope(data={"deleted": True})


@router.get("/online-validations", response_model=ResponseEnvelope)
async def list_online_validations(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="online_validation", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/online-validations", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_online_validation(payload: OnlineValidationCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_online_validation(payload))


@router.get("/online-validations/{resource_id}", response_model=ResponseEnvelope)
async def get_online_validation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="online_validation", resource_id=resource_id))


@router.patch("/online-validations/{resource_id}", response_model=ResponseEnvelope)
async def update_online_validation(resource_id: str, payload: OnlineValidationUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_online_validation(resource_id, payload))


@router.post("/online-validations/{resource_id}/launch", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def launch_online_validation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).launch_generic_resource(resource_type="online_validation", resource_id=resource_id))


@router.post("/online-validations/{resource_id}/cancel", response_model=ResponseEnvelope)
async def cancel_online_validation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).cancel_generic_resource(resource_type="online_validation", resource_id=resource_id))


@router.delete("/online-validations/{resource_id}", response_model=ResponseEnvelope)
async def delete_online_validation(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_generic_resource(resource_type="online_validation", resource_id=resource_id)
    return ResponseEnvelope(data={"deleted": True})


@router.get("/experiments", response_model=ResponseEnvelope)
async def list_experiments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="experiment", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/experiments", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_experiment(payload: ExperimentCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_experiment(payload))


@router.get("/experiments/{resource_id}", response_model=ResponseEnvelope)
async def get_experiment(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="experiment", resource_id=resource_id))


@router.patch("/experiments/{resource_id}", response_model=ResponseEnvelope)
async def update_experiment(resource_id: str, payload: ExperimentUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_experiment(resource_id, payload))


@router.delete("/experiments/{resource_id}", response_model=ResponseEnvelope)
async def delete_experiment(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_generic_resource(resource_type="experiment", resource_id=resource_id)
    return ResponseEnvelope(data={"deleted": True})


@router.get("/deployments", response_model=ResponseEnvelope)
async def list_deployments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).list_generic_resources(resource_type="deployment", page=page, size=size, keyword=keyword, status=status_text))


@router.post("/deployments", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_deployment(payload: ModelDeploymentCreateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).create_deployment(payload))


@router.get("/deployments/{resource_id}", response_model=ResponseEnvelope)
async def get_deployment(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_generic_resource(resource_type="deployment", resource_id=resource_id))


@router.patch("/deployments/{resource_id}", response_model=ResponseEnvelope)
async def update_deployment(resource_id: str, payload: ModelDeploymentUpdateRequest, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).update_deployment(resource_id, payload))


@router.post("/deployments/{resource_id}/launch", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def launch_deployment(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).launch_generic_resource(resource_type="deployment", resource_id=resource_id))


@router.post("/deployments/{resource_id}/cancel", response_model=ResponseEnvelope)
async def cancel_deployment(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).cancel_generic_resource(resource_type="deployment", resource_id=resource_id))


@router.delete("/deployments/{resource_id}", response_model=ResponseEnvelope)
async def delete_deployment(resource_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_generic_resource(resource_type="deployment", resource_id=resource_id)
    return ResponseEnvelope(data={"deleted": True})
