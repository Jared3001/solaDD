#!/usr/bin/env python3
"""
ai_scraper.py — AI-assisted rent comp scraper (Zillow via Firecrawl + Gemini).

Workflow:
  1. Build a Zillow rental search URL from ZIP code + bed count.
     apartments.com was the first target but its Akamai WAF blocks Firecrawl;
     Zillow renders cleanly with the same tool.
  2. Firecrawl renders the JS-heavy page → clean markdown (~10 k chars/search).
  3. Gemini 2.5 Flash extracts structured listing records from that markdown using
     JSON-mode (responseMimeType + responseSchema) — same API pattern as om_extract.py.
  4. normalize() maps each record to the same flat dict rentcast.normalize()
     produces, so comps.py / rollup_buildings() needs no changes.

Env vars:
  FIRECRAWL_API_KEY  — get at https://firecrawl.dev  (free: 500 credits/mo)
  GEMINI_API_KEY     — same key already used by OM extraction and ModularZ

ToS note: Zillow prohibits automated scraping. Firecrawl handles the technical
rendering barrier; the analyst is responsible for compliance.
Use only for deal-specific spot-checks, not bulk or recurring harvesting.

Scope of data (search-results page):
  * Tier A fields usually present: address, rent, beds, baths, sqft (when shown).
  * year_built and full amenity detail require individual listing-page visits —
    same gap as RentCast. Year and amenities come through when the card shows them;
    they are blank otherwise (analyst fills via site visit, per Tier-B / Tier-C).
  * distance_mi is None (scraped listings carry no lat/lon); rollup_buildings
    handles this cleanly — the grid shows blank for distance.
"""
import json
import os
import re
import urllib.parse
import urllib.request

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com"
GEMINI_MODEL = os.environ.get("GEMINI_COMPS_MODEL", "gemini-2.5-flash")
FIRECRAWL_KEY_ENV = "FIRECRAWL_API_KEY"
GEMINI_KEY_ENV = "GEMINI_API_KEY"

ZILLOW_BASE = "https://www.zillow.com/homes/for_rent"
# Zillow rental URL bed-count slugs
BEDS_SLUG = {0: "studio_beds", 1: "1-_beds", 2: "2-_beds",
             3: "3-_beds", 4: "4-_beds"}
DEFAULT_LIMIT = 50
MAX_MARKDOWN_CHARS = 20000   # Zillow pages are large; first 20k has ~17 unique listings


# ---- credentials ----------------------------------------------------------------

def _fc_key():
    k = os.environ.get(FIRECRAWL_KEY_ENV)
    if not k:
        raise RuntimeError(
            f"{FIRECRAWL_KEY_ENV} not set. Get a free key at https://firecrawl.dev "
            f"(500 credits/mo free tier). Then: export {FIRECRAWL_KEY_ENV}=... "
            f"Or pass --demo to use the offline fixture."
        )
    return k


def _gemini_key():
    k = os.environ.get(GEMINI_KEY_ENV)
    if not k:
        raise RuntimeError(
            f"{GEMINI_KEY_ENV} not set. Use the same key as OM extraction / ModularZ."
        )
    return k


# ---- URL builder ----------------------------------------------------------------

def search_url(zipcode: str, bedrooms: int) -> str:
    """Zillow rental search URL for a given ZIP + bed count."""
    bed_slug = BEDS_SLUG.get(bedrooms, f"{bedrooms}-_beds")
    return f"{ZILLOW_BASE}/{zipcode}_rb/{bed_slug}/"


# ---- Firecrawl scrape -----------------------------------------------------------

