from __future__ import annotations

import sys
import types
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from agent.tools.file_parsers import parse_docx_bytes, parse_pdf_bytes, parse_tex_bytes
from agent.tools import paper_format_checker
from agent.tools.paper_format_checker import check_paper_format
from agent.tools.paper_format_templates import get_paper_template
from app.services.paper_review_runtime_service import PaperReviewDependencyError


def _ready_runtime_status() -> dict:
    return {
        "ok": True,
        "status": "healthy",
        "engines_used": ["enhanced_parser", "macro_correct_token", "macro_correct_punct", "languagetool", "vale"],
        "engine_status": [
            {"name": "docx", "ok": True, "detail": "installed"},
            {"name": "lxml", "ok": True, "detail": "installed"},
            {"name": "macro_correct_token", "ok": True, "detail": "installed"},
            {"name": "macro_correct_punct", "ok": True, "detail": "installed"},
            {"name": "languagetool", "ok": True, "detail": "http://localhost:8010"},
            {"name": "vale", "ok": True, "detail": "vale 3"},
        ],
    }


def _build_docx_bytes() -> bytes:
    doc = Document()
    doc.add_heading("论文标题。", level=1)
    doc.add_paragraph("这是  一个包含连续空格的正文段落，mix punctuation, 需要检查。")
    doc.add_paragraph("关键词：查非；格式检查")
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_parse_docx_bytes_extracts_structure_and_layout():
    parsed = parse_docx_bytes(_build_docx_bytes())

    assert parsed["kind"] == "docx"
    assert parsed["paragraphs"]
    assert parsed["headings"][0]["text"].startswith("论文标题")
    assert "page_layout" in parsed
    assert parsed["section_count"] >= 1


def test_parse_docx_enhanced_extracts_template_check_metadata():
    from agent.tools.paper_docx_parser import parse_docx_enhanced

    parsed = parse_docx_enhanced(_build_docx_bytes())

    assert "orientation" in parsed["page_layout"]
    assert "gutter_cm" in parsed["page_layout"]
    assert "toc_entries" in parsed
    assert "table_titles" in parsed
    assert "formula_numbers" in parsed
    assert "word_metadata" in parsed
    assert "ooxml" in parsed
    assert "style_id" in parsed["paragraphs"][0]
    assert "xml_path" in parsed["paragraphs"][0]
    assert "text_runs" in parsed["paragraphs"][0]
    assert "word_section_index" in parsed["paragraphs"][0]


def test_parse_docx_enhanced_restores_word_numbered_references(monkeypatch):
    from agent.tools.paper_docx_parser import parse_docx_enhanced

    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])

    doc = Document()
    doc.add_heading("摘要", level=1)
    doc.add_paragraph("正文引用[1]和[2]。")
    doc.add_heading("参考文献", level=1)
    doc.add_paragraph("张三. 分布式系统研究[J]. 计算机学报, 2024, 47(1): 1-9.", style="List Number")
    doc.add_paragraph("李四. 通信优化方法[M]. 北京: 科学出版社, 2023.", style="List Number")
    buffer = BytesIO()
    doc.save(buffer)

    parsed = parse_docx_enhanced(buffer.getvalue())

    assert parsed["references"][0].startswith("[1] 张三.")
    assert parsed["references"][1].startswith("[2] 李四.")

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="帮我查非",
        template_id=None,
    )
    issue_codes = {item["code"] for item in report["issues"]}
    assert "references.numbering_missing" not in issue_codes
    assert "references.citation_missing_in_bibliography" not in issue_codes


def test_parse_tex_bytes_extracts_commands_and_sections():
    content = r"""
\documentclass{article}
\title{A Demo Paper}
\author{Tester}
\begin{document}
\maketitle
\section{引言}
这是正文。
\begin{figure}
\end{figure}
\end{document}
""".encode("utf-8")
    parsed = parse_tex_bytes(content)

    assert parsed["kind"] == "tex"
    assert parsed["commands"]["title"] == "A Demo Paper"
    assert parsed["sections"][0]["title"] == "引言"
    assert parsed["figure_count"] == 1


def test_parse_pdf_bytes_extracts_page_evidence(monkeypatch):
    class FakePage:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakePdfReader:
        def __init__(self, stream):
            self.pages = [
                FakePage("1 Introduction\nThis is page one."),
                FakePage("References\n[1] Example source."),
            ]

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakePdfReader))

    parsed = parse_pdf_bytes(b"%PDF-1.7")

    assert parsed["kind"] == "pdf"
    assert parsed["page_count"] == 2
    assert parsed["pages"][0]["page_no"] == 1
    assert parsed["pages"][0]["blocks"][0]["type"] == "text"
    assert parsed["headings"][0]["text"] == "1 Introduction"
    assert parsed["references"] == ["[1] Example source."]
    assert parsed["layout"]["analysis"] == "text_only"


def test_paper_format_checker_has_no_removed_chinese_corrector_entrypoint():
    removed_entrypoint = "_check_" + "py" + "corrector"
    assert not hasattr(paper_format_checker, removed_entrypoint)


