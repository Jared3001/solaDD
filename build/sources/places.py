#!/usr/bin/env python3
"""
places.py — proximity readers (nearest_* fields, Tier-A via OpenStreetMap).

Each "nearest X" field = the closest amenity of a type to the parcel, by straight-
line distance. Source: OpenStreetMap via the Overpass API (free, no key). The
geocoder gives lat/lon; we query Overpass `around` and pick the nearest match.

OSM is community data — completeness varies, so these are informational reads
(Source: OpenStreetMap) rather than authoritative designations. A Google Places
backend could be swapped in later (needs an API key) for the same field set.
"""
import json
import urllib.parse
import urllib.request

import _arcgis as ag   # for haversine_m

OVERPASS_ENDPOINTS = ["https://overpass-api.de/api/interpreter",
                      "https://overpass.kumi.systems/api/interpreter"]
HEADERS = {"User-Agent": "solaDD/1.0 (DD automation)", "Accept": "application/json",
           "Content-Type": "application/x-www-form-urlencoded"}


def _overpass(selectors, lat, lon, radius):
    body = "".join(f"{s}(around:{radius},{lat},{lon});" for s in selectors)
    q = f"[out:json][timeout:25];({body});out center tags;"
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=data, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("elements", [])
        except Exception as e:
            last = e
    raise RuntimeError(f"Overpass query failed on all endpoints: {last}")


def _nearest(geo, selectors, label, radii=(1600, 4800)):
    lon, lat = geo["lon"], geo["lat"]
    for radius in radii:
        best, best_d = None, None
        for e in _overpass(selectors, lat, lon, radius):
            elat = e.get("lat") or (e.get("center") or {}).get("lat")
            elon = e.get("lon") or (e.get("center") or {}).get("lon")
            if elat is None or elon is None:
                continue
            d = ag.haversine_m(lon, lat, elon, elat)
            if best_d is None or d < best_d:
                best, best_d = e, d
        if best is not None:
            name = (best.get("tags") or {}).get("name") or f"unnamed {label}"
            return {"answer": f"{name} — {best_d:.0f} m ({best_d / 1609:.2f} mi)",
                    "notes": f"Nearest {label}: {name}, {best_d:.0f} m ({best_d / 1609:.2f} mi). Source: OpenStreetMap."}
    return {"answer": f"None within {radii[-1] / 1609:.1f} mi",
            "notes": f"No {label} found within {radii[-1] / 1609:.1f} mi. Source: OpenStreetMap."}


def nearest_bus_stop(geo):
    return _nearest(geo, ["node[highway=bus_stop]", "node[public_transport=platform][bus=yes]"],
                    "bus stop", radii=(800, 1600))


def nearest_grocery_store(geo):
    return _nearest(geo, ["nwr[shop=supermarket]", "nwr[shop=grocery]"], "grocery store")


def nearest_park(geo):
    return _nearest(geo, ["nwr[leisure=park]"], "park")


def nearest_medical_clinic(geo):
    return _nearest(geo, ["nwr[amenity=clinic]", "nwr[amenity=doctors]", "nwr[healthcare=clinic]"],
                    "medical clinic")


def nearest_library(geo):
    return _nearest(geo, ["nwr[amenity=library]"], "library")


def nearest_pharmacy(geo):
    return _nearest(geo, ["nwr[amenity=pharmacy]"], "pharmacy")


def nearest_school(geo):
    return _nearest(geo, ["nwr[amenity=school]"], "school")


def nearest_qualifying_transit_stop(geo):
    # "qualifying / major transit stop" proxy: nearest rail / metro / light-rail station
    return _nearest(geo, ["nwr[railway=station]", "nwr[station=subway]", "nwr[station=light_rail]",
                          "nwr[railway=halt]", "node[public_transport=station][train=yes]"],
                    "rail / major transit station", radii=(1600, 6400))


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    for fn in (nearest_bus_stop, nearest_grocery_store, nearest_park, nearest_medical_clinic,
               nearest_library, nearest_pharmacy, nearest_school, nearest_qualifying_transit_stop):
        try:
            print(f"{fn.__name__:32} {fn(g)['answer']}")
        except Exception as e:
            print(f"{fn.__name__:32} ERROR {e}")
