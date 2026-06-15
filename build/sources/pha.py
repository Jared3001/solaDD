#!/usr/bin/env python3
"""
pha.py — pha reader: the Public Housing Authority that governs the site.

A site is governed by its CITY's housing authority if that city operates one,
else by the COUNTY authority. We resolve from the incorporated city (geocoder
`place`) + county against HUD's authoritative Public Housing Authorities layer:
  - city PHA  = a PHA in the county whose formal name contains the city and NOT
    "County" (e.g. 'Housing Authority of the City of Santa Monica');
  - county PHA = the county authority (formal name contains "County", e.g.
    'Los Angeles County Development Authority').

We do NOT use HUD's service-area POLYGON layer: HUD flags it 'proposed/
experimental' and its polygons overlap (every LA point falsely hits Baldwin
Park), so a name+county lookup on the authoritative point layer is more reliable.
"""
import _arcgis as ag
from jurisdiction import _county_basename

HUD = ("https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/"
       "Public_Housing_Authorities/FeatureServer")
FIELDS = "PARTICIPANT_CODE,FORMAL_PARTICIPANT_NAME,STD_CITY,HA_PHN_NUM"


def _esc(s):
    return str(s).replace("'", "''")


def pha(geo) -> dict:
    county = _county_basename(geo)
    if not county:
        raise LookupError("PHA resolution needs a California county")
    cty = _esc(county)
    city = geo.get("place")

    # 1) City PHA — the city operates its own authority (name has the city, not "County").
    if city:
        c = _esc(city)
        hits = ag.query(HUD, 0, out_fields=FIELDS,
                        where=(f"CURCNTY_NM LIKE '%{cty}%' "
                               f"AND FORMAL_PARTICIPANT_NAME LIKE '%{c}%' "
                               f"AND FORMAL_PARTICIPANT_NAME NOT LIKE '%County%'"))
        if hits:
            a = hits[0]["attributes"]
            return {"answer": a["FORMAL_PARTICIPANT_NAME"],
                    "notes": f"{a['FORMAL_PARTICIPANT_NAME']} ({a['PARTICIPANT_CODE']}) — "
                             f"{city} operates its own PHA. Source: HUD Public Housing Authorities."}

    # 2) County authority — no city PHA (or unincorporated).
    hits = ag.query(HUD, 0, out_fields=FIELDS,
                    where=f"CURCNTY_NM LIKE '%{cty}%' AND FORMAL_PARTICIPANT_NAME LIKE '%County%'")
    if hits:
        a = hits[0]["attributes"]
        why = f"{city} has no city PHA -> county authority" if city else "unincorporated -> county authority"
        return {"answer": a["FORMAL_PARTICIPANT_NAME"],
                "notes": f"{a['FORMAL_PARTICIPANT_NAME']} ({a['PARTICIPANT_CODE']}) — {why} "
                         f"({county} County). Source: HUD Public Housing Authorities."}

    raise LookupError(f"no PHA found for {city or 'unincorporated'}, {county} County")


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps({"place": g.get("place"), "pha": pha(g)}, indent=2))
