# San Diego County Expansion — Source Analysis & Plan

**Status:** analysis complete, endpoints validated live; build not started. 2026-06-16.
**Goal:** extend the DD feasibility automation to cover San Diego County deals, the
same way it covers LA today — reusing every reader that is national or CA-statewide,
and replacing the LA-City / LA-County-specific readers with San Diego equivalents.

---

## Verdict

The automation has **two layers**, and they port very differently:

- **Eligibility + hazard data (federal + CA-statewide) — ports for free.** ~27 of the
  ~40 automated fields work in San Diego with **zero code changes**: they key off
  census tract, ZIP, lat/lon, or county FIPS against national/statewide services.
- **Parcel + municipal-zoning data (LA-specific) — must be rebuilt.** 13 fields plus the
  block-assemblage tool are wired to `maps.lacity.org` (ZIMAS/NavigateLA), LA City
  Parcels, and LA County layers. They `raise` or mis-route outside LA County.

The foundation is already statewide: the **geocoder keystone** works anywhere (Census +
Nominatim fallback; county-FIPS table includes San Diego `073`), and `geographic_pool`
already maps **San Diego → Coastal Region** via `canonical/cdlac_regions.csv`.

**The good news from validation:** San Diego has a clean analog to LA's stack. The City
of San Diego's ArcGIS server (`webmaps.sandiego.gov`) is the **NavigateLA/ZIMAS
equivalent** — zoning, overlays, airport/ALUC, and transit-priority layers in one place —
and **SANDAG's countywide parcels layer** is a near drop-in for LA City Parcels (APN +
structured situs + polygon geometry in State Plane feet).

---

## Replacement source systems (validated live 2026-06-16)

