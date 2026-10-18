from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
from app.services.report_renderers.report_content import report_sections

_FONT_NAME='PIAPChinese'
_font_available=False
for path in ['/usr/share/fonts/truetype/wqy/wqy-microhei.ttc','C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simsun.ttc']:
    if not Path(path).is_file():continue
    try:
        pdfmetrics.registerFont(TTFont(_FONT_NAME,path,subfontIndex=0));_font_available=True;break
    except Exception:continue


class PdfRenderer:
    def render(self,data):
        font=_FONT_NAME if _font_available else 'Helvetica'
        body=ParagraphStyle('PIAPBody',fontName=font,fontSize=9,leading=13 if data.get('risk_report') else 14,wordWrap='CJK',spaceAfter=4)
        heading=ParagraphStyle('PIAPHeading',parent=body,fontSize=13,leading=19,spaceBefore=12,spaceAfter=7,keepWithNext=True)
        before_table=ParagraphStyle('PIAPBeforeTable',parent=body,keepWithNext=True)
        title=ParagraphStyle('PIAPTitle',parent=heading,fontSize=18,leading=25)
        output=BytesIO();story=[]
        def p(value,style=body):return Paragraph(escape(str(value if value is not None else '未提供')).replace('\n','<br/>'),style)
        story.append(p(('PIAP 演示研判报告 · 模拟资料' if data['risk_report']['snapshot'].get('execution_mode') == 'demo' else 'PIAP 风险研判报告') if data.get('risk_report') else 'PIAP 任务检测记录 · 产品整体未评定',title))
        story.append(p(data.get('report_name') or '任务检测记录'))
        story.append(p(data.get('report_type_label') or '单任务检测记录'))
        for section in report_sections(data):
            story.append(p(section['title'],heading))
            for line in section.get('paragraphs',[]):story.append(p(line,before_table if section.get('rows') else body))
            rows=section.get('rows') or []
            if not rows:continue
            columns=section.get('columns');values=([columns] if columns else [])+rows
            widths=section.get('widths') or [45,115]
            table=Table([[p(cell) for cell in row] for row in values],colWidths=[w*mm for w in widths],repeatRows=1 if columns else 0,hAlign='LEFT')
            table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#CBD5E1')),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEF4FA'))]))
            story.extend([table,Spacer(1,3*mm)])
        doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=25*mm,rightMargin=25*mm,topMargin=22*mm,bottomMargin=20*mm)
        def footer(canvas,document):
            canvas.setFont(font,8);canvas.drawString(25*mm,12*mm,'PIAP · 演示 / 模拟资料 / 生成时快照' if (data.get('risk_report') or {}).get('snapshot', {}).get('execution_mode') == 'demo' else 'PIAP · 生成时快照 / 限定范围记录');canvas.drawRightString(185*mm,12*mm,str(document.page))
        doc.build(story,onFirstPage=footer,onLaterPages=footer)
        return output.getvalue()