def _firecrawl_scrape(url: str, timeout: int = 90) -> str:
    """Render a page via Firecrawl → markdown.

    waitFor=3000 gives the React app time to hydrate the listing cards.
    Returns the markdown string (may be empty if the page 404s or blocks).
    Retries up to 3 times: 429 rate-limit gets a 60s back-off; other errors get 8s/16s."""
    import time
    import urllib.error as _ue
    payload = json.dumps({
        "url": url,
        "formats": ["markdown"],
        "waitFor": 3000,
        "onlyMainContent": True,
    }).encode()
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{FIRECRAWL_BASE}/scrape",
                data=payload,
                headers={
                    "Authorization": f"Bearer {_fc_key()}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            if not data.get("success"):
                raise RuntimeError(f"Firecrawl scrape failed: {data.get('error', data)}")
            return data.get("data", {}).get("markdown", "")
        except _ue.HTTPError as e:
            last_err = e
            if attempt < 2:
                wait = 60 if e.code == 429 else 8 * (attempt + 1)
                print(f"  [ai_scraper] Firecrawl attempt {attempt + 1} HTTP {e.code}, retrying in {wait}s…")
                time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < 2:
                wait = 8 * (attempt + 1)
                print(f"  [ai_scraper] Firecrawl attempt {attempt + 1} failed ({e}), retrying in {wait}s…")
                time.sleep(wait)
    raise RuntimeError(f"Firecrawl failed after 3 attempts: {last_err}")


# ---- Gemini extraction ----------------------------------------------------------

# ---- Search page schema + prompt -----------------------------------------------
# JSON-mode schema — same OpenAPI subset as om_extract.py's _RESPONSE_SCHEMA.
_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["listings"],
    "properties": {
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["address", "rent", "bedrooms"],
                "properties": {
                    "address":     {"type": "string"},
                    "city":        {"type": "string"},
                    "state":       {"type": "string"},
                    "zip":         {"type": "string"},
                    "rent":        {"type": "number",
                                    "description": "Monthly rent in dollars (lowest if range)"},
                    "bedrooms":    {"type": "integer"},
                    "bathrooms":   {"type": "number"},
                    "sqft":        {"type": "number"},
                    "year_built":  {"type": "integer"},
                    "amenities":   {"type": "array", "items": {"type": "string"}},
                    "listing_url": {"type": "string",
                                    "description": "Full Zillow property page URL for this listing "
                                                   "(e.g. https://www.zillow.com/apartments/.../) "
                                                   "without any # anchor fragment"},
                },
            },
        }
    },
}

_PROMPT_TMPL = (
    "You are extracting rental listing data from a Zillow rental search-results page. "
    "Return every distinct {beds}-bedroom apartment or unit listing you find. "
    "For buildings with a rent range (e.g. '$2,200+'), use the lowest figure as `rent`. "
    "If multiple units at one address have different rents or sizes, emit one entry per unit. "
    "Skip ads and non-rental results. Include the street address — Zillow often shows a "
    "building name followed by the address; use the street address as `address`. "
    "For listing_url, extract the Zillow property page URL (starts with "
    "https://www.zillow.com/apartments/...) without any #anchor. "
    "Leave year_built, amenities, and sqft empty/omitted if not shown — do not guess.\n\n"
    "Page content:\n{content}"
)

# ---- Property page (detail) schema + extraction --------------------------------
# Second pass: scrape each shortlisted comp's individual Zillow page to get
# the Available Units table (sqft per bed type), amenities, and year_built.
_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "units": {
            "type": "array",
            "description": "Every row from the Available Units table",
            "items": {
                "type": "object",
                "properties": {
                    "bedrooms":  {"type": "integer"},
                    "bathrooms": {"type": "number"},
                    "sqft":      {"type": "number"},
                    "rent":      {"type": "number"},
                },
            },
        },
        "year_built":  {"type": "integer"},
        "total_units": {"type": "integer",
                        "description": "Total units in the building (if stated)"},
        "amenities":   {"type": "array", "items": {"type": "string"},
                        "description": "All building + unit amenities: appliances, "
                                       "cooling, parking, laundry, community features"},
    },
}

