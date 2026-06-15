#!/usr/bin/env python3
"""
collect.py — run every Tier-A reader against a property workbook through
runner.run_field. This is the keystone (geocoder) feeding the Tier-A source
modules into the state/log loop: each field gets its answer (col C), notes
(col E), a STATE (col A), and a State Log row, with TOOL-FAIL -> MANUAL-VERIFY
escalation handled by run_field.

Usage:
  python build/collect.py --demo "11300 S Main St, Los Angeles, CA 90061"
      copy template/ to a throwaway workbook, geocode the address, run all
      readers, and print the resulting states + cells.
  python build/collect.py path/to/property.xlsx [address]
      run against a real per-property workbook (address read from C3 if omitted).

A field is automated only if it appears in READERS; everything else keeps the
state the template/generator assigned (DESK-PENDING, BROWSER-PENDING, etc.).
"""
import sys, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build" / "sources"))

import yaml
from runner import run_field
from geocoder import geocode
import fema, hud, tcac, oz, calfire, calgem, cgs, ust, zimas, jurisdiction, parcel, nc

# field id -> reader callable(geo) -> {"answer","notes"} (or raises -> TOOL-FAIL)
# Statewide / federal / derived sources — run for any CA parcel.
READERS = {
    "county": jurisdiction.county,
    "geographic_pool": jurisdiction.geographic_pool,
    "land_sf": parcel.land_sf,
    "qct": hud.qct,
    "dda": hud.dda,
    "resource_area": tcac.resource_area,
    "neighborhood_change_area": nc.neighborhood_change,
    "opportunity_zone": oz.opportunity_zone,
    "flood_zone": lambda geo: fema.flood_zone(geo["lon"], geo["lat"]),
    "very_high_fire_hazard_zone": calfire.very_high_fire_hazard_zone,
    "wells_on_site": calgem.wells_on_site,
    "liquefaction_zone": cgs.liquefaction_zone,
    "alquist_priolo_fault_zone": cgs.alquist_priolo_fault_zone,
    "underground_storage_tanks": ust.underground_storage_tanks,
}

# LA-City zoning/hazard block (ZIMAS-equivalent) — only run when the parcel is
# in LA City; off LA City these route to local planning and stay manual.
ZIMAS_READERS = {
    "zoning": zimas.zoning,
    "q_conditions_la": zimas.q_conditions,
    "specific_plan_overlay": zimas.specific_plan_overlay,
    "council_supervisor_district": zimas.council_district,
    "historic_status": zimas.historic_status,
    "methane_hazard_zone_la": zimas.methane_hazard_zone,
    "toc_tier_la": zimas.toc_tier,
    "half_mile_major_transit": zimas.half_mile_major_transit,
    "transitional_height_adj_zones": zimas.transitional_height,   # derived -> JUDGMENT
}


def collect(wb_path, address, property_id=None):
    schema = yaml.safe_load((ROOT / "canonical/schema.yaml").read_text())
    by_id = {f["id"]: f for f in schema["fields"]}
    geo = geocode(address)
    print(f"geocoded: {geo['matched_address']}  tract {geo['geoid']}  "
          f"({geo['lat']:.5f},{geo['lon']:.5f})\n")
    active = dict(READERS)
    if zimas.in_la_city(geo):
        active.update(ZIMAS_READERS)
        print("parcel is in LA City -> running ZIMAS block\n")
    else:
        print("parcel not in LA City -> ZIMAS block skipped (route to local planning)\n")
    results = {}
    for fid, fn in active.items():
        field = by_id[fid]
        state = run_field(wb_path, field, (lambda fn=fn: fn(geo)),
                          property_id=property_id or "DEMO")
        results[fid] = (field["answer_cell"], state)
        print(f"  {field['answer_cell']:5} {fid:28} -> {state}")
    return results, geo


def _dump(wb_path, results):
    from openpyxl import load_workbook
    ws = load_workbook(wb_path)["Site DD"]
    print("\n--- written cells (Status A | answer C | notes E) ---")
    for fid, (cell, _) in results.items():
        row = int(cell[1:])
        print(f"  {fid:28} A={ws.cell(row,1).value!s:14} C={ws.cell(row,3).value!s:18} "
              f"E={(ws.cell(row,5).value or '')[:80]}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--demo":
        address = " ".join(args[1:]) or "11300 S Main St, Los Angeles, CA 90061"
        tmp = ROOT / "build" / "_collect_demo.xlsx"
        shutil.copy(ROOT / "template/Checklist_BLANK_master.xlsx", tmp)
        results, _ = collect(tmp, address)
        _dump(tmp, results)
        print(f"\nworkbook: {tmp}")
    elif args:
        from openpyxl import load_workbook
        wb = args[0]
        address = " ".join(args[1:]) or load_workbook(wb)["Site DD"]["C3"].value
        results, _ = collect(wb, address)
        _dump(wb, results)
    else:
        print(__doc__)
