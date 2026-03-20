import os
import json
import re
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
)
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DRIVE_ROOT_FOLDER = "Instagram Content Ideas"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# ---------------------------------------------------------------------------
# Google Drive helpers
# ---------------------------------------------------------------------------

def get_drive_service():
    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    # GitHub Actions: write credential files from environment variables
    google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    google_token_json = os.getenv("GOOGLE_TOKEN_JSON")

    if google_creds_json:
        creds_path.write_text(google_creds_json)
    if google_token_json:
        token_path.write_text(google_token_json)

    if not creds_path.exists():
        raise FileNotFoundError(
            "credentials.json not found. Download it from Google Cloud Console "
            "(APIs & Services → Credentials → OAuth 2.0 Client)."
        )

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as fh:
            fh.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service, name, parent_id=None):
    query = (
        f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_file(service, local_path: Path, parent_id: str):
    metadata = {"name": local_path.name, "parents": [parent_id]}
    media = MediaFileUpload(str(local_path), mimetype="application/pdf")
    result = service.files().create(
        body=metadata, media_body=media, fields="id,webViewLink"
    ).execute()
    return result


# ---------------------------------------------------------------------------
# Gemini content generation
# ---------------------------------------------------------------------------

def generate_ideas() -> list[dict]:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in .env")

    client = genai.Client(api_key=GEMINI_API_KEY)

    today = datetime.now().strftime("%d %B %Y, %A")

    prompt = f"""Sen gorseli on plana alan, veri odakli stratejiyi estetik cekim gucu ile birlestiren uzman bir Instagram Icerik Ureticisisin.
Yasam Tarzi ve Kisisel Gelisim nisleri uzerinde uzmanlasmis olup Reels, Carousel ve Story formatlarinda kaydirilmayi durduran icerikler uretiyorsun.
Temel amacin takipcilere deger sunmak, organik buyumeyi desteklemek ve guven insasidir.

Bugunun tarihi: {today}.

--- YETENEKLERIN ---
- Reels: Ilk 3 saniyede dikkati kacirmayan hook'lar, trend sesler/challenge'lara Yasam Tarzi/Kisisel Gelisim uyarlamasi, izlenme suresi ve paylasimi maksimize eden senaryo yapisi
- Carousel: Kisisel gelisim aliskanliklarini anlatan, kaydetmeyi ve paylasmayi tetikleyen egitici kaydirmali icerik; gorsel hiyerarsiye dikkat
- Story: Gunluk rutinin BTS anlatimlari, anket/slider/S&A etkilesileri, 24 saatlik anlati arki
- Caption & IG SEO: Mikro-blog tarzi aciklamalar, ilgili anahtar kelimeler, nis hashtag stratejisi, guclu CTA
- Marka sesi: Tutarli estetik, samimi ton, rakip analizi

--- GOREV ---
Tam olarak 5 Instagram icerik fikri uret:
- Fikir 1: Reel
- Fikir 2: Carousel
- Fikir 3: Story
- Fikir 4: Reel (farkli konu, farkli hook stili)
- Fikir 5: Reel (farkli konu, farkli hook stili)
Kisisel gelisim, uretkenlik, saglikli yasam, motivasyon ve yasam tarzi konularina odaklan.

--- DIL KURALI ---
Tum icerikler Turkce olmali FAKAT SADECE Ingilizce klavye karakterleri kullan.
Hic ozel Turkce karakter kullanma (no s-cedilla, no g-breve, no u-umlaut, no o-umlaut, no dotless-i, no c-cedilla).
Ornek: "guzellesmek", "olusturmak", "cok", "sehir", "gercek", "icerik"

--- CIKTI ---
YALNIZCA gecerli bir JSON dizisi dondur. Markdown fence veya ekstra metin kesinlikle olmamali.
[
  {{
    "format": "Reel | Carousel | Story",
    "title": "kaydirilmayi durduran, dikkat cekici baslik",
    "hook": "ilk 3 saniyede dikkati yakalayan acilis cumlesi",
    "key_points": ["madde 1", "madde 2", "madde 3"],
    "caption": "mikro-blog tarzinda Instagram aciklamasi (3-4 cumle, samimi ve konusma dili, IG SEO anahtar kelimeler iceriyor)",
    "hashtags": ["#etiket1", "#etiket2", "#etiket3", "#etiket4", "#etiket5",
                 "#etiket6", "#etiket7", "#etiket8", "#etiket9", "#etiket10"],
    "cta": "net ve ikna edici harekete gecirici mesaj"
  }}
]"""

    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt,
    )
    raw = response.text.strip()

    # Strip markdown fences if model adds them
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    ideas = json.loads(raw)
    return ideas[:5]


