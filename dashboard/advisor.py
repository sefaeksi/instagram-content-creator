import os
import json
import re
from datetime import datetime
from pathlib import Path
from google import genai

CONTENT_CREATOR_FILE = Path(__file__).parent.parent / "content-creator.md"
ACCOUNTS_FILE        = Path(__file__).parent.parent / "accounts.json"


def _load_context():
    if CONTENT_CREATOR_FILE.exists():
        return CONTENT_CREATOR_FILE.read_text(encoding="utf-8")
    return ""


def _get_hard75_day():
    if not ACCOUNTS_FILE.exists():
        return None
    accounts = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    for acc in accounts:
        start = acc.get("hard75_start_date")
        if start:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            day = (datetime.now().date() - start_date).days + 1
            return day if 1 <= day <= 75 else None
    return None


def analyze(summary: dict) -> dict:
    """
    Sends Instagram stats to Gemini and returns:
      - analysis: text analysis of account performance
      - ideas: list of 5 content idea dicts
      - best_time: recommended posting time
      - growth_tips: 3 actionable growth tips
    """
    client  = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    account = summary.get("account", {})
    posts   = summary.get("posts", [])
    type_stats = summary.get("type_stats", {})
    hard75_day = _get_hard75_day()
    context    = _load_context()
    today      = datetime.now().strftime("%d %B %Y, %A")

    followers = account.get("followers_count", 0)

    # top 3 posts by engagement rate
    top_posts = sorted(posts, key=lambda p: p.get("engagement_rate", 0), reverse=True)[:3]
    top_posts_txt = "\n".join([
        f"  - [{p.get('media_type')}] ER:{p.get('engagement_rate')}% | "
        f"reach:{p.get('insights',{}).get('reach',0)} | saves:{p.get('insights',{}).get('saved',0)} | "
        f"caption: {(p.get('caption') or '')[:80]}"
        for p in top_posts
    ])

    # format performance table
    type_table = "\n".join([
        f"  - {t}: avg_engagement={v.get('avg_eng')}% avg_reach={v.get('avg_reach')} ({v.get('count')} post)"
        for t, v in type_stats.items()
    ])

    # online hours summary
    online = summary.get("online_hours", {})
    if online:
        best_hour = max(online, key=lambda h: online[h]) if online else "?"
        online_txt = f"En aktif saat: {best_hour}:00"
    else:
        online_txt = "Saat verisi mevcut degil"

    if hard75_day:
        hard75_status = f"\n- 75 HARD: Gun {hard75_day}/75 devam ediyor"
        hard75_idea   = f"- Fikir 1: Reel — 75 HARD {hard75_day}. gun icerigi (bu gune ozgu deneyim ve ton)"
        hard75_rule   = ""
    else:
        hard75_status = ""
        hard75_idea   = "- Fikir 1: Reel"
        hard75_rule   = "\nONEMLI: 75 HARD baslamadi. Hicbir icerigi 75 HARD'a baglaMA."

    accounts_data = []
    try:
        accounts_data = json.loads(Path(__file__).parent.parent.joinpath("accounts.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    life_context  = next((a.get("current_life_context","") for a in accounts_data if a.get("username")=="ssefaeksii"), "")
    recent_topics = next((a.get("recent_topics_used",[]) for a in accounts_data if a.get("username")=="ssefaeksii"), [])
    life_block    = f"\n--- GUNCEL HAYAT BAGLAMI ---\n{life_context}\n" if life_context else ""
    recent_block  = ("\n--- SON KULLANILAN KONULAR (tekrar etme) ---\n" + "\n".join(f"- {t}" for t in recent_topics[-10:]) + "\n") if recent_topics else ""

    prompt = f"""Sen @{account.get('username','ssefaeksii')} icin Instagram buyume danismanisin.

HESAP DURUMU ({today}):
- Takipciler: {followers:,}
- Medya sayisi: {account.get('media_count', 0)}
- Son 28 gun reach: {summary.get('reach_28d', 0):,}
- Profil ziyareti (28g): {summary.get('profile_views_28d', 0):,}{hard75_status}
{life_block}{recent_block}

ICERIK TIPI PERFORMANSI:
{type_table}

EN IYI 3 GONDERI:
{top_posts_txt}

IZLEYICI ONLINE SAATLERI:
{online_txt}

HESAP KARAKTERI VE STRATEJI:
{context}

--- ICERIK FIKIRLERI GOREVI ---
Tam olarak 5 fikir uret:
{hard75_idea}
- Fikir 2: Carousel
- Fikir 3: Story
- Fikir 4: Reel (farkli konu)
- Fikir 5: Reel (farkli konu){hard75_rule}

---
Asagidaki 4 blogu JSON olarak dondur. Markdown fence veya ekstra metin olmamali.
TUM METINLER TURKCE OLMALI. Ingilizce klavye karakterleri kullan (ozel Turkce harf yok: s-cedilla, g-breve, u-umlaut, o-umlaut, dotless-i, c-cedilla).
Hicbir alan Ingilizce olmamali — analysis, growth_tips, title, hook, key_points, caption, cta, why_it_works hepsi Turkce.

{{
  "analysis": "200-300 kelimelik Turkce performans analizi. Neyin isleyip islemedigi, hangi icerik tipi daha iyi, buyumenin yonu.",
  "growth_tips": [
    "Turkce somut buyume tavsiyesi 1",
    "Turkce somut buyume tavsiyesi 2",
    "Turkce somut buyume tavsiyesi 3"
  ],
  "best_posting_time": "Ornegin: Aksam 19:00-21:00 arasi",
  "ideas": [
    {{
      "format": "Reel | Carousel | Story",
      "title": "Turkce dikkat cekici baslik",
      "hook": "Turkce ilk 3 saniye hook",
      "key_points": ["Turkce madde1", "Turkce madde2", "Turkce madde3"],
      "caption": "Turkce mikro-blog tarzinda caption (IG SEO anahtar kelimeler iceriyor)",
      "hashtags": ["#etiket1","#etiket2","#etiket3","#etiket4","#etiket5","#etiket6","#etiket7","#etiket8","#etiket9","#etiket10"],
      "cta": "Turkce harekete gecirici mesaj",
      "why_it_works": "Turkce — neden bu hesap icin iyi performans gosterir (istatistiklere gore)"
    }}
  ]
}}

ideas dizisinde tam olarak 5 fikir olsun. Performans verisine dayanarak en yuksek engagement getirecek formatlari once yaz."""

    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    last_err = None
    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            return json.loads(raw)
        except Exception as e:
            last_err = e
            continue
    raise last_err


def generate_reel_ideas(topic: str) -> dict:
    """
    Generates 5 detailed, trend-worthy reel ideas for a given topic.
    Returns: { "ideas": [...] }
    """
    client  = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    context = _load_context()
    today   = datetime.now().strftime("%d %B %Y, %A")

    accounts_data = []
    try:
        accounts_data = json.loads(Path(__file__).parent.parent.joinpath("accounts.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    life_context  = next((a.get("current_life_context", "") for a in accounts_data if a.get("username") == "ssefaeksii"), "")
    life_block    = f"\n--- GUNCEL HAYAT BAGLAMI ---\n{life_context}\n" if life_context else ""

    prompt = f"""Sen @ssefaeksii icin Instagram reel icerik danismanisin.
Bugun: {today}
{life_block}
HESAP KARAKTERI VE STRATEJI:
{context}

KULLANICININ VERDIGI KONU / ICERIK FIKRI:
\"\"\"{topic}\"\"\"

Bu konuya ozel, birbirinden farkli, trendlere girebilecek 5 REEL fikri uret.

Her fikir:
- Platformda viral olabilecek kadar dikkat cekici olmali
- Ilk 3 saniye hook'u guclu olmali (kaydirmaya durduracak)
- Hesabin kimligine uygun olmali
- Birbirinin tekrari OLMAMALI — farkli acidan, farkli format veya farkli duygusal ton kullan
- Eger konu 75 HARD programiyla ilgiliyse bunu entegre et, degilse zorla baglaMA

Asagidaki JSON formatinda don. Markdown fence veya ekstra metin olmamali.
TUM METINLER TURKCE OLMALI. Ingilizce klavye karakterleri kullan (ozel Turkce harf yok).

{{
  "topic_insight": "Bu konunun neden simdi trend potansiyeli tasidigi — 1-2 cumle Turkce analiz",
  "ideas": [
    {{
      "format": "Reel",
      "title": "Dikkat cekici Turkce baslik",
      "hook": "Ilk 3 saniye hook — izleyiciyi durduracak guclu cumle",
      "angle": "Bu fikri diger 4'ten ayiran yaklasim acisi",
      "key_points": ["Madde 1", "Madde 2", "Madde 3", "Madde 4"],
      "visual_direction": "Gorsel/cekis tarzi ve sahne icin somut tavsiye",
      "caption": "Mikro-blog tarzinda IG SEO anahtar kelimeli Turkce caption",
      "hashtags": ["#etiket1","#etiket2","#etiket3","#etiket4","#etiket5","#etiket6","#etiket7","#etiket8","#etiket9","#etiket10"],
      "cta": "Harekete gecirici mesaj",
      "trend_reason": "Neden su anda trend olabilir — guclu bir neden"
    }}
  ]
}}

ideas dizisinde tam olarak 5 fikir olsun. Fikirleri en trendden en yaratici/nicheye dogru sirala."""

    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    last_err = None
    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            return json.loads(raw)
        except Exception as e:
            last_err = e
            continue
    raise last_err
