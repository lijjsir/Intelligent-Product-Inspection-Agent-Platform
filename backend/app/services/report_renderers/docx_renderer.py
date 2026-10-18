from io import BytesIO
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm,Pt
from app.services.report_renderers.report_content import report_sections


class DocxRenderer:
    def render(self,data):
        document=Document();section=document.sections[0]
        zoom=document.settings.element.find(qn('w:zoom'))
        if zoom is not None:zoom.set(qn('w:percent'),'100')
        section.page_width,section.page_height=Mm(210),Mm(297)
        section.top_margin,section.bottom_margin=Mm(22),Mm(20)
        section.left_margin=section.right_margin=Mm(25)
        for name in ['Normal','Title','Heading 1','Heading 2']:
            style=document.styles[name];style.font.name='Arial';style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'宋体')
        document.styles['Normal'].font.size=Pt(10)
        if data.get('risk_report'):document.styles['Normal'].paragraph_format.space_after=Pt(4)
        document.add_heading(('PIAP 演示研判报告 · 模拟资料' if data['risk_report']['snapshot'].get('execution_mode') == 'demo' else 'PIAP 风险研判报告') if data.get('risk_report') else 'PIAP 任务检测记录 · 产品整体未评定',0)
        document.add_paragraph(data.get('report_name') or '任务检测记录')
        document.add_paragraph(data.get('report_type_label') or '单任务检测记录')
        for item in report_sections(data):
            document.add_heading(item['title'],1)
            for line in item.get('paragraphs',[]):document.add_paragraph(str(line))
            rows=item.get('rows') or []
            if not rows:continue
            columns=item.get('columns');values=([columns] if columns else [])+rows
            widths=item.get('widths') or [45,115]
            table=document.add_table(rows=0,cols=len(widths));table.style='Table Grid';table.autofit=False
            for col,width in zip(table.columns,widths):col.width=Mm(width)
            for index,row in enumerate(values):
                target=table.add_row()
                for cell,width,value in zip(target.cells,widths,row):
                    cell.width=Mm(width);cell.text=str(value if value is not None else '未提供')
                if columns and index==0:
                    repeat=OxmlElement('w:tblHeader');target._tr.get_or_add_trPr().append(repeat)
                # Prevent clipped, long source hashes while preserving their text.
                for cell in target.cells:
                    for para in cell.paragraphs:
                        para.paragraph_format.space_after=Pt(3)
                        for run in para.runs:run.font.size=Pt(9)
        footer=section.footer.paragraphs[0];footer.add_run('PIAP · 演示 / 模拟资料 / 生成时快照 · ' if (data.get('risk_report') or {}).get('snapshot', {}).get('execution_mode') == 'demo' else 'PIAP · 生成时快照 / 限定范围记录 · ')
        page=OxmlElement('w:fldSimple');page.set(qn('w:instr'),'PAGE');footer._p.append(page)
        output=BytesIO();document.save(output);return output.getvalue()
