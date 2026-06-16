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
NOMINATIM = "https://nominatim.openstreetmap.org/search"
BENCHMARK, VINTAGE = "Public_AR_Current", "Current_Current"


def _nominatim(address, timeout=30):
    """OSM fallback geocoder for addresses the Census geocoder can't match.
    Returns (lon, lat, display_name) or None."""
    q = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1, "countrycodes": "us"})
    req = urllib.request.Request(f"{NOMINATIM}?{q}", headers={"User-Agent": "solaDD/1.0 (DD automation)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except Exception:
        return None
    if not d:
        return None
    return float(d[0]["lon"]), float(d[0]["lat"]), d[0].get("display_name")


def _get_json(url, timeout=30, tries=3):
    """GET + parse JSON with a small retry — the Census geocoder is the keystone
    and intermittently 502s/resets, which should not fail the whole run."""
    import time
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (solaDD)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"census geocoder failed after {tries} tries: {last}")


def _place(geographies):
    """Incorporated city name (suffix stripped), or None if unincorporated."""
    ip = geographies.get("Incorporated Places", [])
    if not ip:
        return None
    name = ip[0].get("NAME", "")
    for suf in (" city", " town", " village", " CDP"):
        if name.endswith(suf):
            name = name[: -len(suf)]
            break
    return name or None


def geocode(address: str, timeout: int = 30) -> dict:
    q = urllib.parse.urlencode(
        {"address": address, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json"}
    )
    data = _get_json(f"{BASE}?{q}", timeout)
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        # Census couldn't match — fall back to OSM for lon/lat, then resolve the
        # census tract from those coordinates (tract is what HUD/OZ/TCAC/NC need).
        nm = _nominatim(address, timeout)
        if nm:
            lon, lat, _disp = nm
            geo = geocode_point(lon, lat, timeout)
            geo["matched_address"] = address   # keep the input (has the house number) for parcel matching
            return geo
        raise LookupError(f"no geocoder match for {address!r}")
    m = matches[0]
    c = m["coordinates"]                                   # x=lon, y=lat
    t = m["geographies"]["Census Tracts"][0]
    return {
        "matched_address": m["matchedAddress"],
        "lat": c["y"], "lon": c["x"],
        "state_fips": t["STATE"], "county_fips": t["COUNTY"],
        "tract": t["TRACT"], "geoid": t["GEOID"],          # 11-digit tract id for HUD/TCAC/OZ lookups
        "place": _place(m["geographies"]),                 # incorporated city (None = unincorporated)
    }


def geocode_point(lon: float, lat: float, timeout: int = 30) -> dict:
    """Reverse the keystone: lon/lat -> census tract (for parcels resolved by APN,
    which have a centroid but no address). Same shape as geocode()."""
    q = urllib.parse.urlencode(
        {"x": lon, "y": lat, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json"}
    )
    data = _get_json(f"{COORD}?{q}", timeout)
    geos = data.get("result", {}).get("geographies", {})
    tracts = geos.get("Census Tracts", [])
    if not tracts:
        raise LookupError(f"no census tract for point ({lat},{lon})")
    t = tracts[0]
    return {
        "matched_address": f"({lat:.6f},{lon:.6f})",
        "lat": lat, "lon": lon,
        "state_fips": t["STATE"], "county_fips": t["COUNTY"],
        "tract": t["TRACT"], "geoid": t["GEOID"],
        "place": _place(geos),
    }


if __name__ == "__main__":
    import sys
    addr = " ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061"
    print(json.dumps(geocode(addr), indent=2))
