#!/usr/bin/env python3
"""
airport.py — airport_hazard_zone reader (LA County ALUC, Tier-A).

Source (confirmed live): LA County DRP "A-NET" = the Airport Land Use Commission
viewer. Layer 2 "Airport Influence Area" — point-in-polygon presence = inside an
AIA; the feature names the airport.

Coverage is LA COUNTY ONLY. There is no statewide AIA/ALUCP polygon (each county's
ALUC publishes its own), so off LA County this raises -> the field stays manual
(route to the local ALUC), rather than returning a false "No".
"""
import _arcgis as ag
from jurisdiction import _county_basename

ANET = "https://arcgis.gis.lacounty.gov/arcgis/rest/services/DRP/A_NET/MapServer"


def airport_hazard_zone(geo) -> dict:
    if _county_basename(geo) != "Los Angeles":
        raise LookupError("airport AIA layer is LA County only; route to the local ALUC")
    feats = ag.query(ANET, 2, lon=geo["lon"], lat=geo["lat"], out_fields="AIRPORT,AIRPORT_NAME")
    if feats:
        a = feats[0]["attributes"]
        nm = a.get("AIRPORT_NAME") or a.get("AIRPORT") or "an"
        return {"answer": "Yes",
                "notes": f"In the {nm} Airport Influence Area (LA County ALUC). Source: LA County ALUC A-NET."}
    return {"answer": "No",
            "notes": "Not in any LA County Airport Influence Area (ALUC). Source: LA County ALUC A-NET."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(airport_hazard_zone(g), indent=2))
