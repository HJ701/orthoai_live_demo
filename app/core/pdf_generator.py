from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography import x509
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import settings
import os


BRAND_PRIMARY = colors.HexColor("#6366f1")
BRAND_DARK = colors.HexColor("#1f2937")
BRAND_MUTED = colors.HexColor("#6b7280")
BRAND_LINE = colors.HexColor("#e5e7eb")
PANEL_BG = colors.HexColor("#f8fafc")
SOFT_PURPLE = colors.HexColor("#f5f3ff")
SOFT_GREEN = colors.HexColor("#ecfdf5")
SOFT_AMBER = colors.HexColor("#fff7ed")
SOFT_RED = colors.HexColor("#fef2f2")


def safe_text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return escape(text) if text else fallback


def plain_text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def format_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number <= 1:
        number *= 100
    return f"{number:.0f}%"


def format_seconds(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.2f}s"


def format_date(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        return "-"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def display_class(value: Any) -> str:
    raw = plain_text(value)
    mapping = {
        "0": "Class I",
        "1": "Class II div 1",
        "2": "Class III",
        "unknown": "Unclassified",
    }
    return mapping.get(raw, raw)


def normalize_findings(findings: Dict[str, Any], per_image_evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in findings.get("findings", []) if isinstance(findings.get("findings"), list) else []:
        if not isinstance(item, dict):
            continue
        label = display_class(item.get("type") or item.get("label") or item.get("finding"))
        confidence = item.get("confidence")
        rows.append(
            {
                "label": label,
                "confidence": confidence,
                "risk": risk_for(label, confidence),
                "source": "Overall model output",
                "factor": item.get("factor") or "-",
            }
        )

    if rows:
        return rows

    for evidence in per_image_evidence:
        evidence_findings = evidence.get("findings") if isinstance(evidence, dict) else {}
        detections = evidence_findings.get("detections", []) if isinstance(evidence_findings, dict) else []
        for detection in detections if isinstance(detections, list) else []:
            if not isinstance(detection, dict):
                continue
            label = display_class(detection.get("type") or detection.get("label") or "Finding")
            confidence = detection.get("confidence", evidence.get("confidence"))
            rows.append(
                {
                    "label": label,
                    "confidence": confidence,
                    "risk": risk_for(label, confidence),
                    "source": evidence.get("filename", "Image evidence"),
                    "factor": detection.get("factor") or "-",
                }
            )
    return rows


def risk_for(label: str, confidence: Any) -> str:
    normalized = label.lower()
    if "low" in normalized or "normal" in normalized:
        return "Low"
    if "severe" in normalized or "high" in normalized:
        return "High"
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "Review"
    return "Low" if value < 0.65 else "Medium"


def risk_hex(risk: str) -> str:
    return {
        "Low": "#059669",
        "Medium": "#d97706",
        "High": "#dc2626",
    }.get(risk, "#6366f1")


def make_styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "OrthoAITitle",
            parent=base["Heading1"],
            fontName="Helvetica",
            fontSize=24,
            leading=30,
            textColor=BRAND_DARK,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "OrthoAISubtitle",
            parent=base["Normal"],
            fontSize=9,
            leading=13,
            textColor=BRAND_MUTED,
        ),
        "section": ParagraphStyle(
            "OrthoAISection",
            parent=base["Heading2"],
            fontSize=15,
            leading=19,
            textColor=BRAND_DARK,
            spaceBefore=8,
            spaceAfter=10,
        ),
        "body": ParagraphStyle(
            "OrthoAIBody",
            parent=base["Normal"],
            fontSize=9.5,
            leading=14,
            textColor=BRAND_DARK,
        ),
        "small": ParagraphStyle(
            "OrthoAISmall",
            parent=base["Normal"],
            fontSize=8,
            leading=11,
            textColor=BRAND_MUTED,
        ),
        "label": ParagraphStyle(
            "OrthoAILabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=BRAND_MUTED,
        ),
        "metric": ParagraphStyle(
            "OrthoAIMetric",
            parent=base["Heading2"],
            fontName="Helvetica",
            fontSize=24,
            leading=28,
            alignment=TA_CENTER,
            textColor=BRAND_PRIMARY,
        ),
        "metric_label": ParagraphStyle(
            "OrthoAIMetricLabel",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=BRAND_MUTED,
        ),
        "warning": ParagraphStyle(
            "OrthoAIWarning",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#7f1d1d"),
        ),
    }