def get_trending_topic() -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = """Search the web right now for a recently trended Instagram Reel topic in the Lifestyle and Self-Improvement niche.
Find something that went viral or peaked in popularity in the last few weeks on Instagram.

LANGUAGE RULE: ALL text fields must be in Turkish BUT using ONLY English keyboard characters.
No special Turkish chars (no s-cedilla, no g-breve, no u-umlaut, no o-umlaut, no dotless-i, no c-cedilla).
Example: write "guzellesmek" not "guzelle\u015fmek", "cok" not "\u00e7ok", "icerik" not "i\u00e7erik".

Return ONLY a valid JSON object — no markdown, no extra text:
{
  "topic": "trendin adi veya challenge adi (Turkce, Ingilizce klavye)",
  "peak_period": "ne zaman trend oldu (ornegin 'Mart 2026')",
  "why_trending": "neden viral oldu — detayli aciklama, 2-3 cumle (Turkce, Ingilizce klavye)",
  "platform_stats": "kac video, kac goruntulenme gibi rakamlari varsa yaz, yoksa genel populerlik bilgisi (Turkce, Ingilizce klavye)",
  "niche_adaptation": "Yasam Tarzi/Kisisel Gelisim hesabi bu trendi nasil kullanabilir — somut ve detayli, 3-4 cumle (Turkce, Ingilizce klavye)",
  "content_angle": "bu trend icin onerilecek icecek acisi veya bakis acisi, 2-3 cumle (Turkce, Ingilizce klavye)",
  "video_tips": "video cekim, kurgu ve sunum ipuclari — en az 3 madde (Turkce, Ingilizce klavye)",
  "recommended_audio": "bu trend icin uygun ses/muzik turu veya varsa spesifik trend sesi (Turkce, Ingilizce klavye)",
  "hashtags": ["#trend1", "#trend2", "#trend3", "#trend4", "#trend5"],
  "example_hook": "bu trendi kullanan, kullanima hazir Turkce hook cumlesi (Ingilizce klavye)"
}"""

    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

PURPLE      = HexColor("#7C3AED")
PURPLE_DARK = HexColor("#5B21B6")
PURPLE_MID  = HexColor("#6D28D9")
PURPLE_LIGHT= HexColor("#EDE9FE")
PINK        = HexColor("#DB2777")
BLUE        = HexColor("#0284C7")
DARK        = HexColor("#1F2937")
GRAY        = HexColor("#6B7280")
LIGHT_GRAY  = HexColor("#F9FAFB")
BORDER      = HexColor("#E5E7EB")
GREEN       = HexColor("#059669")

ORANGE      = HexColor("#D97706")
ORANGE_DARK = HexColor("#92400E")
ORANGE_LIGHT= HexColor("#FEF3C7")
ORANGE_MID  = HexColor("#B45309")

ACCENT_COLORS = [PURPLE, PINK, BLUE, PURPLE, PINK]


def _style(name, **kwargs) -> ParagraphStyle:
    defaults = dict(fontName="Helvetica", fontSize=10, textColor=DARK, leading=14)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


