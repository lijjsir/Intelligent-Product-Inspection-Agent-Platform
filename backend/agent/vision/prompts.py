from __future__ import annotations


VISION_INSPECTION_JSON_PROMPT = (
    "请对图片做质量视觉检测，并只返回 JSON 对象，不要输出 Markdown。\n"
    "必须包含字段：summary、objects、possible_defects、defects、risk、image_quality、requires_recheck、confidence。\n"
    "defects 是真实可见且能够定位的缺陷坐标数组；每项格式为 "
    "{\"type\":\"...\",\"confidence\":0.0-1.0,\"bbox\":[x,y,w,h],\"description\":\"...\",\"image_index\":0}。\n"
    "bbox 必须使用相对原图宽高归一化坐标 [x,y,w,h]，范围 0-1，x/y 为左上角，w/h 为宽高。\n"
    "多图时 image_index 使用从 0 开始的图片序号。\n"
    "如果看到异常但无法可靠定位，请把文字放入 possible_defects，并让 defects=[]；不得编造坐标。"
)