def test_check_paper_format_reports_missing_sections_for_docx(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    report = check_paper_format(
        parsed=parse_docx_bytes(_build_docx_bytes()),
        file_name="paper.docx",
        query="帮我查非",
        template_id=None,
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert report["document_type"] == "docx"
    assert report["template_id"] == "generic_cn_thesis"
    assert "structure.abstract_missing" in issue_codes
    assert "text.multiple_spaces" in issue_codes
    assert report["limitations"]
    mixed_issue = next(item for item in report["issues"] if item["code"] == "text.mixed_punctuation")
    assert mixed_issue["evidence"] != "文本中同时出现中文和英文标点组合"
    assert "mix punctuation," in mixed_issue["evidence"]
    assert mixed_issue["location"]["display_text"]
    heading_issue = next(item for item in report["issues"] if item["code"] == "text.heading_trailing_punct")
    assert heading_issue["evidence"] == "论文标题。"
    assert heading_issue["location"]["display_text"]


def test_check_paper_format_reports_fullwidth_ascii_with_exact_location(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n这是ＡBC格式错误。\n关键词：查非",
        "headings": [
            {"text": "摘要", "level": 1, "paragraph_index": 0, "section_index": 1},
        ],
        "paragraphs": [
            {"index": 0, "text": "摘要", "heading_level": 1, "section_title": "摘要", "section_index": 1, "paragraph_no": 0},
            {"index": 1, "text": "这是ＡBC格式错误。", "heading_level": 0, "section_title": "摘要", "section_index": 1, "paragraph_no": 1},
            {"index": 2, "text": "关键词：查非", "heading_level": 0, "section_title": "摘要", "section_index": 1, "paragraph_no": 2},
        ],
        "page_layout": {},
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="帮我查非",
        template_id=None,
    )

    fullwidth_issue = next(item for item in report["issues"] if item["code"] == "text.fullwidth_ascii")
    assert "这是ＡBC格式错误。" == fullwidth_issue["evidence"]
    assert fullwidth_issue["location"]["display_text"] == "第1节《摘要》下第1段"


def test_check_paper_format_reports_tex_limitations():
    parsed = parse_tex_bytes(
        r"""
\documentclass{article}
\title{A Demo Paper}
\author{Tester}
\begin{document}
\maketitle
\section{引言}
\end{document}
""".encode("utf-8")
    )
    report = check_paper_format(
        parsed=parsed,
        file_name="paper.tex",
        query="检查论文格式",
        template_id="generic_cn_thesis",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert report["document_type"] == "tex"
    assert "tex.abstract_missing" in issue_codes
    assert any("LaTeX" in item for item in report["limitations"])


def test_check_macro_correct_uses_batch_detectors(monkeypatch):
    from agent.tools.paper_format_checker import _check_macro_correct

    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_enabled", True)
    monkeypatch.setattr(
        "agent.tools.paper_format_checker.run_macro_correct_token",
        lambda texts: (
            [{"errors": [{"wrong": "錯", "right": "错", "begin": 2, "end": 3, "rule_id": "token"}]}],
            "macro_correct.token",
        ),
    )
    monkeypatch.setattr(
        "agent.tools.paper_format_checker.run_macro_correct_punct",
        lambda texts: (
            [{"errors": [{"wrong": ",", "right": "，", "begin": 5, "end": 6, "rule_id": "punct"}]}],
            "macro_correct.punct",
        ),
    )

    parsed = {
        "paragraphs": [
            {
                "index": 0,
                "text": "这是錯字,示例。",
                "section_title": "摘要",
                "section_index": 1,
                "paragraph_no": 1,
            }
        ]
    }

    issues = _check_macro_correct(parsed)

    assert len(issues) == 2
    assert {item.engine_rule_id for item in issues} == {"macro_correct.token", "macro_correct.punct"}
    assert any(item.actual == {"wrong": "錯", "right": "错"} for item in issues)
    assert any(item.actual == {"wrong": ",", "right": "，"} for item in issues)


def test_check_macro_correct_runs_in_small_batches(monkeypatch):
    from agent.tools.paper_format_checker import _check_macro_correct

    token_batches: list[list[str]] = []
    punct_batches: list[list[str]] = []

    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_enabled", True)
    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_batch_size", 2)

    def fake_token(texts):
        token_batches.append(list(texts))
        return ([{"errors": []} for _ in texts], "macro_correct.token")

    def fake_punct(texts):
        punct_batches.append(list(texts))
        return ([{"errors": []} for _ in texts], "macro_correct.punct")

    monkeypatch.setattr("agent.tools.paper_format_checker.run_macro_correct_token", fake_token)
    monkeypatch.setattr("agent.tools.paper_format_checker.run_macro_correct_punct", fake_punct)

    parsed = {
        "paragraphs": [
            {"index": index, "text": f"这是第 {index} 个中文段落", "paragraph_no": index + 1}
            for index in range(5)
        ]
    }

    assert _check_macro_correct(parsed) == []
    assert [len(batch) for batch in token_batches] == [2, 2, 1]
    assert [len(batch) for batch in punct_batches] == [2, 2, 1]


def test_check_paper_format_raises_when_docx_runtime_unhealthy(monkeypatch):
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync",
        lambda: {
            "ok": False,
            "status": "unhealthy",
            "strict": True,
            "engines_used": ["enhanced_parser", "macro_correct_token", "macro_correct_punct", "languagetool", "vale"],
            "engine_status": [
                {"name": "enhanced_parser", "ok": True, "detail": "python-docx: installed; lxml: installed; PyMuPDF: installed"},
                {"name": "macro_correct_token", "ok": False, "detail": "missing"},
                {"name": "macro_correct_punct", "ok": False, "detail": "missing"},
                {"name": "languagetool", "ok": False, "detail": "connection refused"},
                {"name": "vale", "ok": False, "detail": "missing"},
            ],
        },
    )

    with pytest.raises(PaperReviewDependencyError, match="论文查非增强引擎未就绪"):
        check_paper_format(
            parsed=parse_docx_bytes(_build_docx_bytes()),
            file_name="paper.docx",
            query="帮我查非",
            template_id=None,
        )


def test_check_paper_format_raises_when_runtime_not_ready_for_docx(monkeypatch):
    monkeypatch.setattr(
        "app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync",
        lambda: {
            "ok": False,
            "status": "unhealthy",
            "strict": True,
            "engines_used": ["enhanced_parser", "macro_correct_token", "macro_correct_punct", "languagetool", "vale"],
            "engine_status": [
                {"name": "macro_correct_token", "ok": False, "detail": "missing"},
            ],
        },
    )

    with pytest.raises(PaperReviewDependencyError, match="论文查非增强引擎未就绪"):
        check_paper_format(
            parsed=parse_docx_bytes(_build_docx_bytes()),
            file_name="paper.docx",
            query="帮我查非",
            template_id=None,
        )


def test_cqupt_template_is_registered_with_storage_objects():
    template = get_paper_template("cqupt_graduate_thesis_2022")
    alias_template = get_paper_template("cqupt_graduate_2022")

    assert template["template_id"] == "cqupt_graduate_thesis_2022"
    assert alias_template["template_id"] == "cqupt_graduate_thesis_2022"
    assert template["name"] == "重庆邮电大学研究生学位论文模板（2022版）"
    assert template["storage"]["bucket"] == "paper-templates"
    object_keys = {item["object_key"] for item in template["storage"]["files"]}
    assert "cqupt/graduate-thesis/2022/word-commented-template.docx" in object_keys
    assert "cqupt/graduate-thesis/2022/writing-guide.docx" in object_keys


def test_check_paper_format_reports_cqupt_template_differences(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：查非\n目录\n引言\n正文段落\n参考文献",
        "headings": [
            {"text": "引言", "level": 1, "paragraph_index": 3, "section_index": 1},
            {"text": "参考文献", "level": 1, "paragraph_index": 5, "section_index": 2},
        ],
        "paragraphs": [
            {
                "index": 0,
                "text": "摘要",
                "heading_level": 1,
                "font_name": "宋体",
                "font_size_pt": 12,
                "line_spacing": 1.5,
                "first_line_indent_pt": 0,
                "section_title": "摘要",
                "section_index": 0,
                "paragraph_no": 0,
            },
            {
                "index": 1,
                "text": "关键词：查非",
                "heading_level": 0,
                "font_name": "宋体",
                "font_size_pt": 12,
                "line_spacing": 1.5,
                "first_line_indent_pt": 0,
                "section_title": "摘要",
                "section_index": 0,
                "paragraph_no": 1,
            },
            {
                "index": 2,
                "text": "目录",
                "heading_level": 1,
                "font_name": "宋体",
                "font_size_pt": 12,
                "line_spacing": 1.5,
                "first_line_indent_pt": 0,
                "section_title": "目录",
                "section_index": 0,
                "paragraph_no": 0,
            },
            {
                "index": 3,
                "text": "引言",
                "heading_level": 1,
                "font_name": "黑体",
                "font_size_pt": 12,
                "line_spacing": 1.0,
                "first_line_indent_pt": 0,
                "section_title": "引言",
                "section_index": 1,
                "paragraph_no": 0,
            },
            {
                "index": 4,
                "text": "正文段落",
                "heading_level": 0,
                "font_name": "Arial",
                "font_size_pt": 10.5,
                "line_spacing": 1.0,
                "first_line_indent_pt": 0,
                "section_title": "引言",
                "section_index": 1,
                "paragraph_no": 1,
            },
            {
                "index": 5,
                "text": "参考文献",
                "heading_level": 1,
                "font_name": "黑体",
                "font_size_pt": 12,
                "line_spacing": 1.5,
                "first_line_indent_pt": 0,
                "section_title": "参考文献",
                "section_index": 2,
                "paragraph_no": 0,
            }
        ],
        "page_layout": {
            "top_margin_cm": 2.54,
            "bottom_margin_cm": 2.54,
            "left_margin_cm": 3.18,
            "right_margin_cm": 3.18,
        },
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="按重庆邮电大学模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert report["template_id"] == "cqupt_graduate_thesis_2022"
    assert "template.required_section_missing" in issue_codes
    missing_titles = {item["title"] for item in report["issues"] if item["code"] == "template.required_section_missing"}
    assert "模板要求章节缺失：正文" not in missing_titles
    assert "template.margin_mismatch" in issue_codes
    assert "template.body_font_mismatch" in issue_codes
    assert any("重庆邮电大学" in item for item in report["limitations"])
    font_issue = next(item for item in report["issues"] if item["code"] == "template.body_font_mismatch")
    assert font_issue["location"]["section_title"] == "引言"
    assert "正文样式汇总" in font_issue["location"]["display_text"]
    assert font_issue["actual"]["checked_count"] >= font_issue["actual"]["mismatch_count"] >= 1
    assert font_issue["actual"]["samples"][0]["display_text"] == "第1节《引言》下第1段"
    assert font_issue["actual"]["samples"][0]["text"] == "正文段落"
    assert "正文段落" in font_issue["evidence"]
    assert all(item.get("rule_basis") for item in report["issues"])
    assert all(item.get("location_summary") for item in report["issues"])


def test_check_paper_format_reports_missing_body_when_no_main_text(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：查非\n目录\n参考文献\n致谢",
        "headings": [
            {"text": "摘要", "level": 1, "paragraph_index": 0, "section_index": 0},
            {"text": "目录", "level": 1, "paragraph_index": 2, "section_index": 0},
            {"text": "参考文献", "level": 1, "paragraph_index": 3, "section_index": 1},
        ],
        "paragraphs": [
            {"index": 0, "text": "摘要", "heading_level": 1, "section_title": "摘要", "section_index": 0, "paragraph_no": 0},
            {"index": 1, "text": "关键词：查非", "heading_level": 0, "section_title": "摘要", "section_index": 0, "paragraph_no": 1},
            {"index": 2, "text": "目录", "heading_level": 1, "section_title": "目录", "section_index": 0, "paragraph_no": 0},
            {"index": 3, "text": "参考文献", "heading_level": 1, "section_title": "参考文献", "section_index": 1, "paragraph_no": 0},
            {"index": 4, "text": "致谢", "heading_level": 1, "section_title": "致谢", "section_index": 2, "paragraph_no": 0},
        ],
        "page_layout": {},
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="按重庆邮电大学模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    missing_titles = {item["title"] for item in report["issues"] if item["code"] == "template.required_section_missing"}
    assert "模板要求章节缺失：正文" in missing_titles


def test_check_paper_format_covers_checklist_layout_front_matter_and_word_artifacts(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": (
            "封面\n摘要\n摘要正文引用了图1和[3]。\n关键词：一个，两个\nABSTRACT\nKeywords: one, two\n"
            "目录\n1 绪论\n1.2 研究背景\n正文见图2-1、表2-1和式（2-1）。\n"
            "图2-2 错位图题\n表2-2 错位表题\nE=mc^2 （2-3）\n"
            "参考文献\n[1] 张三. 论文题名[J]. 期刊, 2020.\n[3] 缺少编号二的文献\n"
        ),
        "headings": [
            {"text": "摘要", "level": 1, "paragraph_index": 1, "section_index": 1},
            {"text": "ABSTRACT", "level": 1, "paragraph_index": 4, "section_index": 2},
            {"text": "目录", "level": 1, "paragraph_index": 6, "section_index": 3},
            {"text": "1 绪论", "level": 1, "paragraph_index": 7, "section_index": 4},
            {"text": "1.2 研究背景", "level": 2, "paragraph_index": 8, "section_index": 4},
            {"text": "参考文献", "level": 1, "paragraph_index": 13, "section_index": 5},
        ],
        "paragraphs": [
            {"index": 0, "text": "封面", "heading_level": 0, "section_title": "", "section_index": 0, "paragraph_no": 1},
            {"index": 1, "text": "摘要", "heading_level": 1, "section_title": "摘要", "section_index": 1, "paragraph_no": 0},
            {"index": 2, "text": "摘要正文引用了图1和[3]。", "heading_level": 0, "section_title": "摘要", "section_index": 1, "paragraph_no": 1, "font_name": "宋体", "font_size_pt": 12, "line_spacing": 1.5, "first_line_indent_pt": 0},
            {"index": 3, "text": "关键词：一个，两个", "heading_level": 0, "section_title": "摘要", "section_index": 1, "paragraph_no": 2, "font_name": "宋体", "font_size_pt": 12, "line_spacing": 1.5},
            {"index": 4, "text": "ABSTRACT", "heading_level": 1, "section_title": "ABSTRACT", "section_index": 2, "paragraph_no": 0},
            {"index": 5, "text": "Keywords: one, two", "heading_level": 0, "section_title": "ABSTRACT", "section_index": 2, "paragraph_no": 1, "font_name": "Times New Roman", "font_size_pt": 12, "line_spacing": 1.5},
            {"index": 6, "text": "目录", "heading_level": 1, "section_title": "目录", "section_index": 3, "paragraph_no": 0},
            {"index": 7, "text": "1 绪论", "heading_level": 1, "section_title": "1 绪论", "section_index": 4, "paragraph_no": 0, "font_name": "黑体", "font_size_pt": 15},
            {"index": 8, "text": "1.2 研究背景", "heading_level": 2, "section_title": "1 绪论", "section_index": 4, "paragraph_no": 0, "font_name": "黑体", "font_size_pt": 14},
            {"index": 9, "text": "正文见图2-1、表2-1和式（2-1）。", "heading_level": 0, "section_title": "1 绪论", "section_index": 4, "paragraph_no": 1, "font_name": "宋体", "font_size_pt": 12, "line_spacing": 1.0, "first_line_indent_pt": 0},
            {"index": 10, "text": "图2-2 错位图题", "heading_level": 0, "section_title": "1 绪论", "section_index": 4, "paragraph_no": 2},
            {"index": 11, "text": "表2-2 错位表题", "heading_level": 0, "section_title": "1 绪论", "section_index": 4, "paragraph_no": 3},
            {"index": 12, "text": "E=mc^2 （2-3）", "heading_level": 0, "section_title": "1 绪论", "section_index": 4, "paragraph_no": 4},
            {"index": 13, "text": "参考文献", "heading_level": 1, "section_title": "参考文献", "section_index": 5, "paragraph_no": 0},
            {"index": 14, "text": "[1] 张三. 论文题名[J]. 期刊, 2020.", "heading_level": 0, "section_title": "参考文献", "section_index": 5, "paragraph_no": 1},
            {"index": 15, "text": "[3] 缺少编号二的文献", "heading_level": 0, "section_title": "参考文献", "section_index": 5, "paragraph_no": 2},
        ],
        "toc_entries": [{"title": "1 绪论", "level": 1, "page": "1"}],
        "figure_titles": ["图2-2 错位图题"],
        "table_titles": ["表2-2 错位表题"],
        "formula_numbers": ["2-3"],
        "references": ["[1] 张三. 论文题名[J]. 期刊, 2020.", "[3] 缺少编号二的文献"],
        "word_metadata": {"comment_count": 1, "revision_count": 2, "hidden_text_count": 1},
        "sections": [
            {
                "page_width_cm": 20.0,
                "page_height_cm": 29.7,
                "orientation": "portrait",
                "top_margin_cm": 2.0,
                "bottom_margin_cm": 3.0,
                "left_margin_cm": 2.0,
                "right_margin_cm": 3.0,
                "gutter_cm": 0.5,
                "header_distance_cm": 1.0,
                "footer_distance_cm": 1.0,
                "header_text": "错误页眉",
                "footer_text": "第 1 页",
            }
        ],
        "page_layout": {
            "page_width_cm": 20.0,
            "page_height_cm": 29.7,
            "orientation": "portrait",
            "top_margin_cm": 2.0,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 2.0,
            "right_margin_cm": 3.0,
            "gutter_cm": 0.5,
            "header_distance_cm": 1.0,
            "footer_distance_cm": 1.0,
            "header_text": "错误页眉",
            "footer_text": "第 1 页",
        },
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="按清单和重邮模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert "template.page_size_mismatch" in issue_codes
    assert "template.gutter_mismatch" in issue_codes
    assert "template.header_footer_mismatch" in issue_codes
    assert "abstract.keyword_count_out_of_range" in issue_codes
    assert "toc.required_entry_missing" in issue_codes
    assert "heading.numbering_discontinuous" in issue_codes
    assert "style.paragraph_indent_missing" in issue_codes
    assert "style.line_spacing_small" in issue_codes
    assert "figure.referenced_caption_missing" in issue_codes
    assert "table.referenced_caption_missing" in issue_codes
    assert "formula.numbering_discontinuous" in issue_codes
    assert "references.numbering_discontinuous" in issue_codes
    assert "references.format_mismatch" in issue_codes
    assert "word.comments_or_revisions_present" in issue_codes


def test_check_paper_format_supports_pdf_text_phase_in_strict_runtime(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "pdf",
        "text": "论文标题\n关键词：查非\n参考文献\n正文中有  连续空格。",
        "page_count": 3,
        "pages": [
            {"page_no": 1, "text": "论文标题"},
            {"page_no": 2, "text": "正文中有  连续空格。"},
        ],
        "headings": [],
        "references": [],
        "layout": {},
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.pdf",
        query="检查论文格式",
        template_id="generic_cn_thesis",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert report["document_type"] == "pdf"
    assert "unsupported.document_type" not in issue_codes
    assert "structure.abstract_missing" in issue_codes
    assert "text.multiple_spaces" in issue_codes


def test_header_content_check_starts_from_body_section(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：查非\n目录\n1 绪论\n正文段落\n参考文献",
        "headings": [
            {"text": "摘要", "level": 1, "paragraph_index": 0, "section_index": 1},
            {"text": "目录", "level": 1, "paragraph_index": 2, "section_index": 2},
            {"text": "1 绪论", "level": 1, "paragraph_index": 3, "section_index": 3},
            {"text": "参考文献", "level": 1, "paragraph_index": 5, "section_index": 4},
        ],
        "paragraphs": [
            {"index": 0, "text": "摘要", "heading_level": 1, "section_title": "摘要", "section_index": 1, "word_section_index": 0, "paragraph_no": 0},
            {"index": 1, "text": "关键词：查非", "heading_level": 0, "section_title": "摘要", "section_index": 1, "word_section_index": 0, "paragraph_no": 1},
            {"index": 2, "text": "目录", "heading_level": 1, "section_title": "目录", "section_index": 2, "word_section_index": 1, "paragraph_no": 0},
            {"index": 3, "text": "1 绪论", "heading_level": 1, "section_title": "1 绪论", "section_index": 3, "word_section_index": 2, "paragraph_no": 0},
            {"index": 4, "text": "正文段落", "heading_level": 0, "section_title": "1 绪论", "section_index": 3, "word_section_index": 2, "paragraph_no": 1},
            {"index": 5, "text": "参考文献", "heading_level": 1, "section_title": "参考文献", "section_index": 4, "word_section_index": 2, "paragraph_no": 0},
        ],
        "sections": [
            {"header_text": "错误封面页眉", "footer_text": ""},
            {"header_text": "错误前置页眉", "footer_text": ""},
            {"header_text": "重庆邮电大学硕士学位论文", "footer_text": ""},
        ],
        "page_layout": {
            "page_width_cm": 21.0,
            "page_height_cm": 29.7,
            "orientation": "portrait",
            "top_margin_cm": 3.0,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 3.0,
            "right_margin_cm": 3.0,
            "gutter_cm": 0.0,
            "header_distance_cm": 2.0,
            "footer_distance_cm": 2.0,
        },
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="按重庆邮电大学模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert "template.header_content_mismatch" not in issue_codes


def test_docx_parser_assigns_paragraph_roles():
    doc = Document()
    doc.add_heading("绪论", level=1)
    doc.add_paragraph("这是正文自然语言段落，需要参与中文纠错。")
    doc.add_paragraph("图1-1 系统架构图").style = "Caption"
    doc.add_paragraph("Fig.1-1 System architecture").style = "Caption"
    doc.add_paragraph("(1-1)").style = "Normal"
    doc.add_heading("参考文献", level=1)
    doc.add_paragraph("[1] 张三. 论文题名[J]. 期刊, 2024, 10(2): 1-9.")
    buffer = BytesIO()
    doc.save(buffer)

    parsed = parse_docx_bytes(buffer.getvalue())
    roles = {item["text"]: item.get("paragraph_role") for item in parsed["paragraphs"] if item.get("text")}

    assert roles["绪论"] == "heading"
    assert roles["这是正文自然语言段落，需要参与中文纠错。"] == "body"
    assert roles["图1-1 系统架构图"] == "figure_caption"
    assert roles["Fig.1-1 System architecture"] == "figure_caption"
    assert roles["(1-1)"] == "formula"
    assert roles["参考文献"] == "heading"
    assert roles["[1] 张三. 论文题名[J]. 期刊, 2024, 10(2): 1-9."] == "reference_entry"


def test_text_engines_only_receive_allowed_docx_paragraph_roles(monkeypatch):
    from agent.tools.paper_format_checker import _check_macro_correct, _check_vale, _check_language_tool

    token_batches: list[list[str]] = []
    punct_batches: list[list[str]] = []
    captured_language_text: list[str] = []
    captured_vale_text: list[str] = []

    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_enabled", True)
    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_batch_size", 8)
    monkeypatch.setattr("app.core.config.settings.paper_check_languagetool_enabled", True)
    monkeypatch.setattr("app.core.config.settings.paper_check_languagetool_url", "http://lt.invalid")

    def fake_token(texts):
        token_batches.append(list(texts))
        return ([{"errors": []} for _ in texts], "macro_correct.token")

    def fake_punct(texts):
        punct_batches.append(list(texts))
        return ([{"errors": []} for _ in texts], "macro_correct.punct")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"matches": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, _url, data):
            captured_language_text.append(data["text"])
            return FakeResponse()

    def fake_run(cmd, capture_output, text, timeout, check):
        temp_path = cmd[-1]
        captured_vale_text.append(Path(temp_path).read_text(encoding="utf-8"))
        return types.SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("agent.tools.paper_format_checker.run_macro_correct_token", fake_token)
    monkeypatch.setattr("agent.tools.paper_format_checker.run_macro_correct_punct", fake_punct)
    monkeypatch.setattr("agent.tools.paper_format_checker.httpx.Client", FakeClient)
    monkeypatch.setattr("agent.tools.paper_format_checker.subprocess.run", fake_run)

    parsed = {
        "kind": "docx",
        "paragraphs": [
            {"index": 0, "text": "目 录", "paragraph_role": "toc", "section_title": "目录"},
            {"index": 1, "text": "图1-1 系统架构图", "paragraph_role": "figure_caption", "section_title": "绪论"},
            {"index": 2, "text": "[1] 张三. 论文题名[J]. 期刊, 2024, 10(2): 1-9.", "paragraph_role": "reference_entry", "section_title": "参考文献"},
            {"index": 3, "text": "这是正文自然语言段落，需要参与中文纠错。", "paragraph_role": "body", "section_title": "绪论", "section_index": 1, "paragraph_no": 1},
            {"index": 4, "text": "This is an English abstract sentence.", "paragraph_role": "abstract_body", "section_title": "ABSTRACT", "section_index": 2, "paragraph_no": 1},
            {"index": 5, "text": "致谢中文段落，需要参与写作规范检查。", "paragraph_role": "acknowledgement_body", "section_title": "致谢", "section_index": 3, "paragraph_no": 1},
        ],
        "text": "\n".join([
            "目 录",
            "图1-1 系统架构图",
            "[1] 张三. 论文题名[J]. 期刊, 2024, 10(2): 1-9.",
            "这是正文自然语言段落，需要参与中文纠错。",
            "This is an English abstract sentence.",
            "致谢中文段落，需要参与写作规范检查。",
        ]),
    }

    _check_macro_correct(parsed)
    _check_language_tool(parsed, file_name="paper.docx")
    _check_vale(parsed)

    macro_text = "\n".join(sum(token_batches, []) + sum(punct_batches, []))
    assert "目 录" not in macro_text
    assert "图1-1 系统架构图" not in macro_text
    assert "[1] 张三" not in macro_text
    assert "这是正文自然语言段落" in macro_text
    assert "This is an English abstract sentence." in captured_language_text[0]
    assert "图1-1 系统架构图" not in captured_language_text[0]
    assert "致谢中文段落" in captured_vale_text[0]
    assert "[1] 张三" not in captured_vale_text[0]


def test_even_page_header_satisfies_cqupt_template(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed, timings=None: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：查非\nABSTRACT\nKeywords: test\n目录\n绪论\n正文段落\n参考文献\n致谢",
        "headings": [
            {"text": "摘要", "level": 1, "paragraph_index": 0, "section_index": 1},
            {"text": "目录", "level": 1, "paragraph_index": 4, "section_index": 2},
            {"text": "绪论", "level": 1, "paragraph_index": 5, "section_index": 3},
            {"text": "参考文献", "level": 1, "paragraph_index": 7, "section_index": 4},
        ],
        "paragraphs": [
            {"index": 0, "text": "摘要", "heading_level": 1, "section_title": "摘要", "section_index": 1, "word_section_index": 0},
            {"index": 1, "text": "关键词：查非；格式；论文", "paragraph_role": "abstract_body", "section_title": "摘要", "section_index": 1, "word_section_index": 0, "paragraph_no": 1},
            {"index": 4, "text": "目录", "heading_level": 1, "section_title": "目录", "section_index": 2, "word_section_index": 1},
            {"index": 5, "text": "绪论", "heading_level": 1, "section_title": "绪论", "section_index": 3, "word_section_index": 2},
            {"index": 6, "text": "正文段落", "paragraph_role": "body", "section_title": "绪论", "section_index": 3, "word_section_index": 2, "paragraph_no": 1, "font_name": "宋体", "font_size_pt": 12},
            {"index": 7, "text": "参考文献", "heading_level": 1, "section_title": "参考文献", "section_index": 4, "word_section_index": 2},
        ],
        "toc_entries": [{"title": "摘要"}, {"title": "ABSTRACT"}, {"title": "参考文献"}, {"title": "致谢"}],
        "sections": [
            {"default_header_text": "", "even_header_text": ""},
            {"default_header_text": "目 录", "even_header_text": "目 录"},
            {"default_header_text": "第1章 绪论", "even_header_text": "重庆邮电大学硕士学位论文"},
        ],
        "page_layout": {
            "page_width_cm": 21.0,
            "page_height_cm": 29.7,
            "orientation": "portrait",
            "top_margin_cm": 3.0,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 3.0,
            "right_margin_cm": 3.0,
            "gutter_cm": 0.0,
            "header_distance_cm": 2.0,
            "footer_distance_cm": 2.0,
        },
        "figure_titles": [],
        "table_titles": [],
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="按重庆邮电大学模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert "template.header_content_mismatch" not in issue_codes
    assert "toc.required_entry_missing" not in issue_codes
    assert "template.figure_toc_conditionally_missing" not in issue_codes
    assert "template.table_toc_conditionally_missing" not in issue_codes


def test_body_font_and_spacing_ignore_captions_and_fixed_twenty_point(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed, timings=None: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：一；二；三\nABSTRACT\nKeywords: one; two; three\n目录\n绪论\n正文段落\n图1-1 系统架构图\n参考文献\n致谢",
        "headings": [{"text": "绪论", "level": 1, "paragraph_index": 5, "section_index": 3}],
        "paragraphs": [
            {"index": 5, "text": "绪论", "heading_level": 1, "paragraph_role": "heading", "section_title": "绪论", "section_index": 3},
            {"index": 6, "text": "正文段落", "paragraph_role": "body", "section_title": "绪论", "section_index": 3, "paragraph_no": 1, "font_name": "宋体", "font_size_pt": 12, "line_spacing": 254000.0, "first_line_indent_pt": 24},
            {"index": 7, "text": "图1-1 系统架构图", "paragraph_role": "figure_caption", "section_title": "绪论", "section_index": 3, "paragraph_no": 2, "font_size_pt": 10.5, "line_spacing": 254000.0},
        ],
        "toc_entries": [{"title": "摘要"}, {"title": "ABSTRACT"}, {"title": "参考文献"}, {"title": "致谢"}],
        "sections": [{"default_header_text": "第1章 绪论", "even_header_text": "重庆邮电大学硕士学位论文"}],
        "page_layout": {
            "page_width_cm": 21.0,
            "page_height_cm": 29.7,
            "orientation": "portrait",
            "top_margin_cm": 3.0,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 3.0,
            "right_margin_cm": 3.0,
            "gutter_cm": 0.0,
            "header_distance_cm": 2.0,
            "footer_distance_cm": 2.0,
        },
        "figure_titles": ["图1-1 系统架构图"],
        "table_titles": [],
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="按重庆邮电大学模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    issue_codes = {item["code"] for item in report["issues"]}
    assert "template.body_font_mismatch" not in issue_codes
    assert "template.line_spacing_mismatch" not in issue_codes
    assert "style.line_spacing_small" not in issue_codes


def test_reference_rules_validate_gbt7714_types_and_aggregate_format_issues(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed, timings=None: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": (
            "正文引用[1][2][4]。\n参考文献\n"
            "[1] 张三. 中文期刊论文[J]. 计算机学报, 2024, 47(2): 1-9.\n"
            "[2] LI M, WANG H. English book title[M]. Beijing: Science Press, 2021.\n"
            "[2] 重复编号. 缺类型和年份\n"
            "[4] 王五. 一种并行仿真方法: 202410000000[P]. 2024-01-02.\n"
            "[5] BAD ENTRY WITHOUT TYPE OR YEAR\n"
        ),
        "references": [
            "[1] 张三. 中文期刊论文[J]. 计算机学报, 2024, 47(2): 1-9.",
            "[2] LI M, WANG H. English book title[M]. Beijing: Science Press, 2021.",
            "[2] 重复编号. 缺类型和年份",
            "[4] 王五. 一种并行仿真方法: 202410000000[P]. 2024-01-02.",
            "[5] BAD ENTRY WITHOUT TYPE OR YEAR",
        ],
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="检查参考文献",
        template_id="generic_cn_thesis",
    )

    by_code = {item["code"]: item for item in report["issues"]}
    assert "references.duplicate_number" in by_code
    assert "references.numbering_discontinuous" in by_code
    assert "references.format_mismatch" in by_code
    assert "references.entry_format_incomplete" not in by_code
    format_issue = by_code["references.format_mismatch"]
    assert format_issue["aggregate_count"] == 2
    assert len(format_issue["samples"]) == 2
    assert "缺少文献类型标识" in format_issue["actual"]["problem_kinds"]
    assert format_issue["confidence"] == "high"
    assert report["engine_timings_ms"]["reference_rules"] >= 0


def test_cqupt_allows_six_chinese_keywords(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed, timings=None: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：大语言模型；智能体通信；多智能体系统；共享记忆；工具调用；协议互操作\n目录\n1 引言\n正文\n参考文献\n致谢",
        "paragraphs": [
            {"index": 0, "text": "摘要", "heading_level": 1, "paragraph_role": "heading", "section_title": "摘要"},
            {"index": 1, "text": "关键词：大语言模型；智能体通信；多智能体系统；共享记忆；工具调用；协议互操作", "paragraph_role": "abstract_body", "section_title": "摘要"},
            {"index": 2, "text": "1 引言", "heading_level": 1, "paragraph_role": "heading", "section_title": "1 引言"},
            {"index": 3, "text": "正文", "paragraph_role": "body", "section_title": "1 引言", "font_name": "宋体", "font_size_pt": 12, "line_spacing": 254000.0, "first_line_indent_pt": 24},
        ],
        "headings": [{"text": "摘要", "level": 1}, {"text": "1 引言", "level": 1}, {"text": "参考文献", "level": 1}],
        "toc_entries": [{"title": "摘要"}, {"title": "ABSTRACT"}, {"title": "参考文献"}, {"title": "致谢"}],
        "references": [],
        "figure_titles": [],
        "table_titles": [],
        "page_layout": {
            "page_width_cm": 21.0,
            "page_height_cm": 29.7,
            "top_margin_cm": 3.0,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 3.0,
            "right_margin_cm": 3.0,
            "header_distance_cm": 2.0,
            "footer_distance_cm": 2.0,
        },
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="重邮模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    assert "abstract.keyword_count_out_of_range" not in {item["code"] for item in report["issues"]}


def test_reference_rules_do_not_mark_cited_one_to_ten_as_unused():
    citations = "\n".join(f"正文段落引用[{index}]。" for index in range(1, 11))
    refs = [
        f"[{index}] 作者{index}. 题名{index}[J]. 期刊, 2024, 10(2): 1-9."
        for index in range(1, 11)
    ]
    parsed = {
        "kind": "docx",
        "text": citations + "\n参考文献\n" + "\n".join(refs),
        "references": refs,
    }

    issues = paper_format_checker._check_reference_rules(parsed)

    assert "references.unused_reference" not in {item.code for item in issues}


def test_reference_rules_accept_bracket_dot_numbering_as_listed_references():
    citations = "\n".join(f"正文段落引用[{index}]。" for index in range(1, 11))
    refs = [
        f"[{index}]. 作者{index}. 题名{index}[J]. 期刊, 2024, 10(2): 1-9."
        for index in range(1, 11)
    ]
    parsed = {
        "kind": "docx",
        "text": citations + "\n参考文献\n" + "\n".join(refs),
        "references": refs,
    }

    issues = paper_format_checker._check_reference_rules(parsed)
    issue_codes = {item.code for item in issues}

    assert "references.citation_missing_in_bibliography" not in issue_codes
    assert "references.unused_reference" not in issue_codes


def test_reference_boundary_ignores_toc_reference_label():
    reference_heading = "\u53c2\u8003\u6587\u732e"
    refs = [
        f"[{index}]. 作者{index}. 题名{index}[J]. 期刊, 2024, 10(2): 1-9."
        for index in range(1, 11)
    ]
    parsed = {
        "kind": "docx",
        "text": (
            "目录\n"
            "1 引言.............................1\n"
            f"{reference_heading}..........................31\n"
            "1 引言\n"
            + "\n".join(f"正文引用[{index}]。" for index in range(1, 11))
            + "\n"
            f"{reference_heading}\n"
            + "\n".join(refs)
        ),
        "references": refs,
    }

    issues = paper_format_checker._check_reference_rules(parsed)

    assert "references.unused_reference" not in {item.code for item in issues}


def test_macro_correct_filters_period_to_comma_punctuation_noise(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_enabled", True)
    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_punct_enabled", True)
    monkeypatch.setattr("app.core.config.settings.paper_check_macro_correct_batch_size", 8)
    monkeypatch.setattr(
        "agent.tools.paper_format_checker.run_macro_correct_token",
        lambda texts: ([{"errors": []} for _ in texts], "macro_correct.token"),
    )

    def fake_punct(texts):
        return (
            [
                {"errors": [{"begin": 4, "end": 5, "wrong": "。", "right": "，", "rule_id": "punct"}]}
                for _ in texts
            ],
            "macro_correct.punct",
        )

    monkeypatch.setattr("agent.tools.paper_format_checker.run_macro_correct_punct", fake_punct)
    parsed = {
        "kind": "docx",
        "paragraphs": [
            {
                "index": index,
                "text": f"这是第{index}个自然句。后面继续说明。",
                "paragraph_role": "body",
                "section_title": "1 引言",
                "section_index": 1,
                "paragraph_no": index,
            }
            for index in range(35)
        ],
    }

    issues = paper_format_checker._check_macro_correct(parsed)

    assert "macro_correct.punct.aggregate" not in {item.code for item in issues}


def test_abstract_forbidden_content_check_is_limited_to_abstract_window(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed, timings=None: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": (
            "摘要：本文介绍智能体通信机制，不包含引用编号。\n"
            "关键字：智能体通信；多智能体系统；共享记忆\n"
            "Abstract: This review introduces agent communication.\n"
            "Keywords: Agent communication; multi-agent systems; shared memory\n"
            "目录\n1 引言\n"
            "正文讨论 Abstract State Machine 与相关研究[13]。\n"
            "参考文献\n[13]. 作者. 题名[J]. 期刊, 2024, 10(2): 1-9.\n致谢"
        ),
        "paragraphs": [
            {"index": 0, "text": "摘要：本文介绍智能体通信机制，不包含引用编号。", "paragraph_role": "abstract_body", "section_title": "摘要"},
            {"index": 1, "text": "关键字：智能体通信；多智能体系统；共享记忆", "paragraph_role": "abstract_body", "section_title": "摘要"},
            {"index": 2, "text": "Abstract: This review introduces agent communication.", "paragraph_role": "abstract_body", "section_title": "ABSTRACT"},
            {"index": 3, "text": "Keywords: Agent communication; multi-agent systems; shared memory", "paragraph_role": "abstract_body", "section_title": "ABSTRACT"},
            {"index": 4, "text": "正文讨论 Abstract State Machine 与相关研究[13]。", "paragraph_role": "body", "section_title": "1 引言", "font_name": "宋体", "font_size_pt": 12, "line_spacing": 254000.0, "first_line_indent_pt": 24},
        ],
        "headings": [{"text": "1 引言", "level": 1}, {"text": "参考文献", "level": 1}],
        "toc_entries": [{"title": "摘要"}, {"title": "ABSTRACT"}, {"title": "参考文献"}, {"title": "致谢"}],
        "references": ["[13]. 作者. 题名[J]. 期刊, 2024, 10(2): 1-9."],
        "figure_titles": [],
        "table_titles": [],
        "page_layout": {
            "page_width_cm": 21.0,
            "page_height_cm": 29.7,
            "top_margin_cm": 3.0,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 3.0,
            "right_margin_cm": 3.0,
            "header_distance_cm": 2.0,
            "footer_distance_cm": 2.0,
        },
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="重邮模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    assert "abstract.contains_figure_formula_or_citation" not in {item["code"] for item in report["issues"]}


def test_rule_issues_include_template_basis_and_brief_location(monkeypatch):
    monkeypatch.setattr("app.services.paper_review_runtime_service.PaperReviewRuntimeService.diagnose_sync", _ready_runtime_status)
    monkeypatch.setattr("agent.tools.paper_format_checker._check_macro_correct", lambda parsed, timings=None: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_language_tool", lambda parsed, file_name: [])
    monkeypatch.setattr("agent.tools.paper_format_checker._check_vale", lambda parsed: [])
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：一；二；三\n目录\n1 引言\n正文\n参考文献",
        "paragraphs": [
            {"index": 0, "text": "摘要", "heading_level": 1, "paragraph_role": "heading", "section_title": "摘要"},
            {"index": 1, "text": "关键词：一；二；三", "paragraph_role": "abstract_body", "section_title": "摘要"},
            {"index": 2, "text": "1 引言", "heading_level": 1, "paragraph_role": "heading", "section_title": "1 引言"},
            {"index": 3, "text": "正文", "paragraph_role": "body", "section_title": "1 引言", "font_name": "Calibri", "font_size_pt": 10.5, "line_spacing": 1.0, "first_line_indent_pt": 0},
        ],
        "headings": [{"text": "摘要", "level": 1}, {"text": "1 引言", "level": 1}, {"text": "参考文献", "level": 1}],
        "toc_entries": [{"title": "1 引言"}],
        "references": [],
        "figure_titles": [],
        "table_titles": [],
        "page_layout": {
            "page_width_cm": 21.59,
            "page_height_cm": 27.94,
            "top_margin_cm": 2.54,
            "bottom_margin_cm": 3.0,
            "left_margin_cm": 3.0,
            "right_margin_cm": 3.0,
            "header_distance_cm": 1.5,
            "footer_distance_cm": 1.5,
        },
    }

    report = check_paper_format(
        parsed=parsed,
        file_name="paper.docx",
        query="重邮模板查非",
        template_id="cqupt_graduate_thesis_2022",
    )

    assert report["issues"]
    for issue in report["issues"]:
        assert issue.get("location_summary")
        if issue.get("engine") == "rule":
            assert issue.get("rule_basis")
