#!/usr/bin/env python3
"""
tcac.py — resource_area reader (CTCAC/HCD Opportunity Map, Tier-A).

STATEWIDE source (all 58 CA counties), confirmed live 2026-06-16. The previous
endpoint (lacda.org-hosted ArcGIS FeatureServer "2026_TCAC_HCD_Opportunity_Area_Maps")
was an LA-County-only republished copy and returned nothing outside FIPS 06037.
Every other public ArcGIS copy we found is likewise a single-county republish
(Placer, Fresno/Madera, San Diego's "Neighborhood Opportunity", etc.).

The only confirmed-statewide public source for the adopted 2026 map is the
official UC Berkeley Othering & Belonging Institute mapping tool (the data
backend the State Treasurer/CTCAC links to from treasurer.ca.gov/ctcac/opportunity),
served as a static GeoJSON — NOT an ArcGIS REST service, so this reader fetches
and indexes the GeoJSON instead of using _arcgis.ag.query. 11,337 tracts, all 58
counties (e.g. 803 in San Diego 06073, 2,519 in LA 06037).

Keyed by 11-digit census tract GEOID in property `fips` (string, leading zero
kept, e.g. '06073005301'). Category text is `oppcat` (Highest / High / Moderate /
Low Resource); a separate `pov_seg_flag`==1 marks "High Segregation & Poverty"
tracts (reported as the category, matching prior reader behaviour). `oppcat` is
null for ~665 excluded/non-residential tracts -> LookupError.

Schema change vs the old LA layer: the 2026 statewide schema dropped
`env_burden_flag` (only `env_site_score` remains), so the environmental-burden
note is no longer emitted. The companion "Neighborhood Change" data is bundled in
the same GeoJSON (field `nbrhood_chng`) but stays manual for now.

Updated annually; bump SRC/YEAR on the new map (find the new "unpacked/<id>"
under belonging.berkeley.edu's <YEAR>-ctcachcd-affh-mapping-tool page).
"""
import json, threading, urllib.request
from pathlib import Path

YEAR = 2026
# Static statewide GeoJSON behind the official 2026 OBI/CTCAC mapping tool. This is
# the SAME 39 MB file nc.py reads (it carries both oppcat and nbrhood_chng); we
# disk-cache a slim {fips: {oppcat,region,pov_seg_flag}} index under _cache/ exactly
# like nc.py, so the big download happens once and persists across processes.
SRC = ("https://belonging.berkeley.edu/sites/default/files/external_pages/"
       "unpacked/12382/data/final_2026.geojson")
UA = "Mozilla/5.0 (solaDD Tier-A reader)"
CACHE = Path(__file__).resolve().parent / "_cache" / f"tcac_{YEAR}.json"

_INDEX = None          # {fips: {oppcat, region, pov_seg_flag}}
_INDEX_LOCK = threading.Lock()


def _load_index():
    """Return {fips: slim props}, building the on-disk cache from the GeoJSON once."""
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is not None:
            return _INDEX
        if CACHE.exists():
            _INDEX = json.loads(CACHE.read_text())
            return _INDEX
        req = urllib.request.Request(SRC, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:   # ~39 MB, one-time
            data = json.load(r)
        idx = {}
        for feat in data.get("features", []):
            p = feat.get("properties") or {}
            fips = p.get("fips")
            if fips:
                idx[str(fips)] = {"oppcat": p.get("oppcat"), "region": p.get("region"),
                                  "pov_seg_flag": p.get("pov_seg_flag")}
        if not idx:
            raise RuntimeError(f"{YEAR} TCAC statewide GeoJSON had no usable features")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(idx))
        _INDEX = idx
        return _INDEX


def resource_area(geo) -> dict:
    idx = _load_index()
    p = idx.get(geo["geoid"])
    if p is None:
        raise LookupError(f"no {YEAR} TCAC opportunity polygon for tract {geo['geoid']}")
    cat = p.get("oppcat")
    seg = p.get("pov_seg_flag") in (1, 1.0)
    if not cat and not seg:
        # excluded / non-residential tract: legitimately no category
        raise LookupError(f"tract {geo['geoid']} has no {YEAR} TCAC resource category")
    if seg:
        cat = "High Segregation & Poverty"
    region = p.get("region") or ""
    note = f"{cat} ({YEAR} CTCAC/HCD map, {region}; tract {geo['geoid']})"
    if seg:
        note += "; High Segregation & Poverty flag"
    note += ". Source: CTCAC/HCD Opportunity Map (statewide)."
    return {"answer": cat, "notes": note}


if __name__ == "__main__":
    import sys, json as _json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(_json.dumps(resource_area(g), indent=2))
