"""
utils.py - 配置常量 + 通用工具函数
==================================
职责：
  - 集中存放所有配置常量（模型路径、知识库路径、阈值、枚举、字段权重、CoT 步骤等）
  - MVTec 缺陷类型词典（15 类）
  - 通用工具函数：mask→bbox、IoU、pixel AUC、JSON 解析

依赖：os / re / json / time / torch / numpy / PIL / typing
其他模块通过 `from utils import *` 复用这些常量与函数（`__all__` 显式导出，
含下划线前缀的 `_parse_json_from_text` 以及 numpy/torch/PIL 等模块别名）。
"""

import os
import re
import json
import time
import torch
import numpy as np
from typing import Optional
from PIL import Image


# =====================================================
# 配置常量
# =====================================================

MODEL_PATH   = "/kaggle/input/models/lijc888/qwen3-vl-lora-merged-v2-single/transformers/default/1"
KB_JSON_PATH = "/kaggle/working/mvtec_kb.json"
KB_FAISS_PATH = "/kaggle/working/mvtec_kb.faiss"
KB_META_PATH  = "/kaggle/working/mvtec_kb_meta.json"

EMBED_MODEL_NAME = "BAAI/bge-small-zh"

# 置信度路由阈值（路线图 2.4.4 节）
CONFIDENCE_THRESHOLD = 0.7
# 二次检索扩大 top-k
RETRIEVE_K_LOW_CONF = 8
RETRIEVE_K_HIGH_CONF_DEFAULT = 5

# 决策路由阈值（创新点一）
DECISION_U_THRESHOLD = 0.5            # u < 0.5 → 特征融合；u ≥ 0.5 → 二次校准
DECISION_ALIGNMENT_THRESHOLD = 0.7    # alignment_score ≥ 0.7 → 无冲突快通道

# 字段对齐权重（路线图 2.3 节）
# 仅覆盖开题报告定义的 7 个对齐字段；has_defect / confidence 不参与 alignment_score。
FIELD_WEIGHTS: dict[str, float] = {
    # 视觉缺陷类别/严重度是核心判定；risk_type 仅作较粗粒度语义桥接。
    "risk_type":          1.5,
    "severity":           2.0,
    "defect_category":    3.0,
    "location_hint":      1.5,
    "evidence_summary":   1.5,
    # 情绪不是产品是否有缺陷的证据，避免其主导 supported/not_supported。
    "emotion_label":      0.2,
    "emotion_intensity":  0.1,
    # confidence 不参与对齐，仅作权重
}

# 8 个 risk_type 枚举
RISK_TYPE_ENUM = [
    "appearance_abnormality", "structural_damage", "surface_defect",
    "deformation", "contamination", "safety_risk",
    "quality_defect", "none",
]

_RISK_TYPE_ALIAS_GROUPS: list[tuple[str, set[str]]] = [
    ("appearance_abnormality", {
        "appearance_abnormality", "appearance abnormality",
        "color_abnormality", "color abnormality", "color abnormal",
        "print_defect", "print defect", "printing defect", "印刷异常", "印字异常", "喷码异常",
    }),
    ("structural_damage", {
        "structural_damage", "structural damage",
        "broken", "breakage", "damaged", "damage",
        "破损", "破裂", "断裂", "碎裂", "缺件", "缺失", "部件缺失",
    }),
    ("surface_defect", {
        "surface_defect", "surface defect",
        "crack", "cracked", "scratch", "scratched", "cut", "surface_damage", "surface damage",
        "裂纹", "裂缝", "开裂", "划痕", "切口", "割裂", "撕裂",
    }),
    ("deformation", {
        "deformation", "deformed", "misalignment", "misaligned", "bent",
        "变形", "错位", "歪斜", "弯曲", "弯折",
    }),
    ("contamination", {
        "contamination", "contaminant", "dirty", "stain", "liquid",
        "污染", "污渍", "异物", "脏污", "漏液", "油污",
    }),
    ("safety_risk", {
        "safety_risk", "safety risk", "unsafe", "danger", "hazard",
        "不安全", "危险", "安全隐患",
    }),
    ("quality_defect", {
        "quality_defect", "quality defect", "quality issue", "product quality",
        "product_quality", "product quality issue", "product_quality_issue",
        "combined", "复合缺陷", "多种缺陷", "多个问题",
    }),
]

