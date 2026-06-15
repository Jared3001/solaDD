#!/usr/bin/env python3
"""
fema.py — flood_zone reader (reference Tier-A source).

Source: FEMA official NFHL ArcGIS REST (free, no key). Verified service:
  https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer
Layers used: 28 = flood hazard areas (FLD_ZONE, SFHA_TF, ZONE_SUBTY),
             3  = FIRM panels (FIRM_PAN, EFF_DATE).
Point query returns the polygon at the parcel as JSON — no PDF, no viewer.

Maps to schema field `flood_zone`: Yes/No cell = inside/outside SFHA;
zone + panel + effective date go to Notes.

NOTE: layer ids should be confirmed against the live service on first run
(ArcGIS layer ordering can change); requires outbound HTTPS to hazards.fema.gov.
"""
import datetime, json, urllib.parse, urllib.request

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
LAYER_FLOOD, LAYER_PANEL = 28, 3   # confirmed live 2026-06-15: 28=Flood Hazard Zones, 3=FIRM Panels


def _fmt_eff_date(v):
    """NFHL EFF_DATE is epoch milliseconds; render as ISO date for the Notes cell."""
    if v in (None, ""):
        return None
    try:
        return datetime.datetime.fromtimestamp(int(v) / 1000, datetime.timezone.utc).date().isoformat()
    except (ValueError, TypeError, OSError):
        return str(v)


def _point_query(layer: int, lon: float, lat: float, out_fields: str, timeout: int = 30) -> list:
    params = {
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields,
        "returnGeometry": "false", "f": "json",
    }
    url = f"{NFHL}/{layer}/query?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.load(r)
    if "error" in data:
        raise RuntimeError(f"NFHL layer {layer} error: {data['error']}")
    return data.get("features", [])


def flood_zone(lon: float, lat: float) -> dict:
    """Returns answer for the flood_zone cell + a Notes string."""
    feats = _point_query(LAYER_FLOOD, lon, lat, "FLD_ZONE,SFHA_TF,ZONE_SUBTY")
    if not feats:
        return {"answer": "No", "notes": "Zone X — outside SFHA (no flood-hazard polygon at parcel). Source: FEMA NFHL REST."}
    a = feats[0]["attributes"]
    in_sfha = a.get("SFHA_TF") == "T"
    panel = _point_query(LAYER_PANEL, lon, lat, "FIRM_PAN,EFF_DATE")
    pa = panel[0]["attributes"] if panel else {}
    note = (f"Zone {a.get('FLD_ZONE')}"
            + (f" ({a.get('ZONE_SUBTY')})" if a.get("ZONE_SUBTY") else "")
            + f"; FIRM panel {pa.get('FIRM_PAN')}, eff. {_fmt_eff_date(pa.get('EFF_DATE'))}. Source: FEMA NFHL REST.")
    return {"answer": "Yes" if in_sfha else "No", "notes": note}


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps({**g, **flood_zone(g["lon"], g["lat"])}, indent=2))
