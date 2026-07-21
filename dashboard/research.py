"""
LightReel-lite arastirma motoru.

instagram_scraper ile toplanan gercek Instagram verisini Gemini'ye besleyip
creator kesfi, trend/hook sohbeti ve script performans analizi uretir.
"""
import os
import re
import json
from pathlib import Path

from google import genai

import instagram_scraper

CONTENT_CREATOR_FILE = Path(__file__).parent.parent / "content-creator.md"

MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

SCRAPER_ERROR_MESSAGES = {
    "rate_limited": "Instagram su anda cok fazla istek nedeniyle engelliyor. Lutfen birkac dakika sonra tekrar deneyin.",
    "not_found":     "Bu hashtag veya kullanici bulunamadi.",
    "private":       "Bu hesap gizli, veri alinamadi.",
    "login_required": "Instagram bu veri icin giris gerektiriyor. .env dosyasina IG_USERNAME/IG_PASSWORD ekleyin.",
    "unknown":       "Instagram verisi alinirken bir hata olustu.",
}


def scraper_message(err: instagram_scraper.ScraperError) -> str:
    return SCRAPER_ERROR_MESSAGES.get(err.kind, SCRAPER_ERROR_MESSAGES["unknown"])


def _load_context() -> str:
    if CONTENT_CREATOR_FILE.exists():
        return CONTENT_CREATOR_FILE.read_text(encoding="utf-8")
    return ""


def _generate(prompt: str) -> str:
    """Gemini'ye sorar, ham metni dondurur. Modeller sirayla denenir."""
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    last_err = None
    for model in MODELS:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text.strip()
        except Exception as e:
            last_err = e
            continue
    raise last_err


def _generate_json(prompt: str) -> dict:
    raw = _generate(prompt)
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


def _format_posts_for_prompt(posts: list) -> str:
    lines = []
    for p in posts:
        video_note = f", {p['video_view_count']} izlenme" if p.get("video_view_count") else ""
        tags = " #".join(p["hashtags"]) if p["hashtags"] else "-"
        lines.append(
            f"- @{p['owner_username']}: \"{p['caption']}\" "
            f"({p['likes']} begeni, {p['comments']} yorum{video_note}) #{tags}"
        )
    return "\n".join(lines) if lines else "(veri bulunamadi)"


# --- Creator kesfi ------------------------------------------------------------

def discover_creators(hashtag: str, min_followers: int = 0, max_followers: int = 0) -> dict:
    """Hashtag altindaki creator'lari bulur ve Gemini ile degerlendirip siralar."""
    creators = instagram_scraper.discover_creators(
        hashtag, 30, min_followers, max_followers or None
    )
    if not creators:
        raise ValueError("Bu hashtag icin uygun kriterlere sahip creator bulunamadi.")

    creators_block = "\n".join(
        f"- @{c['username']} ({c['full_name']}): {c['followers']} takipci, {c['mediacount']} gonderi"
        f"{', dogrulanmis' if c['is_verified'] else ''} — bio: {c['biography'] or '(yok)'}"
        for c in creators
    )

    prompt = f"""#{hashtag} hashtag'i altinda bulunan gercek Instagram creator'lari:

{creators_block}

Bu creator'lari icerik isbirligi acisindan degerlendir ve en uygun olanlari sirala.

Asagidaki JSON'u dondur. Markdown fence veya ekstra metin olmamali.
TUM METINLER TURKCE OLMALI. Ingilizce klavye karakterleri kullan (ozel Turkce harf yok).

{{
  "summary": "2-3 cumlelik Turkce genel degerlendirme — bu hashtag'teki creator profili nasil",
  "creators": [
    {{
      "username": "kullanici_adi (yukaridaki listeden birebir)",
      "reason": "Turkce tek cumle — neden uygun veya uygun degil",
      "potential": "Dusuk | Orta | Yuksek"
    }}
  ]
}}

creators dizisinde yukaridaki her creator icin bir kayit olsun, isbirligi potansiyeli
en yuksek olan basta olacak sekilde sirala."""

    result = _generate_json(prompt)

    # LLM degerlendirmesini gercek profil verisiyle birlestir — istatistikler
    # her zaman scraper'dan gelsin, LLM'in uydurmasina birakma.
    by_username = {c["username"].lower(): c for c in creators}
    merged = []
    for item in result.get("creators", []):
        profile = by_username.pop(str(item.get("username", "")).lstrip("@").lower(), None)
        if not profile:
            continue
        merged.append({**profile, "reason": item.get("reason", ""), "potential": item.get("potential", "")})
    # LLM'in atladigi creator'lar da listede kalsin
    for profile in by_username.values():
        merged.append({**profile, "reason": "", "potential": ""})

    return {"summary": result.get("summary", ""), "creators": merged}


