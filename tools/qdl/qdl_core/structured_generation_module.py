"""
structured_generation_module.py - 结构化生成层
============================================
职责：
  - generate_structured_text：核心 8 字段 + has_defect 的结构化文本生成
      （含枚举/数值校验 + 兜底 + 一致性校验）
  - confidence_routing：置信度二档路由
      confidence ≥ 0.7 直接返回；< 0.7 触发二次检索（扩大 top-k）+ 重新生成
  - generate_image_side_json：VLM 原始输出 8 字段 JSON
      （has_defect/risk/severity/defect/location/evidence/confidence/bbox）
      运行时补齐 emotion 字段；含 Bug 1（占位符）+ Bug 2（has_defect 一致性）修复

依赖：utils / models / rag_module（adaptive_retrieve、RETRIEVE_K_LOW_CONF）
"""

from utils import *
from models import (
    StructuredPipelineModels,
    _llm_text_inference,
    _vlm_image_inference,
    _vlm_image_inference_batch_dual,
)
from rag_module import adaptive_retrieve, RETRIEVE_K_LOW_CONF


# =====================================================
# 0. 结构化字段归一化辅助函数
# =====================================================

_EMPTY_TEXT_VALUES = {"", "none", "null", "nan", "n/a", "unknown"}
_SEVERITY_ZH = {"none": "无", "low": "轻度", "medium": "中度", "high": "重度"}
_TEXT_TRACKED_FIELDS = [
    "has_defect",
    "risk_type",
    "severity",
    "location_hint",
    "evidence_summary",
    "defect_category",
    "confidence",
    "emotion_label",
    "emotion_intensity",
]
_IMAGE_TRACKED_FIELDS = [
    "has_defect",
    "risk_type",
    "severity",
    "location_hint",
    "evidence_summary",
    "defect_category",
    "confidence",
    "bbox",
]
_NONE_LIKE_VALUES = {"none", "", "null", "unknown", "n/a", "nan"}
_NO_DEFECT_EVIDENCE_TERMS = (
    "完好无损",
    "无异常",
    "无明显异常",
    "未见异常",
    "未发现异常",
    "无缺陷",
    "无明显缺陷",
    "基本正常",
    "表面正常",
    "状态正常",
    "符合标准",
    "符合出厂标准",
    "符合质量标准",
    "无破损",
    "no defect",
    "no visible defect",
    "normal surface",
    "looks normal",
    "intact",
)
_EXPLICIT_IMAGE_EVIDENCE_TERMS = (
    "裂纹",
    "裂缝",
    "破损",
    "破裂",
    "崩边",
    "崩裂",
    "断裂",
    "缺口",
    "碎裂",
    "孔洞",
    "孔",
    "洞",
    "划痕",
    "刮伤",
    "磨损",
    "凹陷",
    "变形",
    "弯曲",
    "弯折",
    "扭曲",
    "污染",
    "污渍",
    "脏污",
    "异物",
    "腐蚀",
    "氧化",
    "烧焦",
    "断线",
    "缺失",
    "空缺",
    "脱落",
    "剥落",
    "外露",
    "暴露",
    "不连续",
    "中断",
    "稀疏",
    "偏移",
    "缺脚",
    "缺针",
    "错位",
    "切口",
    "撕裂",
    "割裂",
    "印刷异常",
    "印刷缺陷",
    "打印错误",
    "颜色异常",
    "crack",
    "broken",
    "scratch",
    "scrape",
    "dent",
    "damage",
    "contamination",
    "stain",
    "deformation",
    "missing",
    "exposed",
    "peeling",
    "sparse",
    "disconnected",
    "tear",
    "hole",
    "cut",
    "bent",
    "misalignment",
    "discoloration",
    "printing defect",
 )
