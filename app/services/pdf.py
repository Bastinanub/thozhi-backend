import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)


# ─────────────────────────────────────────────
# Colour palette
# ─────────────────────────────────────────────
INDIGO     = colors.HexColor("#4F46E5")
LIGHT_BG   = colors.HexColor("#F5F3FF")
BORDER     = colors.HexColor("#DDD6FE")
TEXT_DARK  = colors.HexColor("#1E1B4B")
TEXT_MID   = colors.HexColor("#4B5563")
TEXT_LIGHT = colors.HexColor("#6B7280")
GREEN      = colors.HexColor("#059669")
AMBER      = colors.HexColor("#D97706")
RED        = colors.HexColor("#DC2626")
WHITE      = colors.white


def _severity_color(interpretation: str) -> colors.Color:
    lower = interpretation.lower()
    if "minimal" in lower or "no " in lower:
        return GREEN
    if "mild" in lower:
        return colors.HexColor("#16A34A")
    if "moderate" in lower and "severe" not in lower:
        return AMBER
    if "moderately severe" in lower:
        return colors.HexColor("#EA580C")
    return RED


# ─────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────
def _build_styles() -> dict:
    def s(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        "cover_title":    s("cover_title", fontName="Helvetica-Bold", fontSize=18,
                              textColor=WHITE, alignment=TA_CENTER, spaceAfter=4),
        "cover_sub":      s("cover_sub", fontName="Helvetica", fontSize=10,
                              textColor=colors.HexColor("#C4B5FD"), alignment=TA_CENTER),
        "section_head":   s("section_head", fontName="Helvetica-Bold", fontSize=12,
                              textColor=INDIGO, spaceBefore=16, spaceAfter=4),
        "body":           s("body", fontName="Helvetica", fontSize=10,
                              textColor=TEXT_DARK, leading=15, spaceAfter=4),
        "body_mid":       s("body_mid", fontName="Helvetica", fontSize=10,
                              textColor=TEXT_MID, leading=15, spaceAfter=4),
        "small":          s("small", fontName="Helvetica", fontSize=9,
                              textColor=TEXT_DARK, leading=13),
        "small_mid":      s("small_mid", fontName="Helvetica", fontSize=9,
                              textColor=TEXT_MID, leading=13),
        "bullet":         s("bullet", fontName="Helvetica", fontSize=10,
                              textColor=TEXT_DARK, leading=15, leftIndent=14, spaceAfter=3),
        "score_num":      s("score_num", fontName="Helvetica-Bold", fontSize=32,
                              textColor=INDIGO, alignment=TA_CENTER),
        "score_sub":      s("score_sub", fontName="Helvetica", fontSize=10,
                              textColor=TEXT_MID, alignment=TA_CENTER),
        "disclaimer":     s("disclaimer", fontName="Helvetica-Oblique", fontSize=8,
                              textColor=TEXT_LIGHT, leading=12),
        "pro_label":      s("pro_label", fontName="Helvetica-Bold", fontSize=9,
                              textColor=INDIGO),
        "pro_note":       s("pro_note", fontName="Helvetica", fontSize=9,
                              textColor=TEXT_MID, leading=13),
    }


# ─────────────────────────────────────────────
# Header / footer on every page
# ─────────────────────────────────────────────
def _make_on_page(doc_title: str, generated_at: str):
    def _draw(canvas, doc):
        canvas.saveState()
        w, h = A4

        # Top bar
        canvas.setFillColor(INDIGO)
        canvas.rect(0, h - 34, w, 34, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(WHITE)
        canvas.drawString(0.5 * inch, h - 22, doc_title)

        # Footer
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(0.5 * inch, 28, w - 0.5 * inch, 28)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(TEXT_LIGHT)
        canvas.drawString(0.5 * inch, 14, f"Generated: {generated_at}")
        canvas.drawRightString(w - 0.5 * inch, 14, f"Page {doc.page}")
        canvas.restoreState()
    return _draw


# ─────────────────────────────────────────────
# Section helpers
# ─────────────────────────────────────────────
def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=6)


def _section(title: str, styles: dict) -> list:
    return [Paragraph(title, styles["section_head"]), _hr()]


