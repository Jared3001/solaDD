#!/usr/bin/env python3
"""
streetview.py — Street View imagery AID for the site-visit fields (key-ready).

Top-down satellite can't see vertical/ground features (guy wires, signs, slope,
people); Street View can. But Street View imagery is Google's (needs an API key)
and is DATED + single-time, so it is a PRE-SCREEN AID, never a VERIFIED source —
the site visit still closes trees / billboards / guy wires / squatters.

This module fetches Street View Static panorama images at four headings for a
parcel and saves them (plus the capture date) so an analyst — or a vision pass —
can review before the visit. It does NOT auto-interpret (no vision in-pipeline),
so it is intentionally NOT wired into collect.py's reader set; use it on demand.

Set GOOGLE_MAPS_API_KEY to enable. Without it, every call raises a clear error.
"""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

KEY_ENV = "GOOGLE_MAPS_API_KEY"
META = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMG = "https://maps.googleapis.com/maps/api/streetview"
HEADINGS = (0, 90, 180, 270)


def have_key():
    return bool(os.environ.get(KEY_ENV))


def _key():
    k = os.environ.get(KEY_ENV)
    if not k:
        raise LookupError(f"Street View needs {KEY_ENV} (set it to enable)")
    return k


def metadata(lat, lon):
    """Free metadata call: is there a pano here, and what's its capture date?"""
    q = urllib.parse.urlencode({"location": f"{lat},{lon}", "key": _key()})
    with urllib.request.urlopen(f"{META}?{q}", timeout=30) as r:
        return json.load(r)


def fetch(geo, out_dir, headings=HEADINGS, size="640x480"):
    """Save Street View images at each heading into out_dir. Returns a summary dict."""
    key = _key()
    lat, lon = geo["lat"], geo["lon"]
    m = metadata(lat, lon)
    if m.get("status") != "OK":
        return {"status": m.get("status", "UNKNOWN"), "date": None, "images": []}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    images = []
    for h in headings:
        q = urllib.parse.urlencode({"location": f"{lat},{lon}", "size": size,
                                    "heading": h, "fov": 90, "pitch": 5, "key": key})
        p = out / f"streetview_{h:03d}.jpg"
        urllib.request.urlretrieve(f"{IMG}?{q}", p)
        images.append(str(p))
    return {"status": "OK", "date": m.get("date"), "images": images, "pano_id": m.get("pano_id")}


if __name__ == "__main__":
    import sys
    from geocoder import geocode
    if not have_key():
        print(f"Set {KEY_ENV} to use Street View. (module is key-ready; not wired into collect yet)")
        sys.exit(0)
    g = geocode(" ".join(sys.argv[1:]) or "4201 Pico Blvd, Los Angeles, CA")
    print(json.dumps(fetch(g, "build/_streetview_demo"), indent=2))
