#!/usr/bin/env python3
"""
assemblage.py — multi-APN block-assemblage support.

A site can be one legal lot or a BLOCK ASSEMBLAGE of several APNs bought together
(e.g. 4201 Pico = "entire block"). collect.py sizes only the anchor parcel; this
takes a LIST of APNs, sizes the combined site, and aggregates every Tier-A
designation across the parcels — reporting a single site-level answer and
flagging where parcels DIFFER (mixed zoning, a hazard on only some lots, a tract
split, etc.).

Land area: the LA City Parcels layer (Landbase_Information/MapServer/5, keyed by
BPP) reproduces ZIMAS lot areas as polygon geometry in EPSG:2229 (US survey ft).
One APN can map to several lot polygons; we sum them per APN and across the site.

Each parcel runs the same readers as collect.py (statewide via the parcel's
census tract from geocode_point; ZIMAS via the parcel centroid). Aggregation:
  - yes/no hazard fields  -> "Yes" if ANY parcel is Yes (names the APNs); else No
  - text/enum fields      -> the shared value, or "MIXED: v (apns); w (apns)"
The combined land_sf, the APN list, and every aggregated field are written to a
site workbook (cols A/C/E), with per-parcel detail in Notes.

Usage:
  python build/assemblage.py <wb.xlsx> APN1 APN2 ...
  python build/assemblage.py --demo APN1 APN2 ...   (throwaway workbook)
"""
import re
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
sys.path.insert(0, str(ROOT / "build" / "sources"))

import yaml
import _arcgis as ag
from geocoder import geocode_point
from collect import READERS, ZIMAS_READERS
import zimas

LACITY_PARCELS = "https://maps.lacity.org/lahub/rest/services/Landbase_Information/MapServer"
PARCEL_LAYER = 5   # "Parcels" — geometry area in EPSG:2229 reproduces ZIMAS lot area


def _norm(apn: str) -> str:
    """'5082-024-018' -> '5082024018' (BPP key)."""
    return re.sub(r"[^0-9A-Za-z]", "", apn).upper()


def _ring_area_sf(rings):
    """Shoelace area (sq ft) of an ArcGIS polygon whose coords are in EPSG:2229 ft."""
    tot = 0.0
    for ring in rings:
        s = 0.0
        for i in range(len(ring) - 1):
            s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        tot += s / 2.0
    return abs(tot)


def parcel_info(apn: str) -> dict:
    """Resolve an APN to {apn, bpp, n_lots, land_sf, lon, lat, geoid}."""
    bpp = _norm(apn)
    where = f"BPP='{bpp}'"
    feet = ag.query(LACITY_PARCELS, PARCEL_LAYER, where=where, return_geometry=True,
                    out_sr=2229, out_fields="BPP,LOT")
    if not feet:
        raise LookupError(f"no LA City parcel for APN {apn} (BPP {bpp})")
    land_sf = sum(_ring_area_sf(f["geometry"]["rings"]) for f in feet if f.get("geometry"))
    wgs = ag.query(LACITY_PARCELS, PARCEL_LAYER, where=where, return_geometry=True,
                   out_sr=4326, out_fields="BPP")
    # representative point = centroid of the largest lot polygon (in lon/lat)
    best_pt, best_a = None, -1.0
    for f in wgs:
        rings = (f.get("geometry") or {}).get("rings") or []
        if not rings:
            continue
        pts = rings[0]
        a = len(pts)
        if a > best_a:
            best_a = a
            best_pt = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    lon, lat = best_pt
    geo = geocode_point(lon, lat)
    return {"apn": apn, "bpp": bpp, "n_lots": len(feet), "land_sf": round(land_sf, 1),
            "lon": lon, "lat": lat, "geoid": geo["geoid"],
            "state_fips": geo["state_fips"], "county_fips": geo["county_fips"],
            "matched_address": geo["matched_address"]}


def _run_readers(parcel):
    """Run every reader for one parcel; return {fid: {'answer','state','error'}}."""
    geo = {"lon": parcel["lon"], "lat": parcel["lat"], "geoid": parcel["geoid"],
           "state_fips": parcel["state_fips"], "county_fips": parcel["county_fips"],
           "matched_address": parcel["matched_address"]}
    out = {}
    for fid, fn in {**READERS, **ZIMAS_READERS}.items():
        if fid == "land_sf":   # assemblage writes COMBINED land_sf itself
            continue
        try:
            r = fn(geo)
            out[fid] = {"answer": r.get("answer"), "state": r.get("state", "VERIFIED")}
        except Exception as e:
            out[fid] = {"answer": None, "state": "TOOL-FAIL", "error": str(e)[:120]}
    return out


