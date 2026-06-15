#!/usr/bin/env python3
"""
oz.py — opportunity_zone reader (federal QOZ, Tier-A).

Source: Federal Opportunity Zones (2018 designation, 2010-census tracts),
confirmed live 2026-06-15:
  services2.arcgis.com/FiaPA4ga0iQKduv3/.../Opportunity_Zones_1/FeatureServer/0
Keyed by GEOID in field CENSUSTRAC; the layer holds only the 8,764 designated
tracts, so membership = a row exists.

VINTAGE CAVEAT: this is the original 2018 round (2010 GEOIDs). Under the 2025
OBBBA the current designations sunset 2026-12-31; a new round (2020 GEOIDs)
takes effect 2027-01-01. Re-source the layer once Treasury publishes the 2027
list. The note string states the vintage so a stale answer self-identifies.
"""
import _arcgis as ag

SVC = ("https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
       "Opportunity_Zones_1/FeatureServer")
VINTAGE = "2018 designation, 2010 GEOIDs (sunsets 2026-12-31)"


def opportunity_zone(geo) -> dict:
    feats = ag.query(SVC, 0, where=f"CENSUSTRAC='{geo['geoid']}'",
                     out_fields="CENSUSTRAC,STATENAME,COUNTYNAME")
    if feats:
        return {"answer": "Yes",
                "notes": f"In a federal Opportunity Zone, tract {geo['geoid']} [{VINTAGE}]. "
                         f"Source: CDFI/Novogradac OZ layer."}
    return {"answer": "No",
            "notes": f"Not a federal Opportunity Zone, tract {geo['geoid']} [{VINTAGE}]. "
                     f"Source: CDFI/Novogradac OZ layer."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps(opportunity_zone(g), indent=2))
