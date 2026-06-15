# Acquisition Site Feasibility — Due Diligence Runbook (Automation Edition)

*Version 2.0 — 2026-06-15. Supersedes the prior manual runbook. The manual method
is unchanged where it matters; what is new is that the checklist is now
schema-driven, state-tracked, and partly automatable.*

## 0. Canonical home

**Spec + code (source of truth): https://github.com/Jared3001/solaDD**

- `canonical/` — `schema.yaml` (field definitions = source of truth), `taxonomy.yaml`
  (cell-state vocabulary), `feasibility.md` (map-automation assessment), `cdlac_regions.csv`
- `build/` — `validate.py` (drift guard), `generate.py` (build the master from the schema)
- `template/` — the blank master (copied per property, never edited)

Working files live in Drive at **`SOLA/DD/`**: `template/` (the blank to copy),
`properties/<deal>/` (per-property instances), `logs/`. The canonical spec is NOT
mirrored into Drive — it lives only in git, to avoid the two drifting apart.

**The one rule — schema is canonical.** Change `canonical/schema.yaml`, never the
master directly. `python build/validate.py` fails the build if the master drifts from
the schema (labels, dropdown menus, formulas, status initialization). Rebuild a clean
structural master with `python build/generate.py`.

## 1. What "done" means

Every in-scope row has (a) an entry in the answer column (Column C) and (b) a STATE
in the Status column (Column A). Each entry is a verified fact, an OM-sourced secondary
fact, or an open item carrying the right state. Never an invented fact — missing input
gets a state, never a plausible guess. Dropdown cells get exactly one menu option;
qualifiers go to Notes (Column E).

## 2. The method in one breath

Copy the template, re-point it at the actual jurisdiction FIRST, desk-fill the OM
"given" facts, verify every map designation against the government source of record
(treating OM claims as claims), and give everything else its state.

## 3. The state model (new — see taxonomy.yaml)

State lives in the **Status column (Column A)**; the answer stays in Column C. Twelve
states: DESK-PENDING, BROWSER-PENDING, EXTERNAL-PENDING, SITE-VISIT, JUDGMENT,
TOOL-FAIL, MANUAL-VERIFY (open); VERIFIED, OM-SOURCED, COMPUTED, NA (closed); ASSIGN.
Tool-failure is its own retryable state: `TOOL-FAIL n/3`, auto-escalating to
MANUAL-VERIFY after 3 attempts. Each property's attempt history is logged in that
workbook's **State Log** tab (per-property). Stamp the schema + taxonomy version into
each instance so later spec changes are traceable.

## 4. Per-property workflow

1. Copy `template/` → `SOLA/DD/properties/<deal>/`; fill header + version stamp.
2. **Jurisdiction first** — set City/Jurisdiction; this auto-marks LA-City-only fields
   N/A off LA City and routes every jurisdiction-specific authority.
3. Desk-fill OM facts (note gross vs. buildable); tag OM hazard/overlay claims "to verify."
4. Verify map designations against source — automated where Tier A/B (see §5), else manual.
5. Proximity + providers via Places / service-area maps; will-serve = EXTERNAL-PENDING.
6. Flag judgment items (revenue class, ½-mile transit, SB8, entitlement, leads) → JUDGMENT.
7. Phase 6 notes hygiene (Column C glance answers; Column E reconciled to verified C; log deletions).
8. `validate.py` clean + recalc 0 errors → hand off.

## 5. Automation tiers (new — see feasibility.md)

A **geocoder** (address → census tract + lat/lon) is the keystone. Then:
- **Tier A (data/API, bypasses the viewer):** HUD QCT/DDA, TCAC Resource Area, OZ,
  FEMA flood (official NFHL REST), CGS fault/liquefaction, CAL FIRE FHSZ, CalGEM wells
  (REST/data — escapes the unstable viewer), GeoTracker USTs.
- **Tier B (browser agent, one structured read):** ZIMAS (LA-City block), district lookups.
- **Tier C (manual):** utility providers, ALUC, coastal, non-LA historic, permits.
- **External (people produce these):** will-serve, ESA/geotech/ALTA/yield, title, counsel.

Each automated read writes the State Log and sets state: clean → VERIFIED;
endpoint/tool error → TOOL-FAIL n/3 → MANUAL-VERIFY; regulatory/borderline → JUDGMENT.

## 6. Guardrails that still govern (unchanged)

Re-map jurisdiction first. OM claims ≠ facts. Capture gross vs. buildable. CAL FIRE
2025 maps are recommended until adopted — flag the gap. A QCT breaks the
"Highest-Resource ⇒ not OZ" shortcut — always pull the OZ source. Read at the parcel,
not the neighborhood. Utility providers are jurisdiction-specific — never carry over.
Notes hygiene is a two-pass close-out, log every deletion. Never invent. Route
judgment up.

## 7. Source catalog

Per-field sources and URLs are in `schema.yaml` (`source_of_record` / `source_url`);
the automation method per source is in `feasibility.md`. Jurisdiction routing: for a
City-of-LA parcel, ZIMAS resolves most of the zoning+hazard block in one read; for
other cities / unincorporated LA County, those LA-City fields are N/A and you route to
the local planning dept plus the statewide sources (HUD, TCAC, FEMA, CGS, CAL FIRE).
