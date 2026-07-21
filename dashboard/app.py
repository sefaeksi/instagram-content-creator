import sys
import json
import time
import io
import os
import functools
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file, Response
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from instagram import InstagramAPI
from db       import save_snapshot, get_growth_history, get_weekly_delta
from advisor     import analyze, generate_reel_ideas
from explore     import generate_explore_plan
from pdf_export  import build_advisor_pdf, build_explore_pdf
import instagram_scraper
import research

app = Flask(__name__)


def _check_auth(username, password):
    correct_user = os.getenv("DASHBOARD_USER", "admin")
    correct_pass = os.getenv("DASHBOARD_PASS", "")
    return username == correct_user and password == correct_pass and correct_pass != ""


def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_auth(auth.username, auth.password):
            return Response(
                "Giris yapmaniz gerekiyor.",
                401,
                {"WWW-Authenticate": 'Basic realm="Instagram Dashboard"'},
            )
        return f(*args, **kwargs)
    return decorated


app.before_request_funcs.setdefault(None, [])


@app.before_request
def protect():
    auth = request.authorization
    if not auth or not _check_auth(auth.username, auth.password):
        return Response(
            "Giris yapmaniz gerekiyor.",
            401,
            {"WWW-Authenticate": 'Basic realm="Instagram Dashboard"'},
        )

# ── Simple in-memory cache (1 hour) ─────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 3600


def _cached(key, fn):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"] < CACHE_TTL):
        return entry["data"]
    data = fn()
    _cache[key] = {"data": data, "ts": time.time()}
    return data


def _invalidate():
    _cache.clear()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    try:
        ig      = InstagramAPI()
        summary = _cached("summary", ig.get_summary)
        save_snapshot(summary)
        delta   = get_weekly_delta()
        growth  = get_growth_history(days=60)
        return jsonify({"ok": True, "summary": summary, "weekly_delta": delta, "growth": growth})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    _invalidate()
    return jsonify({"ok": True})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    try:
        ig      = InstagramAPI()
        summary = _cached("summary", ig.get_summary)
        result  = analyze(summary)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reel-ideas", methods=["POST"])
def api_reel_ideas():
    try:
        body  = request.get_json(force=True)
        topic = (body.get("topic") or "").strip()
        if not topic:
            return jsonify({"ok": False, "error": "Konu boş bırakılamaz"}), 400
        result = generate_reel_ideas(topic)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/explore", methods=["POST"])
def api_explore():
    try:
        ig      = InstagramAPI()
        summary = _cached("summary", ig.get_summary)
        result  = generate_explore_plan(summary)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/explore/saved", methods=["GET"])
def api_explore_saved():
    from db import _kv_get, _use_kv
    try:
        if _use_kv():
            data = _kv_get("explore:current")
            if data and isinstance(data, dict):
                return jsonify({"ok": True, "result": data.get("result"), "saved_at": data.get("saved_at")})
        return jsonify({"ok": True, "result": None})
    except Exception:
        return jsonify({"ok": True, "result": None})


@app.route("/api/explore/save", methods=["POST"])
def api_explore_save():
    from db import _kv_set, _use_kv
    try:
        result = request.get_json(force=True)
        if _use_kv():
            _kv_set("explore:current", {
                "result": result,
                "saved_at": datetime.now().isoformat(),
            })
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/export/advisor", methods=["POST"])
def api_export_advisor():
    try:
        result = request.get_json(force=True)
        pdf    = build_advisor_pdf(result)
        fname  = f"ai-advisor-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                         as_attachment=True, download_name=fname)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/export/explore", methods=["POST"])
def api_export_explore():
    try:
        result = request.get_json(force=True)
        pdf    = build_explore_pdf(result)
        fname  = f"explore-plan-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                         as_attachment=True, download_name=fname)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


import json as _json


# ── Arastirma (LightReel-lite) ────────────────────────────────────────────────

