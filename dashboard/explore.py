import os
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from google import genai
from google.genai import types

CONTENT_CREATOR_FILE = Path(__file__).parent.parent / "content-creator.md"
EXPLORE_THRESHOLD    = 1.4   # reach / followers ratio — above this = likely on Explore


def _load_context():
    if CONTENT_CREATOR_FILE.exists():
        return CONTENT_CREATOR_FILE.read_text(encoding="utf-8")
    return ""


def detect_explore_posts(posts: list, followers: int) -> list:
    """Posts whose reach exceeds EXPLORE_THRESHOLD × followers."""
    threshold = max(followers * EXPLORE_THRESHOLD, 500)
    result = []
    for post in posts:
        reach = post.get("insights", {}).get("reach", 0)
        if reach >= threshold:
            ratio = round(reach / max(followers, 1), 2)
            result.append({**post, "reach_ratio": ratio})
    return sorted(result, key=lambda p: p["reach_ratio"], reverse=True)


def _extract_patterns(explore_posts: list, all_posts: list, followers: int) -> dict:
    if not explore_posts:
        return {}

    # format distribution
    fmt_count = {}
    for p in explore_posts:
        t = p.get("media_type", "VIDEO")
        fmt_count[t] = fmt_count.get(t, 0) + 1
    best_format = max(fmt_count, key=fmt_count.get) if fmt_count else "VIDEO"

    # posting hours
    hours = []
    for p in explore_posts:
        ts = p.get("timestamp", "")
        if ts:
            try:
                h = datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
                hours.append(h)
            except Exception:
                pass
    best_hours = sorted(set(hours)) if hours else []

    # avg metrics
    avg_reach  = round(sum(p.get("insights",{}).get("reach",  0) for p in explore_posts) / len(explore_posts))
    avg_views  = round(sum(p.get("insights",{}).get("views",  0) for p in explore_posts) / len(explore_posts))
    avg_saves  = round(sum(p.get("insights",{}).get("saved",  0) for p in explore_posts) / len(explore_posts))
    avg_shares = round(sum(p.get("insights",{}).get("shares", 0) for p in explore_posts) / len(explore_posts))
    avg_ratio  = round(sum(p.get("reach_ratio", 0) for p in explore_posts) / len(explore_posts), 2)

    # caption excerpts of top 3
    top_captions = [
        (p.get("caption") or "")[:100]
        for p in explore_posts[:3]
    ]

    return {
        "count":         len(explore_posts),
        "best_format":   best_format,
        "best_hours":    best_hours,
        "avg_reach":     avg_reach,
        "avg_views":     avg_views,
        "avg_saves":     avg_saves,
        "avg_shares":    avg_shares,
        "avg_ratio":     avg_ratio,
        "top_captions":  top_captions,
        "format_dist":   fmt_count,
    }


def _fetch_trends(client, niche: str, today_str: str) -> str:
    """Step 1: Use Gemini + Google Search to get real-time Instagram trends."""
    search_prompt = (
        f"Bugun {today_str}. "
        f"Instagram'da su anda Turkiye'de '{niche}' nisinde viral olan icerikleri ara. "
        f"Asagidakileri bul:\n"
        f"1. Su an trend olan konu ve temalar\n"
        f"2. En cok paylasilan/kaydedilen icerik tipleri (Reel/Carousel/Story)\n"
        f"3. Viral olan hashtagler\n"
        f"4. Populer hook kaliplari\n"
        f"5. Hangi saatlerde daha cok etkilesim var\n"
        f"Kisa ve somut bir ozet ver, madde madde."
    )
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        return resp.text.strip()
    except Exception:
        return "Trend verisi alinamamadi."


