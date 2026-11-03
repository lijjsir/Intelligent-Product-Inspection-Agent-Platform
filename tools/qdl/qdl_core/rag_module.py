"""
rag_module.py - 自适应检索层（RAG）
================================
职责：
  - adaptive_retrieve：基于 FAISS 的自适应 top-k 检索
      · 高模糊度（>0.6）自动扩大 top-k
      · force_k：二次检索强制 top-k
      · category：品类过滤
      · visual_candidates：视觉侧候选与文本候选取并集后检索

依赖：utils（常量） / models（embedder + faiss_index） / numpy
"""

from utils import *
from models import StructuredPipelineModels
import numpy as np
from typing import Optional


# =====================================================
# 子模块 2：自适应检索层（RAG）
# =====================================================

def adaptive_retrieve(models: StructuredPipelineModels,
                       raw_text: str,
                       candidates: list[str],
                       ambiguity_score: float,
                       enable: bool = True,
                       force_k: Optional[int] = None,
                       category: str = None,
                       visual_candidates: list[str] = None,
                       top_k_multiplier: int = 1,
                       strategy: str = "legacy",
                       retrieval_stage: str = "initial") -> list[dict]:
    """
    返回检索到的知识库文档列表。
    - enable: False 时返回空列表（消融实验用）
    - force_k: 二次检索时强制 top-k
    - category: 品类过滤
    - visual_candidates: 视觉侧预提取候选（与文本候选取并集）
    - top_k_multiplier: top-k 扩大倍数（二次校准用，默认 1 不扩大）
    - strategy: legacy 或 candidate_union_v2
    - retrieval_stage: initial / confidence_reroute / cot_secondary
    """
    trace = {
        "enabled": bool(enable),
        "ready": bool(models.is_rag_ready()),
        "strategy": strategy,
        "retrieval_stage": retrieval_stage,
        "category": category,
        "candidate_count": len(candidates or []),
        "visual_candidate_count": len(visual_candidates or []),
        "requested_k": force_k,
        "search_k": 0,
        "faiss_valid_hits": 0,
        "category_matches": 0,
        "returned_count": 0,
        "empty_reason": "",
        "score_threshold": None,
        "candidate_queries": [],
        "candidate_hits": [],
        "selected_doc_ids": [],
        "category_filtered_count": 0,
    }
    models.last_rag_trace = trace
    if not enable or not models.is_rag_ready():
        trace["empty_reason"] = "disabled" if not enable else "rag_not_ready"
        return []

    # 自适应 top-k（修复：高模糊度走更大的 k）
    if force_k is not None:
        k = force_k
    elif ambiguity_score > 0.6:
        k = RETRIEVE_K_LOW_CONF
    else:
        k = RETRIEVE_K_HIGH_CONF_DEFAULT

    # top_k_multiplier 扩大检索范围（二次校准用）
    k = k * top_k_multiplier

    if strategy == "candidate_union_v2":
        return _candidate_union_retrieve(
            models=models,
            raw_text=raw_text,
            candidates=candidates,
            visual_candidates=visual_candidates,
            category=category,
            final_k=k,
            ambiguity_score=ambiguity_score,
            retrieval_stage=retrieval_stage,
            trace=trace,
        )

    # 构造查询：原始文本 + 文本候选 + 视觉候选（取并集）
    all_candidates = list(candidates)
    if visual_candidates:
        for vc in visual_candidates:
            if vc not in all_candidates:
                all_candidates.append(vc)
    query_text = raw_text + " " + " ".join(all_candidates)

    # 向量化查询
    query_vec = models.embedder.encode(
        [query_text], normalize_embeddings=True,
    )
    query_vec = np.array(query_vec, dtype=np.float32)

    # FAISS 检索（多检索一些，再做品类过滤）
    search_k = k * 3 if category else k
    trace["requested_k"] = k
    trace["search_k"] = search_k
    scores, indices = models.faiss_index.search(query_vec, search_k)
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if 0 <= idx < len(models.kb_docs):
            trace["faiss_valid_hits"] += 1
            doc = models.kb_docs[idx].copy()
            if category and doc.get("category") != category:
                continue
            trace["category_matches"] += 1
            doc["retrieve_score"] = float(score)
            results.append(doc)
            if len(results) >= k:
                break
    trace["returned_count"] = len(results)
    if not results:
        trace["empty_reason"] = (
            "no_category_match" if trace["faiss_valid_hits"] else "no_valid_faiss_hit"
        )
    return results


