# Changelog

## v0.18-draft (2026-06-18) — unincorporated-LA-County zoning block + jurisdiction-routing fix
Integrates the Slauson Ave (1550–1570 E. Slauson, Florence-Firestone) feedback:
the site is in **unincorporated LA County**, which is a different GIS and a different
set of metrics than LA City. Two changes:

- **New `build/sources/lacounty.py`** — the County analog of `zimas.py`/`sandiego.py`,
  reading the LA County Dept. of Regional Planning (DRP) open ArcGIS REST layers
  (`public.gis.lacounty.gov/.../DRP/Open_Data`): Title-22 **zoning** (L3, + General
  Plan land use L8), **specific_plan_overlay** (SP zone + CSD L4 + Zoned District L25
  + named specific plans + SEA L12), **supervisor district** (Political L27 — County
  Supervisor, not a Council member), and **TOD** (L23, the County's transit-oriented
  district in the TOC/Tier cell; `half_mile_major_transit` + `tier_transit_verification`
  derived from it → JUDGMENT). The LA-City LAMC concepts (`q_conditions_la`,
  `methane_hazard_zone_la`, `transitional_height_adj_zones`) are N/A here; `historic_status`
  stays manual (no County REST layer). `land_sf`/`apn` already resolve via the LA County
  Assessor layer. Wired into `collect.py` as a third router branch (`LACOUNTY_READERS`),
  gated on `_county_basename == "Los Angeles" and lacounty.is_unincorporated()`.
- **Jurisdiction-routing fix** — `zimas.in_la_city()` now decides LA-City membership
  from the authoritative LA County **City-Boundaries polygon** (Political L19) instead
  of a 150 m parcel snap. The snap alone misrouted this site: the geocoded point sat
  ~97 m from an LA-City parcel across Slauson Ave (APN 5105-019-015, "1609 E Slauson"),
  so the pipeline grabbed that neighbor and reported its `CM-2D-CPIO` zoning for an
  unincorporated parcel. The boundary polygon is address-independent and also corrects
  `geographic_pool` (City of LA vs Balance of LA County), `apn`, and `land_sf` for these
  border parcels. Falls back to the snap test only outside County boundary coverage.
- **Verified live** end-to-end on the real site (single + 4-parcel assemblage): routes
  to the County block, returns `SP — Florence-Firestone` zoning, Florence-Firestone TOD
  (Metro Blue Line), Supervisorial District 2, APN 6008-034-001…004, 18,299 sf summed.
  Regression-checked routing: LA City → ZIMAS, Santa Monica → manual, San Diego → SD.

## v0.17-draft (2026-06-17) — completed checklists: persistent + one-click to model
Builds on the Financial model tab (v0.16):
- The recent panel ("Completed checklists") is shown up front, and each DD-checklist
  row now has a **"→ Financial model"** button that builds the Stick + Modular
  pro-forma straight from that checklist (chains via `from_job` — no re-upload).
  Model runs don't get the button (`recent_jobs.can_model` = kind single/assemblage
  with a file on disk).
- **The list now survives redeploys.** `web/jobs.py` persists a compact index
  (`DATA_DIR/jobs_index.json`) on each completed run and rehydrates stubs at startup,
  so the list + downloads + "generate model" work immediately after a deploy (the
  workbooks already persisted on the volume; only the in-memory metadata was lost on
  restart). `recent_jobs` uses live field counts or the persisted stub counts;
  `downloadable` now checks the file still exists.
- Verified via the Flask test client (persist → simulated redeploy → rehydrate →
  model from the rehydrated checklist; `/api/recent` exposes `can_model`) and a live
  gunicorn preview (seeded index rehydrated on page load; the row button drove
  `POST /api/run` `from_job` → underwrite → done, both models).

## v0.16-draft (2026-06-17) — "Financial model" tab on the web app
The underwriting exporter (`build/underwrite.py`, DD checklist → Stick + Modular
pro-forma) is now wired into the web front end as a new **Financial model** tab.
Two ways in, per the build decision:
- **Upload** a completed DD checklist (.xlsx) on the new tab → both models, zipped.
- **Chain**: a "Generate financial model" button appears on any finished DD run
  (single or assemblage) and feeds that run's workbook straight in — no re-upload.

