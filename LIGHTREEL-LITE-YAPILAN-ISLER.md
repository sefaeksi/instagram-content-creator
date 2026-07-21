# LightReel-lite — Instagram Araştırma Özellikleri (Yapılan İşler)

> **Tarih:** 2026-07-21
> **Not:** Bu çalışma ilk olarak yanlışlıkla `c:\Users\sefa9\Desktop\vibin\contentcreator` klasöründe yapıldı.
> **✅ GÜNCELLEME (2026-07-21):** Özellikler bu projeye (`instagramcontentcreator(gmail)`) **port edildi** — detaylar için aşağıdaki "Bu Projeye Entegrasyon" bölümüne bak. Aşağıdaki ilk bölümler orijinal (FastAPI/Groq) çalışmayı anlatır.

---

## Amaç

[lightreel.ai](https://lightreel.ai) (AI destekli UGC/trend araştırma platformu — TikTok/Reels tarayıp creator bulma, trend/hook analizi, video geri bildirimi) fikrinin **Instagram'a özel, sadeleştirilmiş bir versiyonunu** mevcut Groq tabanlı içerik üretici projeye eklemek.

Kullanıcıyla netleştirilen kapsam:
- Sadece **Instagram**, `instaloader` ile (TikTok / Graph API / tarayıcı otomasyonu **yok**).
- **Creator keşfi**: hashtag tarayıp, o hashtag altında paylaşım yapan hesapları takipçi filtresine göre listeleme.
- **Trend/hook sohbeti**: kullanıcının sorusunu, gerçek hashtag tarama verisiyle besleyip LLM'e cevaplatma.
- **Script/performans analizi**: gerçek video işleme **yok** — script metni + performans notları yapıştırılır, LLM LightReel tarzı geri bildirim verir.

---

## Yapılan Değişiklikler

### 1. Yeni modül: `instagram_scraper.py`

Instaloader tabanlı **senkron** tarama motoru. Tüm async/threading `main.py` tarafında.

- **Public fonksiyonlar:**
  - `scan_hashtag(hashtag, max_posts=30)` → post listesi (shortcode, owner, caption [300 char kırpılmış], likes, comments, is_video, video_view_count, date, hashtags)
  - `get_profile_stats(username)` → profil (username, full_name, followers, mediacount, is_verified, is_private, biography)
  - `discover_creators(hashtag, max_posts, min_followers, max_followers)` → hashtag tarar, tekil hesapları (max ~15) profil bakışıyla filtreler
- **Cache:** modül içi `dict` + TTL (hashtag 15 dk, profil 60 dk) — Instagram'a tekrar tekrar vurmayı önler.
- **Session/login:** `IG_USERNAME`/`IG_PASSWORD` env'de varsa session dosyası (`.ig_session_<username>`) oluşturur/yeniden kullanır; yoksa anonim erişim.
- **Hata normalizasyonu:** tüm Instaloader hataları tek bir `ScraperError(kind=...)`'a map'lenir → `rate_limited`, `not_found`, `private`, `login_required`, `unknown`.
- **Kritik ayar:** `max_connection_attempts=1`, `request_timeout=15.0` — Instagram 429 döndüğünde Instaloader'ın varsayılan **30 dakikalık bekleme** davranışı yerine ~1.6 saniyede dostça hata döner (sunucuyu kilitlemez).

### 2. `main.py` — 3 yeni endpoint

Mevcut `groq_stream` + Türkçe prompt deseni korunarak eklendi. Scraping çağrıları `asyncio.to_thread` ile event loop'u bloklamıyor.

| Endpoint | Tip | Açıklama |
|---|---|---|
| `POST /api/discover-creators` | JSON | Creator listesi + LLM sıralama/özet döner |
| `POST /api/trend-chat` | Streaming | Gerçek hashtag verisiyle beslenen sohbet |
| `POST /api/analyze-script` | Streaming | Script/caption performans geri bildirimi (scraping yok) |

- `ScraperError` yakalanıp kullanıcıya dostça Türkçe mesajla `HTTPException(502)` döner (`_SCRAPER_ERROR_MESSAGES` sözlüğü).
- Yeni Pydantic modelleri: `DiscoverCreatorsRequest`, `TrendChatRequest`, `AnalyzeScriptRequest`.

### 3. Frontend: `static/index.html`

- `streamTo()` fonksiyonu, parametrik result/actions alanı destekleyecek şekilde genelleştirildi (geriye dönük uyumlu).
- Mevcut görsel dille 3 yeni kart eklendi: **Creator Keşfi**, **Trend & Hook Sohbeti**, **Script Performans Analizi**.
- Creator keşfi JSON döndüğü için ayrı `discoverCreators()` fonksiyonu (liste + özet render).

### 4. Config: `.env.example`

- `IG_USERNAME` / `IG_PASSWORD` eklendi (opsiyonel — boşsa anonim erişim).
- Yanlış `ANTHROPIC_API_KEY` satırı `GROQ_API_KEY` olarak düzeltildi.

---

## Test Sonuçları

- ✅ `/api/analyze-script` — **tam çalışıyor**, gerçek Groq analizi dönüyor (scraping gerektirmez).
- ⚠️ `/api/trend-chat` ve `/api/discover-creators` — kod uçtan uca doğru; ama **Instagram artık anonim hashtag/profil erişimini engelliyor** (`login_required` / `429`). Sunucu çökmeden dostça hata dönüyor.

---

## Önemli Notlar / Sonraki Adımlar

1. **Gerçek veri için Instagram girişi şart:** Trend sohbeti ve creator keşfinin gerçek veri çekebilmesi için `.env` dosyasına bir Instagram hesabının `IG_USERNAME`/`IG_PASSWORD`'ü girilmeli. Instagram anonim erişimi kapattı.
2. **Ban riski:** Gerçek hesapla login, o hesap için checkpoint/challenge riski taşır. Ana hesap yerine **ikincil/test hesabı** kullanılması önerilir.
3. **API anahtarı güvenliği:** Projedeki `.env` dosyasında canlı bir Groq API anahtarı var — git'e / paylaşıma çıkarken `.gitignore` ile korunduğundan emin ol.
4. **Kod taşıma:** ✅ Tamamlandı — aşağıdaki bölüme bak.

---

## Bu Projeye Entegrasyon (2026-07-21)

Doğrudan kopyalama mümkün değildi: kaynak proje **FastAPI + Groq + streaming**, bu proje ise
**Flask + Gemini + JSON** üzerine kurulu. Prompt'lar ve akış korunarak yeniden yazıldı.

### Eklenen / değişen dosyalar

| Dosya | Durum | Açıklama |
|---|---|---|
| `dashboard/instagram_scraper.py` | **yeni** | Kaynaktan olduğu gibi kopyalandı (framework'ten bağımsız) |
| `dashboard/research.py` | **yeni** | Groq/streaming yerine Gemini + JSON. `advisor.py`'nin desenini izler (model fallback zinciri, ```json fence temizliği, Türkçe prompt) |
| `dashboard/app.py` | güncellendi | 3 yeni route |
| `dashboard/templates/index.html` | güncellendi | Yeni "🛰️ Araştırma" sekmesi (CSS + markup + JS) |
| `requirements.txt`, `dashboard/requirements.txt` | güncellendi | `instaloader>=4.11` |
| `.env.example` | güncellendi | `IG_USERNAME` / `IG_PASSWORD` + uyarı notu |
| `.gitignore` | güncellendi | `.ig_session_*` (login cookie'si — asla commit edilmemeli) |

### Endpoint'ler (FastAPI karşılıkları → Flask)

| Yeni endpoint | Karşılığı | Döndürdüğü |
|---|---|---|
| `POST /api/research/discover` | `/api/discover-creators` | `{summary, creators[]}` — LLM değerlendirmesi gerçek profil verisiyle **birleştirilir**, istatistikler her zaman scraper'dan gelir (LLM uydurmasın diye) |
| `POST /api/research/trend-chat` | `/api/trend-chat` | `{answer, observations[], hooks[], post_count, top_posts[]}` |
| `POST /api/research/analyze-script` | `/api/analyze-script` | `{score, overall, hook_analysis, weak_points[], improvements[], alternative_hook}` |

Streaming yerine yapılandırılmış JSON tercih edildi — dashboard'un mevcut
`fetch → json.ok → render` deseni bu şekilde korunuyor.

### Arayüz

Sidebar'a **🛰️ Araştırma** sekmesi eklendi; içinde 3 kart: Creator Keşfi, Trend & Hook Sohbeti,
Script Performans Analizi. Mevcut sınıflar (`explore-box`, `rule-list`, `error-box`, `analysis-text`)
yeniden kullanıldı. Ortak bir `runResearch()` yardımcısı loading/error/buton durumunu yönetiyor.
Script analizi için 0-100 puan göstergesi var.

**Güvenlik:** Instagram caption'ları ve LLM çıktısı `innerHTML`'e basıldığı için `escHtml()`
ile escape ediliyor (projede daha önce ortak bir escape yardımcısı yoktu).

### Test sonuçları (canlı sunucuda doğrulandı)

- ✅ `/api/research/analyze-script` — **tam çalışıyor**, gerçek Gemini analizi döndü (puan, zayıf noktalar, alternatif hook). `content-creator.md` bağlamını da kullanıyor.
- ✅ Doğrulama: boş hashtag/script → `400`; auth'suz istek → `401`; dashboard sayfası → `200`.
- ✅ Sekme HTML'de doğru render oluyor, sunucu logunda hata yok.
- ⚠️ `/api/research/discover` ve `/api/research/trend-chat` — kod uçtan uca doğru, ama Instagram anonim erişimi engellediği için `502` + dostça Türkçe mesaj dönüyor (sunucu çökmüyor, hızlı yanıt veriyor). **Gerçek veri için `.env`'e `IG_USERNAME`/`IG_PASSWORD` girilmeli.**

### Vercel notu

`vercel.json` tüm istekleri `api/index.py`'ye yönlendiriyor. Araştırma sekmesi lokalde
(`dashboard/start.bat`) sorunsuz çalışır; Vercel'de kullanılacaksa instaloader'ın serverless
ortamda oturum dosyası yazamayacağı ve IP'nin Instagram tarafından hızla limitleneceği unutulmamalı
— bu özellik lokal kullanım için daha uygun.