# 风险等价类（同类别内视为部分一致 0.5，跨类视为完全冲突 0.0）
RISK_EQUIVALENCE_CLASSES: list[set[str]] = [
    {"structural_damage", "surface_defect"},               # 结构破裂 / 表面缺陷
    {"contamination", "appearance_abnormality"},           # 污染 / 外观异常
    {"deformation"},                                       # 形变
    {"safety_risk", "quality_defect"},                     # 安全 / 质量
    {"none"},                                              # 无风险
]

# severity 数值映射
SEVERITY_MAP = {"none": 0.0, "low": 0.33, "medium": 0.67, "high": 1.0}

# emotion_label 枚举
EMOTION_ENUM = ["neutral", "anger", "anxiety", "dissatisf", "worry"]

# defect_category 通用闭集：面向跨数据集评测，不直接绑定某个数据集原生标签
DEFECT_CATEGORY_ENUM = [
    "crack",
    "broken",
    "scratch",
    "hole",
    "cut",
    "contamination",
    "liquid",
    "deformation",
    "color_abnormality",
    "misalignment",
    "missing_part",
    "print_defect",
    "surface_damage",
    "combined",
    "other",
    "none",
]

# 开题报告核心 8 字段：用于结构化语义表达与论文口径描述
CORE_SCHEMA_FIELDS_8 = [
    "risk_type", "severity", "location_hint", "evidence_summary",
    "defect_category", "confidence", "emotion_label", "emotion_intensity",
]

# 辅助字段：用于二分类决策、定位或兼容下游模块，不属于论文核心 8 字段
AUXILIARY_FIELDS = ["has_defect", "bbox"]

# 开题报告对齐 7 字段：confidence 不参与对齐，has_defect 也不计入 alignment_score
ALIGNMENT_FIELDS_7 = [
    "risk_type", "severity", "defect_category", "location_hint",
    "evidence_summary", "emotion_label", "emotion_intensity",
]

# 工程内部文本 schema：保留文本侧现状，不改生成逻辑
STRUCTURED_SCHEMA_FIELDS = ["has_defect", *CORE_SCHEMA_FIELDS_8]

# VLM 图像侧原始输出字段（emotion 在运行时补齐为 neutral / 0.0）
IMAGE_SIDE_VLM_FIELDS = [
    "has_defect", "risk_type", "severity", "defect_category",
    "location_hint", "evidence_summary", "confidence", "bbox",
]

# 占位符黑名单（VLM/LLM 偷懒输出的占位符文本）
PLACEHOLDER_TEXTS = {
    "此处填写具体缺陷描述", "简要描述", "string", "description",
    "<根据图像实际内容填写>", "<具体描述>", "此处填写",
    "none", "null", "nan", "n/a", "",
}

# CoT 推理链 7 步（含 Step 4 情感分析 — 修复 3）
COT_STEPS = [
    "visual_evidence",      # Step 1
    "text_evidence",        # Step 2
    "retrieved_standard",   # Step 3
    "emotion_analysis",     # Step 4: 情感分析（新增）
    "bidirectional_verify", # Step 5
    "conflict_type",        # Step 6
    "final_judgment",       # Step 7
]

# 跨模态冲突子型（对齐流程图 4 类）
CROSSMODAL_SUBTYPES = [
    "semantic_hedge",          # 语义对冲
    "reference_drift",         # 指代漂移
    "information_asymmetry",   # 信息不对称
    "expression_redundancy",   # 表达冗余
]


# =====================================================
# MVTec 缺陷类型词典（15 类）
# =====================================================

