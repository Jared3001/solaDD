#!/usr/bin/env python3
"""
jurisdiction.py — county + geographic_pool readers (derived, Tier-A).

county: resolved from the geocoder's county FIPS (CA counties).
geographic_pool: SOLA's CDLAC-region shorthand, derived from county via the
canonical lookup (canonical/cdlac_regions.csv) plus the LA special case —
'City of LA' if within LA city limits, else 'Balance of LA County'.

Both are deterministic derivations from data we already have (FIPS + city
limits via zimas.in_la_city), so they land VERIFIED.
"""
import csv
from pathlib import Path

import zimas

ROOT = Path(__file__).resolve().parent.parent.parent
CDLAC_CSV = ROOT / "canonical" / "cdlac_regions.csv"

# CA county FIPS (3-digit) -> Assessor/CDLAC county name (matches cdlac_regions.csv)
CA_COUNTIES = {
    "001": "Alameda", "003": "Alpine", "005": "Amador", "007": "Butte", "009": "Calaveras",
    "011": "Colusa", "013": "Contra Costa", "015": "Del Norte", "017": "El Dorado", "019": "Fresno",
    "021": "Glenn", "023": "Humboldt", "025": "Imperial", "027": "Inyo", "029": "Kern",
    "031": "Kings", "033": "Lake", "035": "Lassen", "037": "Los Angeles", "039": "Madera",
    "041": "Marin", "043": "Mariposa", "045": "Mendocino", "047": "Merced", "049": "Modoc",
    "051": "Mono", "053": "Monterey", "055": "Napa", "057": "Nevada", "059": "Orange",
    "061": "Placer", "063": "Plumas", "065": "Riverside", "067": "Sacramento", "069": "San Benito",
    "071": "San Bernardino", "073": "San Diego", "075": "San Francisco", "077": "San Joaquin",
    "079": "San Luis Obispo", "081": "San Mateo", "083": "Santa Barbara", "085": "Santa Clara",
    "087": "Santa Cruz", "089": "Shasta", "091": "Sierra", "093": "Siskiyou", "095": "Solano",
    "097": "Sonoma", "099": "Stanislaus", "101": "Sutter", "103": "Tehama", "105": "Trinity",
    "107": "Tulare", "109": "Tuolumne", "111": "Ventura", "113": "Yolo", "115": "Yuba",
}

_REGIONS = None


def _county_basename(geo):
    """CA county name (no 'County' suffix), or None if outside CA."""
    if geo.get("state_fips") != "06":
        return None
    return CA_COUNTIES.get(geo.get("county_fips"))


def _regions():
    global _REGIONS
    if _REGIONS is None:
        _REGIONS = {}
        with open(CDLAC_CSV, newline="") as f:
            for row in csv.DictReader(f):
                _REGIONS[row["County"].strip()] = row["CDLAC Region"].strip()
    return _REGIONS


def county(geo) -> dict:
    name = _county_basename(geo)
    if not name:
        raise LookupError(f"county not resolved (state {geo.get('state_fips')}, fips {geo.get('county_fips')})")
    return {"answer": f"{name} County",
            "notes": f"From geocoded county FIPS {geo.get('state_fips')}{geo.get('county_fips')}. "
                     f"Source: U.S. Census geocoder."}


def geographic_pool(geo) -> dict:
    name = _county_basename(geo)
    if not name:
        return {"answer": "None", "notes": "Outside California — no CDLAC geographic pool. Source: CDLAC region lookup."}
    if name == "Los Angeles":
        in_la = zimas.in_la_city(geo)
        pool = "City of LA" if in_la else "Balance of LA County"
        return {"answer": pool,
                "notes": f"LA County parcel {'within' if in_la else 'outside'} LA city limits -> {pool}. "
                         f"Source: CDLAC region + LA city limits."}
    region = _regions().get(name, "None")
    return {"answer": region,
            "notes": f"{name} County -> {region} (CDLAC region). Source: canonical/cdlac_regions.csv."}


# --- "free wins": identity fields derived from data we already compute ---

def address(geo) -> dict:
    a = geo.get("matched_address")
    if not a:
        raise LookupError("no matched address on geo")
    return {"answer": a, "notes": "Geocoder-matched address. Source: U.S. Census geocoder."}


def apn(geo) -> dict:
    import zimas
    if zimas.in_la_city(geo):
        bpp = zimas._snapped(geo)[0].get("BPP")
        formatted = f"{bpp[:4]}-{bpp[4:7]}-{bpp[7:]}" if bpp and len(bpp) == 10 else bpp
        return {"answer": formatted, "notes": f"APN {formatted} from LA City parcel snap. Source: LA City Parcels."}
    if _county_basename(geo) == "San Diego":
        import sd_parcel
        return sd_parcel.apn(geo)
    import parcel
    ain, matched = parcel._county_snap(geo)
    if not ain:
        raise LookupError("APN not resolved at parcel")
    formatted = f"{ain[:4]}-{ain[4:7]}-{ain[7:]}" if len(ain) == 10 else ain
    flag = "" if matched else " (nearest parcel — verify)"
    return {"answer": formatted, "state": "VERIFIED" if matched else "JUDGMENT",
            "notes": f"APN {formatted} from LA County parcel{flag}. Source: LA County Assessor."}


def city_jurisdiction(geo) -> dict:
    import zimas
    county = _county_basename(geo)
    if zimas.in_la_city(geo):
        return {"answer": "City of Los Angeles",
                "notes": "Parcel within City of LA limits (LA City parcel layer). Source: LA City / Census."}
    place = geo.get("place")
    if place:
        return {"answer": f"City of {place}",
                "notes": f"Incorporated place: {place}. Source: U.S. Census Incorporated Places."}
    if county:
        return {"answer": f"Unincorporated {county} County",
                "notes": f"No incorporated place at parcel -> unincorporated {county} County. Source: U.S. Census."}
    raise LookupError("could not determine jurisdiction")


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps({"address": address(g), "apn": apn(g), "city_jurisdiction": city_jurisdiction(g),
                      "county": county(g), "geographic_pool": geographic_pool(g)}, indent=2))
