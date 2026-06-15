#!/usr/bin/env python3
"""
calfire.py — very_high_fire_hazard_zone reader (CAL FIRE / OSFM FHSZ, Tier-A).

Source: CAL FIRE prefire.calfire ArcGIS org, confirmed live 2026-06-15:
  SRA (adopted, eff. 2024-04-01):      FHSZSRA_23_3/FeatureServer/0
  LRA (OSFM-Recommended 2025-03-24):   FHSALRA25_v1_All/FeatureServer/0
Field FHSZ: -3=NonWildland, 1=Moderate, 2=High, 3=Very High; FHSZ_Description
is the text; SRA field = "SRA"/"LRA". Membership = feature presence, but an LRA
NonWildland parcel returns a feature with FHSZ=-3 (i.e. NOT in a hazard zone),
so query both layers and read the code rather than presence alone.

The schema field asks specifically about a VERY HIGH FHSZ, so answer "Yes" only
when the top class found is Very High (3); High/Moderate are reported in the note.

CAVEAT (runbook guardrail): the LRA map is OSFM-RECOMMENDED, not necessarily
locally adopted; enforceability depends on the jurisdiction's adoption ordinance.
"""
import _arcgis as ag

ORG = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services"
SRA = f"{ORG}/FHSZSRA_23_3/FeatureServer"
LRA = f"{ORG}/FHSALRA25_v1_All/FeatureServer"
CLASS = {3: "Very High", 2: "High", 1: "Moderate", -3: "NonWildland"}


def _attrs_at(service, geo):
    feats = ag.query(service, 0, lon=geo["lon"], lat=geo["lat"],
                     out_fields="FHSZ,FHSZ_Description,SRA")
    return feats[0]["attributes"] if feats else None


def very_high_fire_hazard_zone(geo) -> dict:
    hits = [a for a in (_attrs_at(SRA, geo), _attrs_at(LRA, geo)) if a]
    codes = [a.get("FHSZ") for a in hits if isinstance(a.get("FHSZ"), int) and a.get("FHSZ") > 0]
    if not codes:
        where = "LRA NonWildland" if any(a.get("SRA") == "LRA" for a in hits) else "no mapped FHSZ"
        return {"answer": "No", "notes": f"Not in an FHSZ ({where}). Source: CAL FIRE/OSFM FHSZ."}
    top = max(codes)
    resp = next(a.get("SRA") for a in hits if a.get("FHSZ") == top) or "?"
    note = f"{CLASS.get(top, top)} FHSZ ({resp})."
    if resp == "LRA":
        note += " NOTE: OSFM-recommended LRA map (2025-03-24); local adoption varies."
    note += " Source: CAL FIRE/OSFM FHSZ."
    return {"answer": "Yes" if top == 3 else "No", "notes": note}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps(very_high_fire_hazard_zone(g), indent=2))
