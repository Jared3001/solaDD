#!/usr/bin/env python3
"""
_arcgis.py — shared ArcGIS REST query helper for the Tier-A readers.

Every CA/federal hazard source behind the agency map viewers exposes an ArcGIS
REST `query` endpoint. This wraps the two query shapes we use — point-intersect
(is the parcel inside this polygon?) and proximity (what point features are
within N metres?) — plus a User-Agent (some services reset bare urllib), a small
retry, and ArcGIS error surfacing. Each source module then only encodes its
endpoint + how to read the attributes into the {"answer","notes"} contract that
runner.run_field consumes. A raised exception -> runner records TOOL-FAIL.
"""
import json, math, time, urllib.parse, urllib.request

UA = "Mozilla/5.0 (solaDD Tier-A reader)"


def query(service, layer, *, lon=None, lat=None, where=None, out_fields="*",
          distance=None, return_geometry=False, out_sr=4326, timeout=30, tries=3):
    """Run an ArcGIS REST query; return the features list (raises on failure).

    where=...  -> attribute query (e.g. GEOID membership), no geometry.
    lon/lat    -> point-intersect query; add distance (metres) for proximity.
    """
    params = {"outFields": out_fields,
              "returnGeometry": "true" if return_geometry else "false",
              "f": "json"}
    if where is not None:
        params["where"] = where
    else:
        if lon is None or lat is None:
            raise ValueError("query needs either where= or lon/lat")
        params.update({"geometry": f"{lon},{lat}",
                       "geometryType": "esriGeometryPoint",
                       "inSR": "4326",
                       "spatialRel": "esriSpatialRelIntersects"})
        if distance:
            params.update({"distance": str(distance), "units": "esriSRUnit_Meter"})
    if return_geometry:
        params["outSR"] = str(out_sr)
    url = f"{service}/{layer}/query?{urllib.parse.urlencode(params)}"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            if isinstance(data, dict) and "error" in data:
                e = data["error"]
                raise RuntimeError(f"ArcGIS error {e.get('code')}: {e.get('message')}")
            return data.get("features", [])
        except Exception as exc:
            last = exc
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{service}/{layer} query failed after {tries} tries: {last}")


def haversine_m(lon1, lat1, lon2, lat2):
    """Great-circle distance in metres."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def ring_area(rings):
    """|shoelace area| of an ArcGIS polygon's rings. Coordinates MUST be in a
    projected SR (e.g. EPSG:2229 US ft) for the result to be a real area — lon/lat
    degrees will not give a meaningful value."""
    total = 0.0
    for ring in rings or []:
        s = 0.0
        for i in range(len(ring) - 1):
            s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        total += s / 2.0
    return abs(total)


def nearest(features, lon, lat):
    """Return (feature, distance_m) for the nearest point feature (needs geometry).

    Returns (None, None) when the list is empty / carries no point geometry.
    """
    best, best_d = None, None
    for f in features:
        g = f.get("geometry") or {}
        if "x" not in g or "y" not in g:
            continue
        d = haversine_m(lon, lat, g["x"], g["y"])
        if best_d is None or d < best_d:
            best, best_d = f, d
    return best, best_d
