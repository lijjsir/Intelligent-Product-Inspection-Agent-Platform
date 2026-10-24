from types import SimpleNamespace

from app.services.standard_pdf_reading_text import (
    GLYPH_NOTICE, SYMBOL_NOTICE, damaged_span, normalize_reading_typography, reading_page, render_standard_page,
)
from app.services.standard_candidate_extractor import extract_candidates
from scripts.repair_standard_reading_text import untouched_legacy


def span(text, font='SimSun'):
    return {'text':text,'font':font}


class Page:
    rect = SimpleNamespace(height=800)
    def get_text(self, mode):
        return {'blocks':[
            {'bbox':(0,160,400,200),'lines':[{'spans':[span('５．４．３ 试样尺寸应为１３５ｍｍ×１９５ｍｍ，面积为100cm²。')]}]},
            {'bbox':(0,220,400,260),'lines':[{'spans':[span('犇','E-BX9-PK748220'),span('＝∑(0.5-0.4)²')]}]},
            {'bbox':(0,270,400,300),'lines':[{'spans':[span('犇','E-BX9-PK748220'),span('——同色密度偏差；')]}]},
            {'bbox':(0,310,400,330),'lines':[{'spans':[span('正常汉字犀牛和犬不应被替换。')]}]},
        ]}


def test_reading_text_marks_broken_math_without_corrupting_valid_values_or_cjk():
    text, warnings = reading_page(Page())
    assert '5.4.3 试样尺寸应为135mm×195mm,面积为100cm²。' in text
    assert SYMBOL_NOTICE in text and GLYPH_NOTICE+'——同色密度偏差;' in text
    assert '犇' not in text and '正常汉字犀牛和犬不应被替换。' in text
    assert warnings
    assert not damaged_span(span('犇犀犬'))  # normal Chinese fonts are not math fonts


def test_typography_preserves_scientific_symbols_and_does_not_guess_units_or_missing_digits():
    assert normalize_reading_typography('６． ２ 20℃ cm² ½ 10 mam 1 2') == '6.2 20℃ cm² ½ 10 mam 1 2'


def test_preview_uses_native_pdf_rendering_and_rejects_out_of_range_page():
    import pymupdf
    import pytest
    from app.core.exceptions import ValidationError
    with pymupdf.open() as document:
        document.new_page().insert_text((50,50),'Original 30.8 km/h')
        content=document.tobytes()
    assert render_standard_page(content,1).startswith(b'\x89PNG\r\n\x1a\n')
    for page in [0,2]:
        with pytest.raises(ValidationError):render_standard_page(content,page)


def test_formula_candidate_remains_review_material_never_an_executable_threshold():
    candidates = extract_candidates([{'page_number':6, 'extraction_method':'pdf_text_layer_layout',
        'text_warnings':['Broken symbol mapping'], 'text':'5.4.4.1 检验结果按式(1)计算\n'+SYMBOL_NOTICE}])
    assert len(candidates) == 1
    assert candidates[0]['candidate_type'] == 'body_clause'
    assert candidates[0]['status'] == 'pending' and candidates[0]['operator'] == 'unresolved'
    assert candidates[0]['requirement'] == '' and candidates[0]['reviewed_by'] is None
    assert candidates[0]['text_warnings'] == ['Broken symbol mapping']


def test_repair_never_replaces_published_or_manually_prepared_requirements():
    doc=SimpleNamespace(current_revision_id='old',published_revision_id=None)
    rev=SimpleNamespace(id='old',snapshot={'legacy':True},publication_status='unpublished',review_status='pending',
        reviewed_by=None,candidates_json=[{'status':'pending','requirement':'','prepared_by':None}])
    assert untouched_legacy(doc,rev)
    doc.published_revision_id='published'
    assert not untouched_legacy(doc,rev)
    doc.published_revision_id=None
    rev.candidates_json[0]['requirement']='Human prepared requirement'
    assert not untouched_legacy(doc,rev)
