#!/usr/bin/env python3
"""
places.py — proximity readers (nearest_* fields, Tier-A via OpenStreetMap).

Each "nearest X" field = the closest amenity of a type to the parcel, by straight-
line distance. Source: OpenStreetMap via the Overpass API (free, no key).

All 8 categories are fetched in ONE combined Overpass query per parcel (each
selector carries its own search radius), then classified by tag and reduced to the
nearest per category. The result is cached per coordinate with a per-key lock, so
the 8 field-readers in one collect run share a single HTTP call, while different
parcels (assemblage) still fetch in parallel.

OSM is community data — completeness varies, so these are informational reads
(Source: OpenStreetMap). A Google Places backend could be swapped in later.
"""
import json
import threading
import urllib.parse
import urllib.request

import _arcgis as ag   # for haversine_m

OVERPASS_ENDPOINTS = ["https://overpass-api.de/api/interpreter",
                      "https://overpass.kumi.systems/api/interpreter"]
HEADERS = {"User-Agent": "solaDD/1.0 (DD automation)", "Accept": "application/json",
           "Content-Type": "application/x-www-form-urlencoded"}

# (field id, label, radius_m, overpass selectors, tag predicate)
_CATS = [
    ("nearest_bus_stop", "bus stop", 1600,
     ["node[highway=bus_stop]", "node[public_transport=platform][bus=yes]"],
     lambda t: t.get("highway") == "bus_stop"
     or (t.get("public_transport") in ("platform", "stop_position") and t.get("bus") == "yes")),
    ("nearest_grocery_store", "grocery store", 4800,
     ["nwr[shop=supermarket]", "nwr[shop=grocery]"],
     lambda t: t.get("shop") in ("supermarket", "grocery")),
    ("nearest_park", "park", 4800, ["nwr[leisure=park]"],
     lambda t: t.get("leisure") == "park"),
    ("nearest_medical_clinic", "medical clinic", 4800,
     ["nwr[amenity=clinic]", "nwr[amenity=doctors]", "nwr[healthcare=clinic]"],
     lambda t: t.get("amenity") in ("clinic", "doctors") or t.get("healthcare") == "clinic"),
    ("nearest_library", "library", 4800, ["nwr[amenity=library]"],
     lambda t: t.get("amenity") == "library"),
    ("nearest_pharmacy", "pharmacy", 4800, ["nwr[amenity=pharmacy]"],
     lambda t: t.get("amenity") == "pharmacy"),
    ("nearest_school", "school", 4800, ["nwr[amenity=school]"],
     lambda t: t.get("amenity") == "school"),
    ("nearest_qualifying_transit_stop", "rail / major transit station", 6400,
     ["nwr[railway=station]", "nwr[railway=halt]", "nwr[station=subway]",
      "nwr[station=light_rail]", "node[public_transport=station][train=yes]"],
     lambda t: t.get("railway") in ("station", "halt") or t.get("station") in ("subway", "light_rail")
     or t.get("public_transport") == "station"),
]

_RESULTS = {}
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _key_lock(key):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _fetch_combined(lat, lon):
    stmts = "".join(f"{s}(around:{radius},{lat},{lon});"
                    for _id, _lbl, radius, selectors, _p in _CATS for s in selectors)
    q = f"[out:json][timeout:60];({stmts});out center tags;"
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=data, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r).get("elements", [])
        except Exception as e:
            last = e
    raise RuntimeError(f"Overpass query failed on all endpoints: {last}")


def _all(geo):
    """{field_id: {answer,notes}} for all proximity categories — one HTTP call, cached."""
    key = (round(geo["lon"], 6), round(geo["lat"], 6))
    cached = _RESULTS.get(key)
    if cached is not None:
        return cached
    with _key_lock(key):
        cached = _RESULTS.get(key)
        if cached is not None:
            return cached
        lon, lat = geo["lon"], geo["lat"]
        elements = _fetch_combined(lat, lon)
        out = {}
        for fid, label, radius, _sel, pred in _CATS:
            best, best_d = None, None
            for e in elements:
                if not pred(e.get("tags") or {}):
                    continue
                elat = e.get("lat") or (e.get("center") or {}).get("lat")
                elon = e.get("lon") or (e.get("center") or {}).get("lon")
                if elat is None or elon is None:
                    continue
                d = ag.haversine_m(lon, lat, elon, elat)
                if d > radius:
                    continue
                if best_d is None or d < best_d:
                    best, best_d = e, d
            if best is not None:
                name = (best.get("tags") or {}).get("name") or f"unnamed {label}"
                out[fid] = {"answer": f"{name} — {best_d:.0f} m ({best_d / 1609:.2f} mi)",
                            "notes": f"Nearest {label}: {name}, {best_d:.0f} m ({best_d / 1609:.2f} mi). Source: OpenStreetMap."}
            else:
                out[fid] = {"answer": f"None within {radius / 1609:.1f} mi",
                            "notes": f"No {label} within {radius / 1609:.1f} mi. Source: OpenStreetMap."}
        _RESULTS[key] = out
        return out


def nearest_bus_stop(geo): return _all(geo)["nearest_bus_stop"]
def nearest_grocery_store(geo): return _all(geo)["nearest_grocery_store"]
def nearest_park(geo): return _all(geo)["nearest_park"]
def nearest_medical_clinic(geo): return _all(geo)["nearest_medical_clinic"]
def nearest_library(geo): return _all(geo)["nearest_library"]
def nearest_pharmacy(geo): return _all(geo)["nearest_pharmacy"]
def nearest_school(geo): return _all(geo)["nearest_school"]
def nearest_qualifying_transit_stop(geo): return _all(geo)["nearest_qualifying_transit_stop"]


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    for fid, res in _all(g).items():
        print(f"{fid:32} {res['answer']}")