_DEFECT_ALIAS_HINTS = {
    "crack": ("裂纹", "裂缝", "开裂", "crack", "cracked"),
    "broken": ("破损", "破裂", "断裂", "缺口", "碎裂", "崩边", "崩裂", "broken", "break", "damage", "damaged"),
    "scratch": ("划痕", "刮伤", "刮痕", "磨损", "scratch", "scrape"),
    "contamination": ("污染", "污渍", "异物", "脏污", "污染物", "contamination", "stain", "dirty"),
    "hole": ("孔", "洞", "hole"),
    "cut": ("切口", "撕裂", "割裂", "cut", "tear", "torn"),
    "bent": ("弯曲", "弯折", "变形", "扭曲", "bent", "deformation"),
    "color": ("变色", "色差", "颜色异常", "color", "colour"),
    "metal": ("金属", "metal"),
    "liquid": ("漏液", "液体", "油污", "liquid"),
}
_IMAGE_DEFECT_TO_RISK_TYPE = {
    "crack": "surface_defect",
    "scratch": "surface_defect",
    "cut": "surface_defect",
    "surface_damage": "surface_defect",
    "broken": "structural_damage",
    "hole": "structural_damage",
    "missing_part": "structural_damage",
    "deformation": "deformation",
    "misalignment": "deformation",
    "contamination": "contamination",
    "liquid": "contamination",
    "color_abnormality": "appearance_abnormality",
    "print_defect": "appearance_abnormality",
    "combined": "quality_defect",
    "other": "quality_defect",
}
_IMAGE_CATEGORY_PROMPT_HINTS = {
    "screw": (
        "screw：先检查螺纹、螺钉头、杆体和尖端，再判断形态。重点召回螺纹缺损、头部崩边、杆体弯折、"
        "锈蚀、毛刺和明显划痕；螺纹局部缺口优先考虑 broken/missing_part，杆体弯曲考虑 deformation，"
        "表面线状痕迹考虑 scratch。只有看见明确刀切状切口才使用 cut，不要把螺纹阴影或反光写成 cut。\n"
        "少样本参考（只学习视觉形态，不复制固定坐标）：观察到螺纹连续性中断并有缺口 -> Yes + broken 或 missing_part；"
        "观察到杆体轴线明显弯曲 -> Yes + deformation；仅有细长表面痕迹 -> Yes + scratch。\n"
        "召回补充：螺纹或崩边区域即使细小、低对比度，只要能确认连续性中断、缺口或断裂形态，仍应输出 Yes；"
        "仅有螺纹阴影、反光或无法确认的细线时输出 No。"
    ),
    "toothbrush": (
        "toothbrush：先检查刷毛、刷头连接处、刷柄和表面，再判断形态。重点召回刷毛缺失/稀疏、刷头断裂、"
        "刷柄裂纹、刷毛污染和明显变形；刷毛数量异常优先考虑 missing_part，刷柄线状裂纹考虑 crack，"
        "刷头或刷柄断裂考虑 broken。不要把刷毛排列、轮廓模糊或阴影默认写成 cut。\n"
        "少样本参考（只学习视觉形态，不复制固定坐标）：刷毛区域出现明显空缺 -> Yes + missing_part；"
        "刷柄出现连续裂缝 -> Yes + crack；刷头发生断裂并形成断面 -> Yes + broken。\n"
        "召回补充：刷毛区域即使缺口很小，只要能确认刷毛连续性、密度或排列出现真实空缺，仍应输出 Yes；"
        "仅有正常排列差异、阴影或轮廓模糊时输出 No。"
    ),
    "cable": (
        "cable：沿线缆全长检查绝缘层、外皮、端部和线芯。重点召回外皮开裂、绝缘层破损、线芯外露、"
        "压扁、弯折、磨损和端部缺失；线芯暴露或端部断开考虑 broken/missing_part，外皮线状开裂考虑 crack，"
        "明显压弯考虑 deformation。线缆自然弯曲、反光或局部阴影不是缺陷，也不能默认写 cut。\n"
        "少样本参考（只学习视觉形态，不复制固定坐标）：外皮破裂且能看见内部线芯 -> Yes + broken 或 crack；"
        "仅有局部擦痕 -> Yes + scratch；整体被压扁并改变轮廓 -> Yes + deformation。\n"
        "召回补充：线缆上的细小裂口、外皮断开或线芯外露即使面积很小，只要视觉上能够确认，仍应输出 Yes；"
        "自然弯曲、反光、阴影或无法确认的细线变化时输出 No。"
    ),
    "transistor": (
        "transistor：先检查封装本体、引脚和引脚与封装的连接处。重点召回引脚弯折、缺脚、引脚错位、"
        "封装开裂、烧痕和明显污染；引脚数量减少考虑 missing_part，明显弯曲考虑 deformation，封装裂缝考虑 crack。"
        "不要把封装边缘反光、焊点阴影或轻微轮廓不清默认写成 cut。\n"
        "少样本参考（只学习视觉形态，不复制固定坐标）：引脚偏离原有排列方向 -> Yes + deformation 或 misalignment；"
        "引脚缺失 -> Yes + missing_part；封装表面有连续裂缝 -> Yes + crack。\n"
        "召回补充：细小引脚缺失、弯折或错位只要能和正常排列明确区分，仍应输出 Yes；"
        "仅有焊点阴影、边缘反光或无法确认的轮廓变化时输出 No。"
    ),
}
_TEXT_EMOTION_SUPPORT_PATTERNS = {
    "anger": (
        "气死",
        "愤怒",
        "恼火",
        "烦死",
        "可恶",
        "差劲",
        "破产品",
        "垃圾",
        "太差了",
        "真烂",
        "离谱",
        "火大",
        "生气",
        "angry",
        "furious",
    ),
    "anxiety": (
        "焦虑",
        "着急",
        "急死",
        "紧张",
        "害怕",
        "怕",
        "慌",
        "anxious",
        "panic",
    ),
    "dissatisf": (
        "不满",
        "差评",
        "投诉",
        "退货",
        "拒绝",
        "失望",
        "不舒服",
        "不靠谱",
        "糟糕",
        "太差",
        "坑",
        "dissatisfied",
        "complain",
        "bad review",
    ),
    "worry": (
        "担心",
        "会不会",
        "有没有事",
        "怎么办",
        "严重吗",
        "靠谱吗",
        "不放心",
        "worry",
        "worried",
        "concerned",
    ),
}
_TEXT_GENERIC_EMOTION_PATTERNS = tuple(
    pattern
    for patterns in _TEXT_EMOTION_SUPPORT_PATTERNS.values()
    for pattern in patterns
)
_TEXT_SARCASM_PATTERNS = (
    "呵呵",
    "笑死",
    "真行",
    "还说",
    "居然",
    "居然说",
    "也叫",
    "你管这叫",
    "这也算",
)


def _is_placeholder_text(value) -> bool:
    text = str(value or "").strip()
    lower = text.lower()
    return (
        text in PLACEHOLDER_TEXTS
        or lower in PLACEHOLDER_TEXTS
        or text.startswith("此处填写")
        or text.startswith("简要描述")
    )


def _is_empty_location(value) -> bool:
    return str(value or "").strip().lower() in _EMPTY_TEXT_VALUES


def _normalize_free_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _text_supports_emotion(raw_text: str, emotion_label: str, emotion_intensity: float) -> bool:
    label = str(emotion_label or "").strip().lower()
    if label not in EMOTION_ENUM:
        return False
    try:
        intensity = float(emotion_intensity)
    except (TypeError, ValueError):
        intensity = 0.0
    if label == "neutral" or intensity <= 0.0:
        return True

    text = _normalize_free_text(raw_text)
    if not text:
        return False
    if any(pattern in text for pattern in _TEXT_EMOTION_SUPPORT_PATTERNS.get(label, ())):
        return True
    if any(pattern in text for pattern in _TEXT_GENERIC_EMOTION_PATTERNS):
        return True
    if any(pattern in text for pattern in _TEXT_SARCASM_PATTERNS):
        return True
    return False


def _normalize_text_emotion_fields(result: dict, raw_text: str) -> dict:
    normalized = result.copy()
    label = str(normalized.get("emotion_label", "neutral")).strip().lower()
    try:
        intensity = max(0.0, min(1.0, float(normalized.get("emotion_intensity", 0.0))))
    except (TypeError, ValueError):
        intensity = 0.0
    if label not in EMOTION_ENUM:
        label = "neutral"
        intensity = 0.0
    if label == "neutral":
        intensity = 0.0
    if (
        normalize_has_defect_label(normalized.get("has_defect")) == "No"
        and label != "neutral"
        and not _text_supports_emotion(raw_text, label, intensity)
    ):
        label = "neutral"
        intensity = 0.0
    normalized["emotion_label"] = label
    normalized["emotion_intensity"] = intensity
    return normalized


def _is_no_defect_evidence_summary(value) -> bool:
    text = _normalize_free_text(value)
    return bool(text) and _contains_any_term(text, _NO_DEFECT_EVIDENCE_TERMS)


def _has_explicit_image_evidence_summary(value) -> bool:
    """Require a concrete visual morphology, not just a generic anomaly claim."""
    text = _normalize_free_text(value)
    if not text or _is_no_defect_evidence_summary(text):
        return False
    return _contains_any_term(text, _EXPLICIT_IMAGE_EVIDENCE_TERMS)


def _is_specific_image_defect_category(value) -> bool:
    label = str(value or "").strip().lower()
    return label not in {"", "none", "unknown", "other", "combined"}