Implementation: `run_underwrite(job)` in `web/jobs.py` (reads the DD, calls
`underwrite.export` against the in-repo master template, zips the two .xlsm,
surfaces product/flags/DD-inputs in `job["underwrite"]`); `mode="underwrite"` in
`web/app.py` (multipart upload or JSON `from_job`); new tab + upload field + chain
button + result panel in `index.html`/`app.js`/`style.css`. The DD-checklist
time-saved counter does NOT increment for model runs. Verified end-to-end via the
Flask test client: page renders, upload run → zipped download (application/zip),
chain run → done, and the bad-`from_job`/empty-input error paths.

## v0.15-draft (2026-06-16) — multi-address assemblage in the DD engine
`collect.py` can now run **several addresses as one site** — the address-based
alternative to the APN-keyed web assemblage. Pass a `;`-separated address string
(CLI or any caller; `collect()` splits it internally):
- Geocodes every address; **point/tract readers run on the primary (first) parcel**.
- **`land_sf` is summed** across the unique parcels (deduped by APN) and **every APN
  is listed**; `address` shows all addresses. New `_assemble_parcels()` does the
  aggregation; `_parse_addresses()` does the split.
- **Flags when the assemblage spans multiple census tracts** — QCT/DDA/resource/OZ/
  neighborhood-change reflect the primary parcel only, so they're called out for
  per-parcel verification. Lands JUDGMENT (not VERIFIED) if any parcel was a
  nearest-fallback snap or one couldn't be sized.
- Verified end-to-end: two S Main St parcels summed (24,220 + 12,893 = 37,113 sf),
  both APNs listed, flows through `underwrite.py` to model `C12`. Addresses the
  parcel-selection gap the 3-deal QC found (Colima/Bellflower assemblages).
- **Web front end wired too**: `run_single` in `web/jobs.py` now detects a
  `;`-separated address, runs the assemblage (primary parcel for point/tract
  readers, summed land_sf + listed APNs), surfaces the per-parcel breakdown and
  combined SF, and flags multi-tract assemblages — same UX as the APN tab. The
  address box hint tells users they can enter several addresses with `;`. (The
  APN `run_assemblage` path is unchanged — both options coexist.)

## v0.14-draft (2026-06-16) — underwriting exporter (DD → two pro-forma models)
First-pass underwriting models now auto-generate from a completed DD checklist.
- **New `build/underwrite.py`** — reads a DD checklist (`Site DD` sheet) and writes
  the DD-derived site inputs + confirmed projection-logic assumptions into SoLa's
  pro-forma `.xlsm`, saving **two files per deal**: `<deal> — Stick.xlsm` and
  `<deal> — Modular.xlsm`. openpyxl `keep_vba` preserves the template's macros, 12
  LAMBDA defined names, and existing formulas (round-trip verified).
- **New `build/sources/uw_logic.py`** — pure, unit-testable projection rules
  (UNDERWRITING_INTAKE.md Part B): county strip, QCT/DDA collapse, resource→C6
  vocab, PHA→canonical dropdown label, bedroom mix by resource (Large Family vs
  100% 1B), AMI 10/10/80, CRA derivation, the build-method-aware `C9` construction-
  type formula, and the method overlay (A36, Modular sizes L5/L6, build time
  Draws_Module!B5 = 24/18 mo).
- **Cells set:** B2, C3–C9, C12, I3/I5/I6, R35/R36/R38 (+ method: A36, L5/L6, B5).
  **Left for the analyst (Hand):** stories C15, acquisition price, BIPOC, prevailing
  wage. `--selftest` round-trips an example .xlsm and asserts every written cell;
  PASS on Kinzie (Large Family) and the 11300 S Main demo (Standard/1B).

