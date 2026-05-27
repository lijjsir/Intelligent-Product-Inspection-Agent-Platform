from __future__ import annotations

from typing import Any


PAPER_FORMAT_TEMPLATES: dict[str, dict[str, Any]] = {
    "generic_cn_thesis": {
        "template_id": "generic_cn_thesis",
        "name": "通用中文论文模板",
        "version": "v1",
        "description": "用于第一版论文查非功能的通用规则集。",
        "docx_rules": {
            "required_sections": ["摘要", "关键词", "参考文献"],
        },
        "tex_rules": {
            "required_commands": ["title", "author"],
            "required_sections": ["摘要", "参考文献"],
        },
    }
}


def get_paper_template(template_id: str | None) -> dict[str, Any]:
    if template_id and template_id in PAPER_FORMAT_TEMPLATES:
        return PAPER_FORMAT_TEMPLATES[template_id]
    return PAPER_FORMAT_TEMPLATES["generic_cn_thesis"]
