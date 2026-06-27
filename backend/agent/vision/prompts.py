from __future__ import annotations


VISION_INSPECTION_JSON_PROMPT = (
    "请对图片做质量视觉检测，并只返回 JSON 对象，不要输出 Markdown。\n"
    "必须包含字段：summary、objects、possible_defects、defects、risk、image_quality、requires_recheck、confidence、"
    "expected_product、observed_product、product_match、product_mismatch_reason。\n"
    "expected_product 是任务要求检测的产品；observed_product 是图片中实际可见的主要产品。"
    "如果图片中的主要对象明显不是 expected_product，product_match 必须为 false，risk 必须为 high，"
    "requires_recheck 必须为 true，并在 product_mismatch_reason 中说明原因。\n"
    "defects 是真实可见且能够定位的缺陷坐标数组；每项格式为 "
    "{\"type\":\"...\",\"confidence\":0.0-1.0,\"bbox\":[x,y,w,h],\"description\":\"...\",\"image_index\":0}。\n"
    "bbox 必须使用相对原图宽高归一化坐标 [x,y,w,h]，范围 0-1，x/y 为左上角，w/h 为宽高。\n"
    "多图时 image_index 使用从 0 开始的图片序号。\n"
    "如果看到异常但无法可靠定位，请把文字放入 possible_defects，并让 defects=[]；不得编造坐标。"
)


def build_vision_inspection_prompt(*, product_id: str | None = None, spec_code: str | None = None) -> str:
    product = str(product_id or "").strip() or "未提供"
    spec = str(spec_code or "").strip() or "未提供"
    return (
        f"任务要求检测的产品 expected_product：{product}\n"
        f"所选检测标准 spec_code：{spec}\n"
        f"{VISION_INSPECTION_JSON_PROMPT}"
    )
