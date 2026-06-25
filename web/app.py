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
import hmac
import uuid
import functools

from flask import (
    Flask, request, session, redirect, url_for, render_template, jsonify,
    send_file, abort, g,
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

# Silent run attribution. Each browser/device gets a stable anonymous id stored in
# a long-lived cookie (set transparently below — no UI, no behavior change); the
# connecting IP is recorded as a secondary hint. Runs are stamped with both so the
# admin view can tally usage per device. ADMIN_KEY gates that view; leave it unset
# to disable the admin pages entirely.
DEVICE_COOKIE = "sola_dev"
DEVICE_COOKIE_MAXAGE = 60 * 60 * 24 * 365 * 2          # 2 years
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


def _client_ip():
    # Behind Railway's proxy the real client is the first hop in X-Forwarded-For;
    # request.remote_addr would just be the proxy. Fall back to remote_addr locally.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


@app.before_request
def _identity():
    # Resolve (or mint) this device's anonymous id for the duration of the request.
    did = request.cookies.get(DEVICE_COOKIE)
    g.new_device = not did
    g.device_id = did or uuid.uuid4().hex
    g.client_ip = _client_ip()


@app.after_request
def _set_device_cookie(resp):
    # Persist a freshly minted id so the same browser is recognized next time.
    # Skip health checks (uptime monitors) to keep the device roster clean.
    if getattr(g, "new_device", False) and request.path != "/healthz":
        secure = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"
        resp.set_cookie(DEVICE_COOKIE, g.device_id, max_age=DEVICE_COOKIE_MAXAGE,
                        httponly=True, samesite="Lax", secure=secure)
    return resp


def _actor():
    return {"device": getattr(g, "device_id", ""), "ip": getattr(g, "client_ip", "")}


def _admin_ok():
    """True if the caller has unlocked the admin view. Requires ADMIN_KEY to be set;
    the key is supplied once via /admin?key=… and then carried in the session."""
    if not ADMIN_KEY:
        return False
    if session.get("admin"):
        return True
    key = request.args.get("key") or request.headers.get("X-Admin-Key", "")
    if key and hmac.compare_digest(key, ADMIN_KEY):
        session["admin"] = True
        return True
    return False


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
    jobs.touch_device(_actor())     # register the device even if they only browse
    # Admin-unlock can also be done from the home page via ?key=… (then remembered).
    is_admin = _admin_ok()
    return render_template("index.html", sections=jobs.SECTIONS, sources=jobs.SOURCE_CATALOG,
                           is_admin=is_admin)


@app.get("/modularz")
@login_required
def modularz():
    # Unified ModularZ tool (Dashboard look + Gemini backend). Self-contained
    # page; only the Gemini key is templated in.
    return render_template("modularz.html", gemini_key=GEMINI_API_KEY)


@app.get("/modularz/v28")
@login_required
def modularz_v28():
    """LIHTC v28 underwriting UI — computed server-side by the workbook itself."""
    from web import modularz_calc
    try:
        counties = modularz_calc.counties()
    except Exception:  # noqa: BLE001
        counties = []
    return render_template(
        "modularz_v28.html",
        counties=counties,
        gap_options=modularz_calc.GAP_FINANCING_OPTIONS,
    )


@app.get("/api/modularz/health")
@login_required
def api_modularz_health():
    """Confirms LibreOffice is installed and can recalc the v28 model. Used to
    verify the server-side calc engine after a deploy."""
    try:
        from web import modularz_calc
        return jsonify(modularz_calc.selftest())
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/modularz/research")
@login_required
def api_modularz_research():
    """Resolve a bare address into v28 inputs (county + land estimate) via Gemini."""
    data = request.get_json(silent=True) or {}
    addr = (data.get("address") or "").strip()
    if not addr:
        return jsonify({"ok": False, "error": "Enter an address to research."}), 400
    try:
        from web import modularz_calc
        res = modularz_calc.research_address(addr)
        return jsonify({"ok": True, **res})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/modularz/download")
@login_required
def api_modularz_download():
    """Return the v28 workbook (.xlsm) with the current inputs patched in, set to
    recalc on open in Excel — the underwritten model as a downloadable file."""
    data = request.get_json(silent=True) or {}
    inputs = data.get("inputs") or {}
    try:
        from web import modularz_calc
        num, txt = modularz_calc.split_friendly(inputs)
        blob = modularz_calc.build_download(num, txt)
        name = (inputs.get("project_name") or "LIHTC").strip().replace(" ", "_")[:40] or "LIHTC"
        from flask import Response
        return Response(
            blob,
            mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
            headers={"Content-Disposition": f'attachment; filename="{name}_underwritten_v28.xlsm"'},
        )
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/modularz/extract-om")
@login_required
def api_modularz_extract_om():
    """Extract deal facts from an uploaded OM PDF and map them onto v28 inputs
    (address, acquisition price -> land, lot SF, county)."""
    om = request.files.get("om")
    if not om or not om.filename:
        return jsonify({"ok": False, "error": "No OM file uploaded."}), 400
    try:
        from web import om_extract, modularz_calc
        raw = om_extract.extract(om.read(), om.filename)
        fields = {f["field_id"]: f["value"] for f in raw}
        return jsonify({"ok": True, "inputs": modularz_calc.om_fields_to_inputs(fields), "fields": fields})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/modularz/calc")
@login_required
def api_modularz_calc():
    """Server-side recalculation of the LIHTC v28 workbook via LibreOffice.

    Body: {"inputs": {friendly_name: value, ...}}  (see modularz_calc.INPUT_CELLS)
    Returns: {"outputs": {label: value, ...}}
    """
    data = request.get_json(silent=True) or {}
    inputs = data.get("inputs") or {}
    try:
        from web import modularz_calc
        outputs = modularz_calc.calc_friendly(inputs)
        return jsonify({"ok": True, "outputs": outputs})
    except Exception as e:  # noqa: BLE001 — surface calc failures to the client
        app.logger.exception("modularz calc failed")
        return jsonify({"ok": False, "error": str(e)}), 500


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
        jid = jobs.create_job("single", payload, actor=_actor())
        return jsonify({"job_id": jid})
    if mode == "assemblage":
        raw = data.get("apns") or ""
        apns = [a.strip() for a in raw.replace(",", "\n").splitlines() if a.strip()]
        if not apns:
            return jsonify({"error": "At least one APN is required."}), 400
        if len(apns) > MAX_APNS:
            return jsonify({"error": f"Too many APNs (max {MAX_APNS})."}), 400
        jid = jobs.create_job("assemblage", {"apns": apns}, actor=_actor())
        return jsonify({"job_id": jid})
    if mode == "underwrite":
        # Build the Stick + Modular pro-forma from a completed DD checklist —
        # either an uploaded .xlsx (multipart) or a prior DD run (from_job, JSON).
        payload = {"name": (data.get("name") or "").strip() or None}
        dd_file = request.files.get("dd")
        if dd_file and dd_file.filename:
            dd_bytes = dd_file.read()
            if not dd_bytes:
                return jsonify({"error": "The uploaded checklist is empty."}), 400
            payload["dd_bytes"] = dd_bytes
            payload["dd_name"] = dd_file.filename
        elif data.get("from_job"):
            payload["from_job"] = data.get("from_job")
        else:
            return jsonify({"error": "Upload a DD checklist (.xlsx), or generate from a completed run."}), 400
        # Review/edit step (optional): analyst overrides of the model inputs.
        ov = data.get("overrides")
        if isinstance(ov, str) and ov:
            import json as _json
            try:
                ov = _json.loads(ov)
            except ValueError:
                ov = None
        if isinstance(ov, dict) and ov:
            payload["overrides"] = ov
        jid = jobs.create_job("underwrite", payload, actor=_actor())
        return jsonify({"job_id": jid})
    if mode == "lihtc_scenarios":
        # Generate one .xlsm per selected scenario, zip, return download.
        # Accepts the same source as underwrite (uploaded DD or from_job), plus
        # "scenarios" (list of scenario dicts) and optional "overrides".
        payload = {"name": (data.get("name") or "").strip() or None}
        dd_file = request.files.get("dd") if request.files else None
        if dd_file and dd_file.filename:
            dd_bytes = dd_file.read()
            if not dd_bytes:
                return jsonify({"error": "The uploaded checklist is empty."}), 400
            payload["dd_bytes"] = dd_bytes
            payload["dd_name"] = dd_file.filename
        elif data.get("from_job"):
            payload["from_job"] = data.get("from_job")
        else:
            return jsonify({"error": "Upload a DD checklist (.xlsx), or generate from a completed run."}), 400
        ov = data.get("overrides")
        if isinstance(ov, str) and ov:
            import json as _json
            try:
                ov = _json.loads(ov)
            except ValueError:
                ov = None
        if isinstance(ov, dict) and ov:
            payload["overrides"] = ov
        scns = data.get("scenarios")
        if not scns:
            return jsonify({"error": "No scenarios selected."}), 400
        payload["scenarios"] = scns
        jid = jobs.create_job("lihtc_scenarios", payload, actor=_actor())
        return jsonify({"job_id": jid})
    if mode == "comps":
        address = (data.get("address") or "").strip()
        if not address:
            return jsonify({"error": "Enter the subject address to find rent comps."}), 400
        beds = data.get("beds") or [0, 1, 2]
        if isinstance(beds, str):
            beds = [int(x) for x in beds.replace(",", " ").split() if x.strip().isdigit()]
        jid = jobs.create_job("comps", {"address": address, "beds": beds}, actor=_actor())
        return jsonify({"job_id": jid})
    if mode == "comps_grid":
        if not data.get("grid"):
            return jsonify({"error": "No grid data to write."}), 400
        jid = jobs.create_job("comps_grid", {"from_job": data.get("from_job"),
                                             "grid": data.get("grid")}, actor=_actor())
        return jsonify({"job_id": jid})
    return jsonify({"error": "Unknown mode."}), 400


@app.get("/api/underwrite/intake/<jid>")
@login_required
def api_underwrite_intake(jid):
    # Editable model inputs (defaults + options + derived preview) for the
    # review/edit step before generating the Stick + Modular models.
    try:
        return jsonify(jobs.underwrite_intake(jid))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.get("/api/comps/intake/<jid>")
@login_required
def api_comps_intake(jid):
    # Subject + comp rows + adjustment ruleset for the comp review/edit matrix.
    try:
        return jsonify(jobs.comps_intake(jid))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


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


@app.get("/admin")
@login_required
def admin():
    # Per-device usage view. Hidden unless ADMIN_KEY is set and supplied once via
    # /admin?key=… (then remembered in the session). Not linked from the app.
    if not _admin_ok():
        abort(404)
    return render_template("admin.html")


@app.get("/api/admin/devices")
@login_required
def api_admin_devices():
    if not _admin_ok():
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"devices": jobs.device_totals(),
                    "minutes_per": jobs.MINUTES_PER_CHECKLIST})


@app.post("/api/admin/devices/label")
@login_required
def api_admin_label():
    if not _admin_ok():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    ok = jobs.set_device_label((data.get("device") or "").strip(), data.get("label") or "")
    return jsonify({"ok": ok})


@app.get("/healthz")
def healthz():
    # Plain 200 for uptime monitors (UptimeRobot, Railway healthcheck, etc.).
    return "ok", 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=True)
