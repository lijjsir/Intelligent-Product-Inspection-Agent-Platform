from __future__ import annotations

import sys
import types
from io import BytesIO

from docx import Document

from agent.tools.file_parsers import parse_docx_bytes, parse_pdf_bytes, parse_tex_bytes
from agent.tools.paper_format_checker import check_paper_format
from agent.tools.paper_format_templates import get_paper_template


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


def test_check_paper_format_reports_missing_sections_for_docx():
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


def test_cqupt_template_is_registered_with_storage_objects():
    template = get_paper_template("cqupt_graduate_thesis_2022")

    assert template["template_id"] == "cqupt_graduate_thesis_2022"
    assert template["name"] == "重庆邮电大学研究生学位论文模板（2022版）"
    assert template["storage"]["bucket"] == "paper-templates"
    object_keys = {item["object_key"] for item in template["storage"]["files"]}
    assert "cqupt/graduate-thesis/2022/word-commented-template.docx" in object_keys
    assert "cqupt/graduate-thesis/2022/writing-guide.docx" in object_keys


def test_check_paper_format_reports_cqupt_template_differences():
    parsed = {
        "kind": "docx",
        "text": "摘要\n关键词：查非\n参考文献",
        "headings": [],
        "paragraphs": [
            {
                "index": 0,
                "text": "正文段落",
                "heading_level": 0,
                "font_name": "Arial",
                "font_size_pt": 10.5,
                "line_spacing": 1.0,
                "first_line_indent_pt": 0,
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
    assert "template.margin_mismatch" in issue_codes
    assert "template.body_font_mismatch" in issue_codes
    assert any("重庆邮电大学" in item for item in report["limitations"])


def test_check_paper_format_supports_pdf_text_phase_with_limitations():
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
    assert any("PDF" in item and "文本抽取" in item for item in report["limitations"])
