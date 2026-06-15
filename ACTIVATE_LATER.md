# Activate-Later Features

Features that are **built and ready but intentionally OFF**, pending a credential
or a go-decision. Each lists exactly how to turn it on.

---

## Street View pre-screen (Google Maps API key) — **DEACTIVATED**

- **Status:** deactivated (2026-06-15). `build/sources/streetview.py` sets
  `ENABLED = False` and the module is **not imported by `collect.py`**, so nothing
  runs and no Google calls are made.
- **What it is:** a site-visit *aid* for the visual fields (`trees`,
  `billboards_signs`, `overhead_guy_wires`, `squatters`). It fetches Street View
  Static panoramas (4 headings) + the capture date for a parcel so an analyst (or
  a vision pass) can pre-screen before the visit.
- **Why it's an aid, not an automation:** Street View imagery is **dated and
  single-time**, and top-down/oblique coverage is incomplete — so it must land as
  a `SITE-VISIT`/`JUDGMENT` aid, **never `VERIFIED`**. The site visit still closes
  these fields.
- **Credential / path:** Google Maps API key via the environment variable
  **`GOOGLE_MAPS_API_KEY`**. Endpoints: `maps.googleapis.com/maps/api/streetview`
  (image) and `.../streetview/metadata` (free pano date/availability check).
- **To activate:**
  1. `export GOOGLE_MAPS_API_KEY=<key>`
  2. In `build/sources/streetview.py`, set `ENABLED = True`.
  3. Decide the integration and wire a hook into `build/collect.py` (e.g. save
     images into the deal folder and annotate the site-visit fields with the image
     path + capture date, state `SITE-VISIT`).
- **Note:** the same key would also let `places.py` swap its OpenStreetMap/Overpass
  backend for Google Places if ever desired (not required — OSM works key-free).
