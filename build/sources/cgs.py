#!/usr/bin/env python3
"""
cgs.py — liquefaction_zone + alquist_priolo_fault_zone readers (CGS, Tier-A).

Source: CGS EQ Zapp public ArcGIS Online org, confirmed live 2026-06-15:
  services2.arcgis.com/zr3KAIbsRSUyARHG/...
  Alquist-Priolo:  CGS_Alquist_Priolo_Fault_Zones/FeatureServer/0
  Liquefaction:    CGS_Liquefaction_Zones/FeatureServer/0
Membership = feature presence (no flag field). CGS zones exist only where CGS
has released studies, so a "No" means "not in a mapped zone," not "no hazard"
in unstudied areas — stated in the note.

(The legacy on-prem server gis.conservation.ca.gov/.../CGS_Earthquake_Hazard_Zones
now requires a token (HTTP 499) and is being retired; use the AGOL org above.)
"""
import _arcgis as ag

ORG = "https://services2.arcgis.com/zr3KAIbsRSUyARHG/ArcGIS/rest/services"
AP = f"{ORG}/CGS_Alquist_Priolo_Fault_Zones/FeatureServer"
LIQ = f"{ORG}/CGS_Liquefaction_Zones/FeatureServer"


def _zone(service, geo, label):
    feats = ag.query(service, 0, lon=geo["lon"], lat=geo["lat"], out_fields="QUAD_NAME,GEOPDFLINK")
    if feats:
        a = feats[0]["attributes"]
        return {"answer": "Yes",
                "notes": f"In a CGS {label} zone ({a.get('QUAD_NAME')} quad). "
                         f"Map: {a.get('GEOPDFLINK')}. Source: CGS EQ Zapp."}
    return {"answer": "No",
            "notes": f"Not in a mapped CGS {label} zone (absence != no hazard where unstudied). "
                     f"Source: CGS EQ Zapp."}


def alquist_priolo_fault_zone(geo) -> dict:
    return _zone(AP, geo, "Alquist-Priolo Earthquake Fault")


def liquefaction_zone(geo) -> dict:
    return _zone(LIQ, geo, "liquefaction")


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps({"alquist_priolo_fault_zone": alquist_priolo_fault_zone(g),
                      "liquefaction_zone": liquefaction_zone(g)}, indent=2))