def create_pdf(ideas: list[dict], output_path: Path, trending: dict = None):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    # Styles
    s_header_title = _style("HeaderTitle", fontName="Helvetica-Bold", fontSize=20,
                             textColor=white, alignment=TA_CENTER, leading=26)
    s_header_sub   = _style("HeaderSub", fontSize=11, textColor=HexColor("#DDD6FE"),
                             alignment=TA_CENTER)
    s_header_date  = _style("HeaderDate", fontSize=9, textColor=HexColor("#C4B5FD"),
                             alignment=TA_CENTER)

    s_idea_num  = _style("IdeaNum", fontName="Helvetica-Bold", fontSize=13,
                          textColor=white)
    s_badge     = _style("Badge", fontName="Helvetica-Bold", fontSize=10,
                          textColor=white, alignment=TA_CENTER)
    s_label     = _style("Label", fontName="Helvetica-Bold", fontSize=8,
                          textColor=GRAY, spaceBefore=6, spaceAfter=2)
    s_title     = _style("Title", fontName="Helvetica-Bold", fontSize=12,
                          textColor=DARK, leading=16)
    s_hook      = _style("Hook", fontName="Helvetica-Oblique", fontSize=11,
                          textColor=PURPLE, leading=16)
    s_body      = _style("Body", fontSize=10, textColor=DARK, leading=14)
    s_hashtag   = _style("Hashtag", fontSize=9, textColor=PURPLE)
    s_cta       = _style("CTA", fontName="Helvetica-Bold", fontSize=10,
                          textColor=GREEN)
    s_footer    = _style("Footer", fontSize=8, textColor=GRAY, alignment=TA_CENTER)

    W = 17 * cm  # usable width

    story = []
    today_str = datetime.now().strftime("%A, %B %d, %Y")

    # ── Header ──────────────────────────────────────────────────────────────
    def make_header():
        rows = [
            [Paragraph("Instagram Content Ideas", s_header_title)],
            [Paragraph("Lifestyle &amp; Self-Improvement Niche", s_header_sub)],
            [Paragraph(today_str, s_header_date)],
        ]
        tbl = Table(rows, colWidths=[W])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), PURPLE),
            ("BACKGROUND",    (0, 1), (-1, 1), PURPLE_MID),
            ("BACKGROUND",    (0, 2), (-1, 2), PURPLE_DARK),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (0, 0), 16),
            ("BOTTOMPADDING", (0, 0), (0, 0), 6),
            ("TOPPADDING",    (0, 1), (0, 1), 5),
            ("BOTTOMPADDING", (0, 1), (0, 1), 5),
            ("TOPPADDING",    (0, 2), (0, 2), 5),
            ("BOTTOMPADDING", (0, 2), (0, 2), 14),
        ]))
        return tbl

    story.append(make_header())
    story.append(Spacer(1, 0.6 * cm))

    # ── Idea cards ──────────────────────────────────────────────────────────
    for i, idea in enumerate(ideas):
        color = ACCENT_COLORS[i % len(ACCENT_COLORS)]

        # Card header row
        header_rows = [[
            Paragraph(f"Idea {i + 1}", s_idea_num),
            Paragraph(idea["format"], s_badge),
        ]]
        card_header = Table(header_rows, colWidths=[13 * cm, 4 * cm])
        card_header.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), color),
            ("ALIGN",         (0, 0), (0, 0), "LEFT"),
            ("ALIGN",         (1, 0), (1, 0), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (0, 0), 14),
            ("RIGHTPADDING",  (1, 0), (1, 0), 10),
        ]))

        # Card body content
        body_elements = [
            Paragraph("TITLE", s_label),
            Paragraph(idea["title"], s_title),

            Paragraph("HOOK", s_label),
            Paragraph(f"\u201c{idea['hook']}\u201d", s_hook),

            Paragraph("KEY POINTS", s_label),
            *[Paragraph(f"&bull;  {pt}", s_body) for pt in idea["key_points"]],

            Paragraph("CAPTION", s_label),
            Paragraph(idea["caption"], s_body),

            Paragraph("HASHTAGS", s_label),
            Paragraph("  ".join(idea["hashtags"]), s_hashtag),

            Paragraph("CALL TO ACTION", s_label),
            Paragraph(f"\u27a1  {idea['cta']}", s_cta),
        ]

        body_rows = [[el] for el in body_elements]
        body_tbl = Table(body_rows, colWidths=[W - 0.8 * cm])
        body_tbl.setStyle(TableStyle([
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        # Wrap body in a border table
        border_tbl = Table([[body_tbl]], colWidths=[W])
        border_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GRAY),
            ("BOX",           (0, 0), (-1, -1), 1, BORDER),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))

        story.append(card_header)
        story.append(border_tbl)
        story.append(Spacer(1, 0.5 * cm))

    # ── Bonus: Trending Topic ─────────────────────────────────────────────────
    if trending:
        s_bonus_title  = _style("BonusTitle", fontName="Helvetica-Bold", fontSize=13, textColor=white)
        s_bonus_badge  = _style("BonusBadge", fontName="Helvetica-Bold", fontSize=10, textColor=white, alignment=TA_CENTER)
        s_bonus_topic  = _style("BonusTopic", fontName="Helvetica-Bold", fontSize=14, textColor=ORANGE, leading=18)
        s_bonus_body   = _style("BonusBody", fontSize=10, textColor=DARK, leading=14)
        s_bonus_hook   = _style("BonusHook", fontName="Helvetica-Oblique", fontSize=11, textColor=ORANGE_MID, leading=16)

        bonus_header = Table(
            [[Paragraph("BONUS", s_bonus_title), Paragraph("Trending Topic", s_bonus_badge)]],
            colWidths=[13 * cm, 4 * cm],
        )
        bonus_header.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), ORANGE),
            ("ALIGN",         (0, 0), (0, 0), "LEFT"),
            ("ALIGN",         (1, 0), (1, 0), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (0, 0), 14),
            ("RIGHTPADDING",  (1, 0), (1, 0), 10),
        ]))

        video_tips = trending.get("video_tips", [])
        if isinstance(video_tips, list):
            video_tips_text = "  ".join(f"&bull; {t}" for t in video_tips)
        else:
            video_tips_text = str(video_tips)

        hashtags = trending.get("hashtags", [])
        hashtags_text = "  ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)

        bonus_elements = [
            Paragraph("TREND KONUSU", s_label),
            Paragraph(trending.get("topic", ""), s_bonus_topic),

            Paragraph("TREND DONEMI", s_label),
            Paragraph(trending.get("peak_period", ""), s_bonus_body),

            Paragraph("NEDEN VIRAL OLDU", s_label),
            Paragraph(trending.get("why_trending", ""), s_bonus_body),

            Paragraph("PLATFORM ISTATISTIKLERI", s_label),
            Paragraph(trending.get("platform_stats", ""), s_bonus_body),

            Paragraph("NISINE NASIL UYARLANIR", s_label),
            Paragraph(trending.get("niche_adaptation", ""), s_bonus_body),

            Paragraph("ICERIK ACISI", s_label),
            Paragraph(trending.get("content_angle", ""), s_bonus_body),

            Paragraph("VIDEO IPUCLARI", s_label),
            Paragraph(video_tips_text, s_bonus_body),

            Paragraph("ONERILECEK SES / MUZIK", s_label),
            Paragraph(trending.get("recommended_audio", ""), s_bonus_body),

            Paragraph("TREND HASHTAG'LER", s_label),
            Paragraph(hashtags_text, s_hashtag),

            Paragraph("HAZIR HOOK", s_label),
            Paragraph(f"\u201c{trending.get('example_hook', '')}\u201d", s_bonus_hook),
        ]

        bonus_inner = Table([[el] for el in bonus_elements], colWidths=[W - 0.8 * cm])
        bonus_inner.setStyle(TableStyle([
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        bonus_border = Table([[bonus_inner]], colWidths=[W])
        bonus_border.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), ORANGE_LIGHT),
            ("BOX",           (0, 0), (-1, -1), 1, ORANGE),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))

        story.append(bonus_header)
        story.append(bonus_border)
        story.append(Spacer(1, 0.5 * cm))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 0.15 * cm))
    generated_at = datetime.now().strftime("%Y-%m-%d at %H:%M")
    story.append(Paragraph(
        f"Generated on {generated_at}  \u2022  Instagram Content Creator Agent",
        s_footer,
    ))

    doc.build(story)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Starting Instagram Content Idea Generator...")

    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set. Add it to your .env file.")
        return

    # 1. Generate ideas and trending topic in parallel (sequentially here)
    print("Generating content ideas with Gemini...")
    ideas = generate_ideas()
    print(f"Generated {len(ideas)} ideas.")

    print("Searching for trending topic...")
    try:
        trending = get_trending_topic()
        print(f"Trending topic found: {trending.get('topic', 'N/A')}")
    except Exception as e:
        print(f"Could not fetch trending topic: {e}")
        trending = None

    # 2. Create PDF locally
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    pdf_name = f"content-ideas-{date_str}.pdf"
    pdf_path = Path(pdf_name)

    print("Building PDF...")
    create_pdf(ideas, pdf_path, trending=trending)
    print(f"PDF created: {pdf_name}")

    # 3. Upload to Google Drive
    print("Connecting to Google Drive...")
    service = get_drive_service()

    root_id = get_or_create_folder(service, DRIVE_ROOT_FOLDER)
    date_id = get_or_create_folder(service, date_str, parent_id=root_id)

    print(f"Uploading to: {DRIVE_ROOT_FOLDER} / {date_str} / {pdf_name}")
    result = upload_file(service, pdf_path, date_id)

    # 4. Clean up local file
    pdf_path.unlink()

    print("Done!")
    link = result.get("webViewLink", "")
    if link:
        print(f"View file: {link}")


if __name__ == "__main__":
    main()
