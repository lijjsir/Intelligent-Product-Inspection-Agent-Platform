from __future__ import annotations

from typing import Any


DEFAULT_STRICT_PAPER_TEMPLATE_ID = "cqupt_graduate_thesis_2022"


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
    },
    "cqupt_graduate_thesis_2022": {
        "template_id": "cqupt_graduate_thesis_2022",
        "name": "重庆邮电大学研究生学位论文模板（2022版）",
        "version": "V2.0",
        "description": "基于重庆邮电大学研究生学位论文 Word 模板与写作指南的辅助查非规则。",
        "storage": {
            "bucket": "paper-templates",
            "files": [
                {
                    "role": "word_commented_template",
                    "file_name": "附件1-Word批注版-重庆邮电大学研究生学位论文模板（2022版）V2.0.docx",
                    "object_key": "cqupt/graduate-thesis/2022/word-commented-template.docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
                {
                    "role": "writing_guide",
                    "file_name": "附件4-写作指南-重庆邮电大学研究生学位论文模板（2022版）V2.0.docx",
                    "object_key": "cqupt/graduate-thesis/2022/writing-guide.docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
            ],
        },
        "docx_rules": {
            "required_sections": [
                {
                    "key": "originality_statement",
                    "label": "原创性声明",
                    "aliases": ["独创性声明", "原创性声明"],
                    "severity": "medium",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "authorization_statement",
                    "label": "授权声明",
                    "aliases": ["使用授权书", "授权声明"],
                    "severity": "medium",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "abstract",
                    "label": "摘要",
                    "aliases": ["摘要", "中文摘要"],
                    "severity": "high",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "keywords",
                    "label": "关键词",
                    "aliases": ["关键词", "关键字"],
                    "severity": "medium",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "en_abstract",
                    "label": "英文摘要",
                    "aliases": ["Abstract", "ABSTRACT"],
                    "severity": "high",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "en_keywords",
                    "label": "英文关键词",
                    "aliases": ["Keywords", "Key words"],
                    "severity": "medium",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "toc",
                    "label": "目录",
                    "aliases": ["目录"],
                    "severity": "medium",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "figure_toc",
                    "label": "图目录",
                    "aliases": ["图目录"],
                    "severity": "low",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "table_toc",
                    "label": "表目录",
                    "aliases": ["表目录"],
                    "severity": "low",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "body",
                    "label": "正文",
                    "aliases": ["正文", "引言", "绪论", "研究内容", "实验结果", "结论"],
                    "severity": "medium",
                    "match_mode": "body_between_sections",
                },
                {
                    "key": "references",
                    "label": "参考文献",
                    "aliases": ["参考文献"],
                    "severity": "high",
                    "match_mode": "heading_or_text",
                },
                {
                    "key": "acknowledgements",
                    "label": "致谢",
                    "aliases": ["致谢", "致 謝"],
                    "severity": "medium",
                    "match_mode": "heading_or_text",
                },
            ],
            "section_order": [
                "原创性声明",
                "授权声明",
                "摘要",
                "关键词",
                "ABSTRACT",
                "Keywords",
                "目录",
                "图目录",
                "表目录",
                "正文",
                "参考文献",
                "附录",
                "作者简介",
                "致谢",
            ],
            "toc_required_entries": ["摘要", "ABSTRACT", "图目录", "表目录", "参考文献", "致谢"],
            "page_size_cm": {"width": 21.0, "height": 29.7, "tolerance": 0.2},
            "page_orientation": "portrait",
            "page_margin_cm": {
                "top": 3.0,
                "bottom": 3.0,
                "left": 3.0,
                "right": 3.0,
                "tolerance": 0.2,
            },
            "gutter_cm": {"value": 0.0, "tolerance": 0.1},
            "header_footer": {
                "header_distance_cm": 2.0,
                "footer_distance_cm": 2.0,
                "tolerance": 0.2,
            },
            "abstract_keywords": {
                "min_count": 3,
                "max_count": 5,
                "separators": ["；", ";"],
            },
            "body_font": {
                "zh": "宋体",
                "en": "Times New Roman",
                "size_pt": 12,
            },
            "line_spacing": 1.5,
        },
        "pdf_rules": {
            "required_sections": ["摘要", "关键词", "目录", "参考文献"],
            "limitations": ["PDF 当前仅做文本抽取与结构辅助检查，不做严格版式比对。"],
        },
        "tex_rules": {
            "required_commands": ["title", "author"],
            "required_sections": ["摘要", "参考文献"],
        },
    },
}


def get_paper_template(template_id: str | None) -> dict[str, Any]:
    if template_id and template_id in PAPER_FORMAT_TEMPLATES:
        return PAPER_FORMAT_TEMPLATES[template_id]
    return PAPER_FORMAT_TEMPLATES["generic_cn_thesis"]