def _default_location_hint(category: Optional[str], side: str) -> str:
    anchor = category or "产品"
    if side == "image":
        return f"{anchor}可见表面区域"
    return f"{anchor}相关区域"


def _default_evidence_summary(
    side: str,
    category: Optional[str],
    location_hint: str,
    risk_type: str,
    defect_category: str,
    severity: str,
) -> str:
    loc = location_hint or _default_location_hint(category, side)
    sev_cn = _SEVERITY_ZH.get(severity, "轻度")
    defect_name = defect_category if defect_category not in _EMPTY_TEXT_VALUES else risk_type
    if defect_name in _EMPTY_TEXT_VALUES:
        defect_name = "异常"
    prefix = "图像显示" if side == "image" else "文本提到"
    return f"{prefix}{loc}存在{sev_cn}{defect_name}。"


def is_valid_bbox(value, width=None, height=None):
    if not isinstance(value, list) or len(value) != 4:
        return False
    try:
        x1, y1, x2, y2 = [float(v) for v in value]
    except (TypeError, ValueError):
        return False
    if min(x1, y1, x2, y2) < 0:
        return False
    if x1 > x2 or y1 > y2:
        return False
    try:
        width_f = float(width) if width is not None else None
        height_f = float(height) if height is not None else None
    except (TypeError, ValueError):
        width_f = None
        height_f = None
    if width_f is not None and x2 > width_f:
        return False
    if height_f is not None and y2 > height_f:
        return False
    return True