_DETAIL_PROMPT = (
    "Extract rental details from this Zillow apartment property page.\n"
    "1. Pull every row from the Available Units table: beds, baths, sqft, rent.\n"
    "2. Extract year_built and total_units if stated anywhere on the page.\n"
    "3. List ALL amenities: appliances (dishwasher, refrigerator, range/stove, microwave, "
    "washer/dryer), cooling (central A/C), parking (covered, garage, carport, street), "
    "laundry (in-unit, shared), and community features (pool, fitness center, clubhouse, "
    "elevator, controlled access, patio/balcony). Use concise names.\n\n"
    "Page content:\n{content}"
)


def _gemini_extract_detail(markdown: str, timeout: int = 60) -> dict:
    """Gemini extracts sqft/amenities from a Zillow individual property page."""
    import time
    import urllib.error as _ue
    prompt = _DETAIL_PROMPT.format(content=markdown[:12000])
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _DETAIL_SCHEMA,
            "temperature": 0,
        },
    }).encode()
    url = (f"{GEMINI_API_ROOT}/v1beta/models/{GEMINI_MODEL}:generateContent"
           f"?key={urllib.parse.quote(_gemini_key(), safe='')}")
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
            try:
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                raise RuntimeError(f"Gemini detail parse error: {e}\nRaw: {resp}") from e
        except _ue.HTTPError as e:
            last_err = e
            if attempt < 3:
                wait = 60 if e.code == 429 else 8 * (attempt + 1)
                print(f"  [ai_scraper] Gemini detail attempt {attempt + 1} HTTP {e.code}, retrying in {wait}s…")
                time.sleep(wait)
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gemini detail failed after 4 attempts: {last_err}")


_detail_cache: dict = {}   # url -> detail dict; persists within a Python session


def enrich_comps(comps: list, bedrooms: int, timeout: int = 90) -> list:
    """Second-pass: scrape each comp's Zillow property page to fill sqft/amenities/baths.

    Modifies the comp dicts in place. Silently skips if listing_url is absent or
    if the scrape/extract fails (avoids breaking the grid over one bad URL).
    Sleeps 5s between uncached Firecrawl requests to stay within free-tier rate limits."""
    import time
    for c in comps:
        url = c.get("listing_url")
        if not url:
            continue
        try:
            if url in _detail_cache:
                print(f"  [ai_scraper] detail (cached) → {url}")
                detail = _detail_cache[url]
            else:
                print(f"  [ai_scraper] detail → {url}")
                time.sleep(5)   # Firecrawl free-tier rate limit guard
                md = _firecrawl_scrape(url, timeout=timeout)
                detail = _gemini_extract_detail(md, timeout=60)
                _detail_cache[url] = detail

            # sqft + baths: average across available units matching this bed count
            matching = [u for u in (detail.get("units") or [])
                        if u.get("bedrooms") == bedrooms and u.get("sqft")]
            if matching:
                c["sqft"] = round(sum(u["sqft"] for u in matching) / len(matching))
                if not c.get("bathrooms"):
                    baths = [u["bathrooms"] for u in matching if u.get("bathrooms")]
                    if baths:
                        c["bathrooms"] = baths[0]

            if detail.get("year_built") and not c.get("year_built"):
                c["year_built"] = detail["year_built"]
            if detail.get("amenities"):
                c["amenities_raw"] = detail["amenities"]
                import comp_adjust as _ca
                c["amenity_flags"] = _ca.map_amenities(detail["amenities"])
                c["utility_flags"] = _ca.map_utilities(detail["amenities"])
            if detail.get("total_units") and c.get("n_listings", 1) == 1:
                c["n_listings"] = detail["total_units"]

        except Exception as e:
            print(f"  [ai_scraper] detail scrape skipped ({url}): {e}")

        # year_built fallback: LA County Assessor parcel layer (no Zillow page carries it)
        if not c.get("year_built"):
            addr = c.get("formatted_address") or c.get("address") or ""
            if addr:
                c["year_built"] = _year_built_from_assessor(addr)

        print(f"    sqft={c.get('sqft')}  baths={c.get('bathrooms')}  "
              f"amenities={len(c.get('amenities_raw', []))}  "
              f"yr={c.get('year_built')}")
    return comps


