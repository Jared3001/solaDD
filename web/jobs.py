#!/usr/bin/env python3
"""
jobs.py — background job orchestration for the web front end.

This is a thin layer over the existing CLI pipeline. It REUSES the exact
reader registries and runner from build/ (no logic is forked here):

  - single-address runs replicate collect.py's two-phase flow (fan readers out
    across a thread pool, then write the workbook once) but report each field as
    its reader finishes, so the UI can stream live progress.
  - assemblage runs call assemblage.assess() unchanged and surface its result.

Jobs run in daemon threads and live in an in-memory store, so the app MUST run
as a single gunicorn worker (see Procfile). Filled workbooks are written to a
temp dir and served by /api/download.
"""
import os
import sys
import json
import uuid
import shutil
import tempfile
import datetime
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent          # repo root (web/ -> root)
BUILD = ROOT / "build"
SOURCES = BUILD / "sources"
for _p in (str(BUILD), str(SOURCES)):                  # make build/ + build/sources/ importable
    if _p not in sys.path:
        sys.path.insert(0, _p)

import yaml
from openpyxl import load_workbook

# Reuse the CLI pipeline verbatim — registries, runner, geocoder, readers.
import collect as _collect            # READERS, ZIMAS_READERS
import assemblage as _assemblage      # assess()
from runner import run_reader, apply_outcome
from geocoder import geocode
import zimas
import nc

TEMPLATE = ROOT / "template" / "Checklist_BLANK_master.xlsx"

