from app.services.ai_response_text import normalize_ai_response_content


def test_normalize_ai_response_content_uses_answer_field():
    content, metadata = normalize_ai_response_content(
        '{"answer": "可以检查论文。", "summary": "功能确认"}'
    )

    assert content == "可以检查论文。"
    assert metadata == {
        "response_format": "answer_summary_json",
        "summary": "功能确认",
    }


def test_normalize_ai_response_content_extracts_markdown_json_block():
    content, metadata = normalize_ai_response_content(
        '```json\n{"answer": "已处理", "summary": "ok"}\n```'
    )

    assert content == "已处理"
    assert metadata["summary"] == "ok"


def test_normalize_ai_response_content_extracts_loose_multiline_json():
    content, metadata = normalize_ai_response_content(
        """{
          "answer": "第一段

第二段",
          "summary": "内部摘要"
        }"""
    )

    assert content == "第一段\n\n第二段"
    assert metadata["summary"] == "内部摘要"


def test_normalize_ai_response_content_extracts_unquoted_loose_object():
    content, metadata = normalize_ai_response_content(
        '{answer: "给用户看的内容", summary: "内部摘要"}'
    )

    assert content == "给用户看的内容"
    assert metadata["summary"] == "内部摘要"


def test_normalize_ai_response_content_extracts_bare_answer_summary_text():
    content, metadata = normalize_ai_response_content(
        "answer: 给用户看的内容\nsummary: 内部摘要"
    )

    assert content == "给用户看的内容"
    assert metadata["summary"] == "内部摘要"


def test_normalize_ai_response_content_keeps_plain_text():
    content, metadata = normalize_ai_response_content("普通回复")

    assert content == "普通回复"
    assert metadata == {}
