"""
Instagram Content Idea Generator
- Loops over all accounts in accounts.json
- Analyzes each account's niche via Gemini + Google Search
- Generates tailored daily content ideas
- Creates a styled PDF per account
- Saves to Google Drive: Instagram Content Ideas / {username} / {date} /
- Sends PDF via email for accounts with send_email=true
"""

import os
import json
import re
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google import genai
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
)
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
GMAIL_SENDER     = os.getenv("GMAIL_SENDER", "sefaeksi9@gmail.com")
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD")
DRIVE_ROOT       = "Instagram Content Ideas"
SCOPES           = ["https://www.googleapis.com/auth/drive"]
ACCOUNTS_FILE    = Path(__file__).parent / "accounts.json"
SENT_LOG_FILE    = Path(__file__).parent / "sent_log.json"

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def load_accounts():
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Daily send log  (prevents duplicate emails on the same day)
# ---------------------------------------------------------------------------

def already_sent_today(username):
    today = datetime.now().strftime("%Y-%m-%d")
    if not SENT_LOG_FILE.exists():
        return False
    log = json.loads(SENT_LOG_FILE.read_text(encoding="utf-8"))
    return log.get(username) == today


def mark_sent_today(username):
    today = datetime.now().strftime("%Y-%m-%d")
    log = json.loads(SENT_LOG_FILE.read_text(encoding="utf-8")) if SENT_LOG_FILE.exists() else {}
    log[username] = today
    SENT_LOG_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def get_drive_service():
    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    google_token_json = os.getenv("GOOGLE_TOKEN_JSON")
    if google_creds_json:
        creds_path.write_text(google_creds_json)
    if google_token_json:
        token_path.write_text(google_token_json)

    if not creds_path.exists():
        raise FileNotFoundError("credentials.json not found.")

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


def upload_file(service, local_path, parent_id):
    metadata = {"name": local_path.name, "parents": [parent_id]}
    media = MediaFileUpload(str(local_path), mimetype="application/pdf")
    return service.files().create(
        body=metadata, media_body=media, fields="id,webViewLink"
    ).execute()


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email_with_pdf(to_email, pdf_path, account):
    if not GMAIL_PASSWORD:
        print(f"  [SKIP] GMAIL_APP_PASSWORD not set — skipping email to {to_email}")
        return

    username = account["username"]
    date_str = datetime.now().strftime("%d %B %Y")

    msg = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = to_email
    msg["Subject"] = f"@{username} | Gunluk Instagram Icerik Fikirleri | {date_str}"

    body = (
        f"Merhaba,\n\n"
        f"@{username} hesabiniz icin {date_str} tarihli icerik fikirleri ekte yer almaktadir.\n\n"
        f"Bugun sizin icin 5 farkli icerik fikri hazirladik.\n\n"
        f"Basarilar dileriz!\n"
        f"Instagram Content Creator Agent"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{pdf_path.name}"',
        )
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.send_message(msg)

    print(f"  Email sent to {to_email}")


# ---------------------------------------------------------------------------
# Gemini — Content ideas (account-specific)
# ---------------------------------------------------------------------------

