from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
_FONT_NAME = "WenQuanYiMicroHei"
_FONT_BOLD_NAME = _FONT_NAME  # same font, fake-bold via reportlab

try:
    pdfmetrics.registerFont(TTFont(_FONT_NAME, _FONT_PATH, subfontIndex=0))
    _font_available = True
except Exception:
    _font_available = False


class PdfRenderer:
    def render(self, data: dict) -> bytes:
        font = _FONT_NAME if _font_available else "Helvetica"
        font_bold = _FONT_BOLD_NAME if _font_available else "Helvetica-Bold"

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=25 * mm, bottomMargin=20 * mm)
        story = []

        title_style = ParagraphStyle("Title2", fontName=font_bold, fontSize=20, leading=28)
        h2_style = ParagraphStyle("H2", fontName=font_bold, fontSize=14, leading=20, spaceAfter=6)
        body_style = ParagraphStyle("Body", fontName=font, fontSize=10, leading=14)
        footer_style = ParagraphStyle("Footer", fontName=font, fontSize=10, leading=14, alignment=1)

        # Cover
        story.append(Spacer(1, 30 * mm))
        story.append(Paragraph(data.get("report_name") or "PIAP 检测报告", title_style))
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(f"报告类型：{data.get('report_type_label') or '单任务检测报告'}", body_style))
        story.append(Paragraph(f"生成时间：{_now_str()}", body_style))
        story.append(Spacer(1, 10 * mm))

        # Overview
        story.append(Paragraph("一、检测概览", h2_style))
        task_info = data.get("task") or {}
        result_info = data.get("result") or {}
        overview_data = [
            ["字段", "值"],
            ["任务 ID", str(task_info.get("id") or "-")],
            ["产品编号", str(task_info.get("product_id") or "-")],
            ["检验标准", str(task_info.get("spec_code") or "-")],
            ["判定结果", _verdict_label(result_info.get("verdict"))],
            ["综合评分", f"{float(result_info.get('overall_score') or 0) * 100:.1f} 分"],
            ["模型引擎", str(result_info.get("llm_model") or "-")],
            ["Token 消耗", str(result_info.get("tokens_used") or "-")],
            ["耗时", f"{result_info.get('latency_ms') or '-'} ms" if result_info.get("latency_ms") else "-"],
        ]
        t = Table(overview_data, colWidths=[80 * mm, 80 * mm])
        t.setStyle(_table_style(font))
        story.append(t)
        story.append(Spacer(1, 8 * mm))

        # Defects
        defects = result_info.get("defects") or []
        story.append(Paragraph(f"二、缺陷明细（共 {len(defects)} 项）", h2_style))
        if defects:
            defect_data = [["序号", "缺陷类型", "置信度", "坐标框 (x,y,w,h)", "描述"]]
            for i, d in enumerate(defects):
                bbox = d.get("bbox")
                bbox_str = f"[{bbox[0]:.3f}, {bbox[1]:.3f}, {bbox[2]:.3f}, {bbox[3]:.3f}]" if isinstance(bbox, list) and len(bbox) == 4 else "-"
                defect_data.append([
                    str(i + 1),
                    str(d.get("type") or "-"),
                    f"{float(d.get('confidence') or 0) * 100:.0f}%",
                    bbox_str,
                    str(d.get("description") or ""),
                ])
            dt = Table(defect_data, colWidths=[12 * mm, 22 * mm, 18 * mm, 58 * mm, 50 * mm])
            dt.setStyle(_table_style(font, fontsize=9))
            story.append(dt)
        else:
            story.append(Paragraph("未检出缺陷", body_style))

        story.append(Spacer(1, 8 * mm))

        # Stability
        stability = data.get("stability") or {}
        if stability:
            story.append(Paragraph("三、稳定性评估", h2_style))
            stab_data = [
                ["指标", "分值"],
                ["证据评分", f"{float(stability.get('evidence_score') or 0) * 100:.1f}%"],
                ["一致性评分", f"{float(stability.get('consistency_score') or 0) * 100:.1f}%"],
                ["置信度评分", f"{float(stability.get('confidence_score') or 0) * 100:.1f}%"],
                ["溯源评分", f"{float(stability.get('traceability_score') or 0) * 100:.1f}%"],
                ["异常评分", f"{float(stability.get('anomaly_score') or 0) * 100:.1f}%"],
                ["风险等级", str(stability.get("risk_level") or "-")],
            ]
            st = Table(stab_data, colWidths=[60 * mm, 60 * mm])
            st.setStyle(_table_style(font))
            story.append(st)

        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph("— 报告结束 —", footer_style))

        doc.build(story)
        return buf.getvalue()


def _table_style(font_name: str, fontsize: int = 10) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), fontsize),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _verdict_label(verdict: str | None) -> str:
    if not verdict:
        return "-"
    m = {
        "pass": "合格 (PASS)",
        "fail": "不合格 (FAIL)",
        "uncertain": "不确定 (UNCERTAIN)",
        "manual_required": "需人工复核",
    }
    return m.get(str(verdict).lower(), str(verdict))
