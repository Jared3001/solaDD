#!/usr/bin/env python3
"""
tcac.py — resource_area reader (CTCAC/HCD Opportunity Map, Tier-A).

Source: CTCAC/HCD Opportunity Area Map, confirmed live 2026-06-15:
  services.arcgis.com/RmCCgQtiZLDCtblq/.../2026_TCAC_HCD_Opportunity_Area_Maps/FeatureServer/0
Keyed by census tract GEOID in field `fips`. Category text is `oppcat`
(Highest / High / Moderate / Low Resource, or "High Segregation & Poverty"
when pov_seg_flag==1). Updated annually; bump the URL/YEAR on the new map.

Note: the companion "Neighborhood Change" map (schema field
neighborhood_change_area, C28) is NOT published as a public REST service, so
that field stays manual.
"""
import _arcgis as ag

YEAR = 2026
SVC = ("https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
       "2026_TCAC_HCD_Opportunity_Area_Maps/FeatureServer")


def resource_area(geo) -> dict:
    feats = ag.query(SVC, 0, where=f"fips='{geo['geoid']}'",
                     out_fields="fips,oppcat,oppscore,region,pov_seg_flag,env_burden_flag")
    if not feats:
        raise LookupError(f"no {YEAR} TCAC opportunity polygon for tract {geo['geoid']}")
    a = feats[0]["attributes"]
    cat = a.get("oppcat")
    region = a.get("region") or ""
    flags = []
    if a.get("pov_seg_flag") == 1:
        flags.append("High Segregation & Poverty flag")
    if a.get("env_burden_flag") == 1:
        flags.append("environmental-burden flag")
    note = f"{cat} ({YEAR} CTCAC/HCD map, {region}; tract {geo['geoid']})"
    if flags:
        note += "; " + ", ".join(flags)
    note += ". Source: CTCAC/HCD Opportunity Map."
    return {"answer": cat, "notes": note}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps(resource_area(g), indent=2))
