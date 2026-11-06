import io
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

def generate_pdf(paper, sections, sources):
    """
    Generates an academic research paper PDF in memory using ReportLab.
    Returns the binary PDF content as bytes (ready for browser download).
    """
    buffer = io.BytesIO()
    
    # Initialize ReportLab document template with standard margins
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=54, 
        leftMargin=54, 
        topMargin=54, 
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Define custom styles for Title, Section Headings, and Body Text
    title_style = ParagraphStyle(
        'PaperTitle',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=14
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        spaceBefore=12,
        spaceAfter=6
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        alignment=TA_JUSTIFY,
        fontSize=10,
        leading=14,
        spaceAfter=8
    )

    story = []

    # 1. Render Main Research Topic Title
    story.append(Paragraph(paper.topic, title_style))
    story.append(Spacer(1, 10))

    # 2. Render Paper Sections (Abstract, Keywords, Intro, Lit Review, etc.)
    for sec in sections:
        if sec.section_name.lower() == 'title':
            continue  # Avoid repeating main title block
            
        story.append(Paragraph(sec.section_name, heading_style))
        
        # Split section content into paragraphs to preserve line breaks
        paragraphs = sec.content.split('\n') if sec.content else []
        for p in paragraphs:
            p_text = p.strip()
            if p_text:
                story.append(Paragraph(p_text, body_style))
        story.append(Spacer(1, 6))

    # 3. Render References Section
    if sources:
        story.append(Paragraph("References", heading_style))
        for idx, src in enumerate(sources, 1):
            ref_text = f"[{idx}] {src.authors} ({src.publication_year or 'n.d.'}). <i>{src.title}</i>."
            if src.url:
                ref_text += f" Link: {src.url}"
            story.append(Paragraph(ref_text, body_style))

    # Build PDF into BytesIO memory buffer
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_docx(paper, sections, sources):
    """
    Generates a Word document (.docx) in memory using python-docx.
    Returns the binary DOCX content as bytes (ready for browser download).
    """
    buffer = io.BytesIO()
    doc = Document()

    # 1. Add Main Title
    doc.add_heading(paper.topic, level=0)

    # 2. Add Sections (Abstract, Keywords, Intro, Lit Review, etc.)
    for sec in sections:
        if sec.section_name.lower() == 'title':
            continue
            
        doc.add_heading(sec.section_name, level=1)
        
        paragraphs = sec.content.split('\n') if sec.content else []
        for p in paragraphs:
            p_text = p.strip()
            if p_text:
                doc.add_paragraph(p_text)

    # 3. Add References Section
    if sources:
        doc.add_heading("References", level=1)
        for idx, src in enumerate(sources, 1):
            ref_text = f"[{idx}] {src.authors} ({src.publication_year or 'n.d.'}). {src.title}."
            if src.url:
                ref_text += f" Link: {src.url}"
            doc.add_paragraph(ref_text)

    # Save Word document to memory stream
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
