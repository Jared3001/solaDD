#!/usr/bin/env python3
"""
rentcast.py — rental-listing client for the comp-collection stage (Tier-B source).

Pulls nearby long-term rental listings from the RentCast API and normalizes them
to a flat dict the comp grid understands. RentCast is the *prototype* backend
(free tier: 50 calls/mo, https://www.rentcast.io/pricing); the multifamily-native
path (HelloData) can be swapped in behind the same normalize() contract later.

Contract (verified 2026-06 against developers.rentcast.io):
  GET https://api.rentcast.io/v1/listings/rental/long-term
      ?latitude=&longitude=&radius=&propertyType=&bedrooms=&status=Active&limit=
  Header: X-Api-Key: <key>
  -> [ {id, formattedAddress, addressLine1, city, state, zipCode, latitude,
        longitude, propertyType, bedrooms, bathrooms, squareFootage, yearBuilt,
        lotSize, price, status, daysOnMarket, ...} ]

Key comes from the RENTCAST_API_KEY env var. With no key, callers should use
`--demo` (SAMPLE_LISTINGS) so the end-to-end grid flow is demonstrable offline.

COVERAGE NOTE: RentCast returns *unit-level* listings, not building rollups, and
carries almost no amenity/stories/elevator data — those grid rows land JUDGMENT
or stay blank for the analyst. That sparsity is the documented reason HelloData is
the recommended production source for true multifamily comps.
"""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.rentcast.io/v1/listings/rental/long-term"
AVM = "https://api.rentcast.io/v1/avm/rent/long-term"
KEY_ENV = "RENTCAST_API_KEY"
DEFAULT_RADIUS_MI = 2.0
DEFAULT_LIMIT = 200


def _key():
    k = os.environ.get(KEY_ENV)
    if not k:
        raise RuntimeError(
            f"{KEY_ENV} not set. Get a free key at https://www.rentcast.io/api "
            f"(50 calls/mo), then `export {KEY_ENV}=...`. Or run with --demo."
        )
    return k


def _concession_signal(history: dict, current_price) -> str:
    """Derive a rent-trend / concession note from a listing's price history.

    The grid's 'Rent Concessions' row is an analyst field, but a prior list price
    above the current ask is a concrete concession signal we CAN source. Returns a
    short note ('' if there's no informative prior listing)."""
    if not history or current_price is None:
        return ""
    # history is keyed by date 'YYYY-MM-DD'; take prior events with a different price.
    priors = sorted(
        ((d, e.get("price")) for d, e in history.items()
         if e.get("price") and e.get("price") != current_price),
        key=lambda x: x[0])
    if not priors:
        return ""
    d, p = priors[-1]                              # most recent informative prior
    delta = current_price - p
    arrow = "down" if delta < 0 else "up"
    return f"{arrow} ${abs(delta):,} vs ${p:,} ({d[:7]})"


def normalize(raw: dict) -> dict:
    """RentCast listing/comparable object -> flat comp record (the shape comps.py sees).
    Handles both the listings endpoint (carries `history`) and the AVM comps
    endpoint (carries `distance` + `correlation`, no history)."""
    return {
        "id": raw.get("id"),
        "address": raw.get("addressLine1") or raw.get("formattedAddress"),
        "formatted_address": raw.get("formattedAddress"),
        "city": raw.get("city"),
        "state": raw.get("state"),
        "zip": raw.get("zipCode"),
        "lat": raw.get("latitude"),
        "lon": raw.get("longitude"),
        "property_type": raw.get("propertyType"),
        "bedrooms": raw.get("bedrooms"),
        "bathrooms": raw.get("bathrooms"),
        "sqft": raw.get("squareFootage"),
        "year_built": raw.get("yearBuilt"),
        "rent": raw.get("price"),
        "status": raw.get("status"),
        "days_on_market": raw.get("daysOnMarket"),
        "distance": raw.get("distance"),            # miles, AVM only
        "correlation": raw.get("correlation"),      # 0-1 similarity, AVM only
        "rent_trend": _concession_signal(raw.get("history") or {}, raw.get("price")),
    }


def search_rentals(lat, lon, bedrooms, radius_mi=DEFAULT_RADIUS_MI,
                   property_types=("Apartment", "Multi-Family"),
                   status="Active", limit=DEFAULT_LIMIT, timeout=30) -> list:
    """Nearby long-term rentals of a given bed count. RentCast takes ONE
    propertyType per call, so we fan out across types and merge (dedup by id)."""
    out, seen = [], set()
    for ptype in property_types:
        params = {
            "latitude": lat, "longitude": lon, "radius": radius_mi,
            "bedrooms": bedrooms, "propertyType": ptype,
            "status": status, "limit": limit,
        }
        url = f"{BASE}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"X-Api-Key": _key(),
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        for raw in (data if isinstance(data, list) else data.get("listings", [])):
            n = normalize(raw)
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            out.append(n)
    return out