def _candidate_union_retrieve(models: StructuredPipelineModels,
                              raw_text: str,
                              candidates: list[str],
                              visual_candidates: list[str],
                              category: str,
                              final_k: int,
                              ambiguity_score: float,
                              retrieval_stage: str,
                              trace: dict) -> list[dict]:
    """按候选分别检索，再合并去重，供 RAG v2 使用。"""
    text_candidates = []
    for candidate in candidates or []:
        if candidate and candidate not in text_candidates:
            text_candidates.append(candidate)

    visual_only_candidates = []
    for candidate in visual_candidates or []:
        if candidate and candidate not in text_candidates and candidate not in visual_only_candidates:
            visual_only_candidates.append(candidate)

    query_specs = [
        {"candidate": candidate, "source": "text"}
        for candidate in text_candidates
    ]
    query_specs.extend(
        {"candidate": candidate, "source": "visual"}
        for candidate in visual_only_candidates
    )
    if not query_specs:
        query_specs = [{"candidate": "", "source": "raw_text"}]

    per_candidate_k = 2 if ambiguity_score > 0.6 or final_k > RETRIEVE_K_HIGH_CONF_DEFAULT else 1
    ntotal = int(getattr(models.faiss_index, "ntotal", 0) or 0)
    search_k = ntotal if category else min(ntotal, per_candidate_k)
    trace["requested_k"] = final_k
    trace["search_k"] = search_k
    trace["per_candidate_k"] = per_candidate_k

    merged: dict[str, dict] = {}
    for spec in query_specs:
        candidate = spec["candidate"]
        query_text = raw_text if not candidate else f"{raw_text} {candidate}"
        query_record = {
            "candidate": candidate,
            "source": spec["source"],
            "query_text": query_text,
            "requested_k": per_candidate_k,
            "search_k": search_k,
            "hits": [],
        }
        if search_k <= 0:
            trace["candidate_queries"].append(query_record)
            continue

        query_vec = models.embedder.encode(
            [query_text], normalize_embeddings=True,
        )
        query_vec = np.array(query_vec, dtype=np.float32)
        scores, indices = models.faiss_index.search(query_vec, search_k)
        accepted = 0
        for idx, score in zip(indices[0], scores[0]):
            idx = int(idx)
            if not (0 <= idx < len(models.kb_docs)):
                continue
            trace["faiss_valid_hits"] += 1
            doc = models.kb_docs[idx].copy()
            if category and doc.get("category") != category:
                trace["category_filtered_count"] += 1
                continue
            trace["category_matches"] += 1
            accepted += 1
            doc_id = str(doc.get("id", idx))
            hit = {
                "doc_id": doc_id,
                "index": idx,
                "score": float(score),
                "category": doc.get("category"),
                "defect_type": doc.get("defect_type"),
            }
            query_record["hits"].append(hit)
            existing = merged.get(doc_id)
            if existing is None or float(score) > float(existing.get("retrieve_score", -np.inf)):
                doc["retrieve_score"] = float(score)
                doc["retrieval_queries"] = [{
                    "candidate": candidate,
                    "source": spec["source"],
                    "score": float(score),
                }]
                merged[doc_id] = doc
            else:
                existing.setdefault("retrieval_queries", []).append({
                    "candidate": candidate,
                    "source": spec["source"],
                    "score": float(score),
                })
            if accepted >= per_candidate_k:
                break
        trace["candidate_hits"].append(query_record)
        trace["candidate_queries"].append({
            "candidate": candidate,
            "source": spec["source"],
            "query_text": query_text,
            "requested_k": per_candidate_k,
        })

    results = sorted(
        merged.values(),
        key=lambda doc: float(doc.get("retrieve_score", -np.inf)),
        reverse=True,
    )[:final_k]
    trace["returned_count"] = len(results)
    trace["selected_doc_ids"] = [
        str(doc.get("id", "")) for doc in results
    ]
    if not results:
        trace["empty_reason"] = (
            "no_category_match"
            if trace["faiss_valid_hits"] else "no_valid_faiss_hit"
        )
    return results