@app.route("/api/research/discover", methods=["POST"])
def api_research_discover():
    body    = request.get_json(force=True) or {}
    hashtag = (body.get("hashtag") or "").strip().lstrip("#")
    if not hashtag:
        return jsonify({"ok": False, "error": "Hashtag gerekli."}), 400
    try:
        result = research.discover_creators(
            hashtag,
            int(body.get("min_followers") or 0),
            int(body.get("max_followers") or 0),
        )
        return jsonify({"ok": True, "result": result})
    except instagram_scraper.ScraperError as e:
        return jsonify({"ok": False, "error": research.scraper_message(e)}), 502
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/research/trend-chat", methods=["POST"])
def api_research_trend_chat():
    body     = request.get_json(force=True) or {}
    question = (body.get("question") or "").strip()
    hashtag  = (body.get("hashtag") or "").strip().lstrip("#")
    if not question or not hashtag:
        return jsonify({"ok": False, "error": "Soru ve hashtag gerekli."}), 400
    try:
        result = research.trend_chat(question, hashtag)
        return jsonify({"ok": True, "result": result})
    except instagram_scraper.ScraperError as e:
        return jsonify({"ok": False, "error": research.scraper_message(e)}), 502
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/research/analyze-script", methods=["POST"])
def api_research_analyze_script():
    body   = request.get_json(force=True) or {}
    script = (body.get("script_text") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "Script metni gerekli."}), 400
    try:
        result = research.analyze_script(script, body.get("performance_notes") or "")
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Solo Leveling helpers ─────────────────────────────────────────────────────

def _solo_get(week_key):
    from db import _kv_get, _use_kv
    if _use_kv():
        raw = _kv_get(f"solo:{week_key}")
        return raw if isinstance(raw, dict) else {}
    return _solo_sqlite_get(week_key)


def _solo_save(week_key, data):
    from db import _kv_set, _kv_get, _use_kv
    if _use_kv():
        _kv_set(f"solo:{week_key}", data)
        index = _kv_get("solo:index") or []
        if not isinstance(index, list):
            index = []
        if week_key not in index:
            index.append(week_key)
            _kv_set("solo:index", index)
    else:
        _solo_sqlite_save(week_key, data)


def _solo_sqlite_get(week_key):
    from db import _conn
    try:
        with _conn() as con:
            con.execute("CREATE TABLE IF NOT EXISTS solo_weeks (week_key TEXT PRIMARY KEY, data TEXT)")
            row = con.execute("SELECT data FROM solo_weeks WHERE week_key=?", (week_key,)).fetchone()
            return _json.loads(row["data"]) if row else {}
    except Exception:
        return {}


def _solo_sqlite_save(week_key, data):
    from db import _conn
    with _conn() as con:
        con.execute("CREATE TABLE IF NOT EXISTS solo_weeks (week_key TEXT PRIMARY KEY, data TEXT)")
        con.execute("INSERT INTO solo_weeks(week_key,data) VALUES(?,?) ON CONFLICT(week_key) DO UPDATE SET data=excluded.data",
                    (week_key, _json.dumps(data)))


def _solo_sqlite_history():
    from db import _conn
    try:
        with _conn() as con:
            con.execute("CREATE TABLE IF NOT EXISTS solo_weeks (week_key TEXT PRIMARY KEY, data TEXT)")
            rows = con.execute("SELECT week_key, data FROM solo_weeks ORDER BY week_key").fetchall()
            return [{"key": r["week_key"], "data": _json.loads(r["data"])} for r in rows]
    except Exception:
        return []


# ── Solo Leveling routes ──────────────────────────────────────────────────────

@app.route("/api/solo/history", methods=["GET"])
def api_solo_history():
    from db import _kv_get, _use_kv
    try:
        if _use_kv():
            index = _kv_get("solo:index") or []
            if not isinstance(index, list):
                index = []
            weeks = []
            for k in sorted(index)[-12:]:
                d = _kv_get(f"solo:{k}")
                weeks.append({"key": k, "data": d if isinstance(d, dict) else {}})
        else:
            weeks = _solo_sqlite_history()
        return jsonify({"ok": True, "weeks": weeks})
    except Exception:
        return jsonify({"ok": True, "weeks": []})


@app.route("/api/solo/<week_key>", methods=["GET"])
def api_solo_get(week_key):
    try:
        return jsonify({"ok": True, "data": _solo_get(week_key)})
    except Exception:
        return jsonify({"ok": True, "data": {}})


@app.route("/api/solo/<week_key>", methods=["POST"])
def api_solo_save_route(week_key):
    try:
        data = request.get_json(force=True)
        _solo_save(week_key, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5050)
