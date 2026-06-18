#!/usr/bin/env python3
"""
lacounty.py — Unincorporated-LA-County zoning/land-use/transit block (the County
analog of zimas.py for LA City and sandiego.py for the City of San Diego).

Tier-A: the LA County Dept. of Regional Planning (DRP) publishes its zoning and
land-use data as open, no-auth ArcGIS REST layers on public.gis.lacounty.gov
(confirmed live 2026-06-18). This is a DIFFERENT GIS and a DIFFERENT set of
metrics than LA City: unincorporated parcels are governed by County Title 22
(not the City's LAMC), so they carry a County ZONE (R-1, C-3, SP, ...), a General
Plan / Community Plan land-use category, a Community Standards District (CSD), a
Zoned District (ZD), a Supervisorial District (not a Council District), and a
County Transit Oriented District (TOD) — there is no ZIMAS [Q] condition, no
LA-City methane zone, and no LAMC transitional-height rule.

Services used (public.gis.lacounty.gov/public/rest/services):
  DRP/Open_Data/MapServer
     3 Zoning (ZONE/Z_DESC/NAME/Z_CATEGORY/PLNG_AREA/TITLE_22)
     4 Community Standards District (CSD) (CSD_NAME)
     7 Land Use Policy - Community/Area Plan (PLAN_/PLAN_LEG/COMM_NAME)
     8 Land Use Policy - General Plan 2035 (PLAN_/PLAN_LEG)
    12 Significant Ecological Area (SEA) (SEA_NAME/SEA_TYPE)
    23 Transit Oriented District (TOD) (NAME/FULL_NAME/LINE)
    25 Zoned District (ZD) (ZD_NAME/DISTRICT_NO)
  LACounty_Dynamic/Political_Boundaries/MapServer
    19 City Boundaries (CITY_NAME/CITY_TYPE) — the jurisdiction routing spine
    27 Supervisorial District (Current) (DISTRICT/LABEL)

Jurisdiction: this block runs ONLY for parcels in unincorporated LA County. The
authoritative gate is the County City Boundaries layer (19): CITY_TYPE ==
'Unincorporated'. Incorporated cities (including LA City, which routes to ZIMAS)
return their own name there and are NOT handled here — those readers raise and the
field routes to local planning, never an invented value. This mirrors how the
ZIMAS / SD blocks gate on their own jurisdiction.

Why this exists: a geocoded point in an unincorporated pocket can sit within
~100 m of an LA-City parcel across the street, so a parcel-snap alone misroutes it
into ZIMAS and reports the neighbor's City zoning. The L19 boundary polygon is the
correct, address-independent test.
"""
import _arcgis as ag

BASE = "https://public.gis.lacounty.gov/public/rest/services"
DRP = f"{BASE}/DRP/Open_Data/MapServer"
POL = f"{BASE}/LACounty_Dynamic/Political_Boundaries/MapServer"

L_ZONE, L_CSD, L_COMMPLAN, L_GENPLAN, L_SEA, L_TOD, L_ZD = 3, 4, 7, 8, 12, 23, 25
L_CITYBND, L_SUPV = 19, 27
_BUF = 8   # small buffer (m) so a point on a polygon boundary still returns it

# DRP Specific-Plan sub-layers (each its own polygon layer) -> readable label.
SPECIFIC_PLAN_LAYERS = {
    14: "3rd Street (East LA) Specific Plan",
    15: "Catalina / Two Harbors Specific Plan",
    16: "La Vina Specific Plan",
    17: "Marina del Rey Specific Plan",
    18: "Newhall Ranch Specific Plan",
    19: "NorthLake Specific Plan",
    20: "Universal Studios Specific Plan",
}


_CITY_CACHE = {}   # (round lon,lat) -> city record (shared across all readers + the router)


def _city_record(geo):
    """The County City-Boundaries record (layer 19) at the point, or None.
    Cached per coordinate — the router and every reader hit this."""
    key = (round(geo["lon"], 6), round(geo["lat"], 6))
    if key in _CITY_CACHE:
        return _CITY_CACHE[key]
    feats = ag.query(POL, L_CITYBND, lon=geo["lon"], lat=geo["lat"],
                     out_fields="CITY_NAME,CITY_TYPE", distance=_BUF)
    rec = feats[0]["attributes"] if feats else None
    _CITY_CACHE[key] = rec
    return rec


def la_city_name(geo):
    """Authoritative LA-County incorporation status at the point:
    'Los Angeles' (LA City), 'Unincorporated', or another incorporated city name.
    None if the point is outside LA County's boundary coverage."""
    rec = _city_record(geo)
    return rec.get("CITY_NAME") if rec else None