def draw_header_footer(canvas: Canvas, doc: SimpleDocTemplate) -> None:
    canvas.saveState()
    width, height = letter
    canvas.setFillColor(BRAND_DARK)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(doc.leftMargin, height - 0.48 * inch, "OrthoAI")
    canvas.setFillColor(BRAND_MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - doc.rightMargin, height - 0.45 * inch, "Clinical Diagnostic Assistant")
    canvas.setStrokeColor(BRAND_LINE)
    canvas.line(doc.leftMargin, height - 0.62 * inch, width - doc.rightMargin, height - 0.62 * inch)

    canvas.setStrokeColor(BRAND_LINE)
    canvas.line(doc.leftMargin, 0.58 * inch, width - doc.rightMargin, 0.58 * inch)
    canvas.setFillColor(BRAND_MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(doc.leftMargin, 0.4 * inch, "For decision support only; not a standalone diagnostic tool.")
    canvas.drawString(doc.leftMargin, 0.26 * inch, "Model version: v1.0.0 | Data residency: UAE/GCC")
    canvas.drawRightString(width - doc.rightMargin, 0.26 * inch, f"Page {doc.page}")
    canvas.restoreState()


def paragraph(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(safe_text(text), style)


def key_value_table(rows: List[List[Any]], styles: Dict[str, ParagraphStyle], col_widths: Optional[List[float]] = None) -> Table:
    data = []
    for label, value in rows:
        data.append([Paragraph(safe_text(label), styles["label"]), Paragraph(safe_text(value), styles["body"])])
    table = Table(data, colWidths=col_widths or [1.45 * inch, 4.95 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), PANEL_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eef2f7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def metric_card(value: Any, label: str, bg_color: colors.Color, styles: Dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [[Paragraph(safe_text(value), styles["metric"])], [Paragraph(safe_text(label), styles["metric_label"])]],
        colWidths=[1.75 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                ("BOX", (0, 0), (-1, -1), 0, bg_color),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def generate_pdf_summary(
    case_id: int,
    model_version: str,
    findings: Dict[str, Any],
    summary: str,
    confidences: Dict[str, float],
    per_image_evidence: List[Dict[str, Any]],
    case_metadata: Optional[Dict[str, Any]] = None,
    job_metadata: Optional[Dict[str, Any]] = None,
) -> BytesIO:
    """Generate a clinician-facing OrthoAI diagnostic summary PDF."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.75 * inch,
        title=f"OrthoAI Case {case_id} Summary",
        author="OrthoAI",
    )
    styles = make_styles()
    story: List[Any] = []
    case_metadata = case_metadata or {}
    job_metadata = job_metadata or {}
    prediction = findings.get("prediction", {}) if isinstance(findings.get("prediction"), dict) else {}
    timings = findings.get("timings", {}) if isinstance(findings.get("timings"), dict) else {}
    finding_rows = normalize_findings(findings, per_image_evidence)
    low_risk_count = sum(1 for row in finding_rows if row["risk"] == "Low")
    attention_count = max(len(finding_rows) - low_risk_count, 0)
    predicted_class = display_class(prediction.get("predicted_class"))
    confidence = prediction.get("confidence")
    generated_at = datetime.now(timezone.utc)

    story.append(Paragraph(safe_text(case_metadata.get("title") or "OrthoAI Diagnostic Summary"), styles["title"]))
    story.append(
        Paragraph(
            "AI-assisted orthodontic evaluation prepared for clinician review. This document is not a final diagnosis.",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 0.16 * inch))

    story.append(
        key_value_table(
            [
                ["Case ID", case_id],
                ["Patient ID / Code", case_metadata.get("patient_id") or "Not provided"],
                ["Clinic Location", case_metadata.get("clinic_location") or "Not provided"],
                ["Case Created", format_date(case_metadata.get("created_at"))],
                ["Report Generated", format_date(generated_at)],
                ["Model Version", model_version],
                ["Job ID", job_metadata.get("job_id") or "-"],
                ["Inference Completed", format_date(job_metadata.get("completed_at"))],
            ],
            styles,
        )
    )
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("Executive Summary", styles["section"]))
    summary_text = summary or (
        f"Processed {findings.get('total_images', len(per_image_evidence))} image(s). "
        f"Predicted class: {predicted_class} with {format_percent(confidence)} confidence."
    )
    story.append(paragraph(summary_text, styles["body"]))
    story.append(Spacer(1, 0.12 * inch))

    metrics = Table(
        [
            [
                metric_card(len(finding_rows) or 1, "Findings", SOFT_PURPLE, styles),
                metric_card(low_risk_count, "Low Risk", SOFT_GREEN, styles),
                metric_card(attention_count or 1, "Require Attention", SOFT_AMBER, styles),
            ]
        ],
        colWidths=[2.05 * inch, 2.05 * inch, 2.05 * inch],
        hAlign="LEFT",
    )
    metrics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(metrics)
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Model Output", styles["section"]))
    story.append(
        key_value_table(
            [
                ["Predicted Class", predicted_class],
                ["Overall Confidence", format_percent(confidence)],
                ["Images Processed", findings.get("total_images", len(per_image_evidence))],
                ["Runtime Load", format_seconds(timings.get("runtime_load_seconds"))],
                ["Image Loading", format_seconds(timings.get("image_load_seconds"))],
                ["Model Prediction", format_seconds(timings.get("model_predict_seconds"))],
                ["Total Inference", format_seconds(timings.get("total_inference_seconds"))],
            ],
            styles,
        )
    )
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("Key Findings", styles["section"]))
    if finding_rows:
        finding_table_data = [
            [
                Paragraph("Finding", styles["label"]),
                Paragraph("Confidence", styles["label"]),
                Paragraph("Risk", styles["label"]),
                Paragraph("Source", styles["label"]),
            ]
        ]
        for row in finding_rows:
            finding_table_data.append(
                [
                    Paragraph(safe_text(row["label"]), styles["body"]),
                    Paragraph(format_percent(row["confidence"]), styles["body"]),
                    Paragraph(f"<font color='{risk_hex(row['risk'])}'>{safe_text(row['risk'])}</font>", styles["body"]),
                    Paragraph(safe_text(row["source"]), styles["body"]),
                ]
            )
        finding_table = Table(finding_table_data, colWidths=[2.25 * inch, 1.0 * inch, 0.85 * inch, 2.25 * inch], repeatRows=1)
        finding_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL_BG]),
                    ("BOX", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(finding_table)
    else:
        story.append(paragraph("No structured findings were returned by the model for this case.", styles["body"]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Per-Image Evidence", styles["section"]))
    if per_image_evidence:
        evidence_data = [
            [
                Paragraph("Image", styles["label"]),
                Paragraph("Confidence", styles["label"]),
                Paragraph("Detected Findings", styles["label"]),
            ]
        ]
        for index, evidence in enumerate(per_image_evidence, start=1):
            detections = []
            evidence_findings = evidence.get("findings", {})
            raw_detections = evidence_findings.get("detections", []) if isinstance(evidence_findings, dict) else []
            for detection in raw_detections if isinstance(raw_detections, list) else []:
                if isinstance(detection, dict):
                    detections.append(
                        f"{display_class(detection.get('type'))} ({format_percent(detection.get('confidence'))})"
                    )
            evidence_data.append(
                [
                    Paragraph(f"Image {index}<br/><font color='#6b7280'>{safe_text(evidence.get('filename'))}</font>", styles["body"]),
                    Paragraph(format_percent(evidence.get("confidence")), styles["body"]),
                    Paragraph(safe_text("; ".join(detections) or "No findings recorded"), styles["body"]),
                ]
            )
        evidence_table = Table(evidence_data, colWidths=[2.0 * inch, 1.0 * inch, 3.35 * inch], repeatRows=1)
        evidence_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL_BG]),
                    ("BOX", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(evidence_table)
    else:
        story.append(paragraph("No per-image evidence records were available.", styles["body"]))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Clinical Review Checklist", styles["section"]))
    checklist = [
        ["Verify patient identity using the clinic's de-identified patient ID/code."],
        ["Review image quality, modality selection, and whether OPG/panoramic evidence is present when required."],
        ["Correlate AI findings with clinical examination, radiographic interpretation, and treatment history."],
        ["Record clinician agreement, disagreement, or override rationale in the clinical validation workflow."],
    ]
    checklist_table = Table([[Paragraph(safe_text(item[0]), styles["body"])] for item in checklist], colWidths=[6.4 * inch])
    checklist_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PANEL_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eef2f7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(checklist_table)

    story.append(Spacer(1, 0.22 * inch))
    story.append(
        Table(
            [[Paragraph("Important Clinical Disclaimer", styles["label"])], [Paragraph(
                "OrthoAI is a decision-support system. It is not a standalone diagnostic device and does not replace clinician judgment. "
                "All AI-generated findings must be reviewed by a qualified clinician before use in diagnosis, referral, treatment planning, or patient communication.",
                styles["warning"],
            )]],
            colWidths=[6.4 * inch],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT_RED),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        )
    )

    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    buffer.seek(0)
    return buffer


def sign_pdf(pdf_buffer: BytesIO) -> BytesIO:
    """Sign a PDF with a certificate (simplified - in production use proper PDF signing)."""
    # In production, use proper PDF signing libraries like pyHanko.
    # This function currently preserves the hook and returns the generated PDF unchanged.
    if settings.pdf_signing_key_path and os.path.exists(settings.pdf_signing_key_path):
        pass

    pdf_buffer.seek(0)
    return pdf_buffer
