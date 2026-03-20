import os
import json
import re
from datetime import datetime
from pathlib import Path

from google import genai
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

    prompt = f"""Sen yasam tarzi ve kisisel gelisim alaninda uzman bir Instagram Icerik Ureticisisin.
Bugunun tarihi: {today}.

Tam olarak 3 farkli, yaratici ve uygulanabilir Instagram icerik fikri uret.
Formatlari karistir (Reel, Carousel, Story). Kisisel gelisim, uretkenlik, saglikli yasam ve motivasyon konularina odaklan.
Tum icerikler Turkce olmali FAKAT sadece Ingilizce klavye karakterleri kullan (s, g, u, o, i, c gibi — hic ozel Turkce karakter kullanma: no s with cedilla, no g with breve, no u with umlaut, no o with umlaut, no dotless i, no c with cedilla).
Ornegin: "şehir" yerine "sehir", "güzel" yerine "guzel", "çok" yerine "cok" yaz.

YALNIZCA gecerli bir JSON dizisi dondur — markdown isareti veya ekstra metin olmadan.
Sema:
[
  {{
    "format": "Reel | Carousel | Story",
    "title": "dikkat çekici, kaydırmayı durduran başlık",
    "hook": "ilk 3 saniyede dikkat çeken açılış cümlesi",
    "key_points": ["madde 1", "madde 2", "madde 3"],
    "caption": "kullanıma hazır Instagram açıklaması (3-4 cümle, samimi ve konuşma dili)",
    "hashtags": ["#etiket1", "#etiket2", "#etiket3", "#etiket4", "#etiket5",
                 "#etiket6", "#etiket7", "#etiket8", "#etiket9", "#etiket10"],
    "cta": "net bir harekete geçirici mesaj"
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
    return ideas[:3]


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

ACCENT_COLORS = [PURPLE, PINK, BLUE]


def _style(name, **kwargs) -> ParagraphStyle:
    defaults = dict(fontName="Helvetica", fontSize=10, textColor=DARK, leading=14)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


def create_pdf(ideas: list[dict], output_path: Path):
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

    # 1. Generate ideas
    print("Generating content ideas with Gemini...")
    ideas = generate_ideas()
    print(f"Generated {len(ideas)} ideas.")

    # 2. Create PDF locally
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    pdf_name = f"content-ideas-{date_str}.pdf"
    pdf_path = Path(pdf_name)

    print("Building PDF...")
    create_pdf(ideas, pdf_path)
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
