#!/usr/bin/env python3
"""
parcel.py — land_sf reader (gross land area, Tier-A).

Gross land area from the parcel polygon (the same geometry assemblage.py sizes
blocks with):
  - LA City: LA City Parcels layer (BPP key, geometry in EPSG:2229), summed over
    the APN's lot polygon(s) — reproduces the ZIMAS lot area.
  - non-LA-City LA County: the LA County Assessor parcel polygon area at the point.
Reports GROSS; buildable (setbacks/slope) and ALTA reconciliation stay manual per
the schema guardrail. Lands VERIFIED.
"""
import _arcgis as ag
import re

import zimas

LACITY = "https://maps.lacity.org/lahub/rest/services/Landbase_Information/MapServer"
LACOUNTY = "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer"


def _county_snap(geo):
    """Pick the LA County parcel by ADDRESS (same street + closest house number,
    from the layer's structured Situs fields), else nearest by parcel centroid.
    Returns (AIN, matched) where matched=True means an address match (high
    confidence) vs a nearest-parcel fallback. (AIN, None) -> nothing found."""
    lon, lat = geo["lon"], geo["lat"]
    target_no, street = zimas._addr_parts(geo.get("matched_address") or geo.get("address") or "")
    feats = ag.query(LACOUNTY, 0, lon=lon, lat=lat, distance=150, return_geometry=False,
                     out_fields="AIN,SitusHouseNo,SitusStreet,CENTER_LON,CENTER_LAT")
    rows = []
    for f in feats:
        a = f["attributes"]
        digits = re.sub(r"\D", "", a.get("SitusHouseNo") or "")
        hn = int(digits) if digits else None
        clon, clat = a.get("CENTER_LON"), a.get("CENTER_LAT")
        d = ag.haversine_m(lon, lat, clon, clat) if (clon and clat) else float("inf")
        rows.append({"ain": a.get("AIN"), "hn": hn, "d": d,
                     "street_match": bool(street and street in (a.get("SitusStreet") or "").upper())})
    if not rows:
        return None, None
    addr = [r for r in rows if r["street_match"] and r["hn"] is not None and target_no is not None]
    if addr:
        return min(addr, key=lambda r: (abs(r["hn"] - target_no), r["d"]))["ain"], True
    return min(rows, key=lambda r: r["d"])["ain"], False


def _county_area_sf(ain):
    """Gross area (sq ft) of an AIN's parcel polygon, from geometry in EPSG:2229."""
    af = ag.query(LACOUNTY, 0, where=f"AIN='{ain}'", return_geometry=True, out_sr=2229, out_fields="AIN")
    return sum(ag.ring_area(f["geometry"]["rings"]) for f in af if f.get("geometry"))


def land_sf(geo) -> dict:
    if zimas.in_la_city(geo):
        parcel, _ = zimas._snapped(geo)
        bpp = parcel.get("BPP")
        feet = ag.query(LACITY, 5, where=f"BPP='{bpp}'", return_geometry=True, out_sr=2229, out_fields="BPP")
        lots = [f for f in feet if f.get("geometry")]
        if lots:
            sf = sum(ag.ring_area(f["geometry"]["rings"]) for f in lots)
            apn = f"{bpp[:4]}-{bpp[4:7]}-{bpp[7:]}"
            extra = f", {len(lots)} lots" if len(lots) > 1 else ""
            return {"answer": round(sf),
                    "notes": f"Gross land area {sf:,.0f} sf from LA City Parcels geometry (APN {apn}{extra}). "
                             f"GROSS — capture buildable separately (setbacks/slope); reconcile vs ALTA survey. "
                             f"Source: LA City Parcels."}
    # San Diego County -> SANDAG/SanGIS parcels (LA County layer has no SD parcels).
    from jurisdiction import _county_basename
    if _county_basename(geo) == "San Diego":
        import sd_parcel
        return sd_parcel.land_sf(geo)
    ain, matched = _county_snap(geo)
    if not ain:
        raise LookupError("no LA City/County parcel at/near the geocoded point for land area")
    sf = _county_area_sf(ain)
    flag = "" if matched else " (nearest parcel to geocoded point — VERIFY APN)"
    apn = f"{ain[:4]}-{ain[4:7]}-{ain[7:]}" if ain and len(ain) == 10 else ain
    return {"answer": round(sf), "state": "VERIFIED" if matched else "JUDGMENT",
            "notes": f"Gross land area {sf:,.0f} sf from LA County parcel geometry (APN {apn}){flag}. "
                     f"GROSS — reconcile buildable vs ALTA survey. Source: LA County Assessor parcels."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(land_sf(g), indent=2))
