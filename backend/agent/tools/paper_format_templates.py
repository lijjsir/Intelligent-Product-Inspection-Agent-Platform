from __future__ import annotations

from typing import Any


DEFAULT_STRICT_PAPER_TEMPLATE_ID = "cqupt_graduate_thesis_2022"

PAPER_FORMAT_TEMPLATE_ALIASES = {
    "cqupt_graduate_2022": DEFAULT_STRICT_PAPER_TEMPLATE_ID,
    "cqupt_2022": DEFAULT_STRICT_PAPER_TEMPLATE_ID,
}


PAPER_FORMAT_TEMPLATES: dict[str, dict[str, Any]] = {
    "generic_cn_thesis": {
        "template_id": "generic_cn_thesis",
        "name": "通用中文论文模板",
        "version": "v1",
        "description": "用于第一版论文查非功能的通用规则集。",
        "rule_basis": {
            "structure.*": "模板规则数据：required_sections。",
            "abstract.*": "模板规则数据：abstract_keywords 与摘要规范。",
            "references.*": "模板规则数据：required_sections.references；参考文献格式按 GB/T 7714 本地规则辅助检查。",
            "text.*": "模板规则数据：文本规范辅助检查。",
            "unsupported.*": "系统能力边界：当前查非支持 docx、pdf、tex。",
        },
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
        "rule_basis": {
            "structure.*": "模板规则数据：docx_rules.required_sections；来源为重庆邮电大学研究生学位论文模板（2022版）章节要求。",
            "template.required_section_missing": "模板规则数据：docx_rules.required_sections；来源为重庆邮电大学研究生学位论文模板（2022版）必备章节要求。",
            "template.page_size_mismatch": "模板规则数据：docx_rules.page_size_cm；来源为重庆邮电大学研究生学位论文模板（2022版）页面设置。",
            "template.margin_mismatch": "模板规则数据：docx_rules.page_margin_cm；来源为重庆邮电大学研究生学位论文模板（2022版）页面设置。",
            "template.header_footer_mismatch": "模板规则数据：docx_rules.header_footer；来源为重庆邮电大学研究生学位论文模板（2022版）页眉页脚设置。",
            "template.cover_has_header_footer": "模板规则数据：docx_rules.header_footer.cover_no_header_footer；来源为重庆邮电大学研究生学位论文模板（2022版）封面设置。",
            "template.body_font_mismatch": "模板规则数据：docx_rules.body_font；来源为重庆邮电大学研究生学位论文模板（2022版）正文格式设置。",
            "template.line_spacing_mismatch": "模板规则数据：docx_rules.line_spacing；来源为重庆邮电大学研究生学位论文模板（2022版）正文段落设置。",
            "template.*": "模板规则数据：docx_rules.required_sections、page_size_cm、page_margin_cm、header_footer、body_font、line_spacing。",
            "toc.required_entry_missing": "模板规则数据：docx_rules.toc_required_entries；来源为重庆邮电大学研究生学位论文模板（2022版）目录条目要求。",
            "abstract.*": "写作指南“中、英文摘要”与模板规则数据 abstract_keywords；关键词数量为 3-8 个，摘要避免图表、公式和参考文献编号。",
            "toc.*": "模板规则数据：docx_rules.toc_required_entries 与 toc_conditional_entries。",
            "heading.*": "模板规则数据：章节层级与正文结构检查。",
            "style.*": "模板规则数据：body_font、line_spacing 与正文段落格式。",
            "figure.*": "模板规则数据：图题/图号与正文引用一致性检查。",
            "table.*": "模板规则数据：表题/表号与正文引用一致性检查。",
            "formula.*": "模板规则数据：公式编号与正文引用一致性检查。",
            "references.*": "写作指南“参考文献和引文标注”：执行 GB/T 7714-2015；引用过的文献必须著录，未引用文献不得虚列。",
            "text.*": "写作指南“字体和段落”：中英文混排标点与全半角规范；文本建议仅作辅助复核。",
            "word.*": "模板提交规范：正式提交稿应清理批注、修订和隐藏文字。",
            "unsupported.*": "系统能力边界：当前查非支持 docx、pdf、tex。",
        },
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
            "toc_conditional_entries": {
                "figure_toc": {"label": "图目录", "single_count_threshold": 5, "combined_count_threshold": 10, "severity": "medium"},
                "table_toc": {"label": "表目录", "single_count_threshold": 5, "combined_count_threshold": 10, "severity": "medium"},
            },
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
                "expected_header_text": "重庆邮电大学硕士学位论文",
                "expected_footer_pattern": "page_number_only",
                "cover_no_header_footer": True,
            },
            "abstract_keywords": {
                "min_count": 3,
                "max_count": 8,
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
    template_id = PAPER_FORMAT_TEMPLATE_ALIASES.get(str(template_id or ""), template_id)
    if template_id and template_id in PAPER_FORMAT_TEMPLATES:
        return PAPER_FORMAT_TEMPLATES[template_id]
    return PAPER_FORMAT_TEMPLATES["generic_cn_thesis"]
