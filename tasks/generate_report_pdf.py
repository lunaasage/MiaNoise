"""
Generate a styled PDF from tasks/project_report.md
Output: tasks/MiaNoise_Project_Report.pdf
"""

import re
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY       = colors.HexColor("#0F4C75")
BLUE       = colors.HexColor("#1B98E0")
LIGHT_BLUE = colors.HexColor("#E8F4FD")
CORAL      = colors.HexColor("#E8521A")
CORAL_SOFT = colors.HexColor("#FDF0EB")
INK        = colors.HexColor("#1A2332")
GRAY_TEXT  = colors.HexColor("#4A5568")
GRAY_LIGHT = colors.HexColor("#F7F9FC")
GRAY_MID   = colors.HexColor("#E2E8F0")
GREEN      = colors.HexColor("#1A9E5C")
AMBER      = colors.HexColor("#D97706")
WHITE      = colors.white
CODE_BG    = colors.HexColor("#F1F5F9")
CODE_FG    = colors.HexColor("#1E3A5F")

# ── Custom Flowables ──────────────────────────────────────────────────────────

class CoverPage(Flowable):
    """Full-bleed cover page."""
    def __init__(self, width, height):
        Flowable.__init__(self)
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height

        # Navy background
        c.setFillColor(NAVY)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # Coral accent bar at top
        c.setFillColor(CORAL)
        c.rect(0, h - 6, w, 6, fill=1, stroke=0)

        # Decorative circle (top-right)
        c.setFillColor(colors.HexColor("#1B4F72"))
        c.circle(w + 20, h - 40, 140, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#154360"))
        c.circle(w + 60, h - 120, 90, fill=1, stroke=0)

        # Bottom wave decoration
        c.setFillColor(colors.HexColor("#0D3F63"))
        c.rect(0, 0, w, 80, fill=1, stroke=0)
        c.setFillColor(CORAL)
        c.rect(0, 0, w, 4, fill=1, stroke=0)

        # "MIANOISE" large label
        c.setFillColor(colors.HexColor("#1B98E0"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(54, h - 54, "M I A N O I S E")

        # Divider line under brand
        c.setStrokeColor(CORAL)
        c.setLineWidth(1.5)
        c.line(54, h - 64, 200, h - 64)

        # Main title
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 32)
        c.drawString(54, h - 160, "Full Project Report")

        # Subtitle
        c.setFillColor(colors.HexColor("#A8C8E8"))
        c.setFont("Helvetica", 14)
        c.drawString(54, h - 190, "Sprint 0  →  Sprint 4.3")

        # For Jeanne note
        c.setFillColor(CORAL)
        c.setFont("Helvetica-BoldOblique", 11)
        c.drawString(54, h - 230,
            "For Jeanne — everything you need to present this as if you'd been here.")

        # Scope tag pill
        c.setFillColor(colors.HexColor("#1B4F72"))
        c.roundRect(54, h - 290, 220, 28, 6, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(66, h - 279, "PoC Branch  ·  April 2026")

        # Date
        c.setFillColor(colors.HexColor("#7FB3D3"))
        c.setFont("Helvetica", 10)
        c.drawString(54, 30, "Last updated: April 27, 2026")

        # Page note
        c.setFillColor(colors.HexColor("#7FB3D3"))
        c.setFont("Helvetica", 9)
        c.drawRightString(w - 54, 30, "MiaNoise — Miami Neighborhood Noise Intelligence")


class SectionBadge(Flowable):
    """Colored left-border section header block."""
    def __init__(self, number, title, date=None, width=468):
        Flowable.__init__(self)
        self.number = number
        self.title = title
        self.date = date
        self.width = width
        self.height = 52 if date else 44

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(LIGHT_BLUE)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        # Left accent bar
        c.setFillColor(NAVY)
        c.roundRect(0, 0, 5, self.height, 2, fill=1, stroke=0)
        # Section number
        c.setFillColor(CORAL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(16, self.height - 18, self.number)
        # Title
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(16, self.height - 35, self.title)
        # Date
        if self.date:
            c.setFillColor(GRAY_TEXT)
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(16, 8, self.date)


class QuoteBlock(Flowable):
    """Styled blockquote."""
    def __init__(self, text, width=468):
        Flowable.__init__(self)
        self.text = text
        self.width = width
        # Estimate height: ~13pt per line, ~70 chars per line
        lines = max(3, len(text) // 68 + 1)
        self.height = lines * 15 + 24

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(CORAL_SOFT)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        # Left accent
        c.setFillColor(CORAL)
        c.roundRect(0, 0, 4, self.height, 2, fill=1, stroke=0)
        # Text (simplified — draw as italic)
        c.setFillColor(INK)
        c.setFont("Helvetica-Oblique", 10)
        # Word-wrap manually
        words = self.text.split()
        line, lines_out = [], []
        for w in words:
            test = " ".join(line + [w])
            if c.stringWidth(test, "Helvetica-Oblique", 10) < self.width - 32:
                line.append(w)
            else:
                lines_out.append(" ".join(line))
                line = [w]
        if line:
            lines_out.append(" ".join(line))
        y = self.height - 18
        for ln in lines_out:
            c.drawString(16, y, ln)
            y -= 14


class HorizontalRule(Flowable):
    def __init__(self, width=468, color=GRAY_MID, thickness=0.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 1

    def draw(self):
        c = self.canv
        c.setStrokeColor(self.color)
        c.setLineWidth(self.thickness)
        c.line(0, 0, self.width, 0)


# ── Page Template ─────────────────────────────────────────────────────────────

def draw_cover(canvas, doc):
    """Draw full-bleed cover on page 1."""
    canvas.saveState()
    w, h = letter

    # Navy background
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Coral accent bar at top
    canvas.setFillColor(CORAL)
    canvas.rect(0, h - 6, w, 6, fill=1, stroke=0)

    # Decorative circles
    canvas.setFillColor(colors.HexColor("#1B4F72"))
    canvas.circle(w + 20, h - 40, 140, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#154360"))
    canvas.circle(w + 60, h - 120, 90, fill=1, stroke=0)

    # Bottom bar
    canvas.setFillColor(colors.HexColor("#0D3F63"))
    canvas.rect(0, 0, w, 80, fill=1, stroke=0)
    canvas.setFillColor(CORAL)
    canvas.rect(0, 0, w, 4, fill=1, stroke=0)

    # Brand label
    canvas.setFillColor(colors.HexColor("#1B98E0"))
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(54, h - 54, "M I A N O I S E")
    canvas.setStrokeColor(CORAL)
    canvas.setLineWidth(1.5)
    canvas.line(54, h - 64, 200, h - 64)

    # Main title
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 34)
    canvas.drawString(54, h - 155, "Full Project Report")

    # Sprint range
    canvas.setFillColor(colors.HexColor("#A8C8E8"))
    canvas.setFont("Helvetica", 14)
    canvas.drawString(54, h - 185, "Sprint 0  →  Sprint 4.3")

    # For Jeanne note
    canvas.setFillColor(CORAL)
    canvas.setFont("Helvetica-BoldOblique", 11)
    canvas.drawString(54, h - 225,
        "For Jeanne — everything you need to present this as if you'd been here.")

    # Scope pill
    canvas.setFillColor(colors.HexColor("#1B4F72"))
    canvas.roundRect(54, h - 282, 220, 28, 6, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(66, h - 271, "PoC Branch  ·  April 2026")

    # Section preview pills
    sections = ["Data Ingestion", "RAG Pipeline", "LangChain Agent",
                "Score Recalibration", "RAGAS Evaluation"]
    x = 54
    y = h - 340
    canvas.setFont("Helvetica", 9)
    for s in sections:
        sw = canvas.stringWidth(s, "Helvetica", 9) + 18
        canvas.setFillColor(colors.HexColor("#0D3F63"))
        canvas.roundRect(x, y, sw, 20, 4, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#7FB3D3"))
        canvas.drawString(x + 9, y + 6, s)
        x += sw + 8
        if x > w - 120:
            x = 54
            y -= 28

    # Date
    canvas.setFillColor(colors.HexColor("#7FB3D3"))
    canvas.setFont("Helvetica", 10)
    canvas.drawString(54, 30, "Last updated: April 27, 2026")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 54, 30, "MiaNoise — Miami Neighborhood Noise Intelligence")

    canvas.restoreState()


def make_header_footer(canvas, doc):
    """Draw header/footer on every non-cover page."""
    if doc.page == 1:
        draw_cover(canvas, doc)
        return
    canvas.saveState()
    w = letter[0]

    # Header line
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(0.75)
    canvas.line(0.6 * inch, letter[1] - 0.5 * inch, w - 0.6 * inch, letter[1] - 0.5 * inch)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.6 * inch, letter[1] - 0.42 * inch, "MIANOISE")
    canvas.setFillColor(GRAY_TEXT)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 0.6 * inch, letter[1] - 0.42 * inch, "Full Project Report — April 2026")

    # Footer
    canvas.setStrokeColor(GRAY_MID)
    canvas.setLineWidth(0.5)
    canvas.line(0.6 * inch, 0.55 * inch, w - 0.6 * inch, 0.55 * inch)
    canvas.setFillColor(GRAY_TEXT)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(w / 2, 0.38 * inch, f"{doc.page - 1}")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 0.6 * inch, 0.38 * inch, "Confidential — Internal Use")

    canvas.restoreState()


# ── Style Definitions ─────────────────────────────────────────────────────────

def make_styles():
    s = {}

    s['body'] = ParagraphStyle(
        'body', fontName='Helvetica', fontSize=10, leading=15,
        textColor=INK, spaceAfter=8, spaceBefore=2,
        alignment=TA_JUSTIFY
    )
    s['body_left'] = ParagraphStyle(
        'body_left', parent=s['body'], alignment=TA_LEFT
    )
    s['h2'] = ParagraphStyle(
        'h2', fontName='Helvetica-Bold', fontSize=13, leading=17,
        textColor=NAVY, spaceBefore=18, spaceAfter=6,
        borderPad=0
    )
    s['h3'] = ParagraphStyle(
        'h3', fontName='Helvetica-Bold', fontSize=11, leading=14,
        textColor=NAVY, spaceBefore=14, spaceAfter=4
    )
    s['toc_title'] = ParagraphStyle(
        'toc_title', fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=NAVY, spaceBefore=0, spaceAfter=14
    )
    s['toc_entry'] = ParagraphStyle(
        'toc_entry', fontName='Helvetica', fontSize=10, leading=16,
        textColor=INK, leftIndent=0, spaceAfter=2
    )
    s['bullet'] = ParagraphStyle(
        'bullet', fontName='Helvetica', fontSize=10, leading=14,
        textColor=INK, leftIndent=18, firstLineIndent=-10,
        spaceAfter=4, bulletText='•'
    )
    s['sub_bullet'] = ParagraphStyle(
        'sub_bullet', fontName='Helvetica', fontSize=10, leading=14,
        textColor=INK, leftIndent=36, firstLineIndent=-10,
        spaceAfter=3, bulletText='–'
    )
    s['numbered'] = ParagraphStyle(
        'numbered', fontName='Helvetica', fontSize=10, leading=14,
        textColor=INK, leftIndent=22, firstLineIndent=-14, spaceAfter=3
    )
    s['code_block'] = ParagraphStyle(
        'code_block', fontName='Courier', fontSize=8.5, leading=13,
        textColor=CODE_FG, backColor=CODE_BG,
        leftIndent=12, rightIndent=12,
        spaceBefore=6, spaceAfter=6,
        borderPad=8
    )
    s['caption'] = ParagraphStyle(
        'caption', fontName='Helvetica-Oblique', fontSize=9, leading=12,
        textColor=GRAY_TEXT, spaceBefore=2, spaceAfter=8, alignment=TA_CENTER
    )
    s['attempt_label'] = ParagraphStyle(
        'attempt_label', fontName='Helvetica-Bold', fontSize=10, leading=14,
        textColor=CORAL, spaceBefore=8, spaceAfter=2
    )
    s['sprint_date'] = ParagraphStyle(
        'sprint_date', fontName='Helvetica-Oblique', fontSize=9.5, leading=13,
        textColor=GRAY_TEXT, spaceBefore=0, spaceAfter=8
    )
    s['notable'] = ParagraphStyle(
        'notable', fontName='Helvetica', fontSize=10, leading=14,
        textColor=INK, leftIndent=14, spaceAfter=4,
        borderPad=0
    )
    s['appendix_note'] = ParagraphStyle(
        'appendix_note', fontName='Helvetica-Oblique', fontSize=9, leading=13,
        textColor=GRAY_TEXT, spaceBefore=4, spaceAfter=4, leftIndent=0
    )
    return s


# ── Text Processing ───────────────────────────────────────────────────────────

def escape_xml(text):
    """Escape XML special chars for ReportLab paragraphs."""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text

def md_inline(text):
    """Convert inline markdown to ReportLab XML. Call AFTER escape_xml."""
    # Bold+italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic (asterisk)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Italic (underscore, not inside words)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)
    # Inline code
    text = re.sub(
        r'`([^`]+)`',
        r'<font name="Courier" color="#1E3A5F" backColor="#F1F5F9"> \1 </font>',
        text
    )
    return text

def process_inline(text):
    return md_inline(escape_xml(text))


# ── Table Builder ─────────────────────────────────────────────────────────────

def build_table(rows, styles_map, col_widths=None):
    """Build a styled ReportLab table from markdown rows."""
    if not rows:
        return None

    # Parse header and separator
    header = [c.strip().strip('*') for c in rows[0].split('|') if c.strip()]
    data_rows = []
    for row in rows[2:]:  # skip separator
        cols = [c.strip() for c in row.split('|') if c.strip() != '']
        # Pad/trim to header length
        while len(cols) < len(header):
            cols.append('')
        cols = cols[:len(header)]
        data_rows.append(cols)

    n_cols = len(header)
    avail_width = 468  # points

    # Auto column widths
    if col_widths is None:
        col_widths = [avail_width / n_cols] * n_cols

    # Build paragraph cells
    cell_style_header = ParagraphStyle(
        'th', fontName='Helvetica-Bold', fontSize=9, leading=12,
        textColor=WHITE, alignment=TA_LEFT
    )
    cell_style_body = ParagraphStyle(
        'td', fontName='Helvetica', fontSize=9, leading=12,
        textColor=INK, alignment=TA_LEFT
    )

    table_data = [[Paragraph(process_inline(h), cell_style_header) for h in header]]
    for row in data_rows:
        table_data.append([Paragraph(process_inline(c), cell_style_body) for c in row])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR',  (0, 0), (-1, 0), WHITE),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, 0), 9),
        ('TOPPADDING', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        # Alternating rows
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ('FONTSIZE',  (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        # Grid
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, NAVY),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, GRAY_MID),
        ('LINEBEFORE', (0, 0), (0, -1), 0.5, GRAY_MID),
        ('LINEAFTER', (-1, 0), (-1, -1), 0.5, GRAY_MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    t.setStyle(ts)
    return t


# ── RAGAS Score Table (custom colored) ───────────────────────────────────────

def build_ragas_table():
    cell_h = ParagraphStyle('rh', fontName='Helvetica-Bold', fontSize=9,
                             textColor=WHITE, leading=12)
    cell_b = ParagraphStyle('rb', fontName='Helvetica', fontSize=9,
                             textColor=INK, leading=12)

    def score_color(val):
        if val >= 0.7:  return colors.HexColor("#D1FAE5"), colors.HexColor("#065F46")
        if val >= 0.5:  return colors.HexColor("#FEF3C7"), colors.HexColor("#92400E")
        return colors.HexColor("#FEE2E2"), colors.HexColor("#991B1B")

    rows_data = [
        ["Metric", "Score", "Rating", "What it measures"],
        ["Faithfulness", "0.847", "🟢 Good",
         "Claims grounded in retrieved chunks (hallucination check)"],
        ["Answer Relevancy", "0.321", "⚠ Needs improvement",
         "Answer directly addresses the question asked"],
        ["Context Precision", "0.347", "⚠ Needs improvement",
         "Retrieved chunks relevant to the question (signal-to-noise)"],
        ["Context Recall", "0.322", "⚠ Needs improvement",
         "Retrieved chunks contain facts needed to answer correctly"],
    ]

    scores = [None, 0.847, 0.321, 0.347, 0.322]
    table_data = []
    for i, row in enumerate(rows_data):
        if i == 0:
            table_data.append([Paragraph(c, cell_h) for c in row])
        else:
            table_data.append([Paragraph(process_inline(c), cell_b) for c in row])

    col_w = [120, 48, 100, 200]
    t = Table(table_data, colWidths=col_w, repeatRows=1)

    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, NAVY),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, GRAY_MID),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Score cell: bold
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 1), (1, -1), 10),
        # Row colors
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#D1FAE5")),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor("#FFF7ED")),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor("#FFF7ED")),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor("#FFF7ED")),
        ('TEXTCOLOR', (1, 1), (1, 1), colors.HexColor("#065F46")),
        ('TEXTCOLOR', (1, 2), (1, -1), colors.HexColor("#92400E")),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


# ── Main Parser & Builder ─────────────────────────────────────────────────────

def parse_and_build(md_text, styles):
    story = []
    lines = md_text.split('\n')
    i = 0

    # Section counter map for badges
    section_map = {
        "1. What MiaNoise Is": ("Section 1", "What MiaNoise Is", None),
        "2. System Architecture": ("Section 2", "System Architecture", None),
        "3. Sprint 0": ("Section 3", "Sprint 0 — Foundation", "April 3–5, 2026"),
        "4. Sprint 1": ("Section 4", "Sprint 1 — Data Ingestion & Scoring", "April 6–9, 2026"),
        "5. Sprint 2": ("Section 5", "Sprint 2 — RAG Pipeline", "April 10–13, 2026"),
        "6. Sprint 3": ("Section 6", "Sprint 3 — Agent & UI", "April 14–21, 2026"),
        "7. Sprint 3.4": ("Section 7", "Sprint 3.4 — Score Recalibration", "April 22–24, 2026"),
        "8. Sprint 4": ("Section 8", "Sprint 4 — Evaluation & Polish", "April 25–27, 2026"),
        "9. Evaluation Results": ("Section 9", "Evaluation Results", "Run: April 27, 2026"),
        "10. Known Limitations": ("Section 10", "Known Limitations & Honest Gaps", None),
        "11. Appendix": ("Section 11", "Appendix — Per-Question RAGAS Scores", None),
    }

    def match_section(heading):
        for key, val in section_map.items():
            if key in heading:
                return val
        return None

    skip_toc = False
    in_code_block = False
    code_lines = []

    while i < len(lines):
        line = lines[i]

        # ── Skip markdown TOC ──
        if line.strip() == '## Table of Contents':
            skip_toc = True
            i += 1
            continue
        if skip_toc:
            if line.startswith('## ') or (line.strip() == '---' and i > 5):
                skip_toc = False
                # fall through to process this line
            else:
                i += 1
                continue

        # ── Code block ──
        if line.strip().startswith('```'):
            if not in_code_block:
                in_code_block = True
                code_lines = []
                i += 1
                continue
            else:
                in_code_block = False
                code_text = escape_xml('\n'.join(code_lines))
                story.append(Spacer(1, 4))
                story.append(Paragraph(code_text, styles['code_block']))
                story.append(Spacer(1, 4))
                i += 1
                continue
        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # ── Horizontal rule ──
        if line.strip() == '---':
            story.append(Spacer(1, 8))
            story.append(HorizontalRule())
            story.append(Spacer(1, 8))
            i += 1
            continue

        # ── H1 (title) — skip, handled in cover ──
        if line.startswith('# ') and not line.startswith('## '):
            i += 1
            continue

        # ── ### subtitle line (For Jeanne / Last updated) ──
        if line.startswith('### '):
            i += 1
            continue

        # ── _Last updated_ line ──
        if line.startswith('_Last updated'):
            i += 1
            continue

        # ── H2 — section headers ──
        if line.startswith('## '):
            heading = line[3:].strip()
            match = match_section(heading)
            story.append(Spacer(1, 14))
            if match:
                story.append(KeepTogether([
                    SectionBadge(match[0], match[1], match[2], width=468),
                    Spacer(1, 10)
                ]))
            else:
                # Fallback styled header
                story.append(Paragraph(process_inline(heading), styles['h2']))
            i += 1
            continue

        # ── H3 — subsection headers ──
        if line.startswith('### '):
            heading = line[4:].strip()
            story.append(Spacer(1, 6))
            story.append(Paragraph(process_inline(heading), styles['h3']))
            i += 1
            continue

        # ── H4 ──
        if line.startswith('#### '):
            heading = line[5:].strip()
            story.append(Paragraph(
                f'<b>{process_inline(heading)}</b>',
                ParagraphStyle('h4', fontName='Helvetica-Bold', fontSize=10,
                               textColor=NAVY, spaceBefore=10, spaceAfter=3, leading=13)
            ))
            i += 1
            continue

        # ── Sprint date line ──
        if re.match(r'^_April\s+\d', line.strip()):
            date_text = line.strip().strip('_')
            story.append(Paragraph(date_text, styles['sprint_date']))
            i += 1
            continue

        # ── Blockquote ──
        if line.startswith('> '):
            quote_text = line[2:].strip().strip('*_')
            # Collect multi-line quotes
            while i + 1 < len(lines) and lines[i + 1].startswith('> '):
                i += 1
                quote_text += ' ' + lines[i][2:].strip().strip('*_')
            story.append(Spacer(1, 6))
            story.append(QuoteBlock(quote_text, width=468))
            story.append(Spacer(1, 6))
            i += 1
            continue

        # ── Markdown table ──
        if '|' in line and line.strip().startswith('|'):
            table_rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip().startswith('|'):
                table_rows.append(lines[i])
                i += 1

            # Special case: RAGAS aggregate table
            if any('Faithfulness' in r and 'Score' in r for r in table_rows):
                story.append(Spacer(1, 6))
                story.append(build_ragas_table())
                story.append(Spacer(1, 8))
            else:
                # Determine col widths heuristically by header count
                n_cols = len([c for c in table_rows[0].split('|') if c.strip()])
                if n_cols == 2:
                    widths = [200, 268]
                elif n_cols == 3:
                    widths = [140, 80, 248]
                elif n_cols == 4:
                    widths = [130, 100, 120, 118]
                elif n_cols == 5:
                    widths = [18, 160, 52, 52, 52, 52, 52]
                elif n_cols == 7:
                    widths = [18, 140, 44, 54, 56, 62, 56]
                else:
                    widths = None
                t = build_table(table_rows, styles, widths)
                if t:
                    story.append(Spacer(1, 6))
                    story.append(t)
                    story.append(Spacer(1, 8))
            continue

        # ── Numbered list ──
        num_match = re.match(r'^(\d+)\.\s+(.+)', line)
        if num_match:
            num = num_match.group(1)
            text = num_match.group(2)
            story.append(Paragraph(
                f'{num}. {process_inline(text)}',
                styles['numbered']
            ))
            i += 1
            continue

        # ── Bullet list ──
        if line.startswith('- ') or line.startswith('* '):
            text = line[2:].strip()

            # Attempt label pattern: "**Attempt N — ...**:" or "**Attempt N — ...:**"
            attempt_match = re.match(r'\*\*Attempt\s+(\d+)\s*[—-]\s*(.+?)\*\*:?\s*(.*)', text)
            if attempt_match:
                label = f"Attempt {attempt_match.group(1)} — {attempt_match.group(2)}"
                rest = attempt_match.group(3)
                story.append(Paragraph(
                    f'<font color="#E8521A"><b>{escape_xml(label)}:</b></font> {process_inline(rest)}',
                    styles['body_left']
                ))
            else:
                story.append(Paragraph(process_inline(text), styles['bullet']))
            i += 1
            continue

        # ── Sub-bullet (2 or 4 spaces) ──
        if re.match(r'^  +[-*] ', line):
            text = re.sub(r'^  +[-*] ', '', line)
            story.append(Paragraph(process_inline(text), styles['sub_bullet']))
            i += 1
            continue

        # ── "Notable patterns" bullets (starting with -) ──
        if line.startswith('- ') and 'Question' in line:
            story.append(Paragraph(process_inline(line[2:]), styles['notable']))
            i += 1
            continue

        # ── Empty line ──
        if not line.strip():
            story.append(Spacer(1, 4))
            i += 1
            continue

        # ── Last line ──
        if line.startswith('_Report generated'):
            story.append(Spacer(1, 12))
            story.append(HorizontalRule(color=GRAY_MID))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                process_inline(line.strip('_')),
                ParagraphStyle('footer_note', fontName='Helvetica-Oblique',
                               fontSize=9, textColor=GRAY_TEXT, alignment=TA_CENTER)
            ))
            i += 1
            continue

        # ── Default: body paragraph ──
        if line.strip():
            story.append(Paragraph(process_inline(line.strip()), styles['body']))

        i += 1

    return story