## v0.13-draft (2026-06-16) — San Diego expansion complete (parity with LA)
A San Diego County address now auto-fills the same ~37 fields as LA (only the 3
LA-only zoning concepts are N/A). Built in parallel:
- **`resource_area` is now statewide** (`tcac.py`). The old endpoint was LA County's
  republished copy (FIPS 06037 only — 0 San Diego tracts). Switched to the statewide
  2026 CTCAC/HCD Opportunity Map: the official UC Berkeley OBI GeoJSON (11,337 tracts,
  all 58 counties) — the SAME file `nc.py` reads. Disk-cached to `_cache/tcac_2026.json`
  (slim {fips: oppcat/region/pov_seg_flag}) and pre-warmed in collect, mirroring nc.py,
  so the 39 MB download happens once. Works for SD and LA. (Every public ArcGIS copy of
  the TCAC map is single-county; the OBI GeoJSON is the only statewide source.)
- **New `build/sources/sandiego.py`** — the San Diego municipal block (SD analog of the
  LA ZIMAS block), City-of-San-Diego scope (off-city → manual). Readers: `zoning`
  (Base Zones), `specific_plan_overlay` (DSD Zoning_Overlay), `council_supervisor_district`
  (DoIT_Public), `historic_status` (Historic_Preservation_Resources), `toc_tier_la`
  ←Transit Priority Area, `half_mile_major_transit` (TPA = SB743 ½-mi-of-major-transit),
  `tier_transit_verification`. Wired into `collect.py` as `SD_READERS`, gated by
  county == San Diego (mirrors the `in_la_city` ZIMAS gate).
- **`airport.py`** gained a San Diego branch (City DSD/Airports "Airport Influence Areas")
  — `airport_hazard_zone` now resolves for SD instead of routing to manual. LA path intact.
- **`assemblage.py`** works for San Diego: auto-detects LA vs SD per APN (tries LA City
  Parcels, falls back to SANDAG), sizes combined land area via `sd_parcel.parcel_info`,
  and aggregates `{**READERS, **SD_READERS}` for SD blocks (ZIMAS for LA). LA unchanged.
- QA caveats: `half_mile_major_transit` derives from the TPA polygon (the SANDAG Major
  Transit Stops service was dead; a TPA is statutorily within ½ mi of a major transit
  stop). `historic_status` flags pre-1979 structures for manual HRB eligibility.
- Verified end-to-end: full SD `collect.py` run all-VERIFIED (slope JUDGMENT as designed);
  SD assemblage (2 North Park APNs → 29,148.9 sf, full aggregation); LA collect +
  assemblage regression-green.

