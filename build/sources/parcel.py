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
import zimas

LACITY = "https://maps.lacity.org/lahub/rest/services/Landbase_Information/MapServer"
LACOUNTY = "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer"


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
    lon, lat = geo["lon"], geo["lat"]
    # Select the parcel in lon/lat (point-in-parcel, else nearest within 40 m), then
    # read that AIN's polygon in EPSG:2229 (ft) for area.
    sel = ag.query(LACOUNTY, 0, lon=lon, lat=lat, return_geometry=True, out_sr=4326, out_fields="AIN")
    exact = bool([f for f in sel if f.get("geometry")])
    if not exact:
        sel = ag.query(LACOUNTY, 0, lon=lon, lat=lat, distance=40, return_geometry=True, out_sr=4326, out_fields="AIN")
    best, best_d = None, None
    for f in sel:
        rings = (f.get("geometry") or {}).get("rings") or []
        if not rings:
            continue
        pts = rings[0]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        d = ag.haversine_m(lon, lat, cx, cy)
        if best_d is None or d < best_d:
            best, best_d = f, d
    if best is None:
        raise LookupError("no LA City/County parcel polygon at/near the geocoded point for land area")
    ain = best["attributes"].get("AIN")
    af = ag.query(LACOUNTY, 0, where=f"AIN='{ain}'", return_geometry=True, out_sr=2229, out_fields="AIN")
    sf = sum(ag.ring_area(f["geometry"]["rings"]) for f in af if f.get("geometry"))
    flag = "" if exact else " (nearest parcel to geocoded point — VERIFY APN)"
    return {"answer": round(sf), "state": "VERIFIED" if exact else "JUDGMENT",
            "notes": f"Gross land area {sf:,.0f} sf from LA County parcel geometry (AIN {ain}){flag}. "
                     f"GROSS — reconcile buildable vs ALTA survey. Source: LA County Assessor parcels."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(land_sf(g), indent=2))
