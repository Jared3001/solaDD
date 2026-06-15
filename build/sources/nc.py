#!/usr/bin/env python3
"""
nc.py — neighborhood_change_area reader (CTCAC/HCD AFFH, Tier-A via bulk file).

The TCAC/HCD "Neighborhood Change" map is NOT a queryable REST service — it's a
Mapbox app backed by a single static statewide GeoJSON. We download it ONCE,
cache a slim {fips: nbrhood_chng} map under _cache/, and look up by census tract
GEOID. nbrhood_chng: 1 = Yes (designated Neighborhood Change Area), 0/null = No.

VINTAGE: the source URL carries a per-release asset path ('unpacked/12382'); on a
new map release, bump NC_URL/VINTAGE (rediscover it from the Berkeley AFFH tool's
embed). The cache file name carries the vintage so a new year rebuilds cleanly.
"""
import json
import urllib.request
from pathlib import Path

VINTAGE = "2026"
NC_URL = ("https://belonging.berkeley.edu/sites/default/files/external_pages/"
          "unpacked/12382/data/final_2026.geojson")
CACHE = Path(__file__).resolve().parent / "_cache" / f"nc_{VINTAGE}.json"
_MAP = None


def _load():
    """Return {fips: nbrhood_chng}, building the on-disk cache from the GeoJSON once."""
    global _MAP
    if _MAP is not None:
        return _MAP
    if CACHE.exists():
        _MAP = json.loads(CACHE.read_text())
        return _MAP
    req = urllib.request.Request(NC_URL, headers={"User-Agent": "Mozilla/5.0 (solaDD)"})
    with urllib.request.urlopen(req, timeout=300) as r:   # ~39 MB, one-time
        data = json.load(r)
    m = {}
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        fips = p.get("fips")
        if fips is not None:
            m[str(fips)] = p.get("nbrhood_chng")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(m))
    _MAP = m
    return m


def neighborhood_change(geo) -> dict:
    m = _load()
    geoid = str(geo["geoid"])
    v = m.get(geoid)
    yes = v in (1, 1.0)
    if geoid in m:
        note = (f"nbrhood_chng={v} for tract {geoid} ({VINTAGE} CTCAC/HCD AFFH Neighborhood Change; "
                f"1=Yes, 0/null=No). Source: CTCAC/HCD AFFH (UC Berkeley OBI).")
    else:
        note = (f"Tract {geoid} absent from the {VINTAGE} Neighborhood Change dataset — not designated. "
                f"Source: CTCAC/HCD AFFH (UC Berkeley OBI).")
    return {"answer": "Yes" if yes else "No", "notes": note}


if __name__ == "__main__":
    import sys, json as _j
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(_j.dumps(neighborhood_change(g), indent=2))