def _is_zero_bbox(value) -> bool:
    """Return whether bbox is the normalized empty box."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False


def _has_valid_nonzero_bbox(value, width=None, height=None) -> bool:
    if not is_valid_bbox(value, width=width, height=height):
        return False
    if _is_zero_bbox(value):
        return False
    try:
        x1, y1, x2, y2 = [float(item) for item in value]
    except (TypeError, ValueError):
        return False
    return x2 > x1 and y2 > y1


def _has_defect_signal(
    risk_type: str,
    severity: str,
    defect_category: str,
    location_hint: str,
    evidence_summary: str,
    bbox: Optional[list[int]] = None,
) -> bool:
    if risk_type != "none":
        return True
    if severity in ("low", "medium", "high"):
        return True
    if defect_category not in ("none", "", "null", "unknown"):
        return True
    if not _is_empty_location(location_hint):
        return True
    if str(evidence_summary or "").strip():
        return True
    if bbox is not None and bbox != [0, 0, 0, 0]:
        return True
    return False


def _has_strong_image_defect_signal(
    defect_category: str,
    evidence_summary: str,
    bbox: Optional[list[int]] = None,
    confidence: Optional[float] = None,
) -> bool:
    # Keep No->Yes repairs conservative, but do not require a single narrow
    # pattern. Subtle but real defects may surface as:
    #   1) localized bbox + explicit morphology evidence
    #   2) localized bbox + specific category + medium confidence
    #   3) explicit morphology evidence + specific category + high confidence
    has_bbox = False
    if bbox is not None and is_valid_bbox(bbox) and not _is_zero_bbox(bbox):
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
            has_bbox = x2 > x1 and y2 > y1
        except (TypeError, ValueError):
            has_bbox = False
    has_evidence = _has_explicit_image_evidence_summary(evidence_summary)
    has_specific_category = _is_specific_image_defect_category(defect_category)
    try:
        confidence_value = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence_value = 0.0
    return bool(
        (has_bbox and has_evidence)
        or (has_bbox and has_specific_category and confidence_value >= 0.55)
        or (has_evidence and has_specific_category and confidence_value >= 0.75)
    )


def _image_category_prompt_hint(category: Optional[str]) -> str:
    key = str(category or "").strip().lower()
    hint = _IMAGE_CATEGORY_PROMPT_HINTS.get(key, "")
    if not hint:
        return ""
    return f"【类别专属提示】\n{hint}\n\n"


def _infer_defect_category(
    category: Optional[str],
    raw_value,
    evidence_summary: str,
) -> str:
    normalized = normalize_defect_category(category, raw_value)
    if normalized != "none":
        return normalized
    inferred = normalize_defect_category(category, evidence_summary)
    if inferred != "none":
        return inferred
    text = _normalize_free_text(evidence_summary)
    for alias, hints in _DEFECT_ALIAS_HINTS.items():
        if _contains_any_term(text, hints):
            inferred = normalize_defect_category(category, alias)
            if inferred != "none":
                return inferred
    return inferred if inferred != "none" else "none"


def _infer_image_risk_type(
    category: Optional[str],
    raw_risk_type,
    defect_category,
    evidence_summary: str,
) -> str:
    risk_type = normalize_risk_type(raw_risk_type)
    # ``none`` is a valid enum value but means "not inferred" here.  Returning
    # it early prevented category/evidence based risk inference entirely.
    if risk_type != "none":
        return risk_type

    try:
        from _qdl_defect_ontology import infer_semantic_profile
    except ImportError:
        infer_semantic_profile = None
    if infer_semantic_profile is not None:
        profile = infer_semantic_profile(
            defect_category,
            description=evidence_summary,
            product_category=category,
        )
        inferred_risk = str(profile.get("risk_type", "none"))
        if inferred_risk in RISK_TYPE_ENUM and inferred_risk != "none":
            return inferred_risk

    canonical_defect = normalize_defect_category(category, defect_category)
    if canonical_defect == "none":
        canonical_defect = normalize_defect_category(category, evidence_summary)
    return _IMAGE_DEFECT_TO_RISK_TYPE.get(canonical_defect, "none")


def _copy_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items()}


def _tracked_view(payload: dict, side: str) -> dict:
    fields = _IMAGE_TRACKED_FIELDS if side == "image" else _TEXT_TRACKED_FIELDS
    view = {}
    for field in fields:
        if field in payload:
            view[field] = payload.get(field)
    return view


def _build_normalization_debug(raw_payload: dict, normalized_payload: dict, side: str) -> dict:
    raw_view = _tracked_view(raw_payload, side)
    normalized_view = _tracked_view(normalized_payload, side)
    changed_fields = [
        field for field in normalized_view
        if raw_view.get(field) != normalized_view.get(field)
    ]
    raw_has_defect = normalize_has_defect_label(
        raw_view.get("has_defect"), default=""
    )
    normalized_has_defect = normalize_has_defect_label(
        normalized_view.get("has_defect"), default=""
    )
    raw_bbox = raw_view.get("bbox", [0, 0, 0, 0]) if side == "image" else None
    normalized_bbox = normalized_view.get("bbox", [0, 0, 0, 0]) if side == "image" else None
    raw_bbox_invalid = bool(
        side == "image"
        and not is_valid_bbox(raw_bbox, width=1000, height=1000)
    )
    bbox_rescaled = bool(
        side == "image"
        and is_valid_bbox(raw_bbox, width=1000, height=1000)
        and is_valid_bbox(normalized_bbox)
        and raw_bbox != normalized_bbox
        and not _is_zero_bbox(raw_bbox)
        and not _is_zero_bbox(normalized_bbox)
    )
    bbox_missing = bool(
        side == "image"
        and normalized_has_defect == "Yes"
        and (
            not is_valid_bbox(normalized_bbox)
            or normalized_bbox == [0, 0, 0, 0]
        )
    )
    bbox_repaired = bool(
        side == "image"
        and "bbox" in changed_fields
        and normalized_bbox != [0, 0, 0, 0]
        and raw_bbox_invalid
    )
    inferred_fields = []
    repair_reason = []
    for field in changed_fields:
        if field in {"risk_type", "defect_category", "location_hint", "evidence_summary"}:
            inferred_fields.append(field)
        if field == "has_defect":
            repair_reason.append("defect_signal_consistency")
        elif field == "bbox":
            repair_reason.append("bbox_normalization_or_repair")
        elif field in {"risk_type", "defect_category"}:
            repair_reason.append("enum_normalization_or_inference")
        elif field in {"severity", "confidence", "emotion_intensity"}:
            repair_reason.append("value_range_normalization")
    if not repair_reason and changed_fields:
        repair_reason.append("field_normalization")
    return {
        "raw_response": raw_view,
        "normalized_response": normalized_view,
        "changed_fields": changed_fields,
        "normalization_applied": bool(changed_fields),
        "flip_no_to_yes": raw_has_defect == "No" and normalized_has_defect == "Yes",
        "bbox_rescaled": bbox_rescaled,
        "bbox_repaired": bbox_repaired,
        "bbox_missing": bbox_missing,
        "bbox_invalid_raw": raw_bbox_invalid,
        "raw_has_defect": raw_view.get("has_defect"),
        "normalized_has_defect": normalized_view.get("has_defect"),
        "inferred_fields": sorted(set(inferred_fields)),
        "repair_reason": sorted(set(repair_reason)),
    }


def _repair_json_response(models, raw_output: str, side: str) -> tuple[Optional[dict], str]:
    """对无法解析的生成结果进行一次格式专用重试，不重新解释内容。"""
    if not raw_output:
        return None, ""
    schema = (
        '{"has_defect":"Yes|No","risk_type":"...","severity":"none|low|medium|high",'
        '"location_hint":"...","evidence_summary":"...","defect_category":"...",'
        '"confidence":0.0,"bbox":[0,0,0,0]}'
    ) if side == "image" else (
        '{"has_defect":"Yes|No","risk_type":"...","severity":"none|low|medium|high",'
        '"location_hint":"...","evidence_summary":"...","defect_category":"...",'
        '"confidence":0.0,"emotion_label":"neutral","emotion_intensity":0.0}'
    )
    prompt = (
        "将下面模型输出仅转换为一个合法 JSON 对象。保留原意，不增加任何新判断；"
        "不得输出 Markdown、解释文字或额外字段。字段格式参考：" + schema + "\n"
        "模型输出：\n" + str(raw_output)[:4000]
    )
    repaired_raw = _llm_text_inference(models, prompt, max_new_tokens=192)
    return _parse_json_from_text(repaired_raw), repaired_raw


def _has_required_json_shape(obj: dict, side: str) -> bool:
    """只检查结构，不判断字段语义；语义校验留给归一化和 audit 层。"""
    if not isinstance(obj, dict):
        return False
    required = (
        ["has_defect", "risk_type", "severity", "location_hint",
         "evidence_summary", "defect_category", "confidence", "bbox"]
        if side == "image" else
        ["has_defect", "risk_type", "severity", "location_hint",
         "evidence_summary", "defect_category", "confidence",
         "emotion_label", "emotion_intensity"]
    )
    return all(field in obj for field in required)


def _extract_image_confidence(raw_obj: dict, normalized_payload: dict) -> float:
    try:
        return max(0.0, min(1.0, float(raw_obj.get("confidence", 0.3))))
    except (TypeError, ValueError, AttributeError):
        sev_to_conf = {"none": 0.3, "low": 0.5, "medium": 0.7, "high": 0.9}
        return sev_to_conf.get(normalized_payload.get("severity", "none"), 0.3)


def _finalize_image_pass(
    raw_obj: Optional[dict],
    raw_text: str,
    category: str,
    width: int,
    height: int,
) -> dict:
    fallback = {
        "has_defect": "No",
        "bbox": [0, 0, 0, 0],
        "severity": "none",
        "description": "",
        "risk_type": "none",
        "defect_category": "none",
        "location_hint": "",
        "evidence_summary": "",
        "confidence": 0.3,
        "emotion_label": "neutral",
        "emotion_intensity": 0.0,
    }
    obj = raw_obj if isinstance(raw_obj, dict) else {}
    normalized = _normalize_structured_core(
        obj if obj else fallback,
        category=category,
        side="image",
        width=width,
        height=height,
    )
    confidence = _extract_image_confidence(obj, normalized)
    result = {
        "has_defect": normalized["has_defect"],
        "bbox": normalized["bbox"],
        "severity": normalized["severity"],
        "description": normalized["evidence_summary"],
        "risk_type": normalized["risk_type"],
        "defect_category": normalized["defect_category"],
        "location_hint": normalized["location_hint"],
        "evidence_summary": normalized["evidence_summary"],
        "confidence": confidence,
        "emotion_label": "neutral",
        "emotion_intensity": 0.0,
    }
    debug_info = _build_normalization_debug(obj, result, side="image")
    result["raw_response_text"] = raw_text[:1000]
    result.update(debug_info)
    return result


def _normalize_structured_core(
    payload: dict,
    category: Optional[str],
    side: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> dict:
    result = {}

    risk_type = normalize_risk_type(payload.get("risk_type", "none"))
    if side == "image" and risk_type == "none":
        inferred_risk_type = _infer_image_risk_type(
            category,
            payload.get("risk_type", "none"),
            payload.get("defect_category", "none"),
            payload.get("evidence_summary", ""),
        )
        if inferred_risk_type in RISK_TYPE_ENUM:
            risk_type = inferred_risk_type
    result["risk_type"] = risk_type

    severity = str(payload.get("severity", "none")).strip().lower()
    if severity not in SEVERITY_MAP:
        severity = "none"
    result["severity"] = severity

    if side == "image":
        result["defect_category"] = _infer_defect_category(
            category,
            payload.get("defect_category", "none"),
            payload.get("evidence_summary", ""),
        )
    else:
        result["defect_category"] = normalize_defect_category(
            category, payload.get("defect_category", "none")
        )

    location_hint = str(payload.get("location_hint", "")).strip()
    evidence_summary = str(payload.get("evidence_summary", "")).strip()
    if _is_placeholder_text(evidence_summary):
        evidence_summary = ""

    bbox = None
    if side == "image":
        bbox = denormalize_bbox(payload.get("bbox", [0, 0, 0, 0]), width, height, max_coord=1000)

    hd_raw = normalize_has_defect_label(payload.get("has_defect"))
    signal_present = _has_defect_signal(
        result["risk_type"],
        result["severity"],
        result["defect_category"],
        location_hint,
        evidence_summary,
        bbox=bbox,
    )
    if side == "image":
        strong_signal_present = _has_strong_image_defect_signal(
            result["defect_category"],
            evidence_summary,
            bbox=bbox,
            confidence=payload.get("confidence"),
        )
        if hd_raw not in ("Yes", "No"):
            has_defect = "Yes" if strong_signal_present else "No"
        else:
            # 显式 Yes/No 属于模型语义判断。归一化阶段不再根据证据字段
            # 擅自翻转 No；漏报修正统一交给 pipeline 的二次视觉复核。
            has_defect = hd_raw
    else:
        if hd_raw not in ("Yes", "No"):
            has_defect = "Yes" if signal_present else "No"
        else:
            has_defect = hd_raw

    if has_defect == "No":
        result["has_defect"] = "No"
        result["risk_type"] = "none"
        result["severity"] = "none"
        result["defect_category"] = "none"
        result["location_hint"] = ""
        result["evidence_summary"] = ""
        if side == "image":
            result["bbox"] = [0, 0, 0, 0]
        return result

    if result["risk_type"] == "none":
        result["risk_type"] = "quality_defect"
    if result["severity"] == "none":
        result["severity"] = "low"
    if _is_empty_location(location_hint):
        location_hint = _default_location_hint(category, side)
    if side == "image" and _is_no_defect_evidence_summary(evidence_summary):
        evidence_summary = ""
    if side == "image" and result["defect_category"] == "none":
        result["defect_category"] = _infer_defect_category(
            category,
            payload.get("defect_category", "none"),
            evidence_summary,
        )
    if not evidence_summary:
        evidence_summary = _default_evidence_summary(
            side,
            category,
            location_hint,
            result["risk_type"],
            result["defect_category"],
            result["severity"],
        )

    result["has_defect"] = "Yes"
    result["location_hint"] = location_hint
    result["evidence_summary"] = evidence_summary
    if side == "image":
        result["bbox"] = bbox
    return result


# =====================================================
# 1. 子模块 3：结构化文本生成（核心 8 字段 + has_defect）
# =====================================================

def generate_structured_text(models: StructuredPipelineModels,
                              raw_text: str,
                              candidates: list[str],
                              retrieved_docs: list[dict],
                              emotion_label: str,
                              emotion_intensity: float,
                              category: str = None) -> dict:
    """
    生成工程内部文本 schema：
      has_defect + 开题报告核心 8 字段。
    失败时返回兜底 JSON（risk_type=none, confidence=0.0）。
    """
    kb_context = ""
    if retrieved_docs:
        kb_lines = []
        for doc in retrieved_docs[:3]:
            kb_lines.append(
                f"- [{doc['category']}/{doc['defect_type']}] "
                f"{doc['defect_desc']} 判别标准：{doc['criteria']}"
            )
        kb_context = "\n".join(kb_lines)
    allowed_defect_categories = format_allowed_defect_categories(category)

    prompt = (
        "你是工业质检术语转换专家。请基于以下输入生成结构化风险语义 JSON。\n\n"
        f"【原始投诉】{raw_text}\n"
        f"【候选风险类型】{candidates}\n"
        f"【检索到的标准条款】\n{kb_context if kb_context else '（无检索结果）'}\n"
        f"【情感预检】{emotion_label}（强度 {emotion_intensity:.2f}）\n\n"
        f"【缺陷类别标准词表】{allowed_defect_categories}\n\n"
        "请输出以下 JSON 字段（所有字段必须输出，只输出 JSON）：\n"
        "{\n"
        '  "has_defect": "<Yes或No>",\n'
        '  "risk_type": "<从候选选1个>",\n'
        '  "severity": "<none/low/medium/high>",\n'
        '  "location_hint": "<自然语言位置>",\n'
        '  "evidence_summary": "<客观证据摘要1-2句>",\n'
        '  "defect_category": "<从标准词表中选1个>",\n'
        '  "confidence": 0.0,\n'
        '  "emotion_label": "<必须复用情感预检>",\n'
        '  "emotion_intensity": 0.0\n'
        "}\n"
        "⚠️ 重要规则：\n"
        "1. has_defect 只能是 Yes 或 No，禁止输出占位符。\n"
        "2. emotion_label / emotion_intensity 只表示用户或文本态度，不表示产品客观状态；"
        "必须复用【情感预检】结果，禁止自行改写成别的情绪。\n"
        "   如果文本只是客观描述缺陷事实、异常现象、检测结论或处理建议，"
        "即使提到破损、裂纹、异常、需要检查，也必须输出 neutral 和 0.0。\n"
        "   只有出现明确抱怨、投诉、退货、担心、焦虑、生气、反话等态度信号时，"
        "才允许输出 dissatisf / worry / anger / anxiety。\n"
        "3. 若 has_defect=No，则必须同时满足：risk_type=none，severity=none，defect_category=none，"
        'location_hint=""，evidence_summary=""。\n'
        "4. 若 has_defect=Yes，则 location_hint 必须非空，evidence_summary 必须非空，"
        "risk_type 不能为 none，severity 不能为 none。\n"
        f"5. defect_category 必须严格从这个集合中选择：[{allowed_defect_categories}]，无缺陷填 none。\n"
        "6. risk_type 只能输出最终合法枚举 "
        "(appearance_abnormality / structural_damage / surface_defect / deformation / contamination / safety_risk / quality_defect / none)，"
        "禁止输出旧写法或中间态；print_defect / color_abnormality / product_quality / product_quality_issue / combined 只能作为理解线索。\n"
        "7. 如果原文没有明确情绪线索，emotion_label 默认输出 neutral，emotion_intensity 默认输出 0.0。\n"
        "8. 如果文本只模糊表达异常，也要输出最保守但自洽的结果，禁止留空或写模板话术。\n"
        '9. 无缺陷且语气平静示例：{"has_defect":"No","risk_type":"none","severity":"none","location_hint":"","evidence_summary":"","defect_category":"none","confidence":0.20,"emotion_label":"neutral","emotion_intensity":0.0}\n'
        '10. 无缺陷但用户不满示例：{"has_defect":"No","risk_type":"none","severity":"none","location_hint":"","evidence_summary":"","defect_category":"none","confidence":0.31,"emotion_label":"dissatisf","emotion_intensity":0.66}\n'
        '11. 有缺陷但只是客观报缺陷示例：{"has_defect":"Yes","risk_type":"quality_defect","severity":"low","location_hint":"瓶口区域","evidence_summary":"文本提到瓶口区域存在裂纹异常。","defect_category":"crack","confidence":0.76,"emotion_label":"neutral","emotion_intensity":0.0}\n'
        '12. 有缺陷且用户担忧示例：{"has_defect":"Yes","risk_type":"quality_defect","severity":"low","location_hint":"瓶口区域","evidence_summary":"文本提到瓶口区域存在裂纹异常。","defect_category":"crack","confidence":0.76,"emotion_label":"worry","emotion_intensity":0.62}\n'
        "只输出 JSON，不要输出其他内容。\n"
        "JSON："
    )
    raw = _llm_text_inference(models, prompt, max_new_tokens=160)
    original_raw = raw
    obj = _parse_json_from_text(raw)
    json_repair_attempted = False
    json_repair_succeeded = False
    if obj is None or not _has_required_json_shape(obj, side="text"):
        json_repair_attempted = True
        obj, repaired_raw = _repair_json_response(models, raw, side="text")
        if obj is not None:
            json_repair_succeeded = True
            repaired_raw_text = repaired_raw or ""

    fallback = {
        "has_defect": "No",
        "risk_type": "none",
        "severity": "none",
        "location_hint": "",
        "evidence_summary": "",
        "defect_category": "none",
        "confidence": 0.0,
        "emotion_label": emotion_label,
        "emotion_intensity": emotion_intensity,
    }
    if not obj:
        normalized_fallback = _normalize_text_emotion_fields(fallback, raw_text)
        fallback_debug = _build_normalization_debug({}, normalized_fallback, side="text")
        fallback["raw_response_text"] = original_raw[:1000]
        fallback["json_repair_response_text"] = repaired_raw_text[:1000] if json_repair_attempted else ""
        fallback["raw_response"] = {}
        fallback["normalized_response"] = _tracked_view(normalized_fallback, "text")
        fallback["changed_fields"] = fallback_debug["changed_fields"]
        fallback["normalization_applied"] = fallback_debug["normalization_applied"]
        fallback["flip_no_to_yes"] = fallback_debug["flip_no_to_yes"]
        fallback["bbox_repaired"] = fallback_debug["bbox_repaired"]
        fallback["json_repair_attempted"] = json_repair_attempted
        fallback["json_repair_succeeded"] = json_repair_succeeded
        fallback.update(fallback_debug)
        fallback.update(normalized_fallback)
        return fallback

    # A repaired object is not a raw model object; keep it separate so raw
    # schema metrics continue to expose the original parse failure.
    raw_structured = {} if json_repair_attempted else _copy_payload(obj)
    result = fallback.copy()
    for f in STRUCTURED_SCHEMA_FIELDS:
        if f in obj:
            result[f] = obj[f]

    normalized = _normalize_structured_core(result, category=category, side="text")
    result.update(normalized)

    # 数值范围校验
    try:
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
    except (TypeError, ValueError):
        result["confidence"] = 0.0

    # 文本侧情感字段锁定为预检结果，避免结构化生成二次漂移。
    result["emotion_label"] = emotion_label if emotion_label in EMOTION_ENUM else "neutral"
    try:
        result["emotion_intensity"] = max(0.0, min(1.0, float(emotion_intensity)))
    except (TypeError, ValueError):
        result["emotion_intensity"] = 0.0
    result = _normalize_text_emotion_fields(result, raw_text)

    debug_info = _build_normalization_debug(raw_structured, result, side="text")
    result["raw_response_text"] = original_raw[:1000]
    result["json_repair_response_text"] = repaired_raw_text[:1000] if json_repair_attempted else ""
    if json_repair_attempted:
        result["repaired_response"] = dict(obj)
    result["json_repair_attempted"] = json_repair_attempted
    result["json_repair_succeeded"] = json_repair_succeeded
    result.update(debug_info)

    return result


# =====================================================
# 2. 子模块 4：置信度二档路由
# =====================================================

def confidence_routing(models: StructuredPipelineModels,
                        structured_json: dict,
                        raw_text: str,
                        candidates: list[str],
                        ambiguity_score: float,
                        emotion_label: str,
                        emotion_intensity: float,
                        enable: bool = True,
                        category: str = None,
                        visual_candidates: list[str] = None,
                        rag_strategy: str = "legacy") -> dict:
    """
    confidence ≥ 0.7 → 直接返回
    confidence < 0.7 → 触发一次二次检索（扩大 top-k）+ 重新生成
    enable=False 时直接返回原 JSON。
    """
    if not enable:
        return structured_json

    if structured_json.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD:
        return structured_json

    retrieved = adaptive_retrieve(
        models, raw_text, candidates, ambiguity_score,
        enable=models.is_rag_ready(),
        force_k=RETRIEVE_K_LOW_CONF,
        category=category,
        visual_candidates=visual_candidates,
        strategy=rag_strategy,
        retrieval_stage="confidence_reroute",
    )
    new_structured = generate_structured_text(
        models, raw_text, candidates, retrieved,
        emotion_label, emotion_intensity,
        category=category,
    )
    new_structured["_rerouted"] = True
    if rag_strategy != "legacy":
        new_structured["_rerouted_retrieved_docs"] = retrieved
        new_structured["_rerouted_rag_trace"] = dict(
            getattr(models, "last_rag_trace", {}) or {}
        )
    return new_structured


# =====================================================
# 3. VLM 图像侧 JSON 生成（VLM 原始 8 字段 + 运行时标准化）
# =====================================================

def generate_image_side_json(models: StructuredPipelineModels,
                              img_path: str,
                              category: str,
                              width: int, height: int,
                              text_structured: dict = None,
                              retrieved_docs: list = None,
                              inject_text_context: bool = True,
                              inject_rag_context: bool = True,
                              ref_img_path: Optional[str] = None,
                              recheck_hint: str = "") -> dict:
    """
    VLM 原始输出 8 字段 JSON（与微调 prompt 一致），移除 LLM 后处理。

    统一支持：
      - 0-shot 单图：仅输入测试图
      - 1-shot 双图：第 1 张参考正常图，第 2 张待测图

    两种输入协议复用完全相同的 8 字段后处理（Bug 1 + Bug 2 修复）。

    口径说明：
      1. VLM 原始输出：has_defect / risk_type / severity / defect_category /
         location_hint / evidence_summary / confidence / bbox
      2. 运行时标准化后补齐 emotion_label=neutral, emotion_intensity=0.0
      3. 最终图像侧对象是：has_defect + 开题报告核心 8 字段 + bbox
      4. Bug 1 修复：占位符检测 + 兜底描述生成
      5. Bug 2 修复：has_defect 与其他字段一致性校验

    视觉 Prompt 的文本结构化结果和 RAG 条款可分别注入，便于隔离实验：
    - inject_text_context=True：注入文本侧 risk_type / evidence_summary
    - inject_rag_context=True：注入检索到的标准条款
    """
    # ── 构建 VLM prompt ──
    # 注入策略：旁路参考而非强引导
    context_block = ""
    context_lines = []
    if (
        inject_text_context
        and text_structured
        and text_structured.get("risk_type", "none") != "none"
    ):
        context_risk_type = normalize_risk_type(text_structured.get("risk_type", "unknown"))
        context_lines.extend([
            f"【操作员反馈（仅供参考，判断以视觉证据为准）】",
            f"风险类型（已转换为最终枚举）: {context_risk_type}",
            f"证据摘要: {text_structured.get('evidence_summary', '')}",
        ])
    if inject_rag_context and retrieved_docs:
        doc = retrieved_docs[0]
        context_lines.append(f"参考标准: {doc.get('defect_desc', '')}")
    context_block = (
        "\n".join(context_lines) + "\n\n" if context_lines else ""
    )
    recheck_block = (
        "【二次视觉复核】\n"
        "首轮结果未确认缺陷，但文本侧存在明确缺陷线索。请重新逐区域检查测试图，"
        "优先核对细小、低对比度、局部缺口/裂纹/污染/变形；只有看到真实形态证据时才改为 Yes，"
        "若仍无可见异常则保持 No。\n\n"
        if recheck_hint else ""
    )

    allowed_defect_categories = format_allowed_defect_categories(category)
    risk_mapping_block = (
        "risk_type 与 defect_category 不是一回事，必须按下面规则填写：\n"
        "- crack / scratch / cut / surface_damage -> surface_defect\n"
        "- broken / hole / missing_part -> structural_damage\n"
        "- contamination / liquid -> contamination\n"
        "- deformation / misalignment -> deformation\n"
        "- 观察到颜色、印刷或外观呈现异常 -> appearance_abnormality\n"
        "- 缺陷确实存在但无法归入以上风险形态 -> quality_defect\n"
        "- defect_category=combined 只表示多个已分别确认的视觉缺陷，绝不能写入 risk_type。\n"
        "risk_type 是最终输出字段，不是自由描述字段；必须逐字输出上述合法枚举之一。"
        "不要把缺陷类别、数据集标签或自然语言描述直接复制到 risk_type。\n"
        "缺陷类别收口规则：必须先判视觉形态，再选 defect_category。先判断是裂/孔/断/缺/污/歪/弯/锈/磨/印刷异常中的哪一种，再映射到具体类别；不要先决定类别再编证据。\n"
        "cut 是严格类别：只有同时观察到刀切状或线性切口、清晰的撕裂/割裂边缘、或明确的切断面/切伤形态时，才允许使用 cut。\n"
        "轮廓模糊、反光、阴影、边缘不齐、局部缺损感或无法确认的破坏，禁止默认写成 cut；破裂、孔洞、裂纹、弯折、污染等应使用对应具体类别。\n"
        "‘露出内部结构’ 只有在确实看到断裂/缺失导致内部暴露时，才可作为 broken / missing_part 的证据，不要直接等同 cut。\n"
        "只有明确观察到两种或以上、且可以分别命名的不同视觉缺陷时，才允许 defect_category=combined；单一裂纹、划痕、孔洞、污染、变形必须输出对应具体类别。\n"
        "other 只能在确实无法归入任何具体类别时使用，不能作为默认兜底。\n"
        "evidence_summary 必须描述实际可见的缺陷形态和位置；禁止使用‘切割类缺陷’、‘产品被切断’、‘多种异常’、‘质量不达标’等没有视觉依据的模板结论。\n"
        "bbox 必须是实际可见缺陷区域的紧致外接框，不是产品整体框；使用 0-1000 归一化坐标，满足 x1<x2、y1<y2。不要复制提示词中的任何坐标。\n"
        "正常样本 bbox 必须为 [0,0,0,0]；缺陷样本 bbox 必须覆盖实际缺陷，多个明确缺陷使用覆盖它们的最小外接框。\n"
    )
    category_focus_block = _image_category_prompt_hint(category)
    visual_decision_block = (
        "检测顺序必须固定为：先判断是否存在真实视觉异常，再描述实际形态和位置，最后选择 defect_category 和 risk_type。\n"
        "只有反光、阴影、正常纹理、自然结构差异或单一模糊线索，且无法复述具体异常形态时，才输出 No。\n"
        "如果能够观察并复述真实的裂缝、缺口、孔洞、缺失、断裂、污染或变形等形态，即使目标较小、细长、低对比度，也应输出 Yes。\n"
        "小目标、低对比度或边界不规整不能单独证明缺陷，但也不能覆盖已经确认的异常形态；先依据形态证据判断，再给出尽可能紧致的 bbox。\n"
        "不能仅凭‘看起来有点不对’、单一反光/阴影、正常纹理或自然弯曲输出 Yes；类别暂时不确定时，应先根据可见形态选择最接近的具体类别，不能因为类别不确定而漏报已经确认的缺陷。\n"
        "若判断为 Yes，必须给出非零有效 bbox 并在 evidence_summary 中描述实际可见形态；只有没有可复述的真实异常时，才输出 No 和 [0,0,0,0]。\n"
    )
    if ref_img_path is not None:
        vlm_prompt = (
            f"你是一名工业质检专家。\n"
            f"第一张图是正常的 {category} 参考样本。\n"
            f"第二张图是需要检测的 {category} 测试样本。\n\n"
            + context_block + recheck_block +
            "判断标准：\n"
            "- 正常产品：表面光滑，无裂纹，无破损，无污染\n"
            "- 缺陷产品：表面有可见损伤，例如裂纹、破口、污染物\n\n"
            "请仔细对比第一张图的正常状态，判断第二张图中的产品是否存在缺陷。\n"
            "注意：操作员反馈仅供参考，你的判断应基于第二张图中的视觉证据。\n"
            f"如表面正常完好，请输出 has_defect 为 No，bbox 为 [0,0,0,0]，risk_type 为 none。\n"
            f"如存在缺陷，请标注第二张图中缺陷区域的归一化坐标"
            f"（范围 0-1000，图像尺寸映射为 {width}x{height}）。\n\n"
            + visual_decision_block
            + risk_mapping_block +
            category_focus_block +
            "\n"
            "⚠️ 字段填写要求（必须严格遵守）：\n"
            '- 若 has_defect=No，则必须输出：risk_type="none", severity="none", defect_category="none", '
            'location_hint="", evidence_summary="", confidence=0-1 数值, bbox=[0,0,0,0]\n'
            "- 若 has_defect=Yes，则 location_hint 必须非空，evidence_summary 必须是图像中的客观可见证据，bbox 必须为非零框\n"
            "- evidence_summary 禁止输出占位符、模板句、推测性表述\n"
            "- evidence_summary 必须写出具体视觉证据（缺陷类型+位置或形态），禁止只写‘多种异常’、‘质量不达标’等笼统结论\n"
            "- confidence 为必填浮点数，范围 0-1，表示‘存在视觉缺陷’的概率；无论 has_defect 是 Yes 还是 No 都必须输出\n"
            "- risk_type 必须从枚举中选 1 个，且只能输出 appearance_abnormality / structural_damage / surface_defect / deformation / contamination / safety_risk / quality_defect / none；"
            "has_defect=Yes 时不能为 none，也不能输出任何不在该枚举中的标签\n"
            f"- defect_category 必须严格从这个集合中选 1 个：[{allowed_defect_categories}]，无缺陷填 none\n"
            "- 单一裂纹/划痕/孔洞/污染/变形必须使用具体类别；只有两种或以上不同缺陷均有明确视觉证据时才可使用 combined；other 不是默认兜底\n"
            "- 若缺陷位置不够精确，也要给出概括性位置，如'瓶口区域'、'中部表面区域'\n\n"
            f"risk_type 枚举：{RISK_TYPE_ENUM}\n\n"
            "只输出 JSON，不要输出任何其他内容。字段必须严格包含：has_defect、risk_type、severity、defect_category、location_hint、evidence_summary、confidence、bbox。\n"
            "Yes 样本的 bbox 必须根据第二张图实际缺陷逐点填写，禁止复制提示词或记忆中的固定坐标；只有确认无可见异常时才使用 [0,0,0,0]。\n"
            "JSON："
        )
        raw = _vlm_image_inference_batch_dual(
            models,
            [ref_img_path],
            [img_path],
            [vlm_prompt],
            max_new_tokens=320,
            batch_size=1,
        )[0]
    else:
        vlm_prompt = (
            f"你是一名工业质检专家，请仔细观察这张 {category} 图像。\n\n"
            + context_block + recheck_block +
            "判断标准：\n"
            "- 正常产品：表面光滑，无裂纹，无破损，无污染\n"
            "- 缺陷产品：表面有可见损伤，例如裂纹、破口、污染物\n\n"
            "请根据图像中的视觉证据判断产品是否存在缺陷。\n"
            "注意：操作员反馈仅供参考，你的判断应基于视觉证据。\n"
            f"如表面正常完好，请输出 has_defect 为 No，bbox 为 [0,0,0,0]，risk_type 为 none。\n"
            f"如存在缺陷，请标注缺陷区域的归一化坐标（范围 0-1000，图像尺寸映射为 {width}x{height}）。\n\n"
            + visual_decision_block
            + risk_mapping_block +
            category_focus_block +
            "\n"
            "⚠️ 字段填写要求（必须严格遵守）：\n"
            '- 若 has_defect=No，则必须输出：risk_type="none", severity="none", defect_category="none", '
            'location_hint="", evidence_summary="", confidence=0-1 数值, bbox=[0,0,0,0]\n'
            "- 若 has_defect=Yes，则 location_hint 必须非空，evidence_summary 必须是图像中的客观可见证据，bbox 必须为非零框\n"
            "- evidence_summary 禁止输出占位符、模板句、推测性表述\n"
            "- evidence_summary 必须写出具体视觉证据（缺陷类型+位置或形态），禁止只写‘多种异常’、‘质量不达标’等笼统结论\n"
            "- confidence 为必填浮点数，范围 0-1，表示‘存在视觉缺陷’的概率；无论 has_defect 是 Yes 还是 No 都必须输出\n"
            "- risk_type 必须从枚举中选 1 个，且只能输出 appearance_abnormality / structural_damage / surface_defect / deformation / contamination / safety_risk / quality_defect / none；"
            "has_defect=Yes 时不能为 none，也不能输出任何不在该枚举中的标签\n"
            f"- defect_category 必须严格从这个集合中选 1 个：[{allowed_defect_categories}]，无缺陷填 none\n"
            "- 单一裂纹/划痕/孔洞/污染/变形必须使用具体类别；只有两种或以上不同缺陷均有明确视觉证据时才可使用 combined；other 不是默认兜底\n"
            "- 若缺陷位置不够精确，也要给出概括性位置，如'瓶口区域'、'中部表面区域'\n\n"
            f"risk_type 枚举：{RISK_TYPE_ENUM}\n\n"
            "只输出 JSON，不要输出任何其他内容。字段必须严格包含：has_defect、risk_type、severity、defect_category、location_hint、evidence_summary、confidence、bbox。\n"
            "Yes 样本的 bbox 必须根据图像实际缺陷逐点填写，禁止复制提示词或记忆中的固定坐标；只有确认无可见异常时才使用 [0,0,0,0]。\n"
            "JSON："
        )
        raw = _vlm_image_inference(models, img_path, vlm_prompt, max_new_tokens=320)
    original_raw = raw
    obj = _parse_json_from_text(raw)
    json_repair_attempted = False
    json_repair_succeeded = False
    if obj is None or not _has_required_json_shape(obj, side="image"):
        json_repair_attempted = True
        obj, repaired_raw = _repair_json_response(models, raw, side="image")
        if obj is not None:
            json_repair_succeeded = True
            repaired_raw_text = repaired_raw or ""
    result = _finalize_image_pass(obj, original_raw, category, width, height)
    result["json_repair_attempted"] = json_repair_attempted
    result["json_repair_succeeded"] = json_repair_succeeded
    result["json_repair_response_text"] = repaired_raw_text[:1000] if json_repair_attempted else ""
    if json_repair_attempted:
        # repaired_response is usable for normalized inference, but must not
        # be mistaken for the original raw VLM object in audit consumers.
        result["repaired_response"] = dict(obj) if isinstance(obj, dict) else {}
        result["raw_response"] = {}
    return result
