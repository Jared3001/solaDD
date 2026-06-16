#!/usr/bin/env python3
"""
sandiego.py — City-of-San-Diego municipal zoning/transit/historic block (the SD
analog of zimas.py). Tier-A: the City's own data is published as open, no-auth
ArcGIS REST layers on webmaps.sandiego.gov (confirmed live 2026-06-16).

Services used:
  DoIT_Public/DoIT_Public/MapServer      5 Council District (DISTRICT/NAME) ·
                                         7 City Boundary (City-of-SD gate)
  Planning/PLN_LongRangePlanning/MS     27 Base Zones (ZONE_NAME)
  DSD/Zoning_Overlay/MapServer          0-11 overlay zones (Coastal, CPIOZ,
                                         Transit Area, Urban Village, height, ...)
  Planning/Historic_Preservation_Resources/MS
                                         0 HRB designated resources (feature_nm) ·
                                         2 Historic districts (NAME)
  Planning/PLN_TransitPriorityArea/MS    0 Transit Priority Areas (SB743 TPA =
                                         within ½ mi of a major transit stop)

Jurisdiction: webmaps.sandiego.gov is CITY-OF-SAN-DIEGO ONLY. Each reader first
confirms the point is inside the City boundary (layer 7); off the City (other
SD-County cities, unincorporated county) it raises -> the field routes to manual
(local planning / county), never an invented "None"/"No". This mirrors how the
ZIMAS block routes non-LA-City parcels to local planning.

Point queries use a small distance buffer (some hosted polygon services don't
return a polygon on a bare point); the geocoded point is accurate enough for
overlay/district intersects (unlike parcel snapping, which sd_parcel handles).
"""
import _arcgis as ag

WEBMAPS = "https://webmaps.sandiego.gov/arcgis/rest/services"
DOIT = f"{WEBMAPS}/DoIT_Public/DoIT_Public/MapServer"
ZONE = f"{WEBMAPS}/Planning/PLN_LongRangePlanning/MapServer"
OVERLAY = f"{WEBMAPS}/DSD/Zoning_Overlay/MapServer"
HIST = f"{WEBMAPS}/Planning/Historic_Preservation_Resources/MapServer"
TPA = f"{WEBMAPS}/Planning/PLN_TransitPriorityArea/MapServer"

L_CD, L_CITYBND = 5, 7
L_ZONE = 27
L_HRB, L_HIST_DIST = 0, 2
L_TPA = 0
_BUF = 5   # tiny buffer (m) so point-on-boundary still returns the polygon

# Overlay sub-layers + a readable label (the layer name is the overlay name).
OVERLAY_LAYERS = {
    0: "Clairemont Mesa Height Limitation Overlay Zone",
    1: "Coastal Height Limitation Overlay Zone",
    2: "Coastal Overlay Zone",
    3: "Community Plan Implementation Overlay Zone (CPIOZ)",
    4: "Mission Trails Design District",
    5: "Mobile Home Park Overlay Zone",
    7: "Parking Impact Overlay Zone",
    8: "Residential Tandem Parking Overlay Zone",
    9: "Transit Area Overlay Zone",
    10: "Urban Village Overlay Zone",
    11: "Community Enhancement Overlay Zone",
}


def _in_city(geo) -> bool:
    """Point inside the City of San Diego boundary (layer 7)."""
    feats = ag.query(DOIT, L_CITYBND, lon=geo["lon"], lat=geo["lat"],
                     out_fields="Name", distance=_BUF)
    return bool(feats)


def _require_city(geo):
    if not _in_city(geo):
        raise LookupError("point is not within the City of San Diego "
                          "(webmaps.sandiego.gov is City-only) — route to the local jurisdiction")


# ---- field readers (each returns {"answer","notes"} or raises -> TOOL-FAIL) ----

def zoning(geo) -> dict:
    _require_city(geo)
    feats = ag.query(ZONE, L_ZONE, lon=geo["lon"], lat=geo["lat"],
                     out_fields="ZONE_NAME", distance=_BUF)
    if not feats:
        raise LookupError("no City of San Diego base-zone polygon at the point")
    z = feats[0]["attributes"].get("ZONE_NAME")
    return {"answer": z,
            "notes": f"Base zone {z}. Source: City of San Diego Base Zones "
                     f"(PLN_LongRangePlanning L27)."}


def specific_plan_overlay(geo) -> dict:
    _require_city(geo)
    hits = []
    for lyr, label in OVERLAY_LAYERS.items():
        feats = ag.query(OVERLAY, lyr, lon=geo["lon"], lat=geo["lat"],
                         out_fields="*", distance=_BUF)
        if feats:
            zn = feats[0]["attributes"].get("ZONENAME")
            hits.append(f"{label}" + (f" ({zn})" if zn else ""))
    if not hits:
        return {"answer": "None",
                "notes": "Not within any City of San Diego zoning overlay zone. "
                         "Source: City of San Diego Zoning Overlay."}
    names = "; ".join(hits)
    return {"answer": names,
            "notes": f"Overlay zone(s): {names}. Source: City of San Diego Zoning Overlay."}


