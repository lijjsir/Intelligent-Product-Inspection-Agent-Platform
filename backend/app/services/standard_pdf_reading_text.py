"""Recover PDF line layout without guessing glyphs, formulae or numeric limits.

Some electronic standards map Latin/math fonts to unrelated CJK codepoints.
Their rendered PDF is correct; OCR can introduce new errors in otherwise valid
Chinese and numbers. Keep the original extraction and mark damaged spans instead.
"""
import re

SYMBOL_NOTICE = "〔公式或特殊符号请查看本页原件〕"
GLYPH_NOTICE = "〔符号见原页〕"
_BAD_CJK = re.compile(r"[\u4e00-\u9fff]")
_PRIVATE = re.compile(r"[\ue000-\uf8ff\ufffd]")
_GLYPH = re.compile(r"/G[0-9a-fA-F]{2,4}")


def normalize_reading_typography(text):
    # Unlike NFKC this preserves superscripts, subscripts, ℃ and fractions.
    result = "".join(chr(ord(c)-0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else " " if c == "\u3000" else c for c in text)
    return re.sub(r"(?<=\d)[ \t]*\.[ \t]*(?=\d)", ".", result)


def damaged_span(span):
    text, font = span.get("text", ""), span.get("font", "")
    custom_symbol_font = font.startswith('E-') or bool(re.match(r'^O\d+-PK',font))
    return bool(_PRIVATE.search(text) or _GLYPH.search(text) or (_BAD_CJK.search(text) and custom_symbol_font))


def reading_page(page):
    lines, warnings = [], []
    damaged = False
    blocks = [block for block in page.get_text("dict").get("blocks", []) if 'lines' in block]
    bands = []
    for block in blocks:
        spans = [span for line in block['lines'] for span in line['spans']]
        plain = ''.join(span['text'] for span in spans if not damaged_span(span))
        if any(damaged_span(span) for span in spans) and not re.search(r'[\u4e00-\u9fff]',plain) and block['bbox'][1] >= page.rect.height*.12:
            bands.append((block['bbox'][1],block['bbox'][3]))
    groups = []
    for start,end in sorted(bands):
        if groups and start <= groups[-1][1]+4:groups[-1][1]=max(end,groups[-1][1])
        else:groups.append([start,end])
    emitted=set()
    for block in blocks:
        if "lines" not in block:continue
        spans = [span for line in block["lines"] for span in line["spans"]]
        bad = any(damaged_span(span) for span in spans)
        plain = "".join(span["text"] for span in spans if not damaged_span(span))
        group = next((index for index,(start,end) in enumerate(groups) if block['bbox'][1] >= start-1 and block['bbox'][3] <= end+1),None)
        if group is not None and not re.search(r'[\u4e00-\u9fff]',plain):
            damaged=True
            if group not in emitted:lines.append(SYMBOL_NOTICE);emitted.add(group)
            continue
        # Formula-only blocks include disconnected sum/fraction components whose
        # reading order cannot be reconstructed from plain text.
        if bad and not re.search(r"[\u4e00-\u9fff]", plain):
            damaged = True
            # A damaged running header is not part of a body clause.
            if block["bbox"][1] < page.rect.height * .12 and re.search(r"(?:19|20)[0-9]{2}", normalize_reading_typography(plain)):
                continue
            lines.append(SYMBOL_NOTICE)
            continue
        for line in block["lines"]:
            parts, replacing = [], False
            for span in line["spans"]:
                if damaged_span(span):
                    damaged = True
                    if not replacing:parts.append(GLYPH_NOTICE)
                    replacing = True
                else:
                    parts.append(span["text"]); replacing = False
            value = normalize_reading_typography("".join(parts)).strip()
            if value:lines.append(value)
    if damaged:warnings.append("PDF部分字母或公式的字体映射异常；相关位置已标记，请查看原页，不据此推断公式、数字或阈值。")
    return "\n".join(lines), warnings


def restore_pdf_reading_layout(pages, file_path):
    try:
        import pymupdf
    except ImportError:
        return pages
    result = []
    with pymupdf.open(str(file_path)) as document:
        for item in pages:
            page_number = int(item["page_number"])
            original = str(item.get("text") or "")
            native = document[page_number-1]
            # Image-only OCR remains an explicitly different extraction method.
            if not native.get_text().strip():
                result.append({**item, "extraction_method":"ocr"}); continue
            text, warnings = reading_page(native)
            if not text.strip():
                result.append(item); continue
            result.append({**item, "raw_text":original, "text":text,
                "extraction_method":"pdf_text_layer_layout", "text_warnings":warnings})
    return result


def render_standard_page(content, page_number):
    import pymupdf
    from app.core.exceptions import ValidationError
    with pymupdf.open(stream=content, filetype='pdf') as document:
        if page_number < 1 or page_number > len(document):
            raise ValidationError('原PDF页码超出范围')
        page=document[page_number-1]
        scale=min(2.0,1800/max(page.rect.width,page.rect.height))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).tobytes('png')
