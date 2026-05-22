from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from agent.rag.embedder import Embedder, EmbeddingModelNotConfigured
from app.repositories.algo_resource_repo import (
    DatasetAlignmentPairRepository,
    DatasetAugmentationProposalRepository,
    DatasetProcessingEntityRepository,
)
from app.repositories.dataset_repo import DatasetRepository, DatasetSampleRepository
from app.services.object_storage.base import ObjectStorage


DEFECT_TERMS = {
    "scratch": "划痕",
    "划痕": "划痕",
    "dent": "凹陷",
    "凹陷": "凹陷",
    "crack": "裂纹",
    "裂纹": "裂纹",
    "污点": "污点",
    "stain": "污点",
    "burn": "烧伤",
    "烧伤": "烧伤",
}

PART_TERMS = {
    "screen": "屏幕",
    "panel": "面板",
    "cover": "盖板",
    "lens": "镜头",
    "housing": "外壳",
    "外壳": "外壳",
    "屏幕": "屏幕",
    "镜头": "镜头",
    "边框": "边框",
}

PROCESS_TERMS = {
    "inspect": "检测",
    "inspection": "检测",
    "assembly": "装配",
    "repair": "返修",
    "polish": "抛光",
    "检测": "检测",
    "装配": "装配",
    "返修": "返修",
    "清洗": "清洗",
}

ATTRIBUTE_TERMS = {
    "color": "颜色",
    "尺寸": "尺寸",
    "size": "尺寸",
    "brightness": "亮度",
    "亮度": "亮度",
    "颜色": "颜色",
    "dark": "偏暗",
    "bright": "偏亮",
}

ENTITY_REPLACEMENTS = {
    "划痕": "轻微划痕",
    "凹陷": "局部凹陷",
    "裂纹": "细小裂纹",
    "屏幕": "显示屏",
    "外壳": "机身外壳",
    "污点": "表面污点",
}


@dataclass
class ProcessingDeps:
    org_id: str
    user_id: str
    datasets: DatasetRepository
    samples: DatasetSampleRepository
    kg_repo: DatasetProcessingEntityRepository
    pair_repo: DatasetAlignmentPairRepository
    proposal_repo: DatasetAugmentationProposalRepository
    storage: ObjectStorage