# Filled workbooks + the persistent counter live in DATA_DIR. Defaults to a
# temp dir (resets on a Railway redeploy); point DATA_DIR at a mounted volume
# for a counter that survives deploys.
DATA_DIR = Path(os.environ.get("DATA_DIR") or (Path(tempfile.gettempdir()) / "sola_dd_runs"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
RUN_DIR = DATA_DIR
COUNTER_FILE = DATA_DIR / "counter.json"

# Time-saved metric. STARTING_CHECKLISTS = sites already automated before the
# app started counting; each automated checklist saves MINUTES_PER_CHECKLIST.
STARTING_CHECKLISTS = int(os.environ.get("STARTING_CHECKLISTS", "9"))
MINUTES_PER_CHECKLIST = int(os.environ.get("MINUTES_PER_CHECKLIST", "30"))
_counter_lock = threading.Lock()

# Schema metadata for labelling / grouping results in the UI.
_schema = yaml.safe_load((ROOT / "canonical" / "schema.yaml").read_text())
FIELD_BY_ID = {f["id"]: f for f in _schema["fields"]}
SECTIONS = [{"id": s["id"], "label": s["label"]} for s in _schema["sections"]]

MAX_JOBS = 50                          # keep the most recent N; prune older + their files
_jobs = {}
_lock = threading.Lock()

# Reader landing states that are legitimate "good" outcomes (mirrors runner.py).
_LANDING = {"VERIFIED", "JUDGMENT", "NA", "COMPUTED", "OM-SOURCED"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _jsonable(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _field_meta(fid):
    f = FIELD_BY_ID.get(fid, {})
    return f.get("label", fid), f.get("section", "other")


def _record(job, fid, answer, state, notes):
    label, section = _field_meta(fid)
    entry = {
        "id": fid, "label": label, "section": section,
        "answer": _jsonable(answer), "state": state, "notes": notes or "",
    }
    # The worker thread writes while poll requests read; guard the dict so a
    # concurrent iteration in public_view() can't hit "changed size".
    with job["_lock"]:
        job["fields"][fid] = entry


# --------------------------------------------------------------------------- #
# single address
# --------------------------------------------------------------------------- #
def _display_outcome(outcome):
    """Map a run_reader result to (state, answer, notes) for the UI.

    A fresh single run = one attempt, so a failure shows as TOOL-FAIL (the saved
    workbook records the real 'TOOL-FAIL 1/3' counter via apply_outcome)."""
    kind, payload = outcome
    if kind == "ok":
        st = payload.get("state", "VERIFIED")
        if st not in _LANDING:
            st = "VERIFIED"
        return st, payload.get("answer"), payload.get("notes", "")
    return "TOOL-FAIL", None, str(payload)[:200]


def run_single(job):
    address = job["input"]["address"]
    geo = geocode(address)
    job["geo"] = {
        "matched_address": geo["matched_address"], "geoid": geo["geoid"],
        "lat": round(geo["lat"], 6), "lon": round(geo["lon"], 6),
    }
    job["label"] = geo["matched_address"]

    active = dict(_collect.READERS)
    in_la = False
    try:
        in_la = zimas.in_la_city(geo)      # also warms the shared parcel snap
    except Exception:
        pass
    if in_la:
        active.update(_collect.ZIMAS_READERS)
    job["in_la_city"] = in_la
    job["total"] = len(active)
    job["phase"] = ("In City of LA — running ZIMAS zoning/hazard block. "
                    if in_la else "Outside LA City — ZIMAS block skipped. ") + "Running readers…"

    try:
        nc._load()                         # warm the Neighborhood-Change cache once
    except Exception:
        pass

    # Phase 1 — fan all readers out; report each as it finishes.
    outcomes = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(run_reader, (lambda fn=fn: fn(geo))): fid
                for fid, fn in active.items()}
        for fut in as_completed(futs):
            fid = futs[fut]
            try:
                outcome = fut.result()
            except Exception as e:               # defensive — run_reader catches its own
                outcome = ("fail", e)
            outcomes[fid] = outcome
            st, ans, notes = _display_outcome(outcome)
            _record(job, fid, ans, st, notes)
            job["completed"] = len(outcomes)

    # Phase 2 — write the workbook once (reuses apply_outcome for the real file).
    wb = load_workbook(TEMPLATE)
    ws, log = wb["Site DD"], wb["State Log"]
    ts = _now()
    for fid in active:
        apply_outcome(ws, log, FIELD_BY_ID[fid], outcomes[fid],
                      property_id=job["input"].get("property_id") or "WEB", ts=ts)
    out_path = RUN_DIR / f"{job['id']}.xlsx"
    wb.save(out_path)
    job["file"] = str(out_path)
    job["filename"] = _safe_name(geo["matched_address"]) + ".xlsx"
    job["phase"] = "Complete"


# --------------------------------------------------------------------------- #
# multi-APN assemblage
# --------------------------------------------------------------------------- #
def run_assemblage(job):
    apns = job["input"]["apns"]
    job["phase"] = f"Resolving {len(apns)} APN(s) and running readers across parcels…"
    out_path = RUN_DIR / f"{job['id']}.xlsx"
    shutil.copy(TEMPLATE, out_path)

    result = _assemblage.assess(str(out_path), apns, property_id="WEB-ASSEMBLAGE")

    job["parcels"] = [
        {"apn": p["apn"], "n_lots": p["n_lots"], "land_sf": p["land_sf"], "geoid": p["geoid"]}
        for p in result["parcels"]
    ]
    job["combined_sf"] = result["combined_sf"]

    # Site-level fields assess() computes itself (written to the workbook, not in .fields).
    apn_list = ", ".join(p["apn"] for p in result["parcels"])
    _record(job, "apn", apn_list, "VERIFIED",
            f"Block assemblage of {len(result['parcels'])} APN(s).")
    _record(job, "land_sf", round(result["combined_sf"]), "VERIFIED",
            f"Combined gross land area = {result['combined_sf']:,.1f} sf "
            f"({result['combined_sf'] / 43560:.3f} ac) across {len(result['parcels'])} APN(s).")
    for fid, a in result["fields"].items():
        _record(job, fid, a["answer"], a["state"], a.get("notes", ""))

    job["total"] = job["completed"] = len(job["fields"])
    job["file"] = str(out_path)
    job["filename"] = f"assemblage_{result['parcels'][0]['apn'].replace('-', '')}_{len(apns)}APN.xlsx"
    job["phase"] = "Complete"


# --------------------------------------------------------------------------- #
# job store
# --------------------------------------------------------------------------- #
def _safe_name(s):
    keep = "".join(c if c.isalnum() or c in " -," else "_" for c in str(s))
    return ("_".join(keep.split()) or "site")[:80]


# --------------------------------------------------------------------------- #
# time-saved counter (persisted) + stats
# --------------------------------------------------------------------------- #
def _read_count():
    try:
        return int(json.loads(COUNTER_FILE.read_text()).get("count", 0))
    except Exception:
        return 0


def _bump_count():
    with _counter_lock:
        n = _read_count() + 1
        try:
            COUNTER_FILE.write_text(json.dumps({"count": n}))
        except Exception:
            traceback.print_exc()
        return n


def stats():
    runs = _read_count()
    total = STARTING_CHECKLISTS + runs
    minutes = total * MINUTES_PER_CHECKLIST
    return {
        "app_runs": runs, "starting": STARTING_CHECKLISTS,
        "total_automated": total, "minutes_per": MINUTES_PER_CHECKLIST,
        "minutes_saved": minutes, "hours_saved": round(minutes / 60, 1),
    }


def recent_jobs(n=10):
    """Most recent completed runs, newest first, for the re-download list."""
    with _lock:
        done = [j for j in _jobs.values() if j["status"] == "done"]
    done.sort(key=lambda j: j.get("finished") or "", reverse=True)
    out = []
    for j in done[:n]:
        with j["_lock"]:
            states = [f["state"] for f in j["fields"].values()]
        flags = sum(1 for s in states
                    if s.startswith("TOOL-FAIL") or s == "MANUAL-VERIFY")
        out.append({
            "id": j["id"], "kind": j["kind"], "label": j.get("label") or j["id"],
            "finished": j.get("finished"), "fields": len(states), "flags": flags,
            "downloadable": bool(j.get("file")),
        })
    return out


def _prune():
    """Evict oldest jobs (and their files) beyond MAX_JOBS. Caller holds _lock."""
    if len(_jobs) <= MAX_JOBS:
        return
    for jid in sorted(_jobs, key=lambda j: _jobs[j]["started"])[:len(_jobs) - MAX_JOBS]:
        old = _jobs.pop(jid)
        if old.get("file"):
            try:
                Path(old["file"]).unlink(missing_ok=True)
            except Exception:
                pass


def create_job(kind, payload):
    jid = uuid.uuid4().hex[:12]
    label = payload.get("address") or ", ".join(payload.get("apns", [])) or jid
    job = {
        "id": jid, "kind": kind, "status": "running", "input": payload, "label": label,
        "geo": None, "in_la_city": None, "phase": "Starting…",
        "total": 0, "completed": 0, "fields": {},
        "parcels": None, "combined_sf": None,
        "error": None, "file": None, "filename": None,
        "started": _now(), "finished": None,
        "_lock": threading.Lock(),
    }
    with _lock:
        _jobs[jid] = job
        _prune()
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return jid


def _run(job):
    try:
        run_single(job) if job["kind"] == "single" else run_assemblage(job)
        job["status"] = "done"
        _bump_count()                  # one completed checklist = MINUTES_PER_CHECKLIST saved
    except Exception as e:
        traceback.print_exc()
        job["status"] = "error"
        job["error"] = str(e)
        job["phase"] = "Error"
    finally:
        job["finished"] = _now()


def get_job(jid):
    return _jobs.get(jid)


def public_view(job):
    """Serialize a job for the API (omits the on-disk path + internal lock)."""
    with job["_lock"]:
        fields = list(job["fields"].values())
    return {
        "id": job["id"], "kind": job["kind"], "status": job["status"],
        "phase": job["phase"], "geo": job["geo"], "in_la_city": job["in_la_city"],
        "total": job["total"], "completed": job["completed"],
        "fields": fields,
        "parcels": job["parcels"], "combined_sf": job["combined_sf"],
        "error": job["error"], "downloadable": bool(job["file"]),
        "started": job["started"], "finished": job["finished"],
    }
