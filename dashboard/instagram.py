import os
import requests
from datetime import datetime, timedelta

GRAPH = "https://graph.facebook.com/v21.0"


class InstagramAPI:
    def __init__(self):
        self.token   = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.user_id = os.getenv("INSTAGRAM_USER_ID")
        if not self.token or not self.user_id:
            raise RuntimeError("INSTAGRAM_ACCESS_TOKEN ve INSTAGRAM_USER_ID .env dosyasinda olmali.")

    def _get(self, path, **params):
        params["access_token"] = self.token
        r = requests.get(f"{GRAPH}/{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    # ── Account ──────────────────────────────────────────────────────────────

    def get_account(self):
        return self._get(
            self.user_id,
            fields="id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website",
        )

    # ── Account-level insights ────────────────────────────────────────────────

    def get_account_insights(self, days=28):
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        until = int(datetime.now().timestamp())
        result = {}
        # time-series metrics
        try:
            data = self._get(
                f"{self.user_id}/insights",
                metric="reach",
                period="day",
                since=since,
                until=until,
            )
            for item in data.get("data", []):
                result[item["name"]] = item.get("values", [])
        except Exception:
            pass
        # total_value metrics (new API format)
        try:
            data = self._get(
                f"{self.user_id}/insights",
                metric="profile_views,accounts_engaged,total_interactions",
                metric_type="total_value",
                period="day",
                since=since,
                until=until,
            )
            for item in data.get("data", []):
                result[item["name"]] = item.get("total_value", {}).get("value", 0)
        except Exception:
            pass
        return result

    def get_follower_count_history(self, days=30):
        """Returns [{date, value}] for follower_count over last N days."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        until = int(datetime.now().timestamp())
        try:
            data = self._get(
                f"{self.user_id}/insights",
                metric="follower_count",
                period="day",
                since=since,
                until=until,
            )
            for item in data.get("data", []):
                if item["name"] == "follower_count":
                    return [
                        {"date": v["end_time"][:10], "value": v["value"]}
                        for v in item.get("values", [])
                    ]
        except Exception:
            pass
        return []

    def get_online_followers(self):
        """Returns hourly online follower data for best post time."""
        try:
            data = self._get(
                f"{self.user_id}/insights",
                metric="online_followers",
                period="lifetime",
            )
            for item in data.get("data", []):
                if item["name"] == "online_followers":
                    return item.get("values", [{}])[0].get("value", {})
        except Exception:
            pass
        return {}

    def get_audience_demographics(self):
        try:
            result = {}
            for metric in ("audience_gender_age", "audience_city", "audience_country"):
                data = self._get(
                    f"{self.user_id}/insights",
                    metric=metric,
                    period="lifetime",
                )
                for item in data.get("data", []):
                    if item["name"] == metric:
                        result[metric] = item.get("values", [{}])[0].get("value", {})
            return result
        except Exception:
            return {}

    # ── Media ─────────────────────────────────────────────────────────────────

    def get_media(self, limit=20):
        data = self._get(
            f"{self.user_id}/media",
            fields="id,media_type,timestamp,like_count,comments_count,media_url,thumbnail_url,caption,permalink",
            limit=limit,
        )
        posts = data.get("data", [])
        # attach insights to each post
        for post in posts:
            post["insights"] = self.get_media_insights(post["id"], post.get("media_type", "IMAGE"))
        return posts

    def get_media_insights(self, media_id, media_type="IMAGE"):
        base    = "reach,likes,comments,shares,saved"
        metrics = base + ",views" if media_type in ("VIDEO", "REEL") else base
        try:
            data = self._get(f"{media_id}/insights", metric=metrics)
            return {
                item["name"]: item.get("values", [{}])[0].get("value", item.get("value", 0))
                for item in data.get("data", [])
            }
        except Exception:
            # fallback without views
            try:
                data = self._get(f"{media_id}/insights", metric=base)
                return {
                    item["name"]: item.get("values", [{}])[0].get("value", item.get("value", 0))
                    for item in data.get("data", [])
                }
            except Exception:
                return {}

    # ── Aggregate helpers ────────────────────────────────────────────────────

    def get_summary(self):
        """Single call that returns everything the dashboard needs."""
        account  = self.get_account()
        posts    = self.get_media(limit=20)
        insights = self.get_account_insights(days=28)
        growth   = self.get_follower_count_history(days=30)
        online   = self.get_online_followers()

        # compute per-post engagement rate
        followers = account.get("followers_count", 1) or 1
        for post in posts:
            ins = post.get("insights", {})
            eng = ins.get("likes", 0) + ins.get("comments", 0) + ins.get("saves", post.get("saved", 0))
            post["engagement_rate"] = round(eng / followers * 100, 2)

        # best content type
        type_stats = {}
        for post in posts:
            t = post.get("media_type", "IMAGE")
            ins = post.get("insights", {})
            eng = post.get("engagement_rate", 0)
            if t not in type_stats:
                type_stats[t] = {"count": 0, "total_eng": 0, "total_reach": 0}
            type_stats[t]["count"]      += 1
            type_stats[t]["total_eng"]  += eng
            type_stats[t]["total_reach"] += ins.get("reach", 0)
        for t in type_stats:
            c = type_stats[t]["count"] or 1
            type_stats[t]["avg_eng"]   = round(type_stats[t]["total_eng"]  / c, 2)
            type_stats[t]["avg_reach"] = round(type_stats[t]["total_reach"] / c)

        # reach is time-series, others are total_value scalars
        total_reach = sum(v["value"] for v in insights.get("reach", []))
        total_pv    = insights.get("profile_views", 0)
        total_eng   = insights.get("accounts_engaged", 0)
        total_inter = max(insights.get("total_interactions", 0), 0)

        return {
            "account":           account,
            "posts":             posts,
            "growth":            growth,
            "online_hours":      online,
            "type_stats":        type_stats,
            "reach_28d":         total_reach,
            "accounts_engaged":  total_eng,
            "total_interactions": total_inter,
            "profile_views_28d": total_pv,
        }