def generate_explore_plan(summary: dict) -> dict:
    """
    Returns:
      - explore_posts: list of posts that likely hit Explore
      - patterns: extracted viral patterns
      - gemini_analysis: text analysis of why they went viral
      - weekly_plan: 7-day content calendar optimized for Explore
    """
    client    = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    posts     = summary.get("posts", [])
    followers = summary.get("account", {}).get("followers_count", 1) or 1
    username  = summary.get("account", {}).get("username", "ssefaeksii")
    context   = _load_context()
    today     = datetime.now()
    today_str = today.strftime("%d %B %Y, %A")

    explore_posts = detect_explore_posts(posts, followers)
    patterns      = _extract_patterns(explore_posts, posts, followers)

    # Step 1: fetch real-time trends via Google Search
    trends_txt = _fetch_trends(client, "lifestyle kisisel gelisim motivasyon", today_str)

    # Build posts summary for prompt
    fmt_map = {"VIDEO": "Reel", "CAROUSEL_ALBUM": "Carousel", "IMAGE": "Foto"}

    explore_txt = "\n".join([
        f"  [{fmt_map.get(p.get('media_type','VIDEO'),'Reel')}] "
        f"ratio:{p.get('reach_ratio')}x | reach:{p.get('insights',{}).get('reach',0):,} | "
        f"views:{p.get('insights',{}).get('views',0):,} | saves:{p.get('insights',{}).get('saved',0)} | "
        f"shares:{p.get('insights',{}).get('shares',0)} | "
        f"caption: {(p.get('caption') or '')[:80]}"
        for p in explore_posts[:6]
    ]) or "  Hic kesfe giren gonderi tespit edilemedi."

    all_txt = "\n".join([
        f"  [{fmt_map.get(p.get('media_type','VIDEO'),'Reel')}] "
        f"ER:{p.get('engagement_rate',0)}% reach:{p.get('insights',{}).get('reach',0):,} | "
        f"caption: {(p.get('caption') or '')[:60]}"
        for p in sorted(posts, key=lambda p: p.get("insights",{}).get("reach",0), reverse=True)[:10]
    ])

    # 7-day dates
    days_tr = ["Pazartesi","Sali","Carsamba","Persembe","Cuma","Cumartesi","Pazar"]
    week_dates = []
    d = today + timedelta(days=1)
    while len(week_dates) < 7:
        week_dates.append({
            "day":  days_tr[d.weekday()],
            "date": d.strftime("%Y-%m-%d"),
        })
        d += timedelta(days=1)
    week_txt = "\n".join(f"  {w['day']} {w['date']}" for w in week_dates)

    patterns_txt = (
        f"- Kese giren gonderi sayisi: {patterns.get('count',0)}\n"
        f"- En iyi format: {fmt_map.get(patterns.get('best_format','VIDEO'),'Reel')}\n"
        f"- Ortalama reach orani: {patterns.get('avg_ratio',0)}x takipci\n"
        f"- Ortalama views: {patterns.get('avg_views',0):,}\n"
        f"- Ortalama saves: {patterns.get('avg_saves',0)}\n"
        f"- Paylasim saatleri: {patterns.get('best_hours',[])}"
    ) if patterns else "- Yeterli veri yok"

    prompt = f"""Sen @{username} icin Instagram Kesif (Explore) analisti ve icerik stratejistsin.

BUGUN: {today_str}
TAKIPCI: {followers:,}

--- INSTAGRAM'DA SU AN TREND OLAN ICERIKLER (Google Search sonucu) ---
{trends_txt}

--- @{username} HESABININ KENDI KESIF VERILERI ---
KESIF ESIGI: reach > {EXPLORE_THRESHOLD}x takipci ({int(followers*EXPLORE_THRESHOLD):,}+)

KESE GIREN KENDI GONDERILERI (reach oranina gore):
{explore_txt}

KENDI GONDERILERININ PERFORMANSI (top 10):
{all_txt}

KENDI HESABINDA TESPIT EDILEN VIRAL KALIPLER:
{patterns_txt}

HESAP KARAKTERI VE STRATEJI:
{context}

GELECEK 7 GUN:
{week_txt}

---
GOREV: Yukaridaki IKI kaynagi birlestir:
1. Dis dunya trendleri (Google Search sonucu) — su an ne viral
2. Bu hesabin kendi viral kaliplari — ne sekilde icerik uretince kesfe giriyor

Bu ikisini birlestirerek haftalik plan ve analiz uret.

Asagidaki JSON'u dondur. Markdown fence veya ekstra metin olmamali.
TUM METINLER TURKCE. Ingilizce klavye karakterleri kullan (ozel Turkce harf yok).

{{
  "gemini_analysis": "200-250 kelimelik Turkce analiz: Dis dunyada ne trend, bu hesabin kendi viral kaliplari ne, ikisini nasil birlestirmeli.",
  "trending_topics": [
    {{"topic": "trend konu 1", "why": "neden trend (1 cumle)", "format": "Reel"}},
    {{"topic": "trend konu 2", "why": "neden trend", "format": "Reel"}},
    {{"topic": "trend konu 3", "why": "neden trend", "format": "Carousel"}},
    {{"topic": "trend konu 4", "why": "neden trend", "format": "Reel"}},
    {{"topic": "trend konu 5", "why": "neden trend", "format": "Story"}}
  ],
  "viral_rules": [
    "Kese girmek icin kural 1 (hem trend hem bu hesaba ozel)",
    "Kese girmek icin kural 2",
    "Kese girmek icin kural 3",
    "Kese girmek icin kural 4"
  ],
  "weekly_plan": [
    {{
      "day": "Pazartesi",
      "date": "YYYY-MM-DD",
      "format": "Reel | Carousel | Story",
      "topic": "kisa konu basligi",
      "title": "icerik basligi",
      "hook": "ilk 3 saniye hook",
      "best_time": "HH:00",
      "explore_potential": "Yuksek | Orta | Dusuk",
      "explore_reason": "neden bu icerik kese girebilir (1 cumle)",
      "key_points": ["madde1", "madde2", "madde3"]
    }}
  ]
}}

weekly_plan dizisinde tam olarak 7 eleman olsun (bir sonraki 7 gun icin).
Her gun icin en yuksek explore potansiyelli formati sec. Viral kaliplara gore optimize et."""

    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    last_err = None
    result = None
    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            result = json.loads(raw)
            break
        except Exception as e:
            last_err = e
            continue

    if result is None:
        raise last_err

    return {
        "explore_posts":    explore_posts,
        "patterns":         patterns,
        "analysis":         result.get("gemini_analysis", ""),
        "trending_topics":  result.get("trending_topics", []),
        "viral_rules":      result.get("viral_rules", []),
        "weekly_plan":      result.get("weekly_plan", []),
    }
