import os
import time
import logging

import instaloader
from instaloader.exceptions import (
    ConnectionException,
    TooManyRequestsException,
    LoginRequiredException,
    BadCredentialsException,
    ProfileNotExistsException,
    QueryReturnedNotFoundException,
    PrivateProfileNotFollowedException,
)

logger = logging.getLogger("instagram_scraper")

MAX_POSTS_CAP = 50
MAX_UNIQUE_PROFILES_CAP = 15
HASHTAG_CACHE_TTL = 15 * 60
PROFILE_CACHE_TTL = 60 * 60

SESSION_FILE_TEMPLATE = ".ig_session_{username}"


class ScraperError(Exception):
    """Raised for any Instagram scraping failure the caller should show to the user."""

    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind


_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if time.time() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value, ttl: float):
    _cache[key] = (time.time() + ttl, value)


_loader_instance: instaloader.Instaloader | None = None


def _get_loader() -> instaloader.Instaloader:
    global _loader_instance
    if _loader_instance is not None:
        return _loader_instance

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
        max_connection_attempts=1,
        request_timeout=15.0,
    )

    username = os.getenv("IG_USERNAME", "").strip()
    password = os.getenv("IG_PASSWORD", "").strip()

    if username:
        session_file = SESSION_FILE_TEMPLATE.format(username=username)
        try:
            if os.path.exists(session_file):
                loader.load_session_from_file(username, filename=session_file)
            elif password:
                loader.login(username, password)
                loader.save_session_to_file(filename=session_file)
        except Exception as e:
            logger.warning("Instagram login/session yüklenemedi, anonim moda düşülüyor: %s", e)

    _loader_instance = loader
    return _loader_instance


def _normalize_error(e: Exception) -> ScraperError:
    if isinstance(e, TooManyRequestsException):
        return ScraperError("Instagram çok fazla istek nedeniyle engelledi.", kind="rate_limited")
    if isinstance(e, (ProfileNotExistsException, QueryReturnedNotFoundException)):
        return ScraperError("Bulunamadı.", kind="not_found")
    if isinstance(e, (LoginRequiredException, BadCredentialsException)):
        return ScraperError("Bu veri için Instagram girişi gerekiyor.", kind="login_required")
    if isinstance(e, PrivateProfileNotFollowedException):
        return ScraperError("Bu hesap gizli.", kind="private")
    if isinstance(e, ConnectionException):
        msg = str(e).lower()
        if "login_required" in msg or "checkpoint_required" in msg:
            return ScraperError("Bu veri için Instagram girişi gerekiyor.", kind="login_required")
        if "429" in msg or "rate" in msg or "please wait" in msg:
            return ScraperError("Instagram çok fazla istek nedeniyle engelledi.", kind="rate_limited")
        return ScraperError(f"Bağlantı hatası: {e}", kind="unknown")
    return ScraperError(f"Beklenmeyen hata: {e}", kind="unknown")


def _extract_post(post: instaloader.Post) -> dict:
    caption = (post.caption or "").strip()
    if len(caption) > 300:
        caption = caption[:300] + "…"
    hashtags = list(post.caption_hashtags)[:15]
    return {
        "shortcode": post.shortcode,
        "owner_username": post.owner_username,
        "caption": caption,
        "likes": post.likes,
        "comments": post.comments,
        "is_video": post.is_video,
        "video_view_count": post.video_view_count if post.is_video else None,
        "date": post.date_utc.isoformat(),
        "hashtags": hashtags,
    }


def _extract_profile(profile: instaloader.Profile) -> dict:
    bio = (profile.biography or "").strip()
    if len(bio) > 300:
        bio = bio[:300] + "…"
    return {
        "username": profile.username,
        "full_name": profile.full_name,
        "followers": profile.followers,
        "mediacount": profile.mediacount,
        "is_verified": profile.is_verified,
        "is_private": profile.is_private,
        "biography": bio,
    }


def scan_hashtag(hashtag: str, max_posts: int = 30) -> list[dict]:
    hashtag = hashtag.strip().lstrip("#")
    max_posts = min(max_posts, MAX_POSTS_CAP)
    cache_key = f"hashtag:{hashtag}:{max_posts}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    loader = _get_loader()
    try:
        ig_hashtag = instaloader.Hashtag.from_name(loader.context, hashtag)
        posts = []
        for i, post in enumerate(ig_hashtag.get_posts()):
            if i >= max_posts:
                break
            posts.append(_extract_post(post))
            if i % 10 == 9:
                time.sleep(1)
    except ScraperError:
        raise
    except Exception as e:
        raise _normalize_error(e)

    _cache_set(cache_key, posts, HASHTAG_CACHE_TTL)
    return posts


def get_profile_stats(username: str) -> dict:
    username = username.strip().lstrip("@")
    cache_key = f"profile:{username}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    loader = _get_loader()
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        data = _extract_profile(profile)
    except ScraperError:
        raise
    except Exception as e:
        raise _normalize_error(e)

    _cache_set(cache_key, data, PROFILE_CACHE_TTL)
    return data


def discover_creators(
    hashtag: str,
    max_posts: int = 30,
    min_followers: int = 0,
    max_followers: int | None = None,
) -> list[dict]:
    posts = scan_hashtag(hashtag, max_posts)

    seen_order: list[str] = []
    for post in posts:
        owner = post["owner_username"]
        if owner not in seen_order:
            seen_order.append(owner)
        if len(seen_order) >= MAX_UNIQUE_PROFILES_CAP:
            break

    creators = []
    for username in seen_order:
        try:
            profile = get_profile_stats(username)
        except ScraperError as e:
            logger.info("Profil atlandı (%s): %s", username, e)
            continue

        if profile["followers"] < min_followers:
            continue
        if max_followers and profile["followers"] > max_followers:
            continue

        creators.append(profile)

    return creators