class AlgoProcessingService:
    def __init__(self, deps: ProcessingDeps):
        self._deps = deps

    async def run_kg_build(self, *, dataset_id: str, resource_id: str, config_json: dict[str, Any] | None = None) -> dict[str, Any]:
        samples = await self._deps.samples.list_for_dataset_all(
            org_id=self._deps.org_id,
            dataset_id=dataset_id,
            owner_user_id=self._deps.user_id,
        )
        existing_entities = await self._deps.kg_repo.list_entities(
            org_id=self._deps.org_id,
            knowledge_graph_id=resource_id,
            created_by=self._deps.user_id,
        )
        existing_relations = await self._deps.kg_repo.list_relations(
            org_id=self._deps.org_id,
            knowledge_graph_id=resource_id,
            created_by=self._deps.user_id,
        )

        for row in existing_relations:
            if (row.properties_json or {}).get("source") != "manual":
                await self._deps.kg_repo.delete_relation(row)
        for row in existing_entities:
            if (row.properties_json or {}).get("source") != "manual":
                await self._deps.kg_repo.delete_entity(row)

        entity_defs: dict[str, dict[str, Any]] = {}
        relation_defs: set[tuple[str, str, str]] = set()
        warnings: list[str] = []

        relation_rules = list((config_json or {}).get("relation_rules") or [])
        for sample in samples:
            sample_key = f"sample::{sample.id}"
            entity_defs[sample_key] = {
                "name": sample.sample_name or sample.id,
                "entity_type": "Sample",
                "description": f"样本 {sample.id}",
                "properties_json": {
                    "source": "auto",
                    "sample_id": sample.id,
                    "sample_type": sample.sample_type,
                },
                "confidence": 1.0,
            }
            extracted_terms = self._extract_terms(sample, config_json=config_json)
            for entity_type, term in extracted_terms:
                entity_key = f"{entity_type.lower()}::{term}"
                entity_defs.setdefault(
                    entity_key,
                    {
                        "name": term,
                        "entity_type": entity_type,
                        "description": f"规则抽取自样本 {sample.sample_name or sample.id}",
                        "properties_json": {"source": "auto"},
                        "confidence": 0.82,
                    },
                )
                relation_defs.add((sample_key, entity_key, f"MENTIONS_{entity_type.upper()}"))
            relation_defs.update(self._build_rule_relations(sample_key, extracted_terms, relation_rules))

        created_entities: dict[str, Any] = {}
        for key, payload in entity_defs.items():
            created_entities[key] = await self._deps.kg_repo.create_entity(
                {
                    "org_id": self._deps.org_id,
                    "dataset_id": dataset_id,
                    "knowledge_graph_id": resource_id,
                    "created_by": self._deps.user_id,
                    **payload,
                }
            )

        for source_key, target_key, relation_type in sorted(relation_defs):
            source = created_entities.get(source_key)
            target = created_entities.get(target_key)
            if source is None or target is None:
                warnings.append(f"skipped relation {relation_type} for missing entity")
                continue
            await self._deps.kg_repo.create_relation(
                {
                    "org_id": self._deps.org_id,
                    "dataset_id": dataset_id,
                    "knowledge_graph_id": resource_id,
                    "created_by": self._deps.user_id,
                    "source_entity_id": source.id,
                    "target_entity_id": target.id,
                    "relation_type": relation_type,
                    "properties_json": {"source": "auto"},
                    "confidence": 0.8,
                }
            )

        stats = {
            "samples": len(samples),
            "entities": len(entity_defs),
            "relations": len(relation_defs),
            "entity_types": dict(Counter(item["entity_type"] for item in entity_defs.values())),
        }
        return self._build_summary(
            processing_type="kg",
            current_stats=stats,
            warnings=warnings,
            extra={"entities": [], "relations": []},
        )

    async def run_alignment_build(
        self,
        *,
        dataset_id: str,
        resource_id: str,
        config_json: dict[str, Any] | None,
        embedding_model: dict[str, Any] | None,
    ) -> dict[str, Any]:
        samples = await self._deps.samples.list_for_dataset_all(
            org_id=self._deps.org_id,
            dataset_id=dataset_id,
            owner_user_id=self._deps.user_id,
        )
        image_samples = [sample for sample in samples if sample.sample_type == "image"]
        text_samples = [sample for sample in samples if sample.sample_type == "text"]
        existing_pairs = await self._deps.pair_repo.list_pairs(
            org_id=self._deps.org_id,
            alignment_id=resource_id,
            created_by=self._deps.user_id,
        )
        for row in existing_pairs:
            if row.confirmation_status != "confirmed":
                await self._deps.pair_repo.delete_pair(row)

        threshold = float((config_json or {}).get("threshold") or 0.72)
        top_k = int((config_json or {}).get("top_k") or 3)
        mutual_check = bool((config_json or {}).get("mutual_check", True))

        image_desc = {sample.id: self._describe_image_sample(sample) for sample in image_samples}
        text_desc = {sample.id: self._describe_text_sample(sample) for sample in text_samples}
        degraded_mode = embedding_model is None
        degraded_reason = None
        vectors: dict[str, list[float]] = {}

        if embedding_model is not None:
            try:
                embedder = Embedder(org_id=self._deps.org_id)
                for sample_id, text in {**image_desc, **text_desc}.items():
                    vectors[sample_id] = await embedder.embed((text or sample_id)[:4000])
            except EmbeddingModelNotConfigured as exc:
                degraded_mode = True
                degraded_reason = str(exc)
        else:
            degraded_reason = "no active embedding model configured"

        forward: dict[str, list[tuple[float, str]]] = {}
        reverse: dict[str, list[tuple[float, str]]] = {}

        for image_id, image_text in image_desc.items():
            scored: list[tuple[float, str]] = []
            for text_id, text_text in text_desc.items():
                if degraded_mode:
                    score = self._token_overlap(image_text, text_text)
                else:
                    score = self._cosine_similarity(vectors.get(image_id) or [], vectors.get(text_id) or [])
                if score >= threshold:
                    scored.append((score, text_id))
            forward[image_id] = sorted(scored, reverse=True)[:top_k]

        for text_id, text_text in text_desc.items():
            scored: list[tuple[float, str]] = []
            for image_id, image_text in image_desc.items():
                if degraded_mode:
                    score = self._token_overlap(text_text, image_text)
                else:
                    score = self._cosine_similarity(vectors.get(text_id) or [], vectors.get(image_id) or [])
                if score >= threshold:
                    scored.append((score, image_id))
            reverse[text_id] = sorted(scored, reverse=True)[:top_k]

        pair_count = 0
        for image_id, candidates in forward.items():
            for score, text_id in candidates:
                if mutual_check and image_id not in {target for _, target in reverse.get(text_id, [])}:
                    continue
                await self._deps.pair_repo.create_pair(
                    {
                        "org_id": self._deps.org_id,
                        "dataset_id": dataset_id,
                        "alignment_id": resource_id,
                        "created_by": self._deps.user_id,
                        "source_sample_id": image_id,
                        "target_sample_id": text_id,
                        "relation_type": "describes",
                        "similarity_score": round(score, 6),
                        "payload_json": {
                            "alignment_method": "embedding" if not degraded_mode else "token_overlap",
                            "source_text": image_desc.get(image_id),
                            "target_text": text_desc.get(text_id),
                            "mutual_check": mutual_check,
                            "degraded_mode": degraded_mode,
                        },
                        "confirmation_status": "suggested",
                    }
                )
                pair_count += 1

        return self._build_summary(
            processing_type="alignment",
            current_stats={
                "image_samples": len(image_samples),
                "text_samples": len(text_samples),
                "pairs": pair_count,
                "threshold": threshold,
                "top_k": top_k,
            },
            warnings=[degraded_reason] if degraded_reason else [],
            degraded_mode=degraded_mode,
            degraded_reason=degraded_reason,
            extra={"pairs": []},
        )

    async def run_augmentation_build(self, *, dataset_id: str, resource_id: str) -> dict[str, Any]:
        samples = await self._deps.samples.list_for_dataset_all(
            org_id=self._deps.org_id,
            dataset_id=dataset_id,
            owner_user_id=self._deps.user_id,
        )
        text_samples = [sample for sample in samples if sample.sample_type == "text" and (sample.text_content or "").strip()]
        existing = await self._deps.proposal_repo.list_proposals(
            org_id=self._deps.org_id,
            batch_id=resource_id,
            created_by=self._deps.user_id,
        )
        for row in existing:
            await self._deps.proposal_repo.delete_proposal(row)

        proposals = 0
        for sample in text_samples:
            base_text = (sample.text_content or "").strip()
            substitution_text = self._entity_substitution(base_text)
            relation_text = self._relation_inference(base_text)
            for method, text in (
                ("entity_substitution", substitution_text),
                ("relation_inference", relation_text),
            ):
                if not text or text == base_text:
                    continue
                await self._deps.proposal_repo.create_proposal(
                    {
                        "org_id": self._deps.org_id,
                        "dataset_id": dataset_id,
                        "batch_id": resource_id,
                        "created_by": self._deps.user_id,
                        "name": f"{method}-{sample.sample_name or sample.id}"[:255],
                        "description": text[:2000],
                        "status": "draft",
                        "config_json": {"source_sample_id": sample.id},
                        "result_summary": {"preview_text": text[:200], "source_text": base_text[:200]},
                        "source_sample_id": sample.id,
                        "augmentation_method": method,
                        "augmentation_params": {"source_sample_id": sample.id},
                    }
                )
                proposals += 1

        return self._build_summary(
            processing_type="augmentation",
            current_stats={"text_samples": len(text_samples), "proposals": proposals},
            warnings=[],
            extra={"proposals": []},
        )

    async def run_export_build(
        self,
        *,
        dataset_id: str,
        resource_id: str,
        dataset: Any,
        config_json: dict[str, Any] | None,
        alignment_resource_id: str | None,
    ) -> dict[str, Any]:
        samples = await self._deps.samples.list_for_dataset_all(
            org_id=self._deps.org_id,
            dataset_id=dataset_id,
            owner_user_id=self._deps.user_id,
        )
        include_augmented = bool((config_json or {}).get("include_augmented", True))
        only_confirmed = bool((config_json or {}).get("only_confirmed_alignment"))
        if not include_augmented:
            samples = [sample for sample in samples if not getattr(sample, "is_augmented", False)]

        train_ratio = float((config_json or {}).get("train_ratio") or 0.7)
        val_ratio = float((config_json or {}).get("val_ratio") or 0.15)
        test_ratio = float((config_json or {}).get("test_ratio") or 0.15)
        if round(train_ratio + val_ratio + test_ratio, 6) != 1.0:
            raise ValueError("train_ratio + val_ratio + test_ratio must equal 1")

        pairs: list[Any] = []
        if alignment_resource_id:
            pairs = await self._deps.pair_repo.list_pairs_filtered(
                org_id=self._deps.org_id,
                alignment_id=alignment_resource_id,
                created_by=self._deps.user_id,
                only_confirmed=only_confirmed,
            )

        ordered_samples = sorted(samples, key=lambda item: (item.created_at or 0, item.id))
        split_indexes = self._split_counts(len(ordered_samples), train_ratio, val_ratio)
        split_map: dict[str, str] = {}
        for index, sample in enumerate(ordered_samples):
            if index < split_indexes[0]:
                split_map[sample.id] = "train"
            elif index < split_indexes[1]:
                split_map[sample.id] = "val"
            else:
                split_map[sample.id] = "test"

        payload = {
            "dataset": {"id": dataset.id, "name": dataset.name, "modality": dataset.modality},
            "split": {"train": train_ratio, "val": val_ratio, "test": test_ratio},
            "records": [
                {
                    "id": sample.id,
                    "split": split_map[sample.id],
                    "sample_type": sample.sample_type,
                    "sample_name": sample.sample_name,
                    "text_content": sample.text_content,
                    "file_url": sample.file_url,
                    "annotation_data": sample.annotation_data,
                    "source_metadata": sample.source_metadata,
                    "is_augmented": bool(getattr(sample, "is_augmented", False)),
                }
                for sample in ordered_samples
            ],
            "alignments": [
                {
                    "id": row.id,
                    "source_sample_id": row.source_sample_id,
                    "target_sample_id": row.target_sample_id,
                    "relation_type": row.relation_type,
                    "similarity_score": row.similarity_score,
                    "confirmation_status": row.confirmation_status,
                }
                for row in pairs
            ],
        }
        artifact_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        manifest = {
            "dataset_id": dataset_id,
            "resource_id": resource_id,
            "format": "vlm-json",
            "sample_count": len(ordered_samples),
            "alignment_count": len(pairs),
        }
        bucket = "dataset-exports"
        object_key = f"dataset-exports/{self._deps.org_id}/{dataset_id}/{resource_id}/vlm.json"
        manifest_key = f"dataset-exports/{self._deps.org_id}/{dataset_id}/{resource_id}/manifest.json"
        self._deps.storage.ensure_bucket(bucket)
        artifact_result = self._deps.storage.put_bytes(
            bucket=bucket,
            object_key=object_key,
            data=artifact_bytes,
            content_type="application/json",
        )
        self._deps.storage.put_bytes(
            bucket=bucket,
            object_key=manifest_key,
            data=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
        )

        current_stats = {
            "total": len(ordered_samples),
            "image": len([sample for sample in ordered_samples if sample.sample_type == "image"]),
            "text": len([sample for sample in ordered_samples if sample.sample_type == "text"]),
            "augmented": len([sample for sample in ordered_samples if getattr(sample, "is_augmented", False)]),
            "alignment_count": len(pairs),
        }
        artifact = {
            "format": "vlm-json",
            "bucket": bucket,
            "object_key": object_key,
            "manifest_key": manifest_key,
            "download_url": artifact_result.get("url")
            or self._deps.storage.presign_download_url(bucket=bucket, object_key=object_key),
            "file_size_bytes": int(artifact_result.get("size_bytes") or len(artifact_bytes)),
            "sample_stats": current_stats,
            "split_counts": dict(Counter(split_map.values())),
        }
        return self._build_summary(
            processing_type="export",
            current_stats=current_stats,
            warnings=[],
            extra={"artifact": artifact},
        )

    def _extract_terms(self, sample: Any, config_json: dict[str, Any] | None = None) -> list[tuple[str, str]]:
        text_parts = [
            str(sample.sample_name or ""),
            str(sample.text_content or ""),
            json.dumps(sample.annotation_data or {}, ensure_ascii=False),
            json.dumps(sample.related_entities or [], ensure_ascii=False),
            json.dumps(sample.source_metadata or {}, ensure_ascii=False),
        ]
        corpus = " ".join(part for part in text_parts if part).lower()
        extracted: list[tuple[str, str]] = []
        lexicon = self._merge_entity_lexicon(config_json)
        for source, normalized in lexicon["Defect"].items():
            if source in corpus:
                extracted.append(("Defect", normalized))
        for source, normalized in lexicon["Part"].items():
            if source in corpus:
                extracted.append(("Part", normalized))
        for source, normalized in lexicon["Process"].items():
            if source in corpus:
                extracted.append(("Process", normalized))
        for source, normalized in lexicon["Attribute"].items():
            if source in corpus:
                extracted.append(("Attribute", normalized))
        seen: set[tuple[str, str]] = set()
        ordered: list[tuple[str, str]] = []
        for item in extracted:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    @staticmethod
    def _merge_entity_lexicon(config_json: dict[str, Any] | None) -> dict[str, dict[str, str]]:
        merged = {
            "Defect": dict(DEFECT_TERMS),
            "Part": dict(PART_TERMS),
            "Process": dict(PROCESS_TERMS),
            "Attribute": dict(ATTRIBUTE_TERMS),
        }
        custom = dict((config_json or {}).get("entity_lexicon") or {})
        for entity_type, values in custom.items():
            entity_bucket = merged.setdefault(str(entity_type), {})
            if isinstance(values, dict):
                for key, value in values.items():
                    entity_bucket[str(key).lower()] = str(value)
            elif isinstance(values, list):
                for item in values:
                    entity_bucket[str(item).lower()] = str(item)
        return merged

    @staticmethod
    def _build_rule_relations(
        sample_key: str,
        extracted_terms: list[tuple[str, str]],
        relation_rules: list[Any],
    ) -> set[tuple[str, str, str]]:
        relations: set[tuple[str, str, str]] = set()
        typed_terms: dict[str, set[str]] = {}
        for entity_type, term in extracted_terms:
          typed_terms.setdefault(entity_type, set()).add(term)
        for rule in relation_rules:
            if not isinstance(rule, dict):
                continue
            source_type = str(rule.get("source") or "")
            target_type = str(rule.get("target") or "")
            relation = str(rule.get("relation") or "").strip()
            if not relation or source_type not in typed_terms or target_type not in typed_terms:
                continue
            for source_term in typed_terms[source_type]:
                for target_term in typed_terms[target_type]:
                    relations.add((f"{source_type.lower()}::{source_term}", f"{target_type.lower()}::{target_term}", relation))
                    relations.add((sample_key, f"{source_type.lower()}::{source_term}", f"MENTIONS_{source_type.upper()}"))
                    relations.add((sample_key, f"{target_type.lower()}::{target_term}", f"MENTIONS_{target_type.upper()}"))
        return relations

    def _describe_image_sample(self, sample: Any) -> str:
        text_bits = [
            sample.sample_name or "",
            json.dumps(sample.annotation_data or {}, ensure_ascii=False),
            json.dumps(sample.related_entities or [], ensure_ascii=False),
            json.dumps(sample.source_metadata or {}, ensure_ascii=False),
        ]
        return " ".join(part for part in text_bits if part).strip()

    def _describe_text_sample(self, sample: Any) -> str:
        text_bits = [
            sample.sample_name or "",
            sample.text_content or "",
            json.dumps(sample.annotation_data or {}, ensure_ascii=False),
            json.dumps(sample.related_entities or [], ensure_ascii=False),
        ]
        return " ".join(part for part in text_bits if part).strip()

    @staticmethod
    def _token_overlap(a: str, b: str) -> float:
        left = set(re.findall(r"[\w\u4e00-\u9fff]+", a.lower()))
        right = set(re.findall(r"[\w\u4e00-\u9fff]+", b.lower()))
        if not left and not right:
            return 0.0
        return len(left & right) / max(1, len(left | right))

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        norm_left = sum(a * a for a in left) ** 0.5 or 1.0
        norm_right = sum(b * b for b in right) ** 0.5 or 1.0
        return dot / (norm_left * norm_right)

    @staticmethod
    def _entity_substitution(text: str) -> str:
        output = text
        for source, target in ENTITY_REPLACEMENTS.items():
            if source in output:
                return output.replace(source, target, 1)
        return output

    @staticmethod
    def _relation_inference(text: str) -> str:
        normalized = text.strip()
        if "导致" in normalized or "because" in normalized.lower():
            return normalized
        if "划痕" in normalized and "屏幕" in normalized:
            return f"{normalized}。推断关系：屏幕存在划痕缺陷。"
        if "外壳" in normalized and "凹陷" in normalized:
            return f"{normalized}。推断关系：外壳部件出现凹陷。"
        return normalized

    @staticmethod
    def _split_counts(total: int, train_ratio: float, val_ratio: float) -> tuple[int, int]:
        train_count = int(total * train_ratio)
        val_count = int(total * val_ratio)
        train_end = min(total, train_count)
        val_end = min(total, train_count + val_count)
        return train_end, val_end

    @staticmethod
    def _build_summary(
        *,
        processing_type: str,
        current_stats: dict[str, Any],
        warnings: list[str],
        degraded_mode: bool = False,
        degraded_reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        phase_map = {
            "kg": ["scan_samples", "extract_entities", "extract_relations", "persist_graph"],
            "alignment": ["describe_samples", "embed_or_fallback", "score_pairs", "persist_pairs"],
            "augmentation": ["generate_proposals", "preview", "apply"],
            "export": ["collect_samples", "build_vlm_json", "write_artifact"],
        }
        payload = {
            "summary": {
                "status": "completed",
                "current_stats": current_stats,
                "degraded_mode": degraded_mode,
                "degraded_reason": degraded_reason,
            },
            "current_stats": current_stats,
            "warnings": warnings,
            "phases": [{"name": name, "status": "completed"} for name in phase_map[processing_type]],
            "progress": 100,
        }
        if extra:
            payload.update(extra)
        return payload
