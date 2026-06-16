#!/usr/bin/env python3
"""
app.py — Flask front end for the DD feasibility automation.

Shared-password auth (APP_PASSWORD), one job store, two run modes (single
address / multi-APN assemblage). Run with a SINGLE gunicorn worker so the
in-memory job store is shared across requests:

  gunicorn web.app:app --workers 1 --threads 8 --timeout 300 --bind 0.0.0.0:$PORT

Local dev:  python -m web.app
"""
import os
import functools

from flask import (
    Flask, request, session, redirect, url_for, render_template, jsonify,
    send_file, abort,
)

from web import jobs

app = Flask(__name__)

# SECRET_KEY signs the session cookie. Set a stable value in Railway so sessions
# survive restarts; the dev fallback is per-process (logs everyone out on reboot).
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
APP_PASSWORD = os.environ.get("APP_PASSWORD", "sola-dev")
if APP_PASSWORD == "sola-dev":
    app.logger.warning("APP_PASSWORD not set — using insecure default 'sola-dev'. "
                       "Set APP_PASSWORD (and SECRET_KEY) before sharing this URL.")

# Cap how much work one request can kick off.
MAX_APNS = 25
# Reject oversized uploads before buffering (OM PDFs go via the Files API). Aligns
# with om_extract's cap (OM_MAX_MB, default 150) + headroom for multipart overhead.
_OM_MAX_MB = int(os.environ.get("OM_MAX_MB", "150"))
app.config["MAX_CONTENT_LENGTH"] = (_OM_MAX_MB + 10) * 1024 * 1024


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": f"Upload too large (max ~{_OM_MAX_MB} MB). Compress the OM PDF and retry."}), 413


# ModularZ (AI proforma/underwriting tool) talks to Google Gemini straight from
# the browser, so the key is necessarily client-side. We inject it from an env
# var rather than hard-coding it in the template; the fallback is the key the
# prototype shipped with. SECURITY: that fallback key is exposed in page source —
# rotate it and set GEMINI_API_KEY in Railway, then drop the fallback.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        if not session.get("authed"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return wrapper


@app.get("/login")
def login():
    if session.get("authed"):
        return redirect(url_for("index"))
    return render_template("login.html", error=None)


@app.post("/login")
def do_login():
    if request.form.get("password", "") == APP_PASSWORD:
        session["authed"] = True
        session.permanent = True
        dest = request.args.get("next") or url_for("index")
        return redirect(dest if dest.startswith("/") else url_for("index"))
    return render_template("login.html", error="Incorrect password."), 401


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("index.html", sections=jobs.SECTIONS, sources=jobs.SOURCE_CATALOG)


@app.get("/modularz")
@login_required
def modularz():
    # Unified ModularZ tool (Dashboard look + Gemini backend). Self-contained
    # page; only the Gemini key is templated in.
    return render_template("modularz.html", gemini_key=GEMINI_API_KEY)


@app.post("/api/run")
@login_required
def api_run():
    # Single-address runs may arrive as multipart (with an OM PDF) or JSON.
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        mode = request.form.get("mode")
        data = request.form
        om_file = request.files.get("om")
    else:
        data = request.get_json(silent=True) or {}
        mode = data.get("mode")
        om_file = None

    if mode == "single":
        address = (data.get("address") or "").strip()
        payload = {"address": address}
        if om_file and om_file.filename:
            om_bytes = om_file.read()
            if not om_bytes:
                return jsonify({"error": "The uploaded OM is empty."}), 400
            payload["om_bytes"] = om_bytes
            payload["om_name"] = om_file.filename
        elif not address:
            return jsonify({"error": "Enter an address or upload an OM."}), 400
        jid = jobs.create_job("single", payload)
        return jsonify({"job_id": jid})
    if mode == "assemblage":
        raw = data.get("apns") or ""
        apns = [a.strip() for a in raw.replace(",", "\n").splitlines() if a.strip()]
        if not apns:
            return jsonify({"error": "At least one APN is required."}), 400
        if len(apns) > MAX_APNS:
            return jsonify({"error": f"Too many APNs (max {MAX_APNS})."}), 400
        jid = jobs.create_job("assemblage", {"apns": apns})
        return jsonify({"job_id": jid})
    return jsonify({"error": "Unknown mode."}), 400


@app.get("/api/stats")
@login_required
def api_stats():
    return jsonify(jobs.stats())


@app.get("/api/recent")
@login_required
def api_recent():
    return jsonify({"runs": jobs.recent_jobs(10)})


@app.get("/api/job/<jid>")
@login_required
def api_job(jid):
    job = jobs.get_job(jid)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(jobs.public_view(job))


@app.get("/api/download/<jid>")
@login_required
def api_download(jid):
    job = jobs.get_job(jid)
    if not job or not job.get("file"):
        abort(404)
    return send_file(job["file"], as_attachment=True,
                     download_name=job.get("filename") or "checklist.xlsx")


@app.get("/healthz")
def healthz():
    # Plain 200 for uptime monitors (UptimeRobot, Railway healthcheck, etc.).
    return "ok", 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=True)