# ── Table of Contents ─────────────────────────────────────────────────────────

def build_toc(styles):
    entries = [
        ("1", "What MiaNoise Is"),
        ("2", "System Architecture"),
        ("3", "Sprint 0 — Foundation"),
        ("4", "Sprint 1 — Data Ingestion & Scoring"),
        ("5", "Sprint 2 — RAG Pipeline"),
        ("6", "Sprint 3 — Agent & UI"),
        ("7", "Sprint 3.4 — Score Recalibration"),
        ("8", "Sprint 4 — Evaluation & Polish"),
        ("9", "Evaluation Results"),
        ("10", "Known Limitations & Honest Gaps"),
        ("11", "Appendix — Per-Question RAGAS Scores"),
    ]
    items = []
    items.append(Paragraph("Table of Contents", styles['toc_title']))
    items.append(HorizontalRule(color=NAVY, thickness=1))
    items.append(Spacer(1, 10))
    for num, title in entries:
        items.append(Paragraph(
            f'<font color="#E8521A"><b>{num}.</b></font>  {title}',
            styles['toc_entry']
        ))
        items.append(Spacer(1, 2))
    return items


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    src = Path(__file__).parent / "project_report.md"
    out = Path(__file__).parent / "MiaNoise_Project_Report.pdf"

    md_text = src.read_text(encoding='utf-8')
    styles = make_styles()

    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="MiaNoise — Full Project Report",
        author="Luna Gerlic Santoni",
        subject="Sprint 0–4.3 Project Report",
    )

    story = []

    # Cover page is drawn via onFirstPage callback — just push to page 2
    story.append(PageBreak())

    # Table of Contents
    for item in build_toc(styles):
        story.append(item)
    story.append(PageBreak())

    # Main content
    content = parse_and_build(md_text, styles)
    story.extend(content)

    doc.build(story, onFirstPage=make_header_footer, onLaterPages=make_header_footer)
    print(f"PDF generated: {out}")
    return out


if __name__ == "__main__":
    main()
