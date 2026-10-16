"""Conservative local extraction: candidates are review material, never rules.

The parser deliberately keeps a clause as a candidate only when it contains an
executable-looking requirement.  It labels the candidate's role so equipment,
method conditions and explanatory prose do not appear as product indicators.
"""
import re
import unicodedata
import uuid

HEADING = re.compile(r"^\s*(\d+(?:\.\d+){0,5})\s+(.{0,160})$")
REQUIREMENT = re.compile(r"应|不得|不应|不大于|不小于|至少|至多|范围|限值|≤|≥|±|质量比|分度值|温度|时间|长度|直径|高度|质量|尺寸")
METHOD = re.compile(r"仪器设备|试验设备|试验步骤|测试步骤|试验条件|环境条件|水槽|干燥箱|钢直尺|游标卡尺|量筒|天平|照度计|试样数量|抽取")
EXPLANATORY = re.compile(r"范围|规范性引用文件|术语和定义|原理|试验报告|报告应至少包含")
_UNIT_TOKEN = r"(?:mm|cm|mL|ml|min|h|℃|°C|g|kg|lx|km/h|MPa|N|%)"
NUMERIC = re.compile(
    rf"(?:\d+(?:\.\d+)?\s*{_UNIT_TOKEN}?\s*(?:±|~|～|至)\s*\d+(?:\.\d+)?\s*{_UNIT_TOKEN}?|"
    rf"[<>≤≥]=?\s*\d+(?:\.\d+)?\s*{_UNIT_TOKEN}?|"
    rf"\d+(?:\.\d+)?\s*{_UNIT_TOKEN}|\d+\s*[:：]\s*\d)",
    re.I,
)
UNIT = re.compile(rf"(?:{_UNIT_TOKEN}|%|±|~|～|至|：|:)", re.I)


def _normalise_ocr(text: str) -> str:
    """Only normalize typography; never infer a broken number or unit."""
    return (text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        .replace("−", "-").replace("－", "-").replace("～", "~").replace("：", ":"))


def _heading_match(line: str):
    """Match ASCII and full-width clause numbering without changing source text."""
    return HEADING.match(unicodedata.normalize("NFKC", str(line or "")))


def _candidate_confidence(text: str, role: str) -> float:
    score = 0.45
    if NUMERIC.search(text): score += 0.25
    if UNIT.search(text): score += 0.12
    if role == "method_condition": score += 0.08
    if role == "body_clause": score -= 0.08
    return round(max(0.0, min(score, 0.99)), 2)


def extract_candidates(pages: list[dict]) -> list[dict]:
    candidates = []
    blocks = []
    clause, title, start_page = "", "", None
    current = []
    for page in pages:
        page_number = int(page["page_number"])
        lines = str(page.get("text") or "").splitlines()
        for line in lines:
            match = _heading_match(line)
            if match:
                if current and clause:
                    blocks.append((clause, title, "\n".join(current), start_page))
                clause, title = match.groups()
                start_page = page_number
                current = [line]
            elif clause:
                current.append(line)
    if current and clause:
        blocks.append((clause, title, "\n".join(current), start_page))
    for number, heading, text, source_page in blocks:
        if not text.strip() or not REQUIREMENT.search(text):
            continue
        # Do not infer the first number as a limit or flatten specification tables.
        p = int(source_page or 1)
        cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"candidate-v1:{p}:{number}:{text}"))
        role = "method_condition" if METHOD.search(text) else "body_clause" if EXPLANATORY.search(text) and not NUMERIC.search(text) else "inspection_requirement"
        normalized = _normalise_ocr(text)
        confidence = _candidate_confidence(normalized, role)
        candidates.append({"id": cid, "clause_no": number, "page_number": p, "source_text": text,
            "candidate_type": role, "indicator": heading, "method": "", "conditions": "", "unit": "", "requirement": "",
            "operator": "unresolved", "measurement_key": "", "applicability": "", "status": "pending",
            "extraction_method": "local_clause_candidates_v1", "missing_fields": ["指标与规格分支", "方法", "试验条件", "单位", "限值或文字要求", "测量字段与适用对象"],
            "warning": "原文候选；表格列、跨页内容和OCR数字须对照原PDF核实。" if role == "inspection_requirement" else "这是方法条件或正文候选，不能直接作为产品合格指标。", "reviewed_by": None,
            "ocr_text": text, "normalized_text": normalized, "extraction_confidence": confidence,
            "normalization_notes": "仅做标点和全角字符规范化；未推断缺失数字、单位或符号。"})
    return candidates


def extract_metadata_candidates(pages: list[dict]) -> dict:
    """Header clues for a human to inspect; never evidence of authenticity."""
    result={}
    number=re.compile(r"\bGB\s*(/\s*T)?\s*(\d+(?:\.\d+)?)\s*[-—–]\s*(20\d{2}|19\d{2})",re.I)
    implemented=re.compile(r"(20\d{2}|19\d{2})\s*[-年.]\s*(\d{1,2})\s*[-月.]\s*(\d{1,2})\s*日?\s*实施")
    for page in pages[:3]:
        for raw in str(page.get("text") or "").splitlines():
            line=raw.strip()
            match=number.search(line)
            if match and "standard_no" not in result:
                prefix="GB/T" if match[1] else "GB"
                result["standard_no"]={"value":f"{prefix} {match[2]}-{match[3]}","page_number":page["page_number"],"source_text":line}
                result["standard_level"]={"value":prefix,"page_number":page["page_number"],"source_text":line}
            if "standard_name" not in result and 6<=len(line)<=65 and re.search(r"技术规范|技术要求|试验方法|检验规则|检验方法|安全要求",line) and not re.search(r"\d|见|按照|依据|符合|本文件|本标准",line):
                result["standard_name"]={"value":line,"page_number":page["page_number"],"source_text":line}
            if "publisher" not in result and any(name in line for name in ["国家市场监督管理总局","国家质量监督检验检疫总局","国家标准化管理委员会"]):
                result["publisher"]={"value":line,"page_number":page["page_number"],"source_text":line}
            match=implemented.search(line)
            if match and "effective_from" not in result:
                from datetime import date
                try: value=date(int(match[1]),int(match[2]),int(match[3])).isoformat()
                except ValueError: continue
                result["effective_from"]={"value":value,"page_number":page["page_number"],"source_text":line}
    return result