_LACOUNTY_PARCEL = (
    "https://public.gis.lacounty.gov/public/rest/services/"
    "LACounty_Cache/LACounty_Parcel/MapServer"
)


def _year_built_from_assessor(address: str, timeout: int = 20):
    """Look up YearBuilt1 from the LA County Assessor parcel layer.

    Mirrors parcel.py._county_snap: geocode → 150m spatial query to get candidate
    parcels → local address-match (house number + street word) → nearest-by-distance
    fallback. This avoids the geocoding-offset error where an 80m spatial query can
    snap to a neighboring parcel built in a different year.
    Silently returns None on any failure."""
    try:
        import _arcgis as ag
        from geocoder import geocode
        import zimas

        geo = geocode(address)
        lon, lat = geo["lon"], geo["lat"]
        target_no, street = zimas._addr_parts(address)
        feats = ag.query(_LACOUNTY_PARCEL, 0,
                         lon=lon, lat=lat, distance=150, return_geometry=False,
                         out_fields="SitusHouseNo,SitusStreet,YearBuilt1,CENTER_LON,CENTER_LAT")
        if not feats:
            return None

        rows = []
        for f in feats:
            a = f["attributes"]
            digits = "".join(c for c in (a.get("SitusHouseNo") or "") if c.isdigit())
            hn = int(digits) if digits else None
            clon, clat = a.get("CENTER_LON"), a.get("CENTER_LAT")
            dist = ag.haversine_m(lon, lat, clon, clat) if (clon and clat) else float("inf")
            situs = (a.get("SitusStreet") or "").upper()
            rows.append({"hn": hn, "dist": dist, "yr": a.get("YearBuilt1"),
                         "street_match": bool(street and street in situs)})

        addr_rows = [r for r in rows if r["street_match"] and r["hn"] is not None
                     and target_no is not None]
        if addr_rows:
            best = min(addr_rows, key=lambda r: (abs(r["hn"] - target_no), r["dist"]))
        else:
            best = min(rows, key=lambda r: r["dist"])

        return int(best["yr"]) if best.get("yr") else None
    except Exception:
        pass
    return None


def _gemini_extract(markdown: str, bedrooms: int, timeout: int = 60) -> list:
    """Pass markdown to Gemini in JSON mode → list of raw listing dicts."""
    import time
    import urllib.error as _ue
    prompt = _PROMPT_TMPL.format(beds=bedrooms, content=markdown[:MAX_MARKDOWN_CHARS])
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
            "temperature": 0,
        },
    }).encode()

    url = (f"{GEMINI_API_ROOT}/v1beta/models/{GEMINI_MODEL}:generateContent"
           f"?key={urllib.parse.quote(_gemini_key(), safe='')}")
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
            # Gemini JSON-mode: candidates[0].content.parts[0].text is already valid JSON
            try:
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text).get("listings", [])
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                raise RuntimeError(f"Gemini extraction parse error: {e}\nRaw: {resp}") from e
        except _ue.HTTPError as e:
            last_err = e
            if attempt < 3:
                wait = 60 if e.code == 429 else 8 * (attempt + 1)
                print(f"  [ai_scraper] Gemini attempt {attempt + 1} HTTP {e.code}, retrying in {wait}s…")
                time.sleep(wait)
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gemini extract failed after 4 attempts: {last_err}")


# ---- normalize ------------------------------------------------------------------

