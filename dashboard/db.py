import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "growth.db"

# ── Backend detection ─────────────────────────────────────────────────────────
# Use Upstash Redis (Vercel KV) when env vars present, otherwise SQLite.

def _use_kv():
    return bool(os.getenv("KV_REST_API_URL") and os.getenv("KV_REST_API_TOKEN"))


# ── Upstash REST helpers ──────────────────────────────────────────────────────

def _kv_get(key: str):
    import urllib.request
    url   = os.getenv("KV_REST_API_URL").rstrip("/") + f"/get/{key}"
    token = os.getenv("KV_REST_API_TOKEN")
    req   = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        body = json.loads(r.read())
    return body.get("result")  # None if key missing


def _kv_set(key: str, value):
    import urllib.request
    url   = os.getenv("KV_REST_API_URL").rstrip("/") + f"/set/{key}"
    token = os.getenv("KV_REST_API_TOKEN")
    data  = json.dumps(value).encode()
    req   = urllib.request.Request(url, data=data, method="POST",
                                   headers={"Authorization": f"Bearer {token}",
                                            "Content-Type": "application/json"})
    with urllib.request.urlopen(req):
        pass


# ── SQLite helpers ────────────────────────────────────────────────────────────

def _conn():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db():
    if _use_kv():
        return
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date             TEXT UNIQUE,
                followers        INTEGER,
                following        INTEGER,
                media_count      INTEGER,
                reach_28d        INTEGER,
                impressions_28d  INTEGER,
                profile_views_28d INTEGER,
                avg_engagement   REAL,
                top_format       TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS post_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                saved_at      TEXT,
                media_id      TEXT,
                media_type    TEXT,
                timestamp     TEXT,
                likes         INTEGER,
                comments      INTEGER,
                saves         INTEGER,
                reach         INTEGER,
                impressions   INTEGER,
                shares        INTEGER,
                plays         INTEGER,
                engagement_rate REAL,
                caption_excerpt TEXT
            )
        """)


# ── Public API ────────────────────────────────────────────────────────────────

def save_snapshot(data: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    acc   = data.get("account", {})
    posts = data.get("posts", [])

    avg_eng    = round(sum(p.get("engagement_rate", 0) for p in posts) / len(posts), 2) if posts else 0.0
    type_stats = data.get("type_stats", {})
    top_format = max(type_stats, key=lambda t: type_stats[t].get("avg_eng", 0)) if type_stats else ""

    row = {
        "date":              today,
        "followers":         acc.get("followers_count", 0),
        "following":         acc.get("follows_count", 0),
        "media_count":       acc.get("media_count", 0),
        "reach_28d":         data.get("reach_28d", 0),
        "impressions_28d":   data.get("impressions_28d", 0),
        "profile_views_28d": data.get("profile_views_28d", 0),
        "avg_engagement":    avg_eng,
        "top_format":        top_format,
    }

    if _use_kv():
        # Store list under key "snapshots"
        raw       = _kv_get("snapshots")
        snapshots = json.loads(raw) if raw else []
        snapshots = [s for s in snapshots if s.get("date") != today]
        snapshots.append(row)
        snapshots = sorted(snapshots, key=lambda s: s["date"])[-90:]  # keep last 90 days
        _kv_set("snapshots", json.dumps(snapshots))
    else:
        with _conn() as con:
            con.execute("""
                INSERT INTO snapshots
                    (date, followers, following, media_count, reach_28d, impressions_28d, profile_views_28d, avg_engagement, top_format)
                VALUES (:date,:followers,:following,:media_count,:reach_28d,:impressions_28d,:profile_views_28d,:avg_engagement,:top_format)
                ON CONFLICT(date) DO UPDATE SET
                    followers        = excluded.followers,
                    following        = excluded.following,
                    media_count      = excluded.media_count,
                    reach_28d        = excluded.reach_28d,
                    impressions_28d  = excluded.impressions_28d,
                    profile_views_28d= excluded.profile_views_28d,
                    avg_engagement   = excluded.avg_engagement,
                    top_format       = excluded.top_format
            """, row)

            saved_at = datetime.now().isoformat()
            for post in posts:
                ins = post.get("insights", {})
                con.execute("""
                    INSERT OR IGNORE INTO post_snapshots
                        (saved_at, media_id, media_type, timestamp, likes, comments, saves,
                         reach, impressions, shares, plays, engagement_rate, caption_excerpt)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    saved_at,
                    post.get("id", ""),
                    post.get("media_type", ""),
                    post.get("timestamp", ""),
                    ins.get("likes", post.get("like_count", 0)),
                    ins.get("comments", post.get("comments_count", 0)),
                    ins.get("saved", ins.get("saves", 0)),
                    ins.get("reach", 0),
                    ins.get("impressions", 0),
                    ins.get("shares", 0),
                    ins.get("plays", ins.get("video_views", 0)),
                    post.get("engagement_rate", 0),
                    (post.get("caption") or "")[:120],
                ))


def get_growth_history(days=60):
    if _use_kv():
        raw       = _kv_get("snapshots")
        snapshots = json.loads(raw) if raw else []
        return sorted(snapshots, key=lambda s: s["date"])[-days:]
    with _conn() as con:
        rows = con.execute("""
            SELECT date, followers, avg_engagement, reach_28d, top_format
            FROM snapshots ORDER BY date DESC LIMIT ?
        """, (days,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_weekly_delta():
    history = get_growth_history(days=8)
    if len(history) < 2:
        return 0
    return history[-1]["followers"] - history[0]["followers"]


init_db()