# ─────────────────────────────────────────────
# Score banner
# ─────────────────────────────────────────────
def _score_banner(report: dict, styles: dict) -> list:
    return [
        Spacer(1, 6),
        Paragraph(f"{report['score']} / {report.get('score_max', '?')}", styles["score_num"]),
        Paragraph(report["interpretation"], styles["score_sub"]),
        Spacer(1, 8),
        Paragraph(report.get("summary", ""), styles["body_mid"]),
        Spacer(1, 10),
    ]


# ─────────────────────────────────────────────
# Score ranges table
# ─────────────────────────────────────────────
def _score_ranges_table(report: dict, styles: dict) -> list:
    ranges = report.get("score_ranges", [])
    if not ranges:
        return []

    current = report["interpretation"].lower()
    rows = [[Paragraph("<b>Range</b>", styles["small"]),
             Paragraph("<b>Severity Level</b>", styles["small"])]]

    highlight_row = None
    for i, r in enumerate(ranges, 1):
        is_cur = r["label"].lower() == current
        if is_cur:
            highlight_row = i
        label_text = f"<b>{r['label']}</b>" if is_cur else r["label"]
        rows.append([Paragraph(r["range"], styles["small"]),
                     Paragraph(label_text, styles["small"])])

    t = Table(rows, colWidths=[1.3 * inch, 5.2 * inch])
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), LIGHT_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), INDIGO),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if highlight_row:
        style_cmds += [
            ("BACKGROUND", (0, highlight_row), (-1, highlight_row), colors.HexColor("#EDE9FE")),
            ("TEXTCOLOR",  (0, highlight_row), (-1, highlight_row), INDIGO),
        ]
    t.setStyle(TableStyle(style_cmds))
    return [t, Spacer(1, 6)]


