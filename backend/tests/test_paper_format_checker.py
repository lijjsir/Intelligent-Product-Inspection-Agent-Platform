from __future__ import annotations

from io import BytesIO

from docx import Document

from agent.tools.file_parsers import parse_docx_bytes, parse_tex_bytes
from agent.tools.paper_format_checker import check_paper_format


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
