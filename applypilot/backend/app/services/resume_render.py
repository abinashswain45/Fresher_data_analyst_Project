"""Render a structured resume into ATS-friendly DOCX and PDF files (single column, standard headings)."""
import io
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from ..schemas import CandidateProfileData


def _contact_line(p: CandidateProfileData) -> str:
    return " | ".join(x for x in (p.email, p.phone, p.location, p.linkedin_url, p.portfolio_url) if x)


def _date_range(start: str, end: str, current: bool) -> str:
    end = "Present" if current and not end else end
    return " – ".join(x for x in (start, end) if x)


def sections(p: CandidateProfileData) -> list[tuple[str, list]]:
    """Normalised section list: (heading, [entries]) where an entry is a str or (title, meta, bullets)."""
    out: list[tuple[str, list]] = []
    if p.professional_summary:
        out.append(("Professional Summary", [p.professional_summary]))
    if p.technical_skills or p.soft_skills:
        items = []
        if p.technical_skills:
            items.append("Technical: " + ", ".join(p.technical_skills))
        if p.soft_skills:
            items.append("Professional: " + ", ".join(p.soft_skills))
        out.append(("Skills", items))
    if p.experience:
        out.append(("Professional Experience", [
            (" – ".join(x for x in (e.title, e.company) if x),
             " | ".join(x for x in (e.location, _date_range(e.start_date, e.end_date, e.is_current)) if x),
             e.responsibilities) for e in p.experience]))
    if p.projects:
        out.append(("Projects", [
            (pr.name, ", ".join(pr.technologies), [pr.description] if pr.description else []) for pr in p.projects]))
    if p.education:
        out.append(("Education", [
            (" – ".join(x for x in (ed.degree + (f" in {ed.field_of_study}" if ed.field_of_study else ""), ed.institution) if x),
             " | ".join(x for x in (_date_range(ed.start_date, ed.end_date, False), ed.grade) if x), []) for ed in p.education]))
    if p.certifications:
        out.append(("Certifications", [" – ".join(x for x in (c.name, c.issuer, c.date) if x) for c in p.certifications]))
    if p.achievements:
        out.append(("Achievements", [("", "", p.achievements)]))
    if p.languages:
        out.append(("Languages", [", ".join(p.languages)]))
    return out


def render_docx(p: CandidateProfileData) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for s in doc.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Pt(50)
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = h.add_run(p.full_name or "Candidate")
    r.bold = True
    r.font.size = Pt(18)
    if p.current_title:
        t = doc.add_paragraph(p.current_title)
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c = doc.add_paragraph(_contact_line(p))
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for heading, entries in sections(p):
        hp = doc.add_paragraph()
        hr = hp.add_run(heading.upper())
        hr.bold = True
        hr.font.size = Pt(12)
        hr.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
        for e in entries:
            if isinstance(e, str):
                doc.add_paragraph(e)
                continue
            title, meta, bullets = e
            if title or meta:
                para = doc.add_paragraph()
                if title:
                    para.add_run(title).bold = True
                if meta:
                    para.add_run(("  |  " if title else "") + meta).italic = True
            for b in bullets:
                doc.add_paragraph(b, style="List Bullet")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_pdf(p: CandidateProfileData) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title=f"{p.full_name} Resume",
                            author=p.full_name)
    ss = getSampleStyleSheet()
    name = ParagraphStyle("name", parent=ss["Title"], fontSize=18, spaceAfter=2)
    center = ParagraphStyle("center", parent=ss["Normal"], alignment=1, fontSize=9.5)
    head = ParagraphStyle("head", parent=ss["Heading3"], textColor="#1F3A5F", spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=13)
    story = [Paragraph(escape(p.full_name or "Candidate"), name)]
    if p.current_title:
        story.append(Paragraph(escape(p.current_title), center))
    story.append(Paragraph(escape(_contact_line(p)), center))
    for heading, entries in sections(p):
        story.append(Paragraph(escape(heading.upper()), head))
        for e in entries:
            if isinstance(e, str):
                story.append(Paragraph(escape(e), body))
                continue
            title, meta, bullets = e
            if title or meta:
                story.append(Paragraph(f"<b>{escape(title)}</b>" + (f"  <i>{escape(meta)}</i>" if meta else ""), body))
            if bullets:
                story.append(ListFlowable([ListItem(Paragraph(escape(b), body), leftIndent=10) for b in bullets],
                                          bulletType="bullet", start="•", leftIndent=12))
            story.append(Spacer(1, 3))
    doc.build(story)
    return buf.getvalue()
