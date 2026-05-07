"""
PDF export for AI Advisor and Explore Plan results.
Uses the same ReportLab styling as main.py.
"""
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Fonts ─────────────────────────────────────────────────────────────────────
_FONTS_LOCAL  = Path(__file__).parent / "fonts"
_FONTS_SYSTEM = Path("C:/Windows/Fonts")
_FONTS = _FONTS_LOCAL if (_FONTS_LOCAL / "arial.ttf").exists() else _FONTS_SYSTEM
pdfmetrics.registerFont(TTFont("Arial",            str(_FONTS / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold",       str(_FONTS / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic",     str(_FONTS / "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", str(_FONTS / "arialbi.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                               italic="Arial-Italic", boldItalic="Arial-BoldItalic")

# ── Colors ────────────────────────────────────────────────────────────────────
PURPLE      = HexColor("#7C3AED")
PURPLE_MID  = HexColor("#6D28D9")
PURPLE_DARK = HexColor("#5B21B6")
PURPLE_DEEP = HexColor("#4C1D95")
PINK        = HexColor("#DB2777")
BLUE        = HexColor("#0284C7")
GREEN       = HexColor("#059669")
DARK        = HexColor("#1F2937")
GRAY        = HexColor("#6B7280")
LIGHT_GRAY  = HexColor("#F9FAFB")
BORDER      = HexColor("#E5E7EB")
ACCENT      = [PURPLE, PINK, BLUE, PURPLE, PINK]
AMBER       = HexColor("#D97706")
TEAL        = HexColor("#0D9488")

W = 17 * cm


def _s(name, **kw):
    d = dict(fontName="Arial", fontSize=10, textColor=DARK, leading=14)
    d.update(kw)
    return ParagraphStyle(name, **d)


def _header(story, title, subtitle, date_str, accent_color=PURPLE):
    s_title = _s("ht", fontName="Arial-Bold", fontSize=18, textColor=white, alignment=TA_CENTER, leading=24)
    s_sub   = _s("hs", fontSize=11, textColor=HexColor("#DDD6FE"), alignment=TA_CENTER)
    s_date  = _s("hd", fontSize=9,  textColor=HexColor("#A78BFA"), alignment=TA_CENTER)

    tbl = Table([
        [Paragraph(title,    s_title)],
        [Paragraph(subtitle, s_sub)],
        [Paragraph(date_str, s_date)],
    ], colWidths=[W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), accent_color),
        ("BACKGROUND",    (0,1), (-1,1), PURPLE_MID),
        ("BACKGROUND",    (0,2), (-1,2), PURPLE_DEEP),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (0,0), 14),
        ("BOTTOMPADDING", (0,0), (0,0), 4),
        ("TOPPADDING",    (0,1), (0,1), 4),
        ("BOTTOMPADDING", (0,1), (0,1), 4),
        ("TOPPADDING",    (0,2), (0,2), 4),
        ("BOTTOMPADDING", (0,2), (0,2), 12),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5*cm))


def _section_title(story, text, color=PURPLE):
    s = _s("st", fontName="Arial-Bold", fontSize=11, textColor=color, spaceBefore=10, spaceAfter=4)
    story.append(Paragraph(text, s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 0.15*cm))


def _idea_card(story, idea, index, color):
    s_num    = _s(f"in{index}", fontName="Arial-Bold", fontSize=13, textColor=white)
    s_badge  = _s(f"ib{index}", fontName="Arial-Bold", fontSize=10, textColor=white, alignment=TA_CENTER)
    s_label  = _s(f"lb{index}", fontName="Arial-Bold", fontSize=8, textColor=GRAY, spaceBefore=5, spaceAfter=2)
    s_title  = _s(f"tt{index}", fontName="Arial-Bold", fontSize=12, textColor=DARK, leading=16)
    s_hook   = _s(f"hk{index}", fontName="Arial-Italic", fontSize=11, textColor=PURPLE, leading=16)
    s_body   = _s(f"bd{index}", fontSize=10, textColor=DARK, leading=14)
    s_hash   = _s(f"hh{index}", fontSize=9,  textColor=PURPLE)
    s_cta    = _s(f"ct{index}", fontName="Arial-Bold", fontSize=10, textColor=GREEN)

    hdr = Table([[
        Paragraph(f"Fikir {index}", s_num),
        Paragraph(idea.get("format",""), s_badge),
    ]], colWidths=[13*cm, 4*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), color),
        ("ALIGN",         (0,0), (0,0), "LEFT"),
        ("ALIGN",         (1,0), (1,0), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (0,0), 14),
        ("RIGHTPADDING",  (1,0), (1,0), 10),
    ]))

    body_els = [
        Paragraph("BASLIK", s_label),
        Paragraph(idea.get("title",""), s_title),
        Paragraph("HOOK", s_label),
        Paragraph(f"“{idea.get('hook','')}”", s_hook),
        Paragraph("ANA NOKTALAR", s_label),
        *[Paragraph(f"•  {pt}", s_body) for pt in idea.get("key_points", [])],
        Paragraph("CAPTION", s_label),
        Paragraph(idea.get("caption",""), s_body),
        Paragraph("HASHTAGLER", s_label),
        Paragraph("  ".join(idea.get("hashtags", [])), s_hash),
        Paragraph("CALL TO ACTION", s_label),
        Paragraph(f"➡  {idea.get('cta','')}", s_cta),
    ]
    if idea.get("why_it_works"):
        body_els += [
            Paragraph("NEDEN ISLER", s_label),
            Paragraph(f"\U0001f4a1  {idea['why_it_works']}", _s(f"wy{index}", fontSize=10, textColor=GRAY, fontName="Arial-Italic")),
        ]

    body_tbl = Table([[el] for el in body_els], colWidths=[W - 0.8*cm])
    body_tbl.setStyle(TableStyle([
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    border = Table([[body_tbl]], colWidths=[W])
    border.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), LIGHT_GRAY),
        ("BOX",           (0,0), (-1,-1), 1, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(hdr)
    story.append(border)
    story.append(Spacer(1, 0.4*cm))


def _footer(story, username):
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  •  Instagram Dashboard  •  @{username}",
        _s("ft", fontSize=8, textColor=GRAY, alignment=TA_CENTER),
    ))


