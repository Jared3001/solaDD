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

NOTE: layer ids confirmed live 2026-06-15 (28=Flood Hazard Zones, 3=FIRM
Panels); requires outbound HTTPS to hazards.fema.gov. Shares _arcgis.query with
the other readers (User-Agent + retry — hazards.fema.gov resets bare clients).
"""
import datetime, json

import _arcgis as ag

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


def flood_zone(lon: float, lat: float) -> dict:
    """Returns answer for the flood_zone cell + a Notes string."""
    feats = ag.query(NFHL, LAYER_FLOOD, lon=lon, lat=lat, out_fields="FLD_ZONE,SFHA_TF,ZONE_SUBTY")
    if not feats:
        return {"answer": "No", "notes": "Zone X — outside SFHA (no flood-hazard polygon at parcel). Source: FEMA NFHL REST."}
    a = feats[0]["attributes"]
    in_sfha = a.get("SFHA_TF") == "T"
    panel = ag.query(NFHL, LAYER_PANEL, lon=lon, lat=lat, out_fields="FIRM_PAN,EFF_DATE")
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