MVTEC_DEFECT_TYPES: dict[str, list[str]] = {
    "bottle":      ["broken_large", "broken_small", "contamination"],
    "cable":       ["bent_wire", "cable_swap", "combined", "cut_inner_insulation",
                    "cut_outer_insulation", "missing_cable", "missing_wire", "poke_insulation"],
    "capsule":     ["crack", "faulty_imprint", "poke", "scratch", "squeeze"],
    "carpet":      ["color", "cut", "hole", "metal_contamination", "thread"],
    "grid":        ["bent", "broken", "glue", "metal_contamination", "thread"],
    "hazelnut":    ["crack", "cut", "hole", "print"],
    "leather":     ["color", "cut", "fold", "glue", "poke"],
    "metal_nut":   ["bent", "color", "flip", "scratch"],
    "pill":        ["color", "combined", "contamination", "crack", "faulty_imprint",
                    "scratch", "type"],
    "screw":       ["manipulated_front", "scratch_head", "scratch_neck",
                    "thread_side", "thread_top"],
    "tile":        ["crack", "glue_strip", "gray_stroke", "oil", "rough"],
    "toothbrush":  ["defective"],
    "transistor":  ["bent_lead", "cut_lead", "damaged_case", "misplaced"],
    "wood":        ["color", "combined", "hole", "liquid", "scratch"],
    "zipper":      ["broken_teeth", "combined", "fabric_border", "fabric_interior",
                    "rough", "split_teeth", "squeezed_teeth"],
}

_NONE_LIKE_VALUES = {"", "null", "nan", "none", "n/a", "unknown"}

_DEFECT_ALIAS_GROUPS: dict[str, set[str]] = {
    "broken": {"broken", "break", "damage", "damaged", "破损", "破裂", "断裂", "碎裂", "坏了"},
    "crack": {"crack", "cracked", "裂纹", "裂缝", "开裂", "裂了", "裂"},
    "cut": {"cut", "tear", "torn", "切口", "切割", "割裂", "撕裂"},
    "contamination": {"contamination", "contaminant", "dirty", "污染", "污渍", "异物", "脏"},
    "scratch": {"scratch", "scratched", "划痕", "刮痕", "擦伤", "磨损"},
    "bent": {"bent", "bend", "弯曲", "弯折", "歪"},
    "color": {"color", "colour", "变色", "色差", "颜色"},
    "glue": {"glue", "胶", "胶水"},
    "hole": {"hole", "孔", "洞"},
    "thread": {"thread", "线头", "丝"},
    "print": {"print", "imprint", "印刷", "印字"},
    "poke": {"poke", "puncture", "针孔", "戳孔", "刺穿"},
    "fold": {"fold", "折痕", "褶皱"},
    "rough": {"rough", "粗糙"},
    "liquid": {"liquid", "油污", "液体", "漏液", "油"},
    "metal": {"metal", "金属"},
    "teeth": {"teeth", "齿", "齿牙"},
    "fabric": {"fabric", "布", "织物"},
    "wire": {"wire", "线", "导线", "电线"},
    "lead": {"lead", "引脚"},
    "case": {"case", "外壳"},
    "flip": {"flip", "翻转"},
    "combined": {"combined", "组合", "复合", "混合"},
    "type": {"type", "型号", "类别"},
    "defective": {"defective", "defect", "异常", "缺陷"},
    "misplaced": {"misplaced", "错位", "偏移"},
    "front": {"front", "前端", "前部"},
    "head": {"head", "头部"},
    "neck": {"neck", "颈部"},
    "side": {"side", "侧面"},
    "top": {"top", "顶部"},
    "large": {"large", "严重", "大面积", "较大"},
    "small": {"small", "轻微", "细小", "小面积"},
    "swap": {"swap", "调换", "错换"},
    "missing": {"missing", "缺失", "缺少"},
    "inner": {"inner", "内部", "内层"},
    "outer": {"outer", "外部", "外层"},
    "insulation": {"insulation", "绝缘"},
    "faulty": {"faulty", "错误", "异常"},
    "gray": {"gray", "grey", "灰色"},
    "stroke": {"stroke", "划线", "条纹"},
    "strip": {"strip", "条带"},
    "manipulated": {"manipulated", "变形", "扰动"},
    "split": {"split", "分裂", "开口"},
    "squeezed": {"squeezed", "挤压"},
    "interior": {"interior", "内部"},
    "border": {"border", "边缘"},
}

