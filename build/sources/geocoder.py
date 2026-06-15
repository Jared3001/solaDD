#!/usr/bin/env python3
"""
geocoder.py — keystone: address -> {lat, lon, census tract, county FIPS}.

Source: U.S. Census Geocoder (free, no key). Verified contract:
  GET https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress
      ?address=<one-line>&benchmark=Public_AR_Current&vintage=Current_Current&format=json
Response: result.addressMatches[].coordinates{x:lon,y:lat}
          result.addressMatches[].geographies["Census Tracts"][0]{STATE,COUNTY,TRACT,GEOID}

NOTE: requires outbound HTTPS to geocoding.geo.census.gov — run in a networked
environment. Geocoding is block-level (approximate); for a parcel on a zone
boundary, fall back to the map.
"""
import json, urllib.parse, urllib.request

BASE = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
BENCHMARK, VINTAGE = "Public_AR_Current", "Current_Current"


def geocode(address: str, timeout: int = 30) -> dict:
    q = urllib.parse.urlencode(
        {"address": address, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json"}
    )
    with urllib.request.urlopen(f"{BASE}?{q}", timeout=timeout) as r:
        data = json.load(r)
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        raise LookupError(f"no geocoder match for {address!r}")
    m = matches[0]
    c = m["coordinates"]                                   # x=lon, y=lat
    t = m["geographies"]["Census Tracts"][0]
    return {
        "matched_address": m["matchedAddress"],
        "lat": c["y"], "lon": c["x"],
        "state_fips": t["STATE"], "county_fips": t["COUNTY"],
        "tract": t["TRACT"], "geoid": t["GEOID"],          # 11-digit tract id for HUD/TCAC/OZ lookups
    }


if __name__ == "__main__":
    import sys
    addr = " ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061"
    print(json.dumps(geocode(addr), indent=2))