# ── AI Advisor PDF ────────────────────────────────────────────────────────────

def build_advisor_pdf(result: dict, username: str = "ssefaeksii") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []
    date_str = datetime.now().strftime("%A, %d %B %Y")

    _header(story, "AI Danishman Raporu", f"@{username}", date_str, PURPLE)

    # Analysis
    _section_title(story, "Performans Analizi", PURPLE)
    story.append(Paragraph(result.get("analysis",""), _s("an", fontSize=10, leading=16)))
    story.append(Spacer(1, 0.3*cm))

    # Best time
    if result.get("best_posting_time"):
        story.append(Paragraph(
            f"⏰  Onerilen paylasim saati: <b>{result['best_posting_time']}</b>",
            _s("bt", fontSize=10, textColor=PURPLE_DARK)
        ))
        story.append(Spacer(1, 0.3*cm))

    # Growth tips
    _section_title(story, "Buyume Tavsiyeleri", PINK)
    s_tip = _s("tp", fontSize=10, leading=15)
    for i, tip in enumerate(result.get("growth_tips", []), 1):
        tbl = Table([[
            Paragraph(str(i), _s(f"tn{i}", fontName="Arial-Bold", fontSize=11, textColor=white, alignment=TA_CENTER)),
            Paragraph(tip, s_tip),
        ]], colWidths=[0.7*cm, W-0.7*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,0), PINK),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING",   (0,0), (0,0), 6),
            ("RIGHTPADDING",  (0,0), (0,0), 6),
            ("LEFTPADDING",   (1,0), (1,0), 10),
            ("ROWBACKGROUNDS",(0,0), (-1,-1), [LIGHT_GRAY, white]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.2*cm))

    # Ideas
    _section_title(story, "Icerik Fikirleri", BLUE)
    for i, idea in enumerate(result.get("ideas", []), 1):
        _idea_card(story, idea, i, ACCENT[(i-1) % len(ACCENT)])

    _footer(story, username)
    doc.build(story)
    return buf.getvalue()


# ── Explore Plan PDF ──────────────────────────────────────────────────────────