def generate_ideas(account):
    client = genai.Client(api_key=GEMINI_API_KEY)
    today  = datetime.now().strftime("%d %B %Y, %A")

    niche          = account.get("niche", "Lifestyle & Self-Improvement")
    content_style  = account.get("content_style", "motivasyonel, egitici")
    target_audience= account.get("target_audience", "genel kitle")
    language       = account.get("language", "Turkish")

    lang_rule = (
        "Tum icerikler Turkce olmali FAKAT SADECE Ingilizce klavye karakterleri kullan. "
        "Hic ozel Turkce karakter kullanma (no s-cedilla, no g-breve, no u-umlaut, no o-umlaut, no dotless-i, no c-cedilla). "
        "Ornek: 'guzellesmek', 'olusturmak', 'cok', 'sehir', 'gercek', 'icerik'"
        if language.lower() in ("turkish", "turkce")
        else f"Write all content in {language}."
    )

    prompt = f"""Sen @{account['username']} hesabina ozel icerik uretiyorsun.

Hesap bilgileri:
- Nis: {niche}
- Icerik stili: {content_style}
- Hedef kitle: {target_audience}

Bugunun tarihi: {today}.

--- YETENEKLERIN ---
- Reels: Ilk 3 saniyede dikkati kacirmayan hook'lar, trend uyarlamasi, izlenme suresi ve paylasimi maksimize eden senaryo
- Carousel: Kaydetmeyi ve paylasmayi tetikleyen egitici kaydirmali icerik; gorsel hiyerarsiye dikkat
- Story: BTS anlatimlari, anlasma artiran etkilesimli sticker'lar, 24 saatlik anlati arki
- Caption & IG SEO: Mikro-blog aciklamalar, anahtar kelimeler, nis hashtag stratejisi, guclu CTA
- Marka sesi: Tutarli estetik, samimi ton, {niche} nisine uygun rakip analizi

--- GOREV ---
Bu hesaba ve nisine OZEL tam olarak 5 icerik fikri uret:
- Fikir 1: Reel
- Fikir 2: Carousel
- Fikir 3: Story
- Fikir 4: Reel (farkli konu, farkli hook stili)
- Fikir 5: Reel (farkli konu, farkli hook stili)
Fikirlerin hepsi {niche} nisine ve bu hesabin kitlesine uygun olmali.

--- DIL KURALI ---
{lang_rule}

--- CIKTI ---
YALNIZCA gecerli bir JSON dizisi dondur. Markdown fence veya ekstra metin kesinlikle olmamali.
[
  {{
    "format": "Reel | Carousel | Story",
    "title": "kaydirilmayi durduran, dikkat cekici baslik",
    "hook": "ilk 3 saniyede dikkati yakalayan acilis cumlesi",
    "key_points": ["madde 1", "madde 2", "madde 3"],
    "caption": "mikro-blog tarzinda Instagram aciklamasi (3-4 cumle, IG SEO anahtar kelimeler iceriyor)",
    "hashtags": ["#etiket1", "#etiket2", "#etiket3", "#etiket4", "#etiket5",
                 "#etiket6", "#etiket7", "#etiket8", "#etiket9", "#etiket10"],
    "cta": "net ve ikna edici harekete gecirici mesaj"
  }}
]"""

    response = client.models.generate_content(
        model="models/gemini-3-flash-preview",
        contents=prompt,
    )
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)[:5]


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

PURPLE       = HexColor("#7C3AED")
PURPLE_DARK  = HexColor("#5B21B6")
PURPLE_MID   = HexColor("#6D28D9")
PINK         = HexColor("#DB2777")
BLUE         = HexColor("#0284C7")
DARK         = HexColor("#1F2937")
GRAY         = HexColor("#6B7280")
LIGHT_GRAY   = HexColor("#F9FAFB")
BORDER       = HexColor("#E5E7EB")
GREEN        = HexColor("#059669")
ACCENT_COLORS = [PURPLE, PINK, BLUE, PURPLE, PINK]


def _style(name, **kwargs):
    defaults = dict(fontName="Helvetica", fontSize=10, textColor=DARK, leading=14)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