_CATEGORY_SPECIFIC_DEFECT_ALIASES: dict[str, dict[str, str]] = {
    "bottle": {
        "chip": "broken",
        "fragment": "broken",
    },
    "grid": {
        "metal": "contamination",
    },
    "toothbrush": {
        "broken": "surface_damage",
        "crack": "surface_damage",
        "scratch": "surface_damage",
        "contamination": "surface_damage",
    },
}

_DATASET_DEFECT_TO_CANONICAL: dict[str, str] = {
    "broken_large": "broken",
    "broken_small": "broken",
    "contamination": "contamination",
    "bent_wire": "deformation",
    "cable_swap": "misalignment",
    "combined": "combined",
    "cut_inner_insulation": "cut",
    "cut_outer_insulation": "cut",
    "missing_cable": "missing_part",
    "missing_wire": "missing_part",
    "poke_insulation": "hole",
    "crack": "crack",
    "faulty_imprint": "print_defect",
    "poke": "hole",
    "scratch": "scratch",
    "squeeze": "deformation",
    "color": "color_abnormality",
    "cut": "cut",
    "hole": "hole",
    "metal_contamination": "contamination",
    "thread": "surface_damage",
    "bent": "deformation",
    "broken": "broken",
    "glue": "contamination",
    "print": "print_defect",
    "fold": "deformation",
    "flip": "misalignment",
    "type": "other",
    "manipulated_front": "misalignment",
    "scratch_head": "scratch",
    "scratch_neck": "scratch",
    "thread_side": "surface_damage",
    "thread_top": "surface_damage",
    "glue_strip": "contamination",
    "gray_stroke": "color_abnormality",
    "oil": "liquid",
    "rough": "surface_damage",
    "defective": "surface_damage",
    "bent_lead": "deformation",
    "cut_lead": "cut",
    "damaged_case": "broken",
    "misplaced": "misalignment",
    "liquid": "liquid",
    "broken_teeth": "broken",
    "fabric_border": "surface_damage",
    "fabric_interior": "surface_damage",
    "split_teeth": "broken",
    "squeezed_teeth": "deformation",
}

# When the QDL package is active, converge legacy normalization on its shared
# hierarchical registry.  The local table remains as a standalone fallback.
try:
    from _qdl_defect_ontology import DATASET_TO_CATEGORY as _QDL_DATASET_TO_CATEGORY
except ImportError:
    _QDL_DATASET_TO_CATEGORY = None
if _QDL_DATASET_TO_CATEGORY:
    _DATASET_DEFECT_TO_CANONICAL.update(_QDL_DATASET_TO_CATEGORY)

_DEFECT_TAG_TO_CANONICAL: dict[str, str] = {
    "crack": "crack",
    "broken": "broken",
    "scratch": "scratch",
    "hole": "hole",
    "cut": "cut",
    "contamination": "contamination",
    "glue": "contamination",
    "metal": "contamination",
    "liquid": "liquid",
    "bent": "deformation",
    "fold": "deformation",
    "manipulated": "deformation",
    "squeezed": "deformation",
    "color": "color_abnormality",
    "gray": "color_abnormality",
    "flip": "misalignment",
    "swap": "misalignment",
    "misplaced": "misalignment",
    "missing": "missing_part",
    "print": "print_defect",
    "faulty": "print_defect",
    "rough": "surface_damage",
    "thread": "surface_damage",
    "fabric": "surface_damage",
    "wire": "surface_damage",
    "lead": "surface_damage",
    "case": "surface_damage",
    "teeth": "surface_damage",
    "defective": "surface_damage",
    "stroke": "surface_damage",
    "strip": "surface_damage",
    "combined": "combined",
    "type": "other",
}


# =====================================================
# 通用工具函数
# =====================================================

def _parse_json_from_text(text: str) -> Optional[dict]:
    """提取第一个完整 JSON 对象，容忍 markdown 包裹和前后说明文本。

    不使用非贪婪正则匹配，因为 evidence_summary 等字符串可能包含大括号，
    此时正则会在对象结束前截断并导致无谓的格式失败。
    """
    if not isinstance(text, str) or not text.strip():
        return None
    clean = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    decoder = json.JSONDecoder()
    for start, char in enumerate(clean):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(clean[start:])
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None


