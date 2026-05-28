from __future__ import annotations

from agent.tools.paper_review_evidence import build_review_evidence_pack


def test_review_evidence_pack_summarizes_all_docx_body_paragraphs():
    parsed = {
        "kind": "docx",
        "text": "引言\n" + "\n".join(f"正文段落{i}" for i in range(60)),
        "headings": [{"text": "引言", "level": 1, "paragraph_index": 0}],
        "paragraphs": [
            {"index": 0, "text": "引言", "heading_level": 1},
            *[
                {
                    "index": i + 1,
                    "text": f"正文段落{i}",
                    "heading_level": 0,
                    "font_name": "宋体" if i < 55 else "Calibri",
                    "font_size_pt": 12 if i < 55 else 10.5,
                    "line_spacing": 1.5,
                }
                for i in range(60)
            ],
        ],
        "page_layout": {},
    }
    check_result = {
        "document_type": "docx",
        "template_id": "cqupt_graduate_thesis_2022",
        "score": 90,
        "issues": [],
        "limitations": [],
    }

    pack = build_review_evidence_pack(
        parsed=parsed,
        check_result=check_result,
        file_name="paper.docx",
    )

    style_summary = pack["style_summary"]
    assert style_summary["style_evidence_scope"] == "all_body_paragraphs"
    assert style_summary["body_paragraph_count"] == 60
    assert style_summary["font_name_counts"]["宋体"] == 55
    assert style_summary["font_name_counts"]["Calibri"] == 5
    assert style_summary["font_size_counts"]["10.5"] == 5


def test_review_evidence_pack_includes_pdf_pages_and_layout():
    parsed = {
        "kind": "pdf",
        "text": "1 Introduction\nThis page has  two spaces.\nReferences\n[1] Example.",
        "page_count": 2,
        "pages": [
            {"page_no": 1, "text": "1 Introduction\nThis page has  two spaces."},
            {"page_no": 2, "text": "References\n[1] Example."},
        ],
        "headings": [{"text": "1 Introduction", "level": 1, "paragraph_index": 0}],
        "references": ["[1] Example."],
        "layout": {"analysis": "text_only", "parser": "pypdf"},
    }
    check_result = {
        "document_type": "pdf",
        "template_id": "generic_cn_thesis",
        "score": 82,
        "issues": [{"code": "text.multiple_spaces", "severity": "low"}],
        "limitations": ["当前 PDF 检查主要基于文本抽取。"],
    }

    pack = build_review_evidence_pack(
        parsed=parsed,
        check_result=check_result,
        file_name="paper.pdf",
    )

    assert pack["document"]["page_count"] == 2
    assert pack["outline"][0]["title"] == "1 Introduction"
    assert pack["style_summary"]["layout"]["analysis"] == "text_only"
    assert pack["style_summary"]["reference_count"] == 1
    assert pack["evidence_snippets"][0]["source"] == "pdf_page"
    assert pack["evidence_snippets"][0]["location"] == "page 1"
