# Changelog

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
