#!/usr/bin/env python3
"""
ust.py — underground_storage_tanks reader (EPA UST Finder, Tier-A).

Source: EPA UST Finder ArcGIS Online, confirmed live 2026-06-15:
  services.arcgis.com/cJ9YHowT8TU7DUyn/.../UST_Finder_Feature_Layer_2/FeatureServer
  Layer 0 = regulated UST facilities, Layer 1 = LUST (leaking) cleanup sites.
  Point features (native WGS84).
Answer "Yes" if a UST facility is on/adjacent (<= FAC_M) OR an open LUST cleanup
site is within LUST_M. Nearest facility + nearest LUST reported for judgment.

EPA UST Finder is a periodic national snapshot; for CA legal DD confirm the
nearest hit against the live State Water Board GeoTracker record.
"""
import _arcgis as ag

SVC = ("https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
       "UST_Finder_Feature_Layer_2/FeatureServer")
FAC_M, LUST_M = 150, 300


def underground_storage_tanks(geo) -> dict:
    lon, lat = geo["lon"], geo["lat"]
    facs = ag.query(SVC, 0, lon=lon, lat=lat, distance=LUST_M, return_geometry=True,
                    out_fields="Name,Address,Open_USTs,Closed_USTs,Facility_Status")
    lusts = ag.query(SVC, 1, lon=lon, lat=lat, distance=LUST_M, return_geometry=True,
                     out_fields="Name,Address,Status,Substance")
    fac_feat, fac_d = ag.nearest(facs, lon, lat)
    lust_feat, lust_d = ag.nearest(lusts, lon, lat)
    parts, yes = [], False
    if fac_feat is not None:
        fa = fac_feat["attributes"]
        if fac_d <= FAC_M:
            yes = True
        parts.append(f"nearest UST facility '{fa.get('Name')}' ({fa.get('Open_USTs')} open tanks), {fac_d:.0f} m")
    if lust_feat is not None:
        la = lust_feat["attributes"]
        open_near = str(la.get("Status") or "").startswith("Open") and lust_d <= LUST_M
        if open_near:
            yes = True
        meta = ", ".join(str(la[k]) for k in ("Status", "Substance") if la.get(k))
        parts.append(f"nearest LUST '{la.get('Name')}' [{meta}], {lust_d:.0f} m")
    if not parts:
        return {"answer": "No", "notes": f"No UST facilities or LUST sites within {LUST_M} m. Source: EPA UST Finder."}
    return {"answer": "Yes" if yes else "No",
            "notes": "; ".join(parts) + ". Source: EPA UST Finder (confirm CA hits via GeoTracker)."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps(underground_storage_tanks(g), indent=2))