def build_explore_pdf(result: dict, username: str = "ssefaeksii") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []
    date_str = datetime.now().strftime("%A, %d %B %Y")

    _header(story, "Kesfet & Haftalik Icerik Plani", f"@{username}", date_str, TEAL)

    # Trending topics
    topics = result.get("trending_topics", [])
    if topics:
        _section_title(story, "Su An Instagram'da Trend Olan Konular", TEAL)
        fmt_map = {"Reel": PINK, "Carousel": BLUE, "Story": GREEN}
        for t in topics:
            color = fmt_map.get(t.get("format",""), PURPLE)
            tbl = Table([[
                Paragraph(t.get("format",""), _s(f"tf{t.get('topic','')[:4]}",
                    fontName="Arial-Bold", fontSize=9, textColor=white, alignment=TA_CENTER)),
                Paragraph(f"<b>{t.get('topic','')}</b> — {t.get('why','')}", _s("tw", fontSize=10, leading=14)),
            ]], colWidths=[1.6*cm, W-1.6*cm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (0,0), color),
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING",    (0,0), (-1,-1), 7),
                ("BOTTOMPADDING", (0,0), (-1,-1), 7),
                ("LEFTPADDING",   (0,0), (0,0), 6),
                ("LEFTPADDING",   (1,0), (1,0), 10),
                ("ROWBACKGROUNDS",(0,0), (-1,-1), [LIGHT_GRAY]),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.15*cm))
        story.append(Spacer(1, 0.3*cm))

    # Weekly plan table
    plan = result.get("weekly_plan", [])
    if plan:
        _section_title(story, "Haftalik Icerik Takvimi", PURPLE)
        pot_colors = {"Yuksek": GREEN, "Orta": AMBER, "Dusuk": GRAY}
        s_day   = _s("pd", fontName="Arial-Bold", fontSize=9, textColor=white, alignment=TA_CENTER)
        s_fmt   = _s("pf", fontName="Arial-Bold", fontSize=8, textColor=white, alignment=TA_CENTER)
        s_title = _s("pt", fontName="Arial-Bold", fontSize=9, textColor=DARK, leading=12)
        s_hook  = _s("ph", fontName="Arial-Italic", fontSize=8, textColor=PURPLE, leading=11)
        s_time  = _s("pm", fontSize=8, textColor=GRAY)
        s_pot   = _s("pp", fontName="Arial-Bold", fontSize=8, textColor=white, alignment=TA_CENTER)

        for day in plan:
            pot   = day.get("explore_potential","Orta")
            pot_c = pot_colors.get(pot, GRAY)
            fmt   = day.get("format","Reel")
            fmt_c = {"Reel":PINK,"Carousel":BLUE,"Story":GREEN}.get(fmt, PURPLE)
            row = Table([[
                Paragraph(f"{day.get('day','')}\n{day.get('date','')[5:]}", s_day),
                Paragraph(fmt, s_fmt),
                Table([[
                    Paragraph(day.get("title",""), s_title),
                    Paragraph(f'"{day.get("hook","")}"', s_hook),
                    Paragraph(f"⏰ {day.get('best_time','')}  {day.get('explore_reason','')}", s_time),
                ]], colWidths=[12*cm]),
                Paragraph(pot, s_pot),
            ]], colWidths=[2*cm, 1.5*cm, 12*cm, 1.5*cm])
            row.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (0,0), PURPLE_MID),
                ("BACKGROUND",    (1,0), (1,0), fmt_c),
                ("BACKGROUND",    (3,0), (3,0), pot_c),
                ("BACKGROUND",    (2,0), (2,0), LIGHT_GRAY),
                ("VALIGN",        (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("LEFTPADDING",   (0,0), (0,0), 4),
                ("LEFTPADDING",   (2,0), (2,0), 8),
                ("BOX",           (0,0), (-1,-1), 0.5, BORDER),
            ]))
            story.append(row)
            story.append(Spacer(1, 0.1*cm))
        story.append(Spacer(1, 0.3*cm))

    # Viral rules
    rules = result.get("viral_rules", [])
    if rules:
        _section_title(story, "Viral Kurallar", PINK)
        icons = ["\U0001f3af","⚡","\U0001f525","\U0001f4a1"]
        for i, rule in enumerate(rules):
            story.append(Paragraph(f"{icons[i % len(icons)]}  {rule}",
                _s(f"vr{i}", fontSize=10, leading=15, spaceBefore=4)))

        story.append(Spacer(1, 0.3*cm))

    # Analysis
    if result.get("analysis"):
        _section_title(story, "Kesfet Analizi", TEAL)
        story.append(Paragraph(result["analysis"], _s("ea", fontSize=10, leading=16)))

    _footer(story, username)
    doc.build(story)
    return buf.getvalue()
