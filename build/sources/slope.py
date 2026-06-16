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
SAMPLE_M = 45.0
THRESHOLD_PCT = 10.0
BEARINGS = list(range(0, 360, 45))   # N, NE, E, SE, S, SW, W, NW — 8 points for better spatial coverage
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
    run_ft = SAMPLE_M * 3.28084
    mx, face = 0.0, "flat"
    for b in BEARINGS:
        th = math.radians(b)
        dN, dE = SAMPLE_M * math.cos(th), SAMPLE_M * math.sin(th)
        la = lat + dN / 111320.0
        lo = lon + dE / (111320.0 * math.cos(math.radians(lat)))
        g = abs(_elev_ft(la, lo) - center) / run_ft * 100.0
        if g > mx:
            mx, face = g, b
    return {"answer": "Yes" if mx >= THRESHOLD_PCT else "No", "state": "JUDGMENT",
            "notes": f"Max grade ~{mx:.1f}% (bearing {face}°, {SAMPLE_M:.0f} m, 8-point sample; >= {THRESHOLD_PCT:.0f}% = Yes). "
                     f"DERIVED screen from USGS 3DEP 1 m DEM — confirm on site (a parcel pad can read flat). Source: USGS EPQS."}


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(slope_grade(g), indent=2))
