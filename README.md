# DD Feasibility — Acquisition Site Due Diligence

Canonical home for the Site DD process. **The schema is the single source of truth;
the master is generated from / validated against it.** Hand-editing the master out of
sync with the schema is the failure this repo exists to prevent.

## Layout
```
canonical/   schema.yaml · taxonomy.yaml · runbook.md · feasibility.md · cdlac_regions.csv
build/       validate.py (drift guard) · generate.py (build master from schema)
             runner.py (read→state→log loop) · collect.py (geocode→all readers→workbook)
             assemblage.py (multi-APN block: combined land area + aggregated designations)
build/sources/  geocoder.py (keystone) + Tier-A readers: fema · hud · tcac · oz ·
             calfire · calgem · cgs · ust · zimas (LA-City block via NavigateLA REST) ·
             jurisdiction (county, geographic_pool) · parcel (land_sf) · nc (neighborhood change)
             (each → {answer,notes}; _arcgis.py shared query helper)
template/    Checklist_BLANK_master.xlsx  ← the blank; copied per property, never edited
logs/        scrub_inventory.csv (one-time master cleanup record)
```
Per-property checklists (instances) live in **Drive** (`SOLA/DD/properties/<deal>/`),
not in this repo. Each instance's State Log is a tab in that instance's workbook
(per-property, by decision).

## The one rule
1. Change `canonical/schema.yaml` (or `taxonomy.yaml`) — never the master directly.
2. `python build/validate.py` — fails if `template/` drifts from the schema.
3. Regenerate if needed: `python build/generate.py` builds a structural master from
   the schema (dropdowns, formulas, Status gutter, lookup, State Log). Cosmetic
   scaffolding (col D `[Link…]`, col F guidance) lives in the styled skeleton in
   `template/`; the validator guards it.

## Version stamping
Schema/taxonomy versions are stamped into the template header (cell E2) and should be
copied into each per-property instance, so a later schema change tells you which old
sheets predate it.

## Not done by automation (people produce these)
Will-serve letters, ESA/geotech/ALTA/yield reports, title, counsel — tracked, not produced.

## Setup (you do this — requires your GitHub credentials)
```
git remote add origin <your-repo-url>
git push -u origin main
```
