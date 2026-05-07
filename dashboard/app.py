import sys
import json
import time
import io
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from instagram import InstagramAPI
from db       import save_snapshot, get_growth_history, get_weekly_delta
from advisor     import analyze
from explore     import generate_explore_plan
from pdf_export  import build_advisor_pdf, build_explore_pdf

app = Flask(__name__)

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


@app.route("/api/explore", methods=["POST"])
def api_explore():
    try:
        ig      = InstagramAPI()
        summary = _cached("summary", ig.get_summary)
        result  = generate_explore_plan(summary)
        return jsonify({"ok": True, "result": result})
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


if __name__ == "__main__":
    app.run(debug=True, port=5050)