def normalize(raw: dict, source_url: str = "") -> dict:
    """AI-scraped listing dict → same flat schema as rentcast.normalize().

    lat/lon are None (scraped pages don't expose coordinates); rollup_buildings
    gracefully returns distance_mi=None for these records."""
    addr = raw.get("address") or ""
    city  = raw.get("city")  or ""
    state = raw.get("state") or ""
    zipcode = raw.get("zip") or ""
    fmt = ", ".join(filter(None, [addr, city,
                                  (f"{state} {zipcode}".strip() if state or zipcode else "")]))
    return {
        "id":               f"ai_{re.sub(r'[^a-z0-9]', '_', addr.lower())[:40]}",
        "address":          addr,
        "formatted_address": fmt,
        "city":             city,
        "state":            state,
        "zip":              zipcode,
        "lat":              None,
        "lon":              None,
        "property_type":    "Apartment",
        "bedrooms":         raw.get("bedrooms"),
        "bathrooms":        raw.get("bathrooms"),
        "sqft":             raw.get("sqft"),
        "year_built":       raw.get("year_built"),
        "rent":             raw.get("rent"),
        "status":           "Active",
        "days_on_market":   None,
        "distance":         None,
        "correlation":      None,
        "rent_trend":       "",
        # extras (not in rentcast schema; available for future comp-editor enrichment)
        "amenities_raw":    raw.get("amenities") or [],
        "listing_url":      raw.get("listing_url"),
        "source":           "ai_scraper",
        "source_url":       source_url,
    }


# ---- main entry point -----------------------------------------------------------

def search_rentals(lat, lon, bedrooms: int, zipcode: str,
                   limit: int = DEFAULT_LIMIT, timeout: int = 90) -> list:
    """Scrape apartments.com for a given ZIP + bed count.

    lat/lon are accepted for signature compatibility with rentcast.search_rentals
    but are not used — apartments.com is queried by ZIP code (more reliable URL
    format than lat/lon bounding boxes, which require dynamic API calls).

    Returns normalized listing records (same shape as rentcast.search_rentals)."""
    if not zipcode:
        raise ValueError("zipcode is required for ai_scraper.search_rentals "
                         "(extract from geocoder matched_address or pass explicitly)")
    url = search_url(zipcode, bedrooms)
    print(f"  [ai_scraper] Firecrawl → {url}")
    markdown = _firecrawl_scrape(url, timeout=timeout)
    print(f"  [ai_scraper] {len(markdown):,} chars rendered (Zillow); extracting with Gemini …")
    raw_listings = _gemini_extract(markdown, bedrooms, timeout=timeout)
    print(f"  [ai_scraper] Gemini extracted {len(raw_listings)} listing(s)")
    results = [normalize(r, source_url=url) for r in raw_listings]
    return results[:limit]


# ---- offline fixture (--demo mode, same structure as live output) ---------------

SAMPLE_LISTINGS = [
    {"address": "9810 Zelzah Ave Apt 12", "city": "Northridge", "state": "CA",
     "zip": "91325", "rent": 2200, "bedrooms": 1, "bathrooms": 1, "sqft": 754,
     "year_built": 1984,
     "amenities": ["Central A/C", "Refrigerator", "Stove/Oven", "Dishwasher"]},
    {"address": "17730 Lassen St Unit 4", "city": "Northridge", "state": "CA",
     "zip": "91325", "rent": 2370, "bedrooms": 1, "bathrooms": 1, "sqft": 837,
     "year_built": 1978,
     "amenities": ["Central A/C", "Refrigerator", "Stove/Oven", "Washer/Dryer Hook-ups"]},
    {"address": "17810 Merridy St Apt 7", "city": "Northridge", "state": "CA",
     "zip": "91325", "rent": 2175, "bedrooms": 1, "bathrooms": 1, "sqft": 850,
     "year_built": 1987,
     "amenities": ["Central A/C", "Refrigerator", "Stove/Oven", "Tuck-under Garage"]},
]


def demo_rentals(bedrooms=None):
    rows = [normalize(r) for r in SAMPLE_LISTINGS]
    if bedrooms is not None:
        rows = [r for r in rows if r["bedrooms"] == bedrooms]
    return rows


if __name__ == "__main__":
    import sys
    print(json.dumps(demo_rentals(int(sys.argv[1]) if len(sys.argv) > 1 else None), indent=2))
