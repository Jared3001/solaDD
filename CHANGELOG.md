# Changelog

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
