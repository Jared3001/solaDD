# DD Map-Automation Feasibility Map

*Companion to the field schema and state taxonomy. Assesses, source by source, what
the checklist's verification layer can realistically be automated against — and what
stays human-only. No build here; this is the go/no-go map that the build plan follows.*

Built 2026-06-15. Endpoint facts below were checked against current sources; reachability
from the actual run environment still needs a live test (see §Caveat).

---

## How automation ties to the state taxonomy

Every automated read resolves to a taxonomy state, so "automatable" always means *automatable
including its failure path*:

- clean read → **VERIFIED** (record source + date + the query/tract/panel used)
- endpoint/tool error or unresponsive → **TOOL-FAIL n/3** → (3 tries) → **MANUAL-VERIFY**
- result exists but needs a regulatory/borderline call → **JUDGMENT** (route up)
- no uniform endpoint / produced by a person → stays **EXTERNAL-PENDING** or human **BROWSER-PENDING**

The win from automation is concentrated in the data/API tier; the runbook §9 is right that the
interactive GIS *viewers* resist extraction. The trick is that for most fields a **data or REST
path exists that bypasses the viewer entirely.**

---

## The keystone: a geocoder unlocks most of Tier A

Most data-driven paths need one of two things: the parcel's **census tract** (HUD QCT/DDA, TCAC
Resource Area, OZ) or its **lat/lon** (FEMA, CGS, CAL FIRE, CalGEM spatial queries). The U.S.
Census **Geocoder API** (`geocoding.geo.census.gov/geocoder/`) returns both — state/county/tract/block
*and* lat/lon — for a single address or a batch, as JSON. Build this once and it feeds everything
below. Caveat: Census geocoding is approximate (block-level), fine for tract/zone lookup but not
for sub-parcel precision; for a parcel that straddles a zone boundary, fall back to the map.

---

## Tier summary

| Source | Fields settled | Tier | Path (bypasses the viewer) | On failure |
|---|---|---|---|---|
| Census Geocoder | (keystone: tract + lat/lon) | A | REST JSON, single/batch | TOOL-FAIL |
| HUD SADDA | qct, dda | A | tract → HUD annual QCT/Small-DDA lists | TOOL-FAIL |
| TCAC/HCD Opportunity | resource_area, neighborhood_change_area | A | tract → published tract table | TOOL-FAIL |
| FEMA NFHL | flood_zone (+ FIRM panel) | A | official ArcGIS REST by point | TOOL-FAIL |
| CalGEM WellSTAR | wells_on_site | A | REST/point-buffer or nightly data download | TOOL-FAIL |
| CGS (EQ Zapp) | alquist_priolo_fault_zone, liquefaction_zone | A/B | ArcGIS REST / county data packages | TOOL-FAIL |
| CAL FIRE FHSZ | very_high_fire_hazard_zone | A/B | ArcGIS REST / county data | TOOL-FAIL → JUDGMENT* |
| OZ (Novogradac/HUD) | opportunity_zone | A | published OZ tract list | TOOL-FAIL |
| GeoTracker | underground_storage_tanks | A/B | bulk download or runReport-by-address | TOOL-FAIL |
| ZIMAS | LA-City zoning/hazard/TOC block | B | Claude-in-Chrome, one get_page_text | TOOL-FAIL |
| District lookups | council_supervisor_district, school district | B | local/Census district REST | TOOL-FAIL |
| Utility service areas | power/sewer/water provider | C | jurisdiction-specific, no uniform API | MANUAL-VERIFY |
| ALUC / Coastal / local historic | airport, coastal_zone, historic (non-LA) | C | heterogeneous layers | MANUAL-VERIFY |
| Permit records | permit_records | C | jurisdiction portal | MANUAL-VERIFY |
| Will-serve, ESA, ALTA, geotech, title, counsel… | reports & external items | — | produced by people | EXTERNAL-PENDING |
| Proximity (Places) | nearest_* | (done) | already automated via Places tool | — |

\* CAL FIRE returns a *tier* and a *recommended-vs-adopted* status — see its note.

---

## Tier A — data/API automatable (no interactive map)

**HUD SADDA → `qct`, `dda`.** HUD publishes the QCT and Small-Area-DDA designations as annual
datasets keyed to census tract / ZCTA. Path: geocode → tract → look up in the current-year list.
This removes the viewer's layer-toggle step (the runbook's main HUD friction). Record the year and
tract. A QCT can also be an OZ — don't infer one from the other.

**TCAC/HCD Opportunity → `resource_area`, `neighborhood_change_area`.** Published each year as a
downloadable tract-level table (designation + score) plus the Neighborhood Change flag. Path:
geocode → tract → table lookup. This removes the "you must click the tract" manual step and is the
authoritative answer ZIMAS's TCAC field lags behind.

**FEMA NFHL → `flood_zone` (+ FIRM panel).** FEMA hosts an official ArcGIS REST service
(`hazards.fema.gov/arcgis/rest/services/public/NFHL`) whose flood-hazard layer returns `FLD_ZONE`,
`SFHA_TF`, and FIRM panel attributes as JSON/geoJSON for a point query. This is a better automation
path than the firmette-PDF workaround (no rendering, structured output) and is a *different endpoint*
than the blocked viewer — so it should be tested even though the viewer is blocked. Yes/No cell =
inside/outside SFHA; the actual zone (X/AE/etc.) + panel + date go in Notes.

