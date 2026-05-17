from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from typing import Dict, Any, List
from app.config import settings
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography import x509
import os


def generate_pdf_summary(
    case_id: int,
    model_version: str,
    findings: Dict[str, Any],
    summary: str,
    confidences: Dict[str, float],
    per_image_evidence: List[Dict[str, Any]]
) -> BytesIO:
    """Generate a PDF summary report"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Title
    story.append(Paragraph("Medical AI Analysis Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Case Information
    story.append(Paragraph(f"<b>Case ID:</b> {case_id}", styles['Normal']))
    story.append(Paragraph(f"<b>Model Version:</b> {model_version}", styles['Normal']))
    story.append(Paragraph(f"<b>Generated:</b> {json.dumps(findings.get('timestamp', ''))}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Summary
    story.append(Paragraph("<b>Summary</b>", styles['Heading2']))
    story.append(Paragraph(summary, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Findings
    story.append(Paragraph("<b>Findings</b>", styles['Heading2']))
    findings_text = json.dumps(findings, indent=2)
    story.append(Paragraph(f"<pre>{findings_text}</pre>", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Confidences
    story.append(Paragraph("<b>Confidence Scores</b>", styles['Heading2']))
    conf_data = [[k, f"{v:.2%}"] for k, v in confidences.items()]
    conf_table = Table(conf_data, colWidths=[3*inch, 2*inch])
    conf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(conf_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Per-image Evidence
    if per_image_evidence:
        story.append(Paragraph("<b>Per-Image Evidence</b>", styles['Heading2']))
        for evidence in per_image_evidence:
            story.append(Paragraph(f"<b>Image:</b> {evidence.get('filename', 'N/A')}", styles['Normal']))
            story.append(Paragraph(f"<b>Confidence:</b> {evidence.get('confidence', 0):.2%}", styles['Normal']))
            evidence_findings = json.dumps(evidence.get('findings', {}), indent=2)
            story.append(Paragraph(f"<pre>{evidence_findings}</pre>", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    buffer.seek(0)
    return buffer


def sign_pdf(pdf_buffer: BytesIO) -> BytesIO:
    """Sign a PDF with a certificate (simplified - in production use proper PDF signing)"""
    # In production, use proper PDF signing libraries like PyPDF2 or pdf-lib
    # This is a placeholder that returns the PDF as-is
    # For real signing, you would:
    # 1. Load the private key and certificate
    # 2. Create a signature field
    # 3. Sign the PDF using cryptographic operations
    
    if settings.pdf_signing_key_path and os.path.exists(settings.pdf_signing_key_path):
        # Placeholder for actual signing logic
        # In production, implement proper PDF signing
        pass
    
    pdf_buffer.seek(0)
    return pdf_buffer