def is_unincorporated(geo) -> bool:
    """True iff the parcel is in unincorporated LA County (the gate for this block)."""
    rec = _city_record(geo)
    return bool(rec) and (rec.get("CITY_TYPE") == "Unincorporated"
                          or (rec.get("CITY_NAME") or "").lower() == "unincorporated")


def _require_unincorporated(geo):
    if not is_unincorporated(geo):
        raise LookupError("point is not in unincorporated LA County "
                          "(DRP zoning is County-jurisdiction only) — route to the local city")


# ---- field readers (each returns {"answer","notes"} or raises -> TOOL-FAIL) ----

def zoning(geo) -> dict:
    _require_unincorporated(geo)
    z = ag.query(DRP, L_ZONE, lon=geo["lon"], lat=geo["lat"],
                 out_fields="ZONE,Z_DESC,NAME,Z_CATEGORY,PLNG_AREA,TITLE_22", distance=_BUF)
    if not z:
        raise LookupError("no LA County zoning polygon at the point")
    a = z[0]["attributes"]
    zone, desc, name = a.get("ZONE"), a.get("Z_DESC"), a.get("NAME")
    # General Plan land-use category adds the policy context the County reads alongside zoning.
    gp = ag.query(DRP, L_GENPLAN, lon=geo["lon"], lat=geo["lat"], out_fields="PLAN_LEG", distance=_BUF)
    gp_leg = gp[0]["attributes"].get("PLAN_LEG") if gp else None
    label = zone + (f" — {desc}" if desc else "") + (f" ({name})" if name and name != desc else "")
    note = (f"County zone {zone}" + (f" — {desc}" if desc else "")
            + (f"; plan: {name}" if name else "")
            + (f". General Plan land use: {gp_leg}" if gp_leg else "")
            + (f". Planning area: {a.get('PLNG_AREA')}" if a.get("PLNG_AREA") else "")
            + (f". Title 22 ref: {a.get('TITLE_22')}" if a.get("TITLE_22") else "")
            + ". Governed by County Title 22 (not City LAMC). "
              "Source: LA County DRP Zoning (Open_Data L3).")
    return {"answer": label, "notes": note}


def specific_plan_overlay(geo) -> dict:
    """County analog of the City specific-plan/overlay cell: an SP zone, a
    Community Standards District (CSD), a Zoned District (ZD), a named Specific
    Plan, and/or a Significant Ecological Area (SEA)."""
    _require_unincorporated(geo)
    lon, lat = geo["lon"], geo["lat"]
    hits = []

    def _q(lyr, fields):
        """Tolerant point query — a single County sub-layer that rejects the query
        (some hosted SP layers 400 on a point) must not sink the whole reader."""
        try:
            return ag.query(DRP, lyr, lon=lon, lat=lat, out_fields=fields, distance=_BUF)
        except Exception:
            return []

    # SP base zone (Z_CATEGORY == 'SP') names the controlling specific plan.
    z = _q(L_ZONE, "Z_CATEGORY,NAME")
    if z and (z[0]["attributes"].get("Z_CATEGORY") == "SP"):
        nm = z[0]["attributes"].get("NAME")
        hits.append(f"Specific Plan zone{f' ({nm})' if nm else ''}")
    csd = _q(L_CSD, "CSD_NAME")
    if csd:
        hits.append(f"Community Standards District ({csd[0]['attributes'].get('CSD_NAME')})")
    zd = _q(L_ZD, "ZD_NAME,DISTRICT_NO")
    if zd:
        a = zd[0]["attributes"]
        hits.append(f"Zoned District {a.get('DISTRICT_NO')} ({a.get('ZD_NAME')})")
    for lyr, lbl in SPECIFIC_PLAN_LAYERS.items():
        if _q(lyr, "OBJECTID"):
            hits.append(lbl)
    sea = _q(L_SEA, "SEA_NAME,SEA_TYPE")
    if sea:
        a = sea[0]["attributes"]
        hits.append(f"Significant Ecological Area ({a.get('SEA_NAME') or a.get('SEA_TYPE')})")
    if not hits:
        return {"answer": "None",
                "notes": "Not within a County specific plan, CSD, zoned district, or SEA. "
                         "Source: LA County DRP (Open_Data)."}
    names = "; ".join(hits)
    return {"answer": names, "notes": f"{names}. Source: LA County DRP (Open_Data)."}