def avm_comps(lat, lon, bedrooms, bathrooms=1, sqft=None,
              property_type="Apartment", comp_count=15, timeout=30) -> dict:
    """RentCast's rent-AVM: a rent estimate + range for the subject, PLUS the exact
    comparables it used (each with `distance` and a `correlation` similarity score,
    and including recently-inactive listings). Better for comp SELECTION than the
    raw listings search. -> {estimate, range_low, range_high, comps: [normalized]}."""
    params = {"latitude": lat, "longitude": lon, "propertyType": property_type,
              "bedrooms": bedrooms, "bathrooms": bathrooms, "compCount": comp_count}
    if sqft:
        params["squareFootage"] = sqft
    url = f"{AVM}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-Api-Key": _key(),
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return {
        "estimate": d.get("rent"),
        "range_low": d.get("rentRangeLow"),
        "range_high": d.get("rentRangeHigh"),
        "comps": [normalize(c) for c in d.get("comparables", [])],
    }


# --- Offline fixture so the grid flow is demonstrable without a key (`--demo`) ---
# Shaped like a real RentCast response near the 17719 Kinzie subject (Northridge).
SAMPLE_LISTINGS = [
    {"id": "z1", "addressLine1": "9810 Zelzah Ave Apt 12", "formattedAddress": "9810 Zelzah Ave, Northridge, CA 91325",
     "city": "Northridge", "state": "CA", "zipCode": "91325", "latitude": 34.2486, "longitude": -118.5340,
     "propertyType": "Apartment", "bedrooms": 1, "bathrooms": 1, "squareFootage": 754, "yearBuilt": 1984,
     "price": 2200, "status": "Active", "daysOnMarket": 21},
    {"id": "z2", "addressLine1": "9810 Zelzah Ave Apt 18", "formattedAddress": "9810 Zelzah Ave, Northridge, CA 91325",
     "city": "Northridge", "state": "CA", "zipCode": "91325", "latitude": 34.2486, "longitude": -118.5340,
     "propertyType": "Apartment", "bedrooms": 1, "bathrooms": 1, "squareFootage": 760, "yearBuilt": 1984,
     "price": 2250, "status": "Active", "daysOnMarket": 9},
    {"id": "l1", "addressLine1": "17730 Lassen St Unit 4", "formattedAddress": "17730 Lassen St, Northridge, CA 91325",
     "city": "Northridge", "state": "CA", "zipCode": "91325", "latitude": 34.2520, "longitude": -118.5285,
     "propertyType": "Apartment", "bedrooms": 1, "bathrooms": 1, "squareFootage": 837, "yearBuilt": 1978,
     "price": 2370, "status": "Active", "daysOnMarket": 33},
    {"id": "m1", "addressLine1": "17810 Merridy St Apt 7", "formattedAddress": "17810 Merridy St, Northridge, CA 91325",
     "city": "Northridge", "state": "CA", "zipCode": "91325", "latitude": 34.2535, "longitude": -118.5360,
     "propertyType": "Multi-Family", "bedrooms": 1, "bathrooms": 1, "squareFootage": 850, "yearBuilt": 1987,
     "price": 2175, "status": "Active", "daysOnMarket": 14},
    {"id": "m2", "addressLine1": "17810 Merridy St Apt 9", "formattedAddress": "17810 Merridy St, Northridge, CA 91325",
     "city": "Northridge", "state": "CA", "zipCode": "91325", "latitude": 34.2535, "longitude": -118.5360,
     "propertyType": "Multi-Family", "bedrooms": 1, "bathrooms": 1, "squareFootage": 845, "yearBuilt": 1987,
     "price": 2150, "status": "Active", "daysOnMarket": 40},
    {"id": "far", "addressLine1": "1 Faraway Blvd", "formattedAddress": "1 Faraway Blvd, Reseda, CA 91335",
     "city": "Reseda", "state": "CA", "zipCode": "91335", "latitude": 34.20, "longitude": -118.53,
     "propertyType": "Apartment", "bedrooms": 1, "bathrooms": 1, "squareFootage": 700, "yearBuilt": 1990,
     "price": 1950, "status": "Active", "daysOnMarket": 5},
]


def demo_rentals(bedrooms=None):
    rows = [normalize(r) for r in SAMPLE_LISTINGS]
    if bedrooms is not None:
        rows = [r for r in rows if r["bedrooms"] == bedrooms]
    return rows


if __name__ == "__main__":
    print(json.dumps(demo_rentals(1), indent=2))
