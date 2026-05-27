from __future__ import annotations

from agent.tools.paper_review_evidence import build_review_evidence_pack


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
