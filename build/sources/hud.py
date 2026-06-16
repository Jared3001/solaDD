#!/usr/bin/env python3
"""
hud.py — qct + dda readers (HUD SADDA, Tier-A).

Source: HUD's published ArcGIS Online layers (the data behind huduser.gov/portal/
sadda), org services.arcgis.com/VTyQ9soqVukalItT. Two designation vintages are
live at once — the current year and the prior year — under fragile, sometimes
mislabeled service names (e.g. the `_2026` QCT service's *description* still reads
"for 2024"; the real year is in the layer `name`, e.g. "QUALIFIED_CENSUS_TRACTS_2026").

QCT/DDA are RE-DESIGNATED ANNUALLY (effective Jan 1) and a tract/ZCTA can flip
year to year. For a given LIHTC deal the GOVERNING designation is the one in
effect at the allocation / bond-issuance / binding-commitment year (plus HUD's
hold-harmless rule) — NOT simply the current calendar year. So we report BOTH
the current and prior year; when they differ, the field lands JUDGMENT so the
analyst confirms which year governs the deal.

QCT keyed by 11-digit GEOID; metro Small-Area DDA keyed by ZCTA5 (query by the
address ZIP, robust to an imprecise geocode point), with a point-in-polygon
fallback for county-keyed non-metro DDAs.
"""
import json
import re
import urllib.request

import _arcgis as ag

ORG = "https://services.arcgis.com/VTyQ9soqVukalItT/ArcGIS/rest/services"
# Both live vintages per program. The reader derives each layer's real year from
# its `name`; order here doesn't matter.
QCT_SVCS = [f"{ORG}/QUALIFIED_CENSUS_TRACTS_2026/FeatureServer",
            f"{ORG}/QUALIFIED_CENSUS_TRACTS/FeatureServer"]
DDA_SVCS = [f"{ORG}/Difficult_Development_Areas_2026/FeatureServer",
            f"{ORG}/Difficult_Development_Areas/FeatureServer"]
_DEAL_NOTE = ("designations are annual (effective Jan 1) and can flip year to year — "
              "the governing year for a deal is its allocation/bond/binding-commitment "
              "year (+ hold-harmless)")
_YEAR_CACHE = {}


def _zip5(geo):
    m = re.findall(r"\b(\d{5})\b", geo.get("matched_address") or "")
    return m[-1] if m else None


def _layer_year(service):
    """Real designation year from the layer's `name` (the service-name suffix and
    description are unreliable). Cached per process."""
    if service in _YEAR_CACHE:
        return _YEAR_CACHE[service]
    yr = None
    try:
        req = urllib.request.Request(service + "/0?f=json", headers={"User-Agent": ag.UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            m = re.search(r"(20\d{2})", json.load(r).get("name", "") or "")
            yr = int(m.group(1)) if m else None
    except Exception:
        yr = None
    _YEAR_CACHE[service] = yr
    return yr


def _two_year(kind, members, key_desc):
    """members: list of (year, is_member). Report current-year answer + both years;
    JUDGMENT when the two years disagree."""
    known = sorted([m for m in members if m[0]], key=lambda x: x[0], reverse=True)
    if not known:                                  # year metadata unavailable — fall back to any hit
        any_hit = any(b for _, b in members)
        return {"answer": "Yes" if any_hit else "No",
                "notes": f"{kind}: {'Yes' if any_hit else 'No'}. {key_desc}. Source: HUD SADDA."}
    cy, cb = known[0]
    parts = [f"{cy}: {'Yes' if cb else 'No'} (current)"]
    state = "VERIFIED"
    if len(known) > 1:
        py, pb = known[1]
        parts.append(f"{py}: {'Yes' if pb else 'No'}")
        if pb != cb:
            state = "JUDGMENT"
    note = f"{kind} — " + "; ".join(parts) + f". {key_desc}. NOTE: {_DEAL_NOTE}. Source: HUD SADDA."
    return {"answer": "Yes" if cb else "No", "state": state, "notes": note}


def qct(geo) -> dict:
    members = [(_layer_year(svc),
               bool(ag.query(svc, 0, where=f"GEOID='{geo['geoid']}'", out_fields="GEOID")))
              for svc in QCT_SVCS]
    return _two_year("HUD Qualified Census Tract", members, f"tract {geo['geoid']}")


def dda(geo) -> dict:
    zip5 = _zip5(geo)

    def hit(svc):
        feats = ag.query(svc, 0, where=f"ZCTA5='{zip5}'", out_fields="ZCTA5") if zip5 else []
        if not feats:   # county-keyed non-metro DDA -> point-in-polygon
            feats = ag.query(svc, 0, lon=geo["lon"], lat=geo["lat"], out_fields="ZCTA5")
        return bool(feats)

    members = [(_layer_year(svc), hit(svc)) for svc in DDA_SVCS]
    return _two_year("HUD Difficult Development Area", members,
                     f"ZIP {zip5}" if zip5 else "by parcel")


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "17719 Kinzie St, Northridge, CA 91325")
    print(json.dumps({"geoid": g["geoid"], "qct": qct(g), "dda": dda(g)}, indent=2))