**CalGEM WellSTAR → `wells_on_site`.** This is the chronic TOOL-FAIL source today — but the
instability is in the *interactive Well Finder viewer*, not the data. CalGEM exposes WellSTAR via an
ArcGIS REST directory (`gis.conservation.ca.gov/server/rest/services/WellSTAR`, incl. a `Wells`
MapServer and an `AreaForXY` geoprocessing service) **and** publishes the well points as downloadable
SHP/CSV/GeoJSON updated nightly. Path: point + buffer spatial query, or download once and spatial-join
locally. **Recommendation: re-point this field from the viewer to the REST/data path — it likely
converts a recurring failure into a reliable lookup, and would close the open Batch-2 C57 reads.**

**CGS (EQ Zapp) → `alquist_priolo_fault_zone`, `liquefaction_zone`.** EQ Zapp is backed by ArcGIS
services, and CGS publishes Seismic Hazard Zone + A-P fault data as county packages. Path: point query
→ zone + quad. Yes triggers mandatory geotech (A-P also reduces buildable area — feed `land_sf`).

**CAL FIRE FHSZ → `very_high_fire_hazard_zone`.** Available via ArcGIS REST / county data by point.
Two real complications, both already flagged: (1) the source returns a **tier** (Moderate/High/Very
High), which the Yes/No cell can't hold honestly — fix the field to an enum_tier or push the tier to
Notes; (2) the 2025 maps are **recommended** until a jurisdiction adopts them by ordinance, so the
*legally governing* answer is a **JUDGMENT** call, not a pure data read. Automate the data pull;
route the regulatory-effectiveness gap up.

**OZ → `opportunity_zone`.** Published OZ tract list; geocode → tract → lookup. Retire the
"Highest Resource ⇒ not an OZ" shortcut in the automated path (it has already misfired on a QCT) —
always do the lookup; it's now free given the geocoder.

**GeoTracker → `underground_storage_tanks`.** Bulk site downloads exist, and the documented
runReport-by-address URL returns a parseable report. Either works; bulk + spatial proximity is the
more robust automated path.

## Tier B — browser-agent automatable (interactive, one structured read)

**ZIMAS (LA City only).** For an LA-City parcel, one Claude-in-Chrome pass (search → expand the three
panels → `get_page_text`) returns the entire zoning + hazard + TOC/ED-1 block. It's the efficient
LA-City convenience path — but note most of those hazard fields *also* have statewide Tier-A sources
(FEMA, CGS, CAL FIRE, CalGEM), so ZIMAS is best used as the LA-City one-shot **plus a cross-check**,
not the sole authority (its TCAC field is known to lag).

**District lookups.** Council/supervisor and school district often have a REST/lookup endpoint
(Census or local). Borderline A/B; low risk.

## Tier C — human / semi-only (heterogeneous, no uniform API)

Utility provider service areas (power/sewer/water **provider** identification), ALUC airport-influence
overlays, the Coastal Zone boundary for the rare coastal site, and non-LA local historic inventories
and permit portals are a patchwork — each jurisdiction differs, with no common interface. Treat as
**MANUAL-VERIFY** (a person opens the right local source). Some (e.g. Coastal Commission, larger county
GIS) have queryable layers and could be promoted to B case-by-case, but they're low-frequency and not
worth a general automation.

## Out of scope for map automation (people produce these)

Will-serve letters, Phase I/II ESA, ALTA survey, geotech/soils, arborist, methane/soil-gas report,
architectural yield study, preliminary title, easements, and litigation/counsel are **EXTERNAL-PENDING**.
Automation's only role here is to *track and chase* them (status, who owns it, age), not to produce them.

---

## Caveat — reachability must be tested in the run environment

Every Tier-A path assumes the execution environment can reach the source endpoint over HTTPS. Two
things to confirm before committing to the data-API approach:

1. **Network egress.** A sandboxed run may allowlist only certain domains; the gov endpoints
   (`geocoding.geo.census.gov`, `hazards.fema.gov`, `gis.conservation.ca.gov`, HUD/TCAC hosts) must be
   reachable, or the data-API tier has to run through the browser agent instead.
2. **REST vs viewer.** The blocked items historically were the *interactive viewers*. The REST
   services and data downloads are different endpoints and should each be probed directly — a blocked
   viewer does not imply a blocked REST service.

If neither is available, the fallback for Tier A/B is the same browser-agent path as ZIMAS, which is
slower but already proven.

---

## Suggested build order (recommendation — senior call)

1. **Geocoder** (keystone; unlocks the rest) — prove address → tract + lat/lon.
2. **One end-to-end reference source** through the full read → State Log → escalate loop. FEMA NFHL
   REST is the cleanest candidate (single point query, structured `FLD_ZONE`/SFHA/panel, no auth).
3. **The rest of Tier A** in parallel once the loop pattern is set, with **CalGEM prioritized** —
   biggest reliability gain (chronic TOOL-FAIL → data lookup) and it clears the open Batch-2 reads.
4. **ZIMAS** browser pass for the LA-City convenience block.
5. Leave Tier C as MANUAL-VERIFY; wire EXTERNAL-PENDING items into status-tracking only.
