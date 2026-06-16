#!/usr/bin/env python3
"""
hud.py — qct + dda readers (HUD SADDA, Tier-A).

Source: HUD's published ArcGIS Online layers (the data behind
huduser.gov/portal/sadda). Confirmed live 2026-06-15:
  org services.arcgis.com/VTyQ9soqVukalItT
  QCT: QUALIFIED_CENSUS_TRACTS_2026/FeatureServer/0  (keyed by 11-digit GEOID)
  DDA: Difficult_Development_Areas_2026/FeatureServer/0  (metro = by ZCTA polygon)
Membership = a row exists (the layers contain only designated areas).

QCT/DDA are reissued ANNUALLY and the service name carries the year. When the
2027 designation publishes, bump YEAR (confirm the new service name via
.../VTyQ9soqVukalItT/ArcGIS/rest/services?f=json — the suffix pattern is not
stable across years).
"""
import re

import _arcgis as ag

ORG = "https://services.arcgis.com/VTyQ9soqVukalItT/ArcGIS/rest/services"
YEAR = 2026
QCT = f"{ORG}/QUALIFIED_CENSUS_TRACTS_{YEAR}/FeatureServer"
DDA = f"{ORG}/Difficult_Development_Areas_{YEAR}/FeatureServer"


def qct(geo) -> dict:
    feats = ag.query(QCT, 0, where=f"GEOID='{geo['geoid']}'", out_fields="GEOID")
    if feats:
        return {"answer": "Yes",
                "notes": f"In a {YEAR} HUD Qualified Census Tract (tract {geo['geoid']}). Source: HUD SADDA."}
    return {"answer": "No",
            "notes": f"Not a {YEAR} HUD QCT (tract {geo['geoid']}). Source: HUD SADDA."}


def _zip5(geo):
    m = re.findall(r"\b(\d{5})\b", geo.get("matched_address") or "")
    return m[-1] if m else None


def dda(geo) -> dict:
    # Metro Small-Area DDAs are keyed by ZCTA5 — query by the address ZIP (robust to
    # an imprecise geocode point that could fall in the wrong ZCTA polygon).
    zip5 = _zip5(geo)
    feats = ag.query(DDA, 0, where=f"ZCTA5='{zip5}'", out_fields="ZCTA5,DDA_TYPE,DDA_NAME") if zip5 else []
    if not feats:   # non-metro DDAs are county-keyed -> fall back to point-in-polygon
        feats = ag.query(DDA, 0, lon=geo["lon"], lat=geo["lat"], out_fields="ZCTA5,DDA_TYPE,DDA_NAME")
    if feats:
        a = feats[0]["attributes"]
        kind = a.get("DDA_TYPE") or ""
        name = a.get("DDA_NAME") or a.get("ZCTA5") or ""
        tag = f"{name}{' ' + kind if kind else ''}".strip()
        return {"answer": "Yes",
                "notes": f"In a {YEAR} HUD Difficult Development Area ({tag}). Source: HUD SADDA."}
    return {"answer": "No",
            "notes": f"Not a {YEAR} HUD DDA. Source: HUD SADDA."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps({"geoid": g["geoid"], "qct": qct(g), "dda": dda(g)}, indent=2))
