#!/usr/bin/env python3
"""
coastal.py — coastal_zone reader (CA Coastal Commission, Tier-A).

Source (confirmed live): the California Coastal Zone Boundary polygon (Coastal Act
PRC Sec. 30103 jurisdiction), published by the CA Coastal Commission and hosted as
a queryable polygon by Caltrans GIS. Statewide (15 coastal counties). Point-in-
polygon presence = inside the Coastal Zone.

(This is the LAND portion of the boundary, which is what a parcel determination
needs. CCC publishes the offshore extent separately.)
"""
import _arcgis as ag

COASTAL = ("https://gisdata.dot.ca.gov/arcgis/rest/services/CHhqenvi/"
           "DEA_Coastal_Zone_Boundary/FeatureServer")


def coastal_zone(geo) -> dict:
    feats = ag.query(COASTAL, 0, lon=geo["lon"], lat=geo["lat"], out_fields="NAME_UCASE")
    if feats:
        return {"answer": "Yes",
                "notes": "Within the CA Coastal Zone — Coastal Act (Coastal Development Permit) jurisdiction. "
                         "Source: CA Coastal Commission / Caltrans."}
    return {"answer": "No",
            "notes": "Outside the CA Coastal Zone. Source: CA Coastal Commission / Caltrans."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "1685 Main St, Santa Monica, CA 90401")
    print(json.dumps(coastal_zone(g), indent=2))