# ─────────────────────────────────────────────
# Question breakdown table
# ─────────────────────────────────────────────
def _question_breakdown_table(report: dict, styles: dict) -> list:
    breakdown = report.get("question_breakdown", [])
    if not breakdown:
        return [Paragraph("No per-question breakdown available for this session.", styles["body_mid"])]

    rows = [[Paragraph("<b>Q#</b>", styles["small"]),
             Paragraph("<b>Score</b>", styles["small"]),
             Paragraph("<b>Response</b>", styles["small"])]]
    for item in breakdown:
        rows.append([
            Paragraph(str(item["question_number"]), styles["small"]),
            Paragraph(str(item["score"]), styles["small"]),
            Paragraph(item["label"], styles["small"]),
        ])

    t = Table(rows, colWidths=[0.6 * inch, 0.8 * inch, 5.1 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), LIGHT_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), INDIGO),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("ALIGN",         (0, 0), (1, -1), "CENTER"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [t, Spacer(1, 6)]


# ─────────────────────────────────────────────
# Severity trend table
# ─────────────────────────────────────────────
def _trend_table(report: dict, styles: dict) -> list:
    trend = report.get("trend", [])
    if len(trend) <= 1:
        return [Paragraph(
            "No previous sessions found. Trend data will appear here after your next screening.",
            styles["body_mid"]
        )]

    rows = [[Paragraph("<b>Date</b>", styles["small"]),
             Paragraph("<b>Score</b>", styles["small"]),
             Paragraph("<b>Severity</b>", styles["small"]),
             Paragraph("<b>Change</b>", styles["small"])]]

    for i, entry in enumerate(trend):
        if i == 0:
            change_str = "—"
        else:
            delta = entry["score"] - trend[i - 1]["score"]
            change_str = f"+{delta}" if delta > 0 else (f"{delta}" if delta < 0 else "No change")

        is_latest = (i == len(trend) - 1)
        b_open  = "<b>" if is_latest else ""
        b_close = "</b>" if is_latest else ""

        rows.append([
            Paragraph(f"{b_open}{entry['date']}{b_close}", styles["small"]),
            Paragraph(f"{b_open}{entry['score']}{b_close}", styles["small"]),
            Paragraph(f"{b_open}{entry['interpretation']}{b_close}", styles["small"]),
            Paragraph(f"{b_open}{change_str}{b_close}", styles["small"]),
        ])

    t = Table(rows, colWidths=[1.3 * inch, 0.8 * inch, 2.8 * inch, 1.6 * inch])
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), LIGHT_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), INDIGO),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        # Highlight latest row
        ("BACKGROUND", (0, len(trend)), (-1, len(trend)), colors.HexColor("#EDE9FE")),
        ("TEXTCOLOR",  (0, len(trend)), (-1, len(trend)), INDIGO),
    ]
    t.setStyle(TableStyle(style_cmds))
    return [t, Spacer(1, 6)]


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────
def generate_pdf(report: dict, filename: str) -> str:
    """
    Generates a detailed, styled PDF and saves it to reports/<filename>.

    Args:
        report:   Dict from report.generate_report()
        filename: Output filename (e.g. "session_123_report.pdf")

    Returns:
        Absolute path to the generated file.
    """
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", filename)

    generated_at = datetime.fromisoformat(report["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
    doc_title    = f"Thozhi – {report['domain']} Screening Report"

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.65 * inch,
        title=doc_title,
        author="Thozhi Mental Wellness",
    )

    styles  = _build_styles()
    on_page = _make_on_page(doc_title, generated_at)
    story   = []

    # ── Cover strip ──────────────────────────────────────────────────────────
    cover = Table(
        [[Paragraph(doc_title, styles["cover_title"])],
         [Paragraph(
             f"{report['tool_used']}  •  {report['domain']}  •  {generated_at}",
             styles["cover_sub"]
         )]],
        colWidths=[6.5 * inch],
    )
    cover.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), INDIGO),
        ("LEFTPADDING",  (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING",   (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 14),
    ]))
    story += [Spacer(1, 0.25 * inch), cover, Spacer(1, 0.25 * inch)]

    # ── 1. Score result ───────────────────────────────────────────────────────
    story += _section("Your Result", styles)
    story += _score_banner(report, styles)

    # ── 2. About the tool ─────────────────────────────────────────────────────
    if report.get("tool_description"):
        story += _section(f"About the {report['tool_used']}", styles)
        story.append(Paragraph(report["tool_description"], styles["body_mid"]))
        story.append(Spacer(1, 6))

    # ── 3. Score range guide ──────────────────────────────────────────────────
    story += _section("Score Range Guide", styles)
    story.append(Paragraph(
        f"Your score of <b>{report['score']}</b> places you in the "
        f"<b>{report['interpretation']}</b> range (highlighted).",
        styles["body_mid"]
    ))
    story.append(Spacer(1, 4))
    story += _score_ranges_table(report, styles)

    # ── 4. Response breakdown ─────────────────────────────────────────────────
    story += _section("Response Breakdown", styles)
    story.append(Paragraph("How you responded to each question:", styles["body_mid"]))
    story.append(Spacer(1, 4))
    story += _question_breakdown_table(report, styles)

    # ── 5. Severity trend ─────────────────────────────────────────────────────
    story += _section("Severity Trend", styles)
    story.append(Paragraph(
        "Your scores across sessions. The most recent session is highlighted.",
        styles["body_mid"]
    ))
    story.append(Spacer(1, 4))
    story += _trend_table(report, styles)

    # ── 6. Coping strategies ──────────────────────────────────────────────────
    story += _section("Coping Strategies", styles)
    story.append(Paragraph(
        "These are gentle, evidence-informed suggestions — try one that feels manageable today.",
        styles["body_mid"]
    ))
    story.append(Spacer(1, 4))
    for tip in report.get("coping_strategies", []):
        story.append(Paragraph(f"• {tip}", styles["bullet"]))
    story.append(Spacer(1, 8))

    # ── 7. Recommendation ─────────────────────────────────────────────────────
    story += _section("Recommendation", styles)
    story.append(Paragraph(report.get("recommendation", ""), styles["body"]))
    story.append(Spacer(1, 8))

    # ── 8. Clinician note (boxed) ─────────────────────────────────────────────
    if report.get("professional_note"):
        pro_box = Table(
            [[Paragraph("For the Clinician", styles["pro_label"]),
              Paragraph(report["professional_note"], styles["pro_note"])]],
            colWidths=[1.3 * inch, 5.2 * inch],
        )
        pro_box.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), LIGHT_BG),
            ("BOX",          (0, 0), (-1, -1), 0.8, INDIGO),
            ("LEFTPADDING",  (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING",   (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(pro_box)
        story.append(Spacer(1, 12))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(_hr())
    story.append(Paragraph(report.get("disclaimer", ""), styles["disclaimer"]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return os.path.abspath(path)