| System | Endpoint | Validation | Replaces |
|---|---|---|---|
| **SANDAG Parcels** (keystone) | `geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer/0` | ✅ 1,089,619 parcels; SR **EPSG:2230** (= sq ft, like LA's 2229); fields `apn`, `situs_address`, `situs_street`, `acreage`, geometry rings | `parcel.land_sf`, `jurisdiction.apn`, `assemblage.py` |
| **City of SD zoning** | `webmaps.sandiego.gov/.../Planning/PLN_LongRangePlanning/MapServer/27` (Base Zones) | ✅ point query → `ZONE_NAME` (e.g. `CCPD-ER`) | `zoning` |
| **City of SD overlays** | `webmaps.sandiego.gov/.../DSD/Zoning_Overlay/MapServer` | ✅ layers incl. Coastal Overlay, Community Plan Implementation, height-limitation overlays | `specific_plan_overlay`, `transitional_height_adj_zones` |
| **City of SD airport/ALUC** | `webmaps.sandiego.gov/.../DSD/Airports/MapServer` | ✅ layers: **Airport Influence Areas**, **ALUC Overlay Zone**, ALUCP Noise Contours | `airport_hazard_zone` |
| **SD Transit Priority Areas** | `webmaps.sandiego.gov/.../Planning/PLN_TransitPriorityArea/MapServer` | ✅ layer: Transit Priority Areas (TPA) | `toc_tier_la` → TPA, part of transit verification |
| **SD Major Transit Stops** | `services9.arcgis.com/6EFrbuKQD1dq7c4Q/.../San_Diego_Major_Transit_Stops/FeatureServer` | ⚠️ exists (confirm layer 0 fields at build) | `half_mile_major_transit` |
| **County (unincorporated)** | `gis-public.sandiegocounty.gov/.../sdep_warehouse/ZONING_CN/MapServer` | ✅ reachable | unincorporated-area zoning |

> **Scope note (mirrors LA exactly):** `webmaps.sandiego.gov` covers the **City of San
> Diego** only. San Diego County has 18 incorporated cities (Chula Vista, Oceanside,
> Carlsbad, El Cajon, …) that each run their own zoning GIS, plus unincorporated County.
> Recommended v1 scope = **City of San Diego (webmaps) + unincorporated County**, with
> other incorporated cities routing to manual — identical to how LA covers LA City +
> LA County unincorporated and routes other cities to local planning. SANDAG Parcels is
> countywide, so `apn`/`land_sf`/assemblage work for the whole county regardless.

---

## Field-by-field

### ✅ Works as-is — ~27 fields (no change)
`address`, `county`, `geographic_pool` (SD→Coastal Region), `city_jurisdiction`
(Census place), `pha`†, `qct`, `dda`, `resource_area`, `neighborhood_change_area`,
`opportunity_zone`, `flood_zone`, `very_high_fire_hazard_zone`, `coastal_zone`‡,
`wells_on_site`, `liquefaction_zone`§, `alquist_priolo_fault_zone`§,
`underground_storage_tanks`, `slope_grade`, `cell_towers`, and the 8 `nearest_*`
proximity fields.

- † `pha` — HUD layer is national; **verify** SD's city authority resolves: it's the
  *San Diego Housing Commission* (no "Authority" in the name), vs *Housing Authority of
  the County of San Diego*.
- ‡ `coastal_zone` — statewide; **especially relevant** in SD (large coastal footprint).
- § `cgs` — CGS EQ Zapp is statewide; SD's **Rose Canyon** AP fault zone and mapped
  liquefaction zones are covered. "No" still means "not in a mapped zone."

### 🔁 Needs a San Diego reader — 13 fields + assemblage

| Field | Today (LA) | San Diego replacement |
|---|---|---|
| `apn` | LA parcels | SANDAG Parcels `apn` (note: SD APN formats differently than LA's 4-3-3) |
| `land_sf` | LA City/County parcels | SANDAG Parcels geometry area (EPSG:2230) |
| *assemblage.py* | LA City Parcels | SANDAG Parcels (same envelope + ring-area pattern) |
| `zoning` | ZIMAS | City Base Zones (city) / County ZONING_CN (unincorp.) |
| `specific_plan_overlay` | ZIMAS | City Zoning_Overlay (Community Plan Implementation, etc.) |
| `council_supervisor_district` | ZIMAS | SD Council districts + County Supervisorial (SanGIS) — *find at build* |
| `historic_status` | ZIMAS | City of SD Historical Resources — *find at build* |
| `airport_hazard_zone` | LA County ALUC | City Airports/ALUC (Airport Influence Areas) |
| `toc_tier_la` | LA TOC | SD **Transit Priority Area** (no "tiers" — boolean/qualitative) |
| `half_mile_major_transit` | LA data | SD Major Transit Stops (½-mi buffer) |
| `tier_transit_verification` | composite | rebuild from TPA + major-transit |

### ⛔ Becomes N/A in San Diego (no source needed)
- `q_conditions_la` — `[Q]` is an LA zoning device; SD has none (handle via overlays).
- `methane_hazard_zone_la` — LA City methane ordinance has no SD equivalent (addressed
  via Phase I ESA).
- `special_grading_area_la` — already LA-only with no automation anywhere; stays manual.

---

## Architecture

Today `collect.py` gates the LA block behind `zimas.in_la_city(geo)`. The clean
extension is a **jurisdiction router**:

```
statewide READERS         → always run (the ~27 portable fields)
if zimas.in_la_city(geo)  → LA block (existing ZIMAS_READERS + LA parcels)
elif county == "San Diego"→ SD block (new sandiego.py readers + SANDAG parcels)
else                      → route to local planning (manual), as today
```

- New module(s): `build/sources/sandiego.py` (zoning/overlay/airport/TPA/transit, mirroring
  `zimas.py`), and a SANDAG-parcels path for `parcel.py` / `jurisdiction.apn` / `assemblage.py`
  (parameterize the parcel layer + SR by county instead of hard-coding LA).
- `_arcgis.py` is reused unchanged (generic ArcGIS REST helper).
- The parcel snap pattern ports directly: SANDAG exposes `situs_address` (numeric) +
  `situs_street`, so the LA County address-aware snap (same street + closest house number,
  envelope buffer) works with field-name swaps.

---

## Suggested phasing

1. **Parcel keystone** (highest leverage): SANDAG Parcels path → unblocks `apn`,
   `land_sf`, and `assemblage.py` countywide. ~1 reader path, validated.
2. **SD zoning/planning block** (`sandiego.py`): `zoning`, `specific_plan_overlay`,
   airport, then districts + historic. City of SD scope first.
3. **Transit**: TPA + Major Transit Stops → `toc`-analog, `half_mile_major_transit`,
   `tier_transit_verification`.
4. **Polish**: mark the N/A fields, SD APN formatter, county router in `collect.py`,
   PHA naming check, scale-test on real SD addresses.

The ~27 portable fields need no work — they light up the moment the router lets a
San Diego address through.

---

## Open items to confirm during build
- Council/Supervisor district + historic-resources REST layers (sources identified as
  City of SD / SanGIS; not yet endpoint-validated).
- Major Transit Stops FeatureServer layer-0 field names + whether "planned" stops should
  count for `half_mile_major_transit`.
- SD APN canonical format for display/validation.
- Whether to extend zoning beyond City of SD + unincorporated to other incorporated
  cities (long tail; recommend deferring, route to manual like non-LA-City today).

## Sources
- SANDAG GIS / REST directory · SANDAG Hosted Parcels (`geo.sandag.org`)
- City of San Diego ArcGIS (`webmaps.sandiego.gov`): Planning, DSD/Zoning_Overlay, DSD/Airports, PLN_TransitPriorityArea
- County of San Diego (`gis-public.sandiegocounty.gov`): sdep_warehouse
- San Diego County Regional Airport Authority ALUCP (`san.org/aluc`)
- San Diego Major Transit Stops (`services9.arcgis.com/6EFrbuKQD1dq7c4Q`)