def create_pdf(ideas, account, output_path):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm,   bottomMargin=2 * cm,
    )

    s_header_title = _style("HT", fontName="Helvetica-Bold", fontSize=18, textColor=white, alignment=TA_CENTER, leading=24)
    s_header_user  = _style("HU", fontName="Helvetica-Bold", fontSize=12, textColor=HexColor("#DDD6FE"), alignment=TA_CENTER)
    s_header_sub   = _style("HS", fontSize=10, textColor=HexColor("#C4B5FD"), alignment=TA_CENTER)
    s_header_date  = _style("HD", fontSize=9,  textColor=HexColor("#A78BFA"), alignment=TA_CENTER)

    s_idea_num = _style("IN", fontName="Helvetica-Bold", fontSize=13, textColor=white)
    s_badge    = _style("IB", fontName="Helvetica-Bold", fontSize=10, textColor=white, alignment=TA_CENTER)
    s_label    = _style("LB", fontName="Helvetica-Bold", fontSize=8, textColor=GRAY, spaceBefore=6, spaceAfter=2)
    s_title    = _style("TT", fontName="Helvetica-Bold", fontSize=12, textColor=DARK, leading=16)
    s_hook     = _style("HK", fontName="Helvetica-Oblique", fontSize=11, textColor=PURPLE, leading=16)
    s_body     = _style("BD", fontSize=10, textColor=DARK, leading=14)
    s_hashtag  = _style("HH", fontSize=9, textColor=PURPLE)
    s_cta      = _style("CT", fontName="Helvetica-Bold", fontSize=10, textColor=GREEN)
    s_footer   = _style("FT", fontSize=8, textColor=GRAY, alignment=TA_CENTER)

    W        = 17 * cm
    today_str = datetime.now().strftime("%A, %d %B %Y")
    niche     = account.get("niche", "")
    username  = account.get("username", "")

    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    header_tbl = Table([
        [Paragraph("Instagram Content Ideas", s_header_title)],
        [Paragraph(f"@{username}", s_header_user)],
        [Paragraph(niche, s_header_sub)],
        [Paragraph(today_str, s_header_date)],
    ], colWidths=[W])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), PURPLE),
        ("BACKGROUND",    (0, 1), (-1, 1), PURPLE_MID),
        ("BACKGROUND",    (0, 2), (-1, 2), PURPLE_DARK),
        ("BACKGROUND",    (0, 3), (-1, 3), HexColor("#4C1D95")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (0, 0), 14),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
        ("TOPPADDING",    (0, 1), (0, 1), 4),
        ("BOTTOMPADDING", (0, 1), (0, 1), 4),
        ("TOPPADDING",    (0, 2), (0, 2), 4),
        ("BOTTOMPADDING", (0, 2), (0, 2), 4),
        ("TOPPADDING",    (0, 3), (0, 3), 4),
        ("BOTTOMPADDING", (0, 3), (0, 3), 12),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 0.6 * cm))

    # ── Idea cards ──────────────────────────────────────────────────────────
    for i, idea in enumerate(ideas):
        color = ACCENT_COLORS[i % len(ACCENT_COLORS)]

        card_header = Table([[
            Paragraph(f"Idea {i + 1}", s_idea_num),
            Paragraph(idea["format"], s_badge),
        ]], colWidths=[13 * cm, 4 * cm])
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

        body_tbl = Table([[el] for el in body_elements], colWidths=[W - 0.8 * cm])
        body_tbl.setStyle(TableStyle([
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

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
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M')}  \u2022  Instagram Content Creator Agent  \u2022  @{username}",
        s_footer,
    ))

    doc.build(story)


# ---------------------------------------------------------------------------
# Process one account
# ---------------------------------------------------------------------------

def process_account(account, drive_service):
    username   = account["username"]
    send_email = account.get("send_email", False)
    # drive_only accounts (send_email=False) go to Google Drive only
    # email accounts (send_email=True)  get email only — no Drive
    print(f"\n--- Processing @{username} ({'email only' if send_email else 'Drive only'}) ---")

    # One delivery per account per day
    if already_sent_today(username):
        print(f"  Skipping — already processed @{username} today.")
        return

    print("  Generating content ideas...")
    ideas = generate_ideas(account)
    print(f"  Generated {len(ideas)} ideas.")

    date_str = datetime.now().strftime("%Y-%m-%d")
    pdf_name = f"content-ideas-{date_str}.pdf"
    pdf_path = Path(pdf_name)

    print("  Building PDF...")
    create_pdf(ideas, account, pdf_path)

    if send_email:
        print(f"  Sending email to {account['email']}...")
        send_email_with_pdf(account["email"], pdf_path, account)
    else:
        print("  Uploading to Google Drive...")
        root_id = get_or_create_folder(drive_service, DRIVE_ROOT)
        user_id = get_or_create_folder(drive_service, username, parent_id=root_id)
        date_id = get_or_create_folder(drive_service, date_str, parent_id=user_id)
        result  = upload_file(drive_service, pdf_path, date_id)
        print(f"  Drive: {DRIVE_ROOT}/{username}/{date_str}/{pdf_name}")
        link = result.get("webViewLink", "")
        if link:
            print(f"  View: {link}")

    mark_sent_today(username)
    pdf_path.unlink()
    print(f"  Done: @{username}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Starting Instagram Content Idea Generator...")

    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set.")
        return

    accounts = load_accounts()
    print(f"Loaded {len(accounts)} account(s): {[a['username'] for a in accounts]}")

    print("Connecting to Google Drive...")
    drive_service = get_drive_service()

    for account in accounts:
        try:
            process_account(account, drive_service)
        except Exception as e:
            print(f"ERROR processing @{account['username']}: {e}")
            import traceback
            traceback.print_exc()

    print("\nAll accounts processed.")


if __name__ == "__main__":
    main()
