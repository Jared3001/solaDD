#!/usr/bin/env python3
"""
calgem.py — wells_on_site reader (CalGEM oil & gas wells, Tier-A).

Source: CalGEM WellSTAR, confirmed live 2026-06-15:
  gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0
Point features; queried by proximity. "On site" is approximated by a tight
radius (parcel footprint); nearby wells and the nearest well's status are
reported for judgment. Status values incl. Active/Idle (live liability) and
Plugged/Buried (legacy / methane risk).
"""
import _arcgis as ag

SVC = "https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer"
ONSITE_M = 50      # "on site" proxy (parcel footprint)
NEARBY_M = 500     # context radius reported in the note


def wells_on_site(geo) -> dict:
    lon, lat = geo["lon"], geo["lat"]
    nearby = ag.query(SVC, 0, lon=lon, lat=lat, distance=NEARBY_M, return_geometry=True,
                      out_fields="API,OperatorName,LeaseName,WellNumber,WellStatus,WellTypeLabel")
    if not nearby:
        return {"answer": "No", "notes": f"No CalGEM wells within {NEARBY_M} m. Source: CalGEM WellSTAR."}
    near_feat, near_d = ag.nearest(nearby, lon, lat)
    on_site = near_d is not None and near_d <= ONSITE_M
    a = near_feat["attributes"]
    desc = (f"nearest well API {a.get('API')} ({a.get('OperatorName')} "
            f"'{a.get('LeaseName')}' #{a.get('WellNumber')}), {a.get('WellStatus')}, {near_d:.0f} m")
    note = f"{len(nearby)} well(s) within {NEARBY_M} m; {desc}. Source: CalGEM WellSTAR."
    return {"answer": "Yes" if on_site else "No", "notes": note}


if __name__ == "__main__":
    import sys, json
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "11300 S Main St, Los Angeles, CA 90061")
    print(json.dumps(wells_on_site(g), indent=2))
