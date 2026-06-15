#!/usr/bin/env python3
"""
slope.py — slope_grade reader (DERIVED from USGS 3DEP elevation, Tier-A).

No imagery — elevation. We sample the USGS Elevation Point Query Service (EPQS,
free, no key) at the parcel center and 4 cardinal points ~40 m out, compute the
max grade (rise/run %), and flag Yes when it exceeds the hillside threshold.

1 m 3DEP DEM can pick up retaining walls / pads as artificial rise, so this is a
screen — lands VERIFIED-from-data but the note says confirm on site. Threshold
10% separates flat (Pico ~1.3%) from hillside (Hollywood Hills ~14.8%) cleanly.
"""
import json
import math
import time
import urllib.parse
import urllib.request

EPQS = "https://epqs.nationalmap.gov/v1/json"
SAMPLE_M = 40.0
THRESHOLD_PCT = 10.0
UA = "Mozilla/5.0 (solaDD slope)"


def _elev_ft(lat, lon, tries=3):
    q = urllib.parse.urlencode({"x": lon, "y": lat, "units": "Feet", "wkid": 4326})
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{EPQS}?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                v = json.load(r).get("value")
            if v is not None and float(v) > -100000:   # sentinel for outside DEM coverage
                return float(v)
        except Exception as e:
            last = e
        time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"EPQS failed at ({lat},{lon}): {last}")


def slope_grade(geo) -> dict:
    lat, lon = geo["lat"], geo["lon"]
    center = _elev_ft(lat, lon)
    dlat = SAMPLE_M / 111320.0
    dlon = SAMPLE_M / (111320.0 * math.cos(math.radians(lat)))
    run_ft = SAMPLE_M * 3.28084
    grades = {}
    for name, (la, lo) in {"N": (lat + dlat, lon), "S": (lat - dlat, lon),
                           "E": (lat, lon + dlon), "W": (lat, lon - dlon)}.items():
        grades[name] = abs(_elev_ft(la, lo) - center) / run_ft * 100.0
    face = max(grades, key=grades.get)
    mx = grades[face]
    return {"answer": "Yes" if mx >= THRESHOLD_PCT else "No",
            "notes": f"Max grade ~{mx:.1f}% ({face} face, {SAMPLE_M:.0f} m sample; >= {THRESHOLD_PCT:.0f}% = Yes). "
                     f"DERIVED from USGS 3DEP 1 m DEM — confirm on site. Source: USGS EPQS."}


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(slope_grade(g), indent=2))
