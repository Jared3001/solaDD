#!/usr/bin/env python3
"""
ust.py — underground_storage_tanks reader (Tier-A proximity).

Primary (CA): the State Water Board's GeoTracker hosted layer — the authoritative,
richer CA source for LUST / cleanup sites (open AND closed). Flag "Yes" if any
UST/LUST site is within ~305 m (≈1,000 ft, the manual DD radius); report the
open/closed split and the nearest site, since for environmental DD even a CLOSED
nearby case warrants Phase I awareness.

Fallback (non-CA, or GeoTracker error): EPA UST Finder (a thinner national snapshot).
"""
import _arcgis as ag

GT = ("https://gispublic.waterboards.ca.gov/portalserver/rest/services/"
      "Hosted/geotracker_sites_download/FeatureServer")
GT_LAYER = 371
EPA = ("https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
       "UST_Finder_Feature_Layer_2/FeatureServer")
RADIUS_M = 305   # ~1,000 ft


def _is_open(status):
    return str(status or "").strip().lower().startswith("open")


def _geotracker(geo) -> dict:
    lon, lat = geo["lon"], geo["lat"]
    feats = ag.query(GT, GT_LAYER, lon=lon, lat=lat, distance=RADIUS_M, return_geometry=True, out_sr=4326,
                     out_fields="business_n,case_type,status,potential_")
    if not feats:
        return {"answer": "No", "notes": f"No GeoTracker UST/LUST cleanup sites within {RADIUS_M} m (~1,000 ft). Source: SWRCB GeoTracker."}
    openn = sum(1 for f in feats if _is_open(f["attributes"].get("status")))
    closed = len(feats) - openn
    near, nd = ag.nearest(feats, lon, lat)
    a = near["attributes"]
    nearest = f"{a.get('business_n')} [{a.get('status')}, {a.get('potential_')}], {nd:.0f} m"
    return {"answer": "Yes",
            "notes": f"{len(feats)} UST/LUST cleanup site(s) within {RADIUS_M} m (~1,000 ft): {openn} open, {closed} closed. "
                     f"Nearest: {nearest}. Phase I review recommended. Source: SWRCB GeoTracker."}


def _epa(geo) -> dict:
    lon, lat = geo["lon"], geo["lat"]
    facs = ag.query(EPA, 0, lon=lon, lat=lat, distance=RADIUS_M, return_geometry=True, out_fields="Name,Open_USTs")
    lusts = ag.query(EPA, 1, lon=lon, lat=lat, distance=RADIUS_M, return_geometry=True, out_fields="Name,Status,Substance")
    fac, fd = ag.nearest(facs, lon, lat)
    lust, ld = ag.nearest(lusts, lon, lat)
    if fac is None and lust is None:
        return {"answer": "No", "notes": f"No UST facilities or LUST sites within {RADIUS_M} m. Source: EPA UST Finder."}
    parts = []
    if fac is not None:
        parts.append(f"UST facility '{fac['attributes'].get('Name')}' {fd:.0f} m")
    if lust is not None:
        la = lust["attributes"]
        parts.append(f"LUST '{la.get('Name')}' [{la.get('Status')}] {ld:.0f} m")
    return {"answer": "Yes", "notes": "; ".join(parts) + ". Source: EPA UST Finder (non-CA fallback)."}


def underground_storage_tanks(geo) -> dict:
    if geo.get("state_fips") == "06":
        try:
            return _geotracker(geo)
        except Exception:
            pass   # GeoTracker down -> EPA fallback
    return _epa(geo)


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "18811 Colima Rd, Rowland Heights, CA")
    print(json.dumps(underground_storage_tanks(g), indent=2))