def supervisor_district(geo) -> dict:
    """Unincorporated parcels are represented by a County Supervisor, not a City
    Council member — this fills the Council/Supervisor District cell (C42)."""
    _require_unincorporated(geo)
    feats = ag.query(POL, L_SUPV, lon=geo["lon"], lat=geo["lat"],
                     out_fields="DISTRICT,LABEL", distance=_BUF)
    if not feats:
        raise LookupError("no LA County supervisorial district polygon at the point")
    d = feats[0]["attributes"].get("DISTRICT")
    return {"answer": f"Supervisorial District {d}",
            "notes": f"LA County Board of Supervisors District {d} (unincorporated — represented by the "
                     f"County Supervisor, not a City Council member). Source: LA County Political "
                     f"Boundaries (Supervisorial District L27)."}


def tod(geo) -> dict:
    """County Transit Oriented District — the unincorporated analog of the City TOC
    tier cell (C48). TOD areas are the County's transit-supportive specific-plan
    zones along Metro lines."""
    _require_unincorporated(geo)
    feats = ag.query(DRP, L_TOD, lon=geo["lon"], lat=geo["lat"],
                     out_fields="NAME,FULL_NAME,LINE", distance=_BUF)
    if not feats:
        return {"answer": "None",
                "notes": "Not within a County Transit Oriented District (TOD). "
                         "(County has no City-style TOC tiers.) Source: LA County DRP TOD (Open_Data L23)."}
    a = feats[0]["attributes"]
    nm, line = a.get("FULL_NAME") or a.get("NAME"), a.get("LINE")
    return {"answer": f"TOD: {a.get('NAME')}" + (f" ({line} Line)" if line else ""),
            "notes": f"Within County Transit Oriented District — {nm}"
                     + (f"; Metro {line} Line" if line else "")
                     + ". The County's transit-supportive specific-plan area (analog of the City TOC tier). "
                       "Source: LA County DRP TOD (Open_Data L23)."}


def half_mile_major_transit(geo) -> dict:
    """½-mile-from-major-transit. The County has no published ½-mile buffer layer,
    so we infer from TOD membership: County TOD specific plans are organized around
    Metro stations, so a parcel inside one is almost certainly within ½ mile of a
    major transit stop — but this is a DERIVED screen (JUDGMENT), not the statutory
    SB-743 polygon. Confirm against the AB-2097 / SB-743 determination."""
    _require_unincorporated(geo)
    feats = ag.query(DRP, L_TOD, lon=geo["lon"], lat=geo["lat"], out_fields="NAME,LINE", distance=_BUF)
    if feats:
        a = feats[0]["attributes"]
        return {"answer": "Yes (derived — within a TOD)", "state": "JUDGMENT",
                "notes": f"Parcel is inside the County '{a.get('NAME')}' Transit Oriented District"
                         + (f" (Metro {a.get('LINE')} Line)" if a.get("LINE") else "")
                         + ", which is organized around a major transit stop — so it is very likely within "
                           "½ mile of major transit. DERIVED from TOD membership; confirm the exact ½-mile "
                           "distance to the station. Source: LA County DRP TOD (Open_Data L23)."}
    return {"answer": "No (not in a County TOD — verify distance)", "state": "JUDGMENT",
            "notes": "Parcel is not in a County TOD; no County ½-mile-from-major-transit layer is published. "
                     "Measure distance to the nearest major transit stop to confirm. "
                     "Source: LA County DRP (no TOD at point)."}


def tier_transit_verification(geo) -> dict:
    """County Tier/Transit verification (C96) — summarizes the TOD finding into one
    line (analog of the City TOC + ½-mile summary). Confirm formal density-bonus /
    state-law transit eligibility against the current County determination."""
    t = tod(geo)
    in_tod = t["answer"].startswith("TOD:")
    return {"answer": f"County TOD: {'Yes' if in_tod else 'No'}",
            "state": "JUDGMENT",
            "notes": f"{t['answer']}. County uses Transit Oriented Districts rather than City TOC tiers; "
                     f"confirm transit-based incentives (density bonus / state law) against the current "
                     f"County DRP determination. Source: LA County DRP TOD (Open_Data L23)."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "1550 E Slauson Ave, Los Angeles, CA 90011")
    rec = _city_record(g)
    print(json.dumps({"city_record": rec, "is_unincorporated": is_unincorporated(g)}, indent=2))
    if not is_unincorporated(g):
        print("off unincorporated LA County — LA County block routes to local jurisdiction")
        sys.exit(0)
    for fid, fn in {"zoning": zoning, "specific_plan_overlay": specific_plan_overlay,
                    "council_supervisor_district": supervisor_district,
                    "toc_tier_la": tod, "half_mile_major_transit": half_mile_major_transit,
                    "tier_transit_verification": tier_transit_verification}.items():
        try:
            print(fid, "->", json.dumps(fn(g)))
        except Exception as e:
            print(fid, "ERR", e)