def _aggregate(fid, atype, per_parcel):
    """Collapse per-parcel answers into one site answer + note + state."""
    vals = {p["apn"]: per_parcel[p["apn"]][fid] for p in per_parcel["_order"]}
    fails = [a for a, v in vals.items() if v["state"] == "TOOL-FAIL"]
    ok = {a: v for a, v in vals.items() if v["state"] != "TOOL-FAIL"}
    if not ok:
        return {"answer": None, "state": "TOOL-FAIL",
                "notes": f"all parcels failed: {'; '.join(fails)}"}

    def grp(pred):  # apns whose answer matches pred
        return [a for a, v in ok.items() if pred(v["answer"])]

    if atype == "yes_no":
        yes = grp(lambda x: str(x).strip().lower().startswith("y"))
        ans = "Yes" if yes else "No"
        note = (f"Yes on APN(s): {', '.join(yes)}" if yes
                else f"No across all {len(ok)} parcel(s)")
    else:  # text / enum / number — distinct values
        by_val = {}
        for a, v in ok.items():
            by_val.setdefault(str(v["answer"]), []).append(a)
        if len(by_val) == 1:
            ans = next(iter(by_val))
            note = f"uniform across {len(ok)} parcel(s)"
        else:
            ans = "MIXED — see notes"
            note = "MIXED: " + "; ".join(f"{val} ({', '.join(ap)})" for val, ap in by_val.items())
    # state: any borderline parcel makes the whole site a JUDGMENT (route up);
    # otherwise a single shared state propagates, else VERIFIED.
    states = {v["state"] for v in ok.values()}
    if "JUDGMENT" in states:
        state = "JUDGMENT"
    elif len(states) == 1:
        state = states.pop()
    else:
        state = "VERIFIED"
    if fails:
        note += f" | NOTE: {len(fails)} parcel(s) failed read: {', '.join(fails)}"
    return {"answer": ans, "state": state, "notes": note}


def assess(wb_path, apns, property_id=None):
    schema = yaml.safe_load((ROOT / "canonical/schema.yaml").read_text())
    by_id = {f["id"]: f for f in schema["fields"]}
    atype = {f["id"]: f.get("answer_type") for f in schema["fields"]}

    parcels = []
    print(f"resolving {len(apns)} APN(s)…")
    for apn in apns:
        p = parcel_info(apn)
        parcels.append(p)
        print(f"  {p['apn']:16} BPP {p['bpp']:12} {p['n_lots']} lot(s)  {p['land_sf']:>10,.1f} sf  tract {p['geoid']}")
    combined = round(sum(p["land_sf"] for p in parcels), 1)
    print(f"  COMBINED LAND AREA: {combined:,.1f} sf  ({combined/43560:.3f} ac)\n")

    per = {"_order": parcels}
    for p in parcels:
        per[p["apn"]] = _run_readers(p)

    # write to workbook
    from openpyxl import load_workbook
    wb = load_workbook(wb_path)
    ws = wb["Site DD"]

    def put(cell, answer, state, notes):
        r = int(cell[1:])
        ws.cell(r, 1, state)
        ws.cell(r, 3, answer)
        ws.cell(r, 5, notes)

    apn_list = ", ".join(p["apn"] for p in parcels)
    put(by_id["apn"]["answer_cell"], apn_list, "VERIFIED",
        "Block assemblage: " + "; ".join(f"{p['apn']} ({p['n_lots']} lot(s), {p['land_sf']:,.0f} sf)" for p in parcels))
    put(by_id["land_sf"]["answer_cell"], combined, "VERIFIED",
        f"Combined gross land area across {len(parcels)} APN(s) = {combined:,.1f} sf "
        f"({combined/43560:.3f} ac). Per-APN: " +
        "; ".join(f"{p['apn']}={p['land_sf']:,.0f}" for p in parcels) +
        ". Source: LA City Parcels geometry (EPSG:2229).")

    print(f"{'field':30} {'SITE answer':24} {'state':10} detail")
    print("-" * 100)
    agg = {}
    for fid in [*READERS, *ZIMAS_READERS]:
        if fid not in by_id or fid == "land_sf":   # land_sf written as combined above
            continue
        a = _aggregate(fid, atype.get(fid), per)
        agg[fid] = a
        put(by_id[fid]["answer_cell"], a["answer"], a["state"], a["notes"])
        print(f"{fid:30} {str(a['answer'])[:24]:24} {a['state']:10} {a['notes'][:48]}")

    wb.save(wb_path)
    print(f"\nworkbook: {wb_path}")
    return {"parcels": parcels, "combined_sf": combined, "fields": agg}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--demo":
        apns = args[1:]
        tmp = ROOT / "build" / "_assemblage_demo.xlsx"
        shutil.copy(ROOT / "template/Checklist_BLANK_master.xlsx", tmp)
        assess(tmp, apns, property_id="ASSEMBLAGE")
    elif len(args) >= 2:
        assess(args[0], args[1:])
    else:
        print(__doc__)
