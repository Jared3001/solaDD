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
COORD = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
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


def geocode_point(lon: float, lat: float, timeout: int = 30) -> dict:
    """Reverse the keystone: lon/lat -> census tract (for parcels resolved by APN,
    which have a centroid but no address). Same shape as geocode()."""
    q = urllib.parse.urlencode(
        {"x": lon, "y": lat, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json"}
    )
    with urllib.request.urlopen(f"{COORD}?{q}", timeout=timeout) as r:
        data = json.load(r)
    tracts = data.get("result", {}).get("geographies", {}).get("Census Tracts", [])
    if not tracts:
        raise LookupError(f"no census tract for point ({lat},{lon})")
    t = tracts[0]
    return {
        "matched_address": f"({lat:.6f},{lon:.6f})",
        "lat": lat, "lon": lon,
        "state_fips": t["STATE"], "county_fips": t["COUNTY"],
        "tract": t["TRACT"], "geoid": t["GEOID"],
    }


if __name__ == "__main__":
    import sys
    addr = " ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061"
    print(json.dumps(geocode(addr), indent=2))