def council_district(geo) -> dict:
    _require_city(geo)
    feats = ag.query(DOIT, L_CD, lon=geo["lon"], lat=geo["lat"],
                     out_fields="DISTRICT,NAME", distance=_BUF)
    if not feats:
        raise LookupError("no City of San Diego council district polygon at the point")
    a = feats[0]["attributes"]
    d, member = a.get("DISTRICT"), a.get("NAME")
    member_str = f" — Councilmember {member}" if member else ""
    return {"answer": f"Council District {d}",
            "notes": f"City of San Diego Council District {d}{member_str}. "
                     f"Source: City of San Diego Council Districts (DoIT_Public L5)."}


def historic_status(geo) -> dict:
    _require_city(geo)
    hrb = ag.query(HIST, L_HRB, lon=geo["lon"], lat=geo["lat"],
                   out_fields="feature_nm,feature_de", distance=_BUF)
    dist = ag.query(HIST, L_HIST_DIST, lon=geo["lon"], lat=geo["lat"],
                    out_fields="NAME", distance=_BUF)
    tags = []
    if hrb:
        nm = hrb[0]["attributes"].get("feature_nm") or hrb[0]["attributes"].get("feature_de") or "listed"
        tags.append(f"HRB-designated historical resource ({nm})")
    if dist:
        nm = dist[0]["attributes"].get("NAME") or "district"
        tags.append(f"Historic district ({nm})")
    if tags:
        return {"answer": "Yes",
                "notes": "; ".join(tags) + ". Confirm parcel-level designation/eligibility against the "
                         "City Historical Resources Database. Source: City of San Diego Historic Preservation Resources."}
    return {"answer": "No",
            "notes": "Not an HRB-designated resource and not within a historic district. "
                     "Pre-1979 structures may still require a historical review; confirm via the City "
                     "Historical Resources Database. Source: City of San Diego Historic Preservation Resources."}


def transit_priority_area(geo) -> dict:
    """SD Transit Priority Area (SB743). TPA = within ½ mile of an existing/planned
    major transit stop, so this is the SD analog of the LA TOC tier cell."""
    _require_city(geo)
    feats = ag.query(TPA, L_TPA, lon=geo["lon"], lat=geo["lat"],
                     out_fields="NAME", distance=_BUF)
    if not feats:
        return {"answer": "Not in a TPA",
                "notes": "Not within a City of San Diego Transit Priority Area (SB743). "
                         "Source: City of San Diego Transit Priority Areas."}
    return {"answer": "Transit Priority Area (TPA)",
            "notes": "Within a City of San Diego Transit Priority Area (SB743 — i.e. within ½ mile "
                     "of a major transit stop). Source: City of San Diego Transit Priority Areas."}


def half_mile_major_transit(geo) -> dict:
    """½-mile-from-major-transit. The SB743 Transit Priority Area is, by definition,
    the area within ½ mile of an existing/planned major transit stop, so TPA
    membership answers this directly (no separate SD major-transit-stops point
    layer is published live)."""
    _require_city(geo)
    feats = ag.query(TPA, L_TPA, lon=geo["lon"], lat=geo["lat"],
                     out_fields="NAME", distance=_BUF)
    if feats:
        return {"answer": "Yes",
                "notes": "Within a Transit Priority Area (SB743), i.e. within ½ mile of an existing/planned "
                         "major transit stop. Source: City of San Diego Transit Priority Areas."}
    return {"answer": "No",
            "notes": "Not within a Transit Priority Area (SB743), i.e. not within ½ mile of a major "
                     "transit stop. Source: City of San Diego Transit Priority Areas."}


def tier_transit_verification(geo) -> dict:
    """SD Tier/Transit verification — summarizes the TPA finding into one
    verification line (the SD analog of the LA TOC+½-mile summary). Confirm formal
    density-bonus / SB transit eligibility against the current City determination."""
    tpa = transit_priority_area(geo)
    in_tpa = tpa["answer"].startswith("Transit")
    return {"answer": f"TPA: {'Yes' if in_tpa else 'No'}",
            "notes": f"City of San Diego Transit Priority Area (SB743): {'Yes' if in_tpa else 'No'} "
                     f"(= {'within' if in_tpa else 'not within'} ½ mile of a major transit stop). "
                     f"Confirm formal transit-based eligibility (density bonus / state law) against the "
                     f"current City determination. Source: City of San Diego Transit Priority Areas."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "525 B St, San Diego, CA 92101")
    if not _in_city(g):
        print(json.dumps({"in_city_of_sd": False,
                          "note": "off City of San Diego — SD block routes to local jurisdiction"}, indent=2))
        sys.exit(0)
    out = {"in_city_of_sd": True}
    for fid, fn in {"zoning": zoning, "specific_plan_overlay": specific_plan_overlay,
                    "council_supervisor_district": council_district,
                    "historic_status": historic_status,
                    "toc_tier_la": transit_priority_area,
                    "half_mile_major_transit": half_mile_major_transit,
                    "tier_transit_verification": tier_transit_verification}.items():
        try:
            out[fid] = fn(g)
        except Exception as e:
            out[fid] = {"error": str(e)}
    print(json.dumps(out, indent=2))