def get_allowed_defect_categories(category: Optional[str]) -> list[str]:
    """返回跨数据集通用 defect_category 词表。"""
    return [value for value in DEFECT_CATEGORY_ENUM if value != "none"]


def format_allowed_defect_categories(category: Optional[str]) -> str:
    """把通用缺陷类别词表格式化成 prompt 片段。"""
    allowed = get_allowed_defect_categories(category)
    return ", ".join(allowed + ["none"]) if allowed else "none"


def normalize_risk_type(value) -> str:
    """将 risk_type 统一收口到闭集。无法映射时返回 none。"""
    clean = _normalize_label_text(value)
    if clean in _NONE_LIKE_VALUES:
        return "none"

    allowed = set(RISK_TYPE_ENUM)
    if clean in allowed:
        return clean

    canonical_map = {_normalize_label_text(cand): cand for cand in RISK_TYPE_ENUM}
    if clean in canonical_map:
        return canonical_map[clean]

    for canonical, aliases in _RISK_TYPE_ALIAS_GROUPS:
        if canonical not in allowed:
            continue
        if any(alias == clean or alias in clean for alias in aliases):
            return canonical

    if "quality" in clean or "quality defect" in clean or "product defect" in clean:
        return "quality_defect"
    if "appearance" in clean or "visual" in clean or "外观" in clean:
        return "appearance_abnormality"
    if "surface" in clean and "defect" in clean:
        return "surface_defect"
    if "structural" in clean and "damage" in clean:
        return "structural_damage"
    if "contamin" in clean or "污染" in clean:
        return "contamination"
    if "deform" in clean or "misalign" in clean or "变形" in clean:
        return "deformation"
    if "safe" in clean or "danger" in clean or "risk" in clean:
        return "safety_risk"

    return "none"