## v0.12-draft (2026-06-16) — San Diego expansion, step 1: parcel keystone
- New `build/sources/sd_parcel.py` — San Diego County `apn` + `land_sf` via SANDAG's
  countywide Hosted/Parcels layer (the SD analog of LA City Parcels). Address-aware
  snap (same street + closest situs house number within a 150 m buffer, nearest-by-
  centroid fallback) mirrors `parcel._county_snap`; gross area from polygon geometry
  in EPSG:2230 (CA State Plane Zone VI, US ft → sq ft, like LA's 2229). APN formatted
  ###-###-##-##. Includes `parcel_info()` for future assemblage wiring.
- `parcel.land_sf` and `jurisdiction.apn` now route to `sd_parcel` when the county is
  San Diego (LA City / LA County paths unchanged; regression-tested green for LA).
- `_arcgis.query` gained `return_centroid` (surfaces each feature's centroid in out_sr)
  for cheap nearest-parcel snapping without fetching full geometry.
- Live-validated on real SD addresses (e.g. 525 B St → APN 533-523-14-00, 24,656 sf,
  VERIFIED); full `collect.py` SD run green — the ~27 statewide/federal readers light up,
  `pha` resolves to San Diego Housing Commission, ZIMAS block correctly skipped.
- Finding (logged in SAN_DIEGO_EXPANSION.md): `tcac.resource_area`'s endpoint is LA
  County's republished copy (0 San Diego tracts) — needs the statewide 2026 TCAC/HCD
  Opportunity Map. Next steps: statewide TCAC source, then the SD zoning/airport/transit
  block.

## v0.11-draft (2026-06-15)
- hud.qct / hud.dda now report BOTH the current and prior designation year and
  land JUDGMENT when they differ. QCT/DDA are re-designated annually (effective
  Jan 1) and flip year to year; the governing year for a LIHTC deal is its
  allocation/bond/binding-commitment year (+ hold-harmless), not simply the
  current calendar year. So a single-year answer caused false human/tool
  conflicts (e.g. Kinzie DDA: 2026 No vs an analyst's 2025 Yes). Now the cell
  shows "2026: No (current); 2025: Yes" and is flagged JUDGMENT to confirm the
  deal year. Year is read from each layer's `name` (HUD's service-name suffix and
  description are unreliable — the `_2026` QCT description still says "for 2024").

## v0.10-draft (2026-06-15)
Scale-test fixes (the 9-site batch surfaced these):
- geocoder: OSM/Nominatim fallback when the Census geocoder can't match an
  address (resolves the tract via the Census coordinates endpoint), keeping the
  input address for downstream parcel matching. 3801 La Cienega — previously a
  hard failure — now fully resolves (APN matches the manual). 9/9 sites automatable.
- zimas.in_la_city now gated on the Census incorporated place — fixes a border
  misroute where a Culver City parcel on the La Cienega line snapped to an LA City
  parcel and ran the ZIMAS block. City-border jurisdiction routing is now correct.
- ust: GeoTracker (SWRCB) is the primary CA source — counts open+closed UST/LUST
  cleanup sites within ~305 m (≈1,000 ft) and flags Yes for any (Phase I), with EPA
  UST Finder as the non-CA fallback. Catches sites EPA's snapshot missed
  (e.g. Rowland Heights: 2 closed LUST within 1,000 ft).
- slope_grade: 8-point sample (was 4) and now lands JUDGMENT ("confirm on site")
  rather than VERIFIED — it is a DEM screen, not a verdict.
- places: 4 Overpass mirrors + 35 s per-endpoint timeout for fast failover (fixes
  the 134 s outlier seen in the batch).
- hud.dda now queries by the address ZIP (ZCTA5) instead of point-in-polygon — an
  imprecise geocode point could fall in the wrong ZCTA and miss a real DDA
  (e.g. La Cienega / ZCTA 90232). Falls back to point-in-polygon for non-metro
  (county-keyed) DDAs.

## v0.9.1-draft (2026-06-15)
- places.py: tightened two loosely-tagged OSM categories. nearest_school now
  means K-12 (excludes preschool/childcare/college by school subtag + name);
  nearest_medical_clinic now targets real medical clinics/hospitals and excludes
  occupational-health and veterinary. Pico: school -> Queen Anne Elementary
  (0.33 mi, was "California Childrens College"); clinic -> Jung Medical Center
  (0.75 mi, was an occupational-health center).
- Verified Neighborhood Change for tract 06037212800 against the authoritative
  AFFH dataset: nbrhood_chng=1 (pathway1a+pathway2, baseline race+income met,
  not excluded) -> Yes. (Confirms the automated answer; the manual sheet's No
  was the error.)

## v0.9-draft (2026-06-15)
- Parallelized the pipeline (readers are I/O-bound -> threads release the GIL).
  Single-parcel collect ~60-90s -> ~10s; 3-parcel assemblage minutes -> ~18s.
  Output is identical — only timing changed.
  - runner.py split: run_reader() runs a reader OFF the workbook (thread-safe);
    apply_outcome() writes one outcome to an already-open workbook. run_field()
    now composes them (selftest unchanged).
  - collect.py: Phase 1 fans all readers across a ThreadPoolExecutor; Phase 2
    applies outcomes in a single workbook open/save (was ~40 load/saves). Shared
    caches (zimas parcel snap, nc Neighborhood-Change file) pre-warmed before the
    fan-out to avoid races.
  - _arcgis.py: thread-safe per-process response cache — dedupes identical queries
    (e.g. zoning/q_conditions/transitional_height all hitting NavigateLA layer 71).
  - places.py: the 8 proximity categories now fetch in ONE combined Overpass query
    per parcel (per-key locked + cached) instead of 8 calls.
  - assemblage.py: APN resolution parallelized; all (parcel x reader) tasks run in
    one pool with per-parcel snaps pre-warmed.

## v0.8.1-draft (2026-06-15)
- Street View logged as an ACTIVATE-LATER feature and DEACTIVATED: streetview.py
  gains an `ENABLED = False` switch (functions raise while off; have_key() returns
  False even if a key is present), and it stays unimported by collect.py. New
  ACTIVATE_LATER.md documents the GOOGLE_MAPS_API_KEY path + the 3-step activation;
  README points to it.

## v0.8-draft (2026-06-15)
- 16 more fields automated (~40 readers total):
  - 3 "free wins" (jurisdiction.py): address, apn, city_jurisdiction (the schema's
    Phase-1 driver) — plumbed from data the pipeline already computes.
  - Proximity batch (places.py, 8 fields): nearest bus stop / grocery / park /
    clinic / library / pharmacy / school / qualifying transit — via OpenStreetMap
    Overpass (free, no key). OSM completeness varies (informational reads).
  - slope_grade (slope.py): DERIVED from USGS 3DEP elevation (EPQS) — max grade
    over a 40 m sample, Yes >= 10%. A DEM screen; confirm on site.
  - cell_towers (towers.py): HIFLD/FCC Cellular Towers proximity (<=150 m = Yes).
    Absence is NOT authoritative (FCC licensing subset is sparse) — caveated.
  - airport_hazard_zone (airport.py): LA County ALUC A-NET (LA County only; raises
    elsewhere -> manual, no statewide AIA layer exists).
  - coastal_zone (coastal.py): CA Coastal Commission / Caltrans Coastal Zone
    polygon (statewide point-in-polygon).
  - tier_transit_verification (zimas.py): derived LA-City summary of TOC tier +
    ½-mile major transit.
- streetview.py: key-ready Street View Static pre-screen AID for the site-visit
  fields. NOT wired into collect (needs GOOGLE_MAPS_API_KEY, and dated/single-time
  imagery is an aid, not a VERIFIED source). geocoder now also returns `place`.

## v0.7-draft (2026-06-15)
- pha automated (pha.py, now 24 readers): resolves the governing Public Housing
  Authority from incorporated city + county against HUD's authoritative Public
  Housing Authorities point layer — city PHA when a PHA's formal name contains the
  city and not "County" (e.g. Housing Authority of the City of Santa Monica), else
  the county authority (name contains "County", e.g. LA County Development
  Authority). Generalizes statewide; verified LA City->HACLA, Santa Monica,
  Pasadena, San Diego->SD Housing Commission, unincorporated->HACoLA. HUD's
  service-area POLYGON layer is avoided (HUD-flagged proposed/experimental; its
  polygons overlap — every LA point falsely hits Baldwin Park).
- geocoder now returns `place` (incorporated city, suffix-stripped) from the
  Census 'Incorporated Places' geography; None for unincorporated areas.

## v0.6-draft (2026-06-15)
- 4 more fields automated (now 23 readers): county, geographic_pool, land_sf,
  neighborhood_change_area.
  - jurisdiction.py: county (from geocoder county FIPS, CA map) and
    geographic_pool (CDLAC region via canonical/cdlac_regions.csv + LA city-limits
    special case: City of LA vs Balance of LA County). Verified across City of LA,
    Balance of LA County (Santa Monica), and Coastal Region (San Diego).
  - parcel.py: land_sf = gross land area. LA City via LA City Parcels geometry
    (EPSG:2229, sums an APN's lots = ZIMAS lot area); non-LA-City LA County via
    the Assessor parcel polygon (point, else nearest-within-40m -> JUDGMENT/verify).
  - nc.py: neighborhood_change_area from the CTCAC/HCD AFFH statewide GeoJSON
    (field nbrhood_chng by tract fips; 1=Yes). Not a query API — downloaded once
    and cached to _cache/ as a slim {fips:flag} map. URL carries a per-vintage
    asset path (update on new releases).
- _arcgis.ring_area (shoelace) shared; assemblage writes COMBINED land_sf and
  aggregates the new derived fields across parcels.

## v0.5-draft (2026-06-15)
- build/assemblage.py: multi-APN block-assemblage support. Sizes the combined
  site (LA City Parcels layer 5 geometry in EPSG:2229 — reproduces ZIMAS lot
  area; sums multi-lot APNs) and runs every reader per parcel, aggregating to a
  site-level answer: yes/no hazards -> Yes if ANY parcel (names APNs); text/enum
  -> shared value or "MIXED: v (apns); …". A JUDGMENT on any parcel makes the
  site field JUDGMENT. Surfaces mixed zoning, partial historic status, tract
  splits — the things a single-parcel read misses.
- geocoder.geocode_point(lon,lat): reverse the keystone (point -> census tract)
  so APN-resolved parcels (centroid, no address) can run the tract-keyed readers.
- Note: one APN can span multiple lot polygons (e.g. 4201 Pico anchor = 2 lots,
  8,547 sf) where ZIMAS shows only one — assemblage sums them and reports per-APN.

## v0.4-draft (2026-06-15)
- transitional_height_adj_zones (C46) automated as a DERIVED reader: no layer
  exists, so it's computed from zoning adjacency (LAMC 12.21.1-A.10) on
  NavigateLA layer 71 — C/M subject + RW1-or-more-restrictive zone within
  49/99/199 ft → 25/33/61 ft cap. Lands JUDGMENT (estimate, route up); non-C/M
  parcels resolve NA.
- runner.run_field now honors an optional reader-returned `state` (validated
  against READER_LANDING_STATES, default VERIFIED) so a derive-only reader can
  land JUDGMENT/NA instead of overclaiming VERIFIED; selftest covers it.
- special_grading_area_la (C56) confirmed NOT automatable without a browser:
  exhaustive search found no REST layer (NavigateLA 352 "Hillside Grading Area"
  is a different dataset); value lives only in ZIMAS's locked parcel DB.

## v0.3-draft (2026-06-15)
- ZIMAS reclassified Tier-B -> Tier-A: build/sources/zimas.py reads the LA-City
  zoning/hazard block via open ArcGIS REST (NavigateLA + LA City Planning AGOL),
  no browser. Parcel snap (NavigateLA 395 + 40 m buffer) -> point-query zoning
  (incl. [Q] prefix), specific plan, HPOZ + Historic-Cultural Monuments, methane
  MZ/MB, council district, TOC tier, ½-mile major transit (AB2097). 8/10 LA-City
  fields automated; transitional_height + special_grading have no public REST
  layer and stay manual. collect.py gates the ZIMAS block on in_la_city().
- fema.py refactored onto shared _arcgis.query (User-Agent + retry); confirmed
  FEMA NFHL is intermittently flaky under burst load -> TOOL-FAIL/escalation
  absorbs it (never invents). feasibility.md + runbook updated to match.

## v0.2-draft (2026-06-15)
- Tier-A readers live-validated against real endpoints and wired through
  runner.run_field: geocoder (Census, keystone) + FEMA NFHL flood, HUD QCT/DDA,
  CTCAC/HCD resource area, federal OZ, CAL FIRE FHSZ (SRA+LRA), CalGEM WellSTAR
  wells, CGS Alquist-Priolo + liquefaction, EPA UST Finder USTs.
- Shared build/sources/_arcgis.py (point/proximity query, UA, retry, error
  surfacing); build/collect.py orchestrates geocode -> all readers -> workbook.
- FEMA EFF_DATE now rendered as ISO date; NFHL layers 28/3 confirmed live.
- Confirmed-contract notes: OZ stamped with 2018 vintage (sunsets 2026-12-31);
  CAL FIRE LRA flagged OSFM-recommended (local adoption varies); CGS "No" = not
  in a mapped zone (not "no hazard" where unstudied). Neighborhood Change (C28)
  has no public REST endpoint — stays manual.

## v0.1-draft (2026-06-15)
- Initial canonical spec: field schema (97 fields), state taxonomy (12 states),
  feasibility map. Scrubbed + stateful blank master (carryover removed, Status
  gutter, State Log tab). validate.py drift-guard; generate.py from-schema builder.
