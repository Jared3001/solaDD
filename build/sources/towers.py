#!/usr/bin/env python3
"""
towers.py — cell_towers reader (HIFLD/FCC Cellular Towers, Tier-A proximity).

Source (confirmed live): HIFLD "Cellular Towers in the United States" ArcGIS layer
(derived from FCC Part 22 cellular licensing). Flag Yes if a registered tower is
on/adjacent to the parcel (<= 150 m); report the nearest tower within 500 m.

IMPORTANT: this is the FCC cellular-LICENSING subset (~24k national points) — it
is sparse, especially in dense urban areas, so a "No" is NOT authoritative
(absence != no antennas). The note says so; confirm on site. A positive hit is
reliable.
"""
import _arcgis as ag

CELL = ("https://services2.arcgis.com/FiaPA4ga0iQKduv3/ArcGIS/rest/services/"
        "Cellular_Towers_in_the_United_States/FeatureServer")
ONSITE_M, NEARBY_M = 150, 500
_CAVEAT = ("NOTE: FCC cellular-licensing subset is sparse (esp. urban) — absence is not "
           "authoritative; confirm on site.")


def cell_towers(geo) -> dict:
    lon, lat = geo["lon"], geo["lat"]
    feats = ag.query(CELL, 0, lon=lon, lat=lat, distance=NEARBY_M, return_geometry=True,
                     out_fields="Licensee,StrucType,AllStruc,TowReg")
    near, nd = ag.nearest(feats, lon, lat)
    if near is None:
        return {"answer": "No", "notes": f"No registered cellular tower within {NEARBY_M} m. {_CAVEAT} Source: HIFLD/FCC Cellular Towers."}
    a = near["attributes"]
    desc = f"{a.get('Licensee')}, {a.get('StrucType')}, {a.get('AllStruc')} m"
    if nd <= ONSITE_M:
        return {"answer": "Yes",
                "notes": f"Registered cellular tower {nd:.0f} m away ({desc}). Source: HIFLD/FCC Cellular Towers."}
    return {"answer": "No",
            "notes": f"No tower within {ONSITE_M} m; nearest {nd:.0f} m ({desc}). {_CAVEAT} Source: HIFLD/FCC Cellular Towers."}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(cell_towers(g), indent=2))
