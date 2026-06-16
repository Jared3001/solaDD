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

# City of San Diego Airports service (DSD/Airports): layer 1 "Airport Influence
# Areas" — point-in-polygon presence = inside an AIA; feature names the airport.
SD_AIRPORTS = "https://webmaps.sandiego.gov/arcgis/rest/services/DSD/Airports/MapServer"
SD_L_AIA = 1


def _san_diego_airport_hazard_zone(geo) -> dict:
    feats = ag.query(SD_AIRPORTS, SD_L_AIA, lon=geo["lon"], lat=geo["lat"],
                     out_fields="Airport,Name,FEATURE_NM,FEATURE_DE", distance=5)
    if feats:
        a = feats[0]["attributes"]
        nm = a.get("Airport") or a.get("FEATURE_NM") or "an"
        area = a.get("Name") or a.get("FEATURE_DE")
        area_str = f" ({area})" if area else ""
        return {"answer": "Yes",
                "notes": f"In the {nm} Airport Influence Area{area_str} (City of San Diego ALUC). "
                         f"Source: City of San Diego Airports (DSD/Airports L1)."}
    return {"answer": "No",
            "notes": "Not in any City of San Diego Airport Influence Area. "
                     "Source: City of San Diego Airports (DSD/Airports L1)."}


def airport_hazard_zone(geo) -> dict:
    if _county_basename(geo) == "San Diego":
        return _san_diego_airport_hazard_zone(geo)
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