def _normalize_label_text(value) -> str:
    s = str(value or "").strip().lower()
    s = s.replace("-", "_")
    s = s.replace("/", " ")
    s = re.sub(r"[(){}\[\],;:]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_has_defect_label(value, default: Optional[str] = None) -> Optional[str]:
    """Normalize Yes/No-like values, including JSON booleans and numbers.

    The raw VLM response is kept unchanged for auditing; callers use this
    helper only when making a binary decision or comparing labels.
    """
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            if np.isnan(value):
                return default
        except TypeError:
            pass
        return "Yes" if value != 0 else "No"

    text = str(value).strip().lower()
    if text in {
        "yes", "true", "1", "y", "是", "有", "存在", "缺陷", "有缺陷",
    }:
        return "Yes"
    if text in {
        "no", "false", "0", "n", "否", "无", "不存在", "正常", "无缺陷",
    }:
        return "No"
    return default


def _tokenize_label_text(value) -> set[str]:
    clean = _normalize_label_text(value).replace("_", " ")
    if clean in _NONE_LIKE_VALUES:
        return set()
    return {tok for tok in re.split(r"[^a-z0-9\u4e00-\u9fff]+", clean) if tok}


def _alias_tags_from_text(value) -> set[str]:
    clean = _normalize_label_text(value)
    tokens = _tokenize_label_text(clean)
    tags = set()
    for tag, variants in _DEFECT_ALIAS_GROUPS.items():
        if any(v in clean or v in tokens for v in variants):
            tags.add(tag)
    return tags


def normalize_defect_category(category: Optional[str], value) -> str:
    """
    将 defect_category 归一化到跨数据集通用闭集。
    无法映射时返回 none。
    """
    clean = _normalize_label_text(value)
    if clean in _NONE_LIKE_VALUES:
        return "none"

    allowed = set(DEFECT_CATEGORY_ENUM)
    if clean in allowed:
        return clean

    canonical_map = {_normalize_label_text(cand): cand for cand in DEFECT_CATEGORY_ENUM}
    if clean in canonical_map:
        return canonical_map[clean]

    dataset_canonical = _DATASET_DEFECT_TO_CANONICAL.get(clean)
    if dataset_canonical in allowed:
        return dataset_canonical

    category_aliases = _CATEGORY_SPECIFIC_DEFECT_ALIASES.get(category or "", {})
    for alias, target in category_aliases.items():
        if alias in clean and target in allowed:
            return target

    input_tags = _alias_tags_from_text(clean)
    priority = [
        "crack",
        "broken",
        "scratch",
        "hole",
        "cut",
        "contamination",
        "liquid",
        "deformation",
        "color_abnormality",
        "misalignment",
        "missing_part",
        "print_defect",
        "surface_damage",
        "combined",
        "other",
    ]
    for tag in priority:
        if tag in input_tags and tag in allowed:
            return tag
        canonical = _DEFECT_TAG_TO_CANONICAL.get(tag)
        if tag in input_tags and canonical in allowed:
            return canonical

    for tag in input_tags:
        canonical = _DEFECT_TAG_TO_CANONICAL.get(tag)
        if canonical in allowed:
            return canonical

    if "surface defect" in clean or "surface_damage" in clean:
        return "surface_damage"
    if "color abnormal" in clean or "颜色异常" in clean or "色差" in clean:
        return "color_abnormality"
    if "missing part" in clean or "缺失" in clean:
        return "missing_part"
    if "print defect" in clean or "印刷异常" in clean:
        return "print_defect"

    return "other"


def get_risk_equivalence_group(value) -> Optional[int]:
    """返回 risk_type 所属等价类索引；无法识别时返回 None。"""
    clean = _normalize_label_text(value)
    if clean in _NONE_LIKE_VALUES:
        clean = "none"
    for idx, group in enumerate(RISK_EQUIVALENCE_CLASSES):
        if clean in group:
            return idx
    return None


def score_risk_type_alignment(text_val, image_val) -> float:
    """
    risk_type 闭集对齐打分：
      - exact match -> 1.0
      - same equivalence class -> 0.5
      - otherwise -> 0.0
    """
    text_clean = normalize_risk_type(text_val)
    image_clean = normalize_risk_type(image_val)
    valid_risk_types = set(RISK_TYPE_ENUM)
    if text_clean not in valid_risk_types or image_clean not in valid_risk_types:
        return 0.0
    if text_clean == image_clean:
        return 1.0
    text_group = get_risk_equivalence_group(text_clean)
    image_group = get_risk_equivalence_group(image_clean)
    if text_group is not None and text_group == image_group:
        return 0.5
    return 0.0


def sanitize_bbox(raw_bbox, max_x: int, max_y: int) -> list[int]:
    """将 bbox 规范到合法坐标范围；非法或零面积框返回 [0,0,0,0]。"""
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return [0, 0, 0, 0]
    try:
        coords = [int(round(float(x))) for x in raw_bbox]
    except (TypeError, ValueError):
        return [0, 0, 0, 0]

    x1, y1, x2, y2 = coords
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))

    max_x = max(0, int(max_x))
    max_y = max(0, int(max_y))
    x1 = max(0, min(max_x, x1))
    x2 = max(0, min(max_x, x2))
    y1 = max(0, min(max_y, y1))
    y2 = max(0, min(max_y, y2))

    if x1 >= x2 or y1 >= y2:
        return [0, 0, 0, 0]
    return [x1, y1, x2, y2]


def sanitize_normalized_bbox(raw_bbox, max_coord: int = 1000) -> list[int]:
    """规范 0-1000 归一化 bbox。"""
    return sanitize_bbox(raw_bbox, max_coord, max_coord)


def denormalize_bbox(raw_bbox, width: int, height: int, max_coord: int = 1000) -> list[int]:
    """将 0-1000 归一化 bbox 转成像素坐标，并再次校验边界。"""
    norm_bbox = sanitize_normalized_bbox(raw_bbox, max_coord=max_coord)
    if norm_bbox == [0, 0, 0, 0]:
        return norm_bbox

    width = max(0, int(width))
    height = max(0, int(height))
    pixel_bbox = [
        int(round(norm_bbox[0] / max_coord * width)),
        int(round(norm_bbox[1] / max_coord * height)),
        int(round(norm_bbox[2] / max_coord * width)),
        int(round(norm_bbox[3] / max_coord * height)),
    ]
    return sanitize_bbox(pixel_bbox, width, height)


