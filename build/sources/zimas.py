#!/usr/bin/env python3
"""
zimas.py — LA-City zoning/hazard block readers (ZIMAS-equivalent, Tier-A).

ZIMAS's own parcel-report API is WAF-locked, but the same data is published as
open, no-auth ArcGIS REST layers — so this is Tier-A (data/API), not a browser
pass. Confirmed live 2026-06-15. Two services:

  NavigateLA MapServer  (maps.lacity.org/.../Mapping/NavigateLA/MapServer):
    395 Parcels (PIN/BPP/CNCL_DIST) · 71 Zoning (ZONE_CMPLT) · 93 Specific Plan
    · 75 HPOZ · 72 Historic-Cultural Monuments · 354 Methane Zone/Buffer
  LA City Planning AGOL (services1.arcgis.com/tzwalEyxl2rpamKs):
    TOC tier (TransitOrientedCommunity_TOC_01042024/11, field `tier`)
    ½-mile major transit (AB_2097_..._half_mile_of_major_transit/56, presence)

Parcel snap: the geocoded point can land on the street and miss every parcel
polygon, so we point-query layer 395, fall back to a 40 m buffer + nearest, and
use the parcel's representative point for every designation query. The snap is
cached per coordinate (shared across all fields in one run).

Jurisdiction: these are LA-City-only / LA-routed fields. in_la_city() gates them
at the orchestration layer; off LA City the parcel snap finds nothing and the
fields route to local planning (left manual), never invented.

NOT available via REST (stay manual): transitional_height_adj_zones (C46) and
special_grading_area_la (C56) — ZIMAS derives both in its locked backend.
"""
import _arcgis as ag

NAV = "https://maps.lacity.org/arcgis/rest/services/Mapping/NavigateLA/MapServer"
LADCP = "https://services1.arcgis.com/tzwalEyxl2rpamKs/arcgis/rest/services"
TOC = f"{LADCP}/TransitOrientedCommunity_TOC_01042024/FeatureServer"
AB2097 = f"{LADCP}/AB_2097_Exempts_parking_minimums_within_a_half_mile_of_major_transit/FeatureServer"

L_PARCEL, L_ZONE, L_SPECPLAN, L_HPOZ, L_HCM, L_METHANE = 395, 71, 93, 75, 74, 354  # 74 = HCM leaf (72 is a group)
L_TOC, L_AB2097 = 11, 56

_SNAP = {}   # (round lon,lat) -> (parcel_attrs, (rlon, rlat))


def _poly_repr_point(geom):
    """Representative lon/lat (mean of outer-ring vertices) for an ArcGIS polygon."""
    rings = (geom or {}).get("rings") or []
    if not rings:
        return None
    pts = rings[0]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _snapped(geo):
    key = (round(geo["lon"], 6), round(geo["lat"], 6))
    if key in _SNAP:
        return _SNAP[key]
    lon, lat = geo["lon"], geo["lat"]
    feats = ag.query(NAV, L_PARCEL, lon=lon, lat=lat, return_geometry=True,
                     out_fields="PIN,PIND,BPP,CNCL_DIST")
    if not feats:   # geocoded point sat on the street — buffer and take nearest
        feats = ag.query(NAV, L_PARCEL, lon=lon, lat=lat, distance=40, return_geometry=True,
                         out_fields="PIN,PIND,BPP,CNCL_DIST")
    best, best_d, best_pt = None, None, None
    for f in feats:
        c = _poly_repr_point(f.get("geometry"))
        if not c:
            continue
        d = ag.haversine_m(lon, lat, c[0], c[1])
        if best_d is None or d < best_d:
            best, best_d, best_pt = f, d, c
    if best is None:
        raise LookupError("no LA City parcel within 40 m of the geocoded point (off LA City?)")
    res = (best["attributes"], best_pt)
    _SNAP[key] = res
    return res


def in_la_city(geo) -> bool:
    try:
        _snapped(geo)
        return True
    except Exception:
        return False


def _name(attrs):
    for k, v in attrs.items():
        if "NAME" in k.upper() and v:
            return v
    return None


# ---- field readers (each returns {"answer","notes"} or raises -> TOOL-FAIL) ----

