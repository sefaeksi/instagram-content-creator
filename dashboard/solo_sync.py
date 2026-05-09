"""
Solo Leveling auto-sync: pulls this week's Instagram posts and stories,
merges them into the KV solo week data without overwriting manual entries.
Run daily via GitHub Actions.
"""
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from instagram import InstagramAPI
from db import _kv_get, _kv_set, _use_kv


# ── Week helpers ──────────────────────────────────────────────────────────────

def week_monday(dt=None):
    d = (dt or datetime.now(timezone.utc)).date()
    return d - timedelta(days=d.weekday())  # Monday


def week_key(dt=None):
    return week_monday(dt).isoformat()


def week_dates(monday_str):
    mon = datetime.fromisoformat(monday_str).date()
    return [(mon + timedelta(days=i)).isoformat() for i in range(7)]


# ── KV helpers ────────────────────────────────────────────────────────────────

def solo_get(key):
    if _use_kv():
        raw = _kv_get(f"solo:{key}")
        return raw if isinstance(raw, dict) else {}
    return {}


def solo_save(key, data):
    if _use_kv():
        _kv_set(f"solo:{key}", data)
        index = _kv_get("solo:index") or []
        if not isinstance(index, list):
            index = []
        if key not in index:
            index.append(key)
            _kv_set("solo:index", index)


# ── Sync logic ────────────────────────────────────────────────────────────────

def sync():
    ig   = InstagramAPI()
    wkey = week_key()
    days = week_dates(wkey)
    data = solo_get(wkey)

    print(f"Syncing week: {wkey}  ({days[0]} → {days[-1]})")

    # Fetch recent media (last 50 to cover full week)
    raw_media = ig._get(
        f"{ig.user_id}/media",
        fields="id,media_type,timestamp,like_count,comments_count,caption,permalink",
        limit=50,
    )
    posts = raw_media.get("data", [])

    # Filter to this week
    week_posts = []
    for p in posts:
        ts = p.get("timestamp", "")
        if not ts:
            continue
        post_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
        if post_date in days:
            p["_date"] = post_date
            week_posts.append(p)

    print(f"  Found {len(week_posts)} posts this week")

    # ── Reels ────────────────────────────────────────────────────────────────
    reels_from_api = [p for p in week_posts if p.get("media_type") in ("VIDEO", "REEL")]
    existing_reels = data.get("reels", [])

    # Keep manually added reels that have a note not matching any API post
    api_permalinks = {p.get("permalink", "") for p in reels_from_api}
    manual_reels   = [r for r in existing_reels if r.get("source") != "api"]

    new_reels = []
    for p in reels_from_api:
        caption = (p.get("caption") or "")[:60]
        new_reels.append({
            "source":    "api",
            "status":    "done",
            "note":      caption or "Reel",
            "date":      p["_date"],
            "permalink": p.get("permalink", ""),
            "likes":     p.get("like_count", 0),
            "comments":  p.get("comments_count", 0),
        })

    data["reels"] = new_reels + manual_reels

    # ── Carousels ────────────────────────────────────────────────────────────
    carousels = [p for p in week_posts if p.get("media_type") == "CAROUSEL_ALBUM"]

    # Try to classify as dump vs info based on caption keywords
    dump_keywords  = ["dump", "hafta", "week", "günlük", "daily", "rutin"]
    existing_dump  = data.get("carousel-dump", {})
    existing_info  = data.get("carousel-info", {})

    assigned_dump = False
    assigned_info = False

    for p in carousels:
        cap   = (p.get("caption") or "").lower()
        short = (p.get("caption") or "")[:60]
        entry = {
            "source":    "api",
            "status":    "done",
            "note":      short or "Carousel",
            "date":      p["_date"],
            "permalink": p.get("permalink", ""),
        }
        is_dump = any(k in cap for k in dump_keywords)
        if is_dump and not assigned_dump:
            # only overwrite if not manually set
            if existing_dump.get("source") != "manual":
                data["carousel-dump"] = entry
            assigned_dump = True
        elif not assigned_info:
            if existing_info.get("source") != "manual":
                data["carousel-info"] = entry
            assigned_info = True

    # If only one carousel, put it in dump slot
    if len(carousels) == 1 and not assigned_dump and not assigned_info:
        p     = carousels[0]
        short = (p.get("caption") or "")[:60]
        if existing_dump.get("source") != "manual":
            data["carousel-dump"] = {
                "source": "api", "status": "done",
                "note": short or "Carousel",
                "date": p["_date"], "permalink": p.get("permalink", ""),
            }

    # ── Stories (available for ~24h only) ───────────────────────────────────
    try:
        stories_raw = ig._get(f"{ig.user_id}/stories",
                              fields="id,timestamp,media_type")
        story_posts = stories_raw.get("data", [])
        if not data.get("stories"):
            data["stories"] = {}
        for s in story_posts:
            ts   = s.get("timestamp", "")
            if not ts:
                continue
            sdate = datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
            if sdate in days:
                # only mark done if not already manually set to skip
                if data["stories"].get(sdate) != "skip":
                    data["stories"][sdate] = "done"
        print(f"  Found {len(story_posts)} active stories")
    except Exception as e:
        print(f"  Stories fetch failed (normal if no active stories): {e}")

    data["last_synced"] = datetime.now(timezone.utc).isoformat()

    solo_save(wkey, data)
    print(f"  Saved to KV: solo:{wkey}")
    print(f"  Reels: {len(data['reels'])}  Carousels-dump: {'✓' if data.get('carousel-dump') else '—'}  Carousels-info: {'✓' if data.get('carousel-info') else '—'}")
    print(f"  Stories: {sum(1 for v in (data.get('stories') or {}).values() if v == 'done')} günde done")


if __name__ == "__main__":
    sync()