def mask_to_bbox(mask_path: str):
    """将二值 mask 转为半开区间 [x1, y1, x2, y2) 外接框；空 mask 返回 None。"""
    mask = np.array(Image.open(mask_path).convert("L"))
    if not np.any(mask):
        return None
    rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    # x2/y2 与 numpy 切片保持一致，使用最大像素索引加一。
    return [int(cmin), int(rmin), int(cmax) + 1, int(rmax) + 1]


def calculate_iou(box1, box2) -> float:
    """计算两个 [x1,y1,x2,y2] 框的 IoU；任一为 None 返回 0.0。"""
    if box1 is None or box2 is None:
        return 0.0
    x1, y1 = max(box1[0], box2[0]), max(box1[1], box2[1])
    x2, y2 = min(box1[2], box2[2]), min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    a2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def calculate_pixel_auc(pred_bbox, gt_mask_path, width, height) -> float:
    """
    计算预测 bbox 与 GT mask 的像素级 AUC（近似 IoU）。
    无 GT mask 或 bbox 为零时返回 0.0。
    """
    if not gt_mask_path or pred_bbox == [0, 0, 0, 0]:
        return 0.0
    try:
        mask_img = Image.open(gt_mask_path).convert("L")
        if mask_img.size != (width, height):
            mask_img = mask_img.resize((width, height))
        mask = np.array(mask_img)
        gt_mask = (mask > 0).astype(np.uint8)
        pred_mask = np.zeros((height, width), dtype=np.uint8)
        x1, y1, x2, y2 = pred_bbox
        pred_mask[max(0, y1):min(height, y2), max(0, x1):min(width, x2)] = 1
        intersection = int(np.logical_and(pred_mask, gt_mask).sum())
        union = int(np.logical_or(pred_mask, gt_mask).sum())
        return float(intersection / union) if union > 0 else 0.0
    except Exception:
        return 0.0


# =====================================================
# 显式导出（含下划线前缀函数 + 模块别名，供 from utils import * 使用）
# =====================================================
__all__ = [
    # 标准库 / 第三方模块别名（透传给下游模块）
    "os", "re", "json", "time", "torch", "np", "Image", "Optional",
    # 配置常量
    "MODEL_PATH", "KB_JSON_PATH", "KB_FAISS_PATH", "KB_META_PATH",
    "EMBED_MODEL_NAME", "CONFIDENCE_THRESHOLD",
    "RETRIEVE_K_LOW_CONF", "RETRIEVE_K_HIGH_CONF_DEFAULT",
    "DECISION_U_THRESHOLD", "DECISION_ALIGNMENT_THRESHOLD",
    "RISK_TYPE_ENUM", "RISK_EQUIVALENCE_CLASSES", "SEVERITY_MAP",
    "EMOTION_ENUM", "DEFECT_CATEGORY_ENUM", "FIELD_WEIGHTS", "CORE_SCHEMA_FIELDS_8",
    "AUXILIARY_FIELDS", "ALIGNMENT_FIELDS_7", "STRUCTURED_SCHEMA_FIELDS",
    "IMAGE_SIDE_VLM_FIELDS", "PLACEHOLDER_TEXTS",
    "COT_STEPS", "CROSSMODAL_SUBTYPES",
    # 词典
    "MVTEC_DEFECT_TYPES",
    # 工具函数
    "_parse_json_from_text",
    "get_allowed_defect_categories", "format_allowed_defect_categories",
    "normalize_risk_type",
    "normalize_has_defect_label",
    "normalize_defect_category",
    "get_risk_equivalence_group", "score_risk_type_alignment",
    "sanitize_bbox", "sanitize_normalized_bbox", "denormalize_bbox",
    "mask_to_bbox", "calculate_iou", "calculate_pixel_auc",
]
