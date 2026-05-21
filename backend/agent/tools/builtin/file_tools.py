"""Built-in file parsing tool manifest and handler."""

from __future__ import annotations

from pathlib import Path

from agent.tools.file_parsers import parse_file_content


TOOL_MANIFESTS = [
    {
        "tool_key": "file.parse",
        "display_name": "文件内容解析",
        "description": "解析 PDF、Word、Excel、CSV、JSON 等文件内容，提取结构化文本和表格信息。",
        "tool_type": "native",
        "category": "file_parse",
        "handler_path": "agent.tools.builtin.file_tools.parse",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "file_type": {"type": "string", "description": "文件类型，可选覆盖后缀判断"},
            },
            "required": ["file_path"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "tables": {"type": "array"},
            },
        },
        "risk_level": "low",
        "is_readonly": True,
    },
]


def parse(file_path: str, file_type: str | None = None) -> dict:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {file_path}")

    effective_name = path.name if not file_type else f"{path.stem}.{file_type.lstrip('.')}"
    parsed = parse_file_content(effective_name, path.read_bytes())
    return {
        "file_name": path.name,
        "file_path": str(path),
        "file_type": file_type or path.suffix.lstrip("."),
        "content": parsed.get("text", ""),
        "tables": parsed.get("sheets") or parsed.get("rows") or [],
        "metadata": {key: value for key, value in parsed.items() if key not in {"text", "sheets", "rows"}},
    }
