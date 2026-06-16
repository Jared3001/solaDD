#!/usr/bin/env python3
"""
sd_parcel.py — San Diego County parcel keystone (apn, land_sf, assemblage-by-APN).

The San Diego analog of LA's parcel.py / LA City Parcels. Source: SANDAG's
countywide Hosted/Parcels layer (confirmed live 2026-06-16), keyed by APN, with
structured situs fields and polygon geometry in EPSG:2230 (CA State Plane Zone VI,
US survey ft) — so polygon area comes out in sq ft, exactly like LA's EPSG:2229.

Snap is address-aware (same street + closest house number within a buffer),
falling back to nearest-parcel-by-centroid — mirroring parcel._county_snap. The
geocoder is block-level and can land ~80 m off the lot, so we never trust the
bare point; we resolve the parcel by situs address.
"""
import re

import _arcgis as ag
from zimas import _addr_parts

PARCELS = "https://geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer"
LAYER = 0
SR = 2230   # CA State Plane Zone VI (US ft) -> polygon area is sq ft, like LA's 2229


def _fmt(apn):
    """'4531221000' -> '453-122-10-00' (San Diego County Assessor display format)."""
    a = re.sub(r"\D", "", apn or "")
    return f"{a[:3]}-{a[3:6]}-{a[6:8]}-{a[8:]}" if len(a) == 10 else (apn or None)


def _snap(geo):
    """(apn, matched) — address-aware parcel snap.

    matched=True  -> high-confidence street + closest-house-number match.
    matched=False -> nearest-parcel-by-centroid fallback (verify the APN).
    (None, None)  -> nothing found near the point."""
    lon, lat = geo["lon"], geo["lat"]
    target_no, street = _addr_parts(geo.get("matched_address") or geo.get("address") or "")
    feats = ag.query(PARCELS, LAYER, lon=lon, lat=lat, distance=150,
                     return_centroid=True, out_sr=4326,
                     out_fields="apn,situs_address,situs_street")
    rows = []
    for f in feats:
        a = f["attributes"]
        c = f.get("centroid") or {}
        hn = a.get("situs_address")
        hn = int(hn) if isinstance(hn, (int, float)) and hn else None
        d = (ag.haversine_m(lon, lat, c["x"], c["y"])
             if c.get("x") is not None and c.get("y") is not None else float("inf"))
        rows.append({"apn": a.get("apn"), "hn": hn, "d": d,
                     "street_match": bool(street and street in (a.get("situs_street") or "").upper())})
    if not rows:
        return None, None
    addr = [r for r in rows if r["street_match"] and r["hn"] is not None and target_no is not None]
    if addr:
        return min(addr, key=lambda r: (abs(r["hn"] - target_no), r["d"]))["apn"], True
    return min(rows, key=lambda r: r["d"])["apn"], False


def _area_sf(apn):
    """(gross_area_sf, n_lots) for an APN's parcel polygon(s), geometry in EPSG:2230."""
    af = ag.query(PARCELS, LAYER, where=f"apn='{apn}'", return_geometry=True,
                  out_sr=SR, out_fields="apn")
    lots = [f for f in af if f.get("geometry")]
    return sum(ag.ring_area(f["geometry"]["rings"]) for f in lots), len(lots)


def land_sf(geo) -> dict:
    apn, matched = _snap(geo)
    if not apn:
        raise LookupError("no SANDAG parcel at/near the geocoded point for land area")
    sf, n = _area_sf(apn)
    if not sf:
        raise LookupError(f"SANDAG parcel {apn} returned no geometry for area")
    flag = "" if matched else " (nearest parcel to geocoded point — VERIFY APN)"
    extra = f", {n} lots" if n > 1 else ""
    return {"answer": round(sf), "state": "VERIFIED" if matched else "JUDGMENT",
            "notes": f"Gross land area {sf:,.0f} sf from SANDAG parcel geometry (APN {_fmt(apn)}{extra}){flag}. "
                     f"GROSS — reconcile buildable vs ALTA survey. Source: SANDAG/SanGIS County Parcels (EPSG:2230)."}


def apn(geo) -> dict:
    ain, matched = _snap(geo)
    if not ain:
        raise LookupError("APN not resolved at SANDAG parcel")
    flag = "" if matched else " (nearest parcel — verify)"
    return {"answer": _fmt(ain), "state": "VERIFIED" if matched else "JUDGMENT",
            "notes": f"APN {_fmt(ain)} from SANDAG/SanGIS County Parcels{flag}. Source: SANDAG parcels."}


def parcel_info(apn_in: str) -> dict:
    """Resolve an APN to {apn, n_lots, land_sf, lon, lat} for assemblage sizing.

    Centroid of the largest lot is the representative point (lon/lat in 4326);
    geoid/tract resolution is left to the caller (geocoder.geocode_point)."""
    norm = re.sub(r"\D", "", apn_in or "")
    where = f"apn='{norm}'"
    feet = ag.query(PARCELS, LAYER, where=where, return_geometry=True, out_sr=SR, out_fields="apn")
    lots = [f for f in feet if f.get("geometry")]
    if not lots:
        raise LookupError(f"no SANDAG parcel for APN {apn_in} (apn {norm})")
    land_sf = sum(ag.ring_area(f["geometry"]["rings"]) for f in lots)
    wgs = ag.query(PARCELS, LAYER, where=where, return_centroid=True, out_sr=4326, out_fields="apn")
    cent = (wgs[0].get("centroid") if wgs else None) or {}
    return {"apn": _fmt(norm), "n_lots": len(lots), "land_sf": round(land_sf, 1),
            "lon": cent.get("x"), "lat": cent.get("y")}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "3900 30th St, San Diego, CA 92104")
    print(json.dumps({"apn": apn(g), "land_sf": land_sf(g)}, indent=2))
