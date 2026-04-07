from __future__ import annotations

import csv
import json
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree import ElementTree


def parse_pdf_bytes(content: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise ValueError(f"pdf parsing dependency unavailable: {exc}") from exc

    reader = PdfReader(BytesIO(content))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n".join(page for page in pages if page)
    return {
        "kind": "pdf",
        "page_count": len(reader.pages),
        "text": text,
    }


def parse_docx_bytes(content: bytes) -> dict:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        data = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    root = ElementTree.fromstring(data)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        merged = "".join(texts).strip()
        if merged:
            paragraphs.append(merged)
    return {
        "kind": "docx",
        "paragraphs": paragraphs,
        "text": "\n".join(paragraphs),
    }


def parse_csv_bytes(content: bytes) -> dict:
    text = content.decode("utf-8", errors="ignore")
    reader = csv.reader(StringIO(text))
    rows = list(reader)
    headers = rows[0] if rows else []
    return {
        "kind": "csv",
        "headers": headers,
        "rows": rows[1:51] if len(rows) > 1 else [],
        "text": text,
    }


def parse_json_bytes(content: bytes) -> dict:
    text = content.decode("utf-8", errors="ignore")
    payload = json.loads(text or "{}")
    return {
        "kind": "json",
        "payload": payload,
        "text": json.dumps(payload, ensure_ascii=False, indent=2),
    }


def parse_xlsx_bytes(content: bytes) -> dict:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            xml = archive.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
            root = ElementTree.fromstring(xml)
            shared_strings = ["".join(node.itertext()) for node in root]
        sheet_entries = []
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            root = ElementTree.fromstring(xml)
            rows = []
            for row in root.iter():
                if row.tag.endswith("row"):
                    cells = []
                    for cell in row:
                        if not cell.tag.endswith("c"):
                            continue
                        value = ""
                        cell_type = cell.attrib.get("t")
                        v_node = next((child for child in cell if child.tag.endswith("v")), None)
                        if v_node is not None and v_node.text is not None:
                            value = v_node.text
                            if cell_type == "s":
                                try:
                                    value = shared_strings[int(value)]
                                except Exception:
                                    pass
                        cells.append(value)
                    if cells:
                        rows.append(cells)
            sheet_entries.append({"sheet": Path(name).stem, "rows": rows[:51]})
    text_lines = []
    for sheet in sheet_entries:
        text_lines.append(f"[{sheet['sheet']}]")
        for row in sheet["rows"][:20]:
            text_lines.append(" | ".join(str(item) for item in row))
    return {
        "kind": "xlsx",
        "sheets": sheet_entries,
        "text": "\n".join(text_lines),
    }


def parse_text_bytes(content: bytes) -> dict:
    text = content.decode("utf-8", errors="ignore")
    return {"kind": "text", "text": text}


def parse_file_content(file_name: str, content: bytes) -> dict:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return parse_pdf_bytes(content)
    if suffix == ".docx":
        return parse_docx_bytes(content)
    if suffix == ".csv":
        return parse_csv_bytes(content)
    if suffix == ".json":
        return parse_json_bytes(content)
    if suffix == ".xlsx":
        return parse_xlsx_bytes(content)
    return parse_text_bytes(content)
