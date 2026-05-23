from __future__ import annotations

from pathlib import PurePath

from agent.router.contracts import NodeSpec


CHAT_NODE_SPECS = {
    "chat.text_node": NodeSpec(
        node_key="chat.text_node",
        accepted_input_kinds=["text"],
        required_model_types=["chat"],
        mode="answer",
        output_artifact_types=["assistant_text"],
    ),
    "chat.rag_answer_node": NodeSpec(
        node_key="chat.rag_answer_node",
        accepted_input_kinds=["rag_hits", "text"],
        required_model_types=["chat"],
        mode="answer",
        output_artifact_types=["assistant_text"],
    ),
    "chat.file_summary_node": NodeSpec(
        node_key="chat.file_summary_node",
        accepted_input_kinds=["document", "text_file"],
        required_model_types=["chat"],
        mode="report",
        output_artifact_types=["file_summary"],
    ),
    "chat.file_qa_node": NodeSpec(
        node_key="chat.file_qa_node",
        accepted_input_kinds=["document", "text_file"],
        required_model_types=["chat"],
        mode="report",
        output_artifact_types=["file_answer"],
    ),
    "chat.image_explain_node": NodeSpec(
        node_key="chat.image_explain_node",
        accepted_input_kinds=["image_understanding"],
        required_model_types=["chat"],
        mode="answer",
        output_artifact_types=["image_analysis"],
    ),
}


INSPECTION_NODE_SPECS = {
    "inspection.intake_node": NodeSpec(
        node_key="inspection.intake_node",
        accepted_input_kinds=["task_payload"],
        required_model_types=[],
        mode="action",
        output_artifact_types=["task_validation"],
    ),
    "inspection.file_parse_node": NodeSpec(
        node_key="inspection.file_parse_node",
        accepted_input_kinds=["document", "spreadsheet", "structured_file"],
        required_model_types=[],
        mode="report",
        output_artifact_types=["parsed_file"],
    ),
    "inspection.vision_node": NodeSpec(
        node_key="inspection.vision_node",
        accepted_input_kinds=["image"],
        required_model_types=["vision", "multimodal", "chat"],
        mode="report",
        output_artifact_types=["image_understanding"],
    ),
    "inspection.knowledge_node": NodeSpec(
        node_key="inspection.knowledge_node",
        accepted_input_kinds=["rag_scope", "standard"],
        required_model_types=[],
        mode="report",
        output_artifact_types=["rag_hits"],
    ),
    "inspection.reasoning_node": NodeSpec(
        node_key="inspection.reasoning_node",
        accepted_input_kinds=["parsed_file", "image_understanding", "rag_hits"],
        required_model_types=["chat", "multimodal"],
        mode="action",
        output_artifact_types=["inspection_result"],
    ),
    "inspection.persist_node": NodeSpec(
        node_key="inspection.persist_node",
        accepted_input_kinds=["inspection_result"],
        required_model_types=[],
        mode="action",
        output_artifact_types=["persisted_result"],
    ),
}


TEXT_FILE_SUFFIXES = {"pdf", "docx", "txt", "md"}
STRUCTURED_FILE_SUFFIXES = {"xlsx", "csv", "json", "jsonl"}
IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "webp", "gif"}


def attachment_kind(attachment: dict) -> str:
    name = str(attachment.get("name") or attachment.get("url") or "")
    suffix = PurePath(name).suffix.lower().lstrip(".")
    kind = str(attachment.get("kind") or "").lower()
    content_type = str(attachment.get("content_type") or "").lower()
    if kind == "image" or content_type.startswith("image/") or suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in STRUCTURED_FILE_SUFFIXES:
        return "structured_file"
    if suffix in TEXT_FILE_SUFFIXES:
        return "document"
    if kind == "file":
        return "document"
    return "unsupported"


def route_attachment_to_node(agent: str, attachment: dict) -> NodeSpec | None:
    kind = attachment_kind(attachment)
    if agent == "chat":
        if kind == "image":
            return CHAT_NODE_SPECS["chat.image_explain_node"]
        if kind in {"document", "structured_file"}:
            return CHAT_NODE_SPECS["chat.file_summary_node"]
    if agent == "inspection_task":
        if kind == "image":
            return INSPECTION_NODE_SPECS["inspection.vision_node"]
        if kind == "document":
            return INSPECTION_NODE_SPECS["inspection.file_parse_node"]
        if kind == "structured_file":
            return INSPECTION_NODE_SPECS["inspection.file_parse_node"]
    return None