def zoning(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(NAV, L_ZONE, lon=lon, lat=lat, out_fields="ZONE_CMPLT,ZONE_CLASS,ZONING_DESCRIPTION")
    if not feats:
        raise LookupError("no LA City zoning polygon at parcel")
    a = feats[0]["attributes"]
    z = a.get("ZONE_CMPLT")
    desc = a.get("ZONING_DESCRIPTION") or ""
    return {"answer": z, "notes": f"{z} — {desc}. Source: ZIMAS (NavigateLA zoning)."}


def q_conditions(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(NAV, L_ZONE, lon=lon, lat=lat, out_fields="ZONE_CMPLT")
    z = feats[0]["attributes"].get("ZONE_CMPLT", "") if feats else ""
    has_q = "[Q]" in z or z.startswith("Q")
    if has_q:
        return {"answer": f"Qualified [Q] classification in {z}",
                "notes": "Zone carries a [Q] qualified prefix; read the controlling ordinance for the "
                         "specific Q conditions (not exposed via REST). Source: ZIMAS (NavigateLA zoning)."}
    return {"answer": "None", "notes": f"No [Q] qualified prefix on zone {z}. Source: ZIMAS (NavigateLA zoning)."}


def specific_plan_overlay(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(NAV, L_SPECPLAN, lon=lon, lat=lat, out_fields="NAME,DIST_TYPE")
    if not feats:
        return {"answer": "None", "notes": "Not in a specific plan / overlay district. Source: ZIMAS (NavigateLA)."}
    names = "; ".join(sorted({f["attributes"].get("NAME") for f in feats if f["attributes"].get("NAME")}))
    return {"answer": names, "notes": f"Specific plan / overlay: {names}. Source: ZIMAS (NavigateLA)."}


def council_district(geo) -> dict:
    parcel, _ = _snapped(geo)
    d = parcel.get("CNCL_DIST")
    if not d:
        raise LookupError("parcel record has no council district")
    return {"answer": f"Council District {d}",
            "notes": f"LA City Council District {d} (from parcel record). Source: ZIMAS (NavigateLA parcels)."}


def historic_status(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    hpoz = ag.query(NAV, L_HPOZ, lon=lon, lat=lat, out_fields="*")
    hcm = ag.query(NAV, L_HCM, lon=lon, lat=lat, out_fields="*")
    tags = []
    if hpoz:
        tags.append(f"HPOZ ({_name(hpoz[0]['attributes']) or 'district'})")
    if hcm:
        tags.append(f"Historic-Cultural Monument ({_name(hcm[0]['attributes']) or 'listed'})")
    if tags:
        return {"answer": "Yes",
                "notes": "; ".join(tags) + ". (SurveyLA/eligibility via HistoricPlacesLA if needed.) "
                         "Source: ZIMAS (NavigateLA)."}
    return {"answer": "No",
            "notes": "Not in an HPOZ and not a Historic-Cultural Monument. Confirm SurveyLA eligibility via "
                     "HistoricPlacesLA. Source: ZIMAS (NavigateLA)."}


def methane_hazard_zone(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(NAV, L_METHANE, lon=lon, lat=lat, out_fields="*")
    if not feats:
        return {"answer": "No", "notes": "Not in an LA City Methane Zone or Buffer Zone. Source: ZIMAS (NavigateLA L354)."}
    a = feats[0]["attributes"]
    code = next((v for k, v in a.items() if k.upper().endswith("ZONE") and v), None)
    label = {"MZ": "Methane Zone", "MB": "Methane Buffer Zone"}.get(code, "Methane Zone")
    return {"answer": label, "notes": f"In LA City {label} (code {code}). Source: ZIMAS (NavigateLA L354)."}


def toc_tier(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(TOC, L_TOC, lon=lon, lat=lat, out_fields="tier")
    if not feats:
        return {"answer": "None", "notes": "Not in a Transit Oriented Communities (TOC) tier area. Source: LA City Planning TOC."}
    tier = feats[0]["attributes"].get("tier")
    return {"answer": f"Tier {tier}", "notes": f"TOC Tier {tier}. Source: LA City Planning TOC (2024)."}


# Transitional height (LAMC 12.21.1-A.10): no published layer exists — DERIVED
# from zoning adjacency. Applies to a C/M lot within set distances of an RW1-or-
# more-restrictive zone, capping height 25/33/61 ft over the 0-49/50-99/100-199 ft
# bands. We approximate by buffering the parcel's representative point, so the
# result is a JUDGMENT candidate flag (route up), never VERIFIED.
TH_BANDS = [(14.9, "0–49 ft", 25), (30.2, "50–99 ft", 33), (60.7, "100–199 ft", 61)]
_RESTRICTIVE = ("A1", "A2", "RA", "RE", "RS", "R1", "RU", "RZ", "RW1")  # "RW1 or more restrictive"


def _restrictive(zone_class) -> bool:
    zc = (zone_class or "").upper()
    return zc.startswith(_RESTRICTIVE) and not zc.startswith("RAS")   # RAS3/RAS4 are denser, not restrictive


def transitional_height(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(NAV, L_ZONE, lon=lon, lat=lat, out_fields="ZONE_CMPLT,ZONE_CLASS")
    if not feats:
        raise LookupError("no LA City zoning polygon at parcel")
    a = feats[0]["attributes"]
    zc, zcmplt = (a.get("ZONE_CLASS") or "").upper(), a.get("ZONE_CMPLT")
    if not (zc.startswith("C") or zc.startswith("M")):
        return {"answer": "N/A — applies only to C/M zones", "state": "NA",
                "notes": f"Transitional height (LAMC 12.21.1-A.10) applies only to commercial/industrial "
                         f"zones; subject is {zcmplt}. Source: derived from ZIMAS zoning (NavigateLA 71)."}
    caveat = ("DERIVED ESTIMATE — distances measured from the parcel centroid on generalized zoning "
              "polygons; the rule governs portions of the lot measured from the lot line and a grade "
              "exception can raise the cap. Confirm in ZIMAS/LADBS.")
    hit = None
    for radius, band, cap in TH_BANDS:
        near = ag.query(NAV, L_ZONE, lon=lon, lat=lat, distance=radius, out_fields="ZONE_CLASS")
        if any(_restrictive(f["attributes"].get("ZONE_CLASS")) for f in near):
            hit = (band, cap)
            break
    if hit:
        band, cap = hit
        return {"answer": f"Likely applies — ~{cap} ft cap ({band} from a more-restrictive zone)",
                "state": "JUDGMENT",
                "notes": f"Subject {zcmplt}; a more-restrictive (RW1-or-tighter) zone lies within {band}. "
                         f"Near-portion cap ≈ {cap} ft. {caveat} Source: derived from ZIMAS zoning (NavigateLA 71)."}
    return {"answer": "Does not appear to apply", "state": "JUDGMENT",
            "notes": f"Subject {zcmplt} (C/M); no more-restrictive zone within ~200 ft of the parcel centroid. "
                     f"{caveat} Source: derived from ZIMAS zoning (NavigateLA 71)."}


def half_mile_major_transit(geo) -> dict:
    _, (lon, lat) = _snapped(geo)
    feats = ag.query(AB2097, L_AB2097, lon=lon, lat=lat, out_fields="OBJECTID")
    if feats:
        return {"answer": "Yes",
                "notes": "Within ½ mile of a major transit stop (AB2097 citywide buffer). Source: LA City Planning."}
    return {"answer": "No",
            "notes": "Not within ½ mile of a major transit stop (AB2097 buffer). Source: LA City Planning."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    if not in_la_city(g):
        print(json.dumps({"in_la_city": False, "note": "off LA City — ZIMAS fields route to local planning"}, indent=2))
        sys.exit(0)
    out = {"in_la_city": True}
    for fid, fn in {"zoning": zoning, "q_conditions_la": q_conditions,
                    "specific_plan_overlay": specific_plan_overlay,
                    "council_supervisor_district": council_district,
                    "historic_status": historic_status, "methane_hazard_zone_la": methane_hazard_zone,
                    "toc_tier_la": toc_tier, "half_mile_major_transit": half_mile_major_transit,
                    "transitional_height_adj_zones": transitional_height}.items():
        try:
            out[fid] = fn(g)
        except Exception as e:
            out[fid] = {"error": str(e)}
    print(json.dumps(out, indent=2))