# --- Trend & hook sohbeti -----------------------------------------------------

def trend_chat(question: str, hashtag: str) -> dict:
    """Gercek hashtag verisiyle beslenen trend/hook sohbeti."""
    posts = instagram_scraper.scan_hashtag(hashtag, 30)
    if not posts:
        raise ValueError("Bu hashtag icin veri bulunamadi.")

    context_block = _format_posts_for_prompt(posts)
    prompt = f"""Kullanicinin sorusu: "{question}"

Asagida #{hashtag} etiketi altinda toplanan gercek, guncel Instagram gonderileri var:

{context_block}

Bu gercek verilere dayanarak kullanicinin sorusunu yanitla. Somut ornekler ver,
yukaridaki gonderilerden gozlemlere referans ver (hangi hesap, hangi hook/format ise yaramis gibi).

Asagidaki JSON'u dondur. Markdown fence veya ekstra metin olmamali.
TUM METINLER TURKCE OLMALI. Ingilizce klavye karakterleri kullan (ozel Turkce harf yok).

{{
  "answer": "Turkce detayli cevap — 200-350 kelime, gercek gonderilere referansli",
  "observations": [
    "Turkce somut gozlem 1 (hangi hesap/format ne yapmis)",
    "Turkce somut gozlem 2",
    "Turkce somut gozlem 3"
  ],
  "hooks": [
    "Bu veriye dayanan Turkce hook onerisi 1",
    "Turkce hook onerisi 2",
    "Turkce hook onerisi 3"
  ]
}}"""

    result = _generate_json(prompt)
    result["post_count"] = len(posts)
    result["top_posts"] = sorted(posts, key=lambda p: p.get("likes", 0), reverse=True)[:5]
    return result


# --- Script performans analizi ------------------------------------------------

def analyze_script(script_text: str, performance_notes: str = "") -> dict:
    """Script/caption metnini LightReel tarzi degerlendirir. Scraping yok."""
    notes_line = (
        f"Performans notlari: {performance_notes}"
        if performance_notes.strip()
        else "Performans notlari: (belirtilmedi)"
    )
    context = _load_context()
    context_block = f"\n--- HESAP KARAKTERI VE STRATEJI ---\n{context}\n" if context else ""

    prompt = f"""Asagidaki Instagram video scriptini/caption'ini profesyonel bir UGC pazarlama analisti gibi degerlendir.

Script:
{script_text}

{notes_line}
{context_block}
Asagidaki JSON'u dondur. Markdown fence veya ekstra metin olmamali.
TUM METINLER TURKCE OLMALI. Ingilizce klavye karakterleri kullan (ozel Turkce harf yok).

{{
  "score": 0-100 arasi bir sayi — scriptin genel performans potansiyeli,
  "overall": "Turkce genel degerlendirme — guclu ve zayif yonler, 2-3 cumle",
  "hook_analysis": "Turkce hook analizi — ilk 3 saniye dikkat cekiyor mu, neden ise yarar/yaramaz",
  "weak_points": [
    "Turkce somut zayif nokta 1 (pacing, mesaj netligi, CTA zayifligi gibi)",
    "Turkce somut zayif nokta 2",
    "Turkce somut zayif nokta 3"
  ],
  "improvements": [
    "Turkce somut iyilestirme onerisi 1",
    "Turkce somut iyilestirme onerisi 2",
    "Turkce somut iyilestirme onerisi 3"
  ],
  "alternative_hook": "Scriptin konusuna uygun, daha guclu bir acilis cumlesi — tam metin"
}}"""

    return _generate_json(prompt)
