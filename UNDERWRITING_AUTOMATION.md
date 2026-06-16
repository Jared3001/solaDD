# Underwriting Automation — Analysis & Plan (PAUSED)

**Status:** analysis complete; build not started. Paused 2026-06-15.
**Goal:** after the DD checklist, auto-produce a first-pass underwriting model
(go/no-go estimate) by feeding the checklist's site outputs into SoLa's company
pro-forma template.

**Model analyzed:** `Stick Large Family - 17719 Kinzie Street.xlsm` (in Downloads;
macro-/LAMBDA-driven `.xlsm`). "Stick" vs "Modular" = construction method (different
cost/time structures); toggle at `Pro_Forma!A36`. Filename = Stick + Large-Family unit type.

## Model structure
- **`Pro_Forma`** — the engine and the canonical per-deal input surface. Already
  populated for Kinzie (`B2`=17719 Kinzie Street, `C3`=Los Angeles, `C12` Lot SF=35,796,
  163 units). Inputs live in `B2:C12`; the go/no-go **outputs are `C24:C30`** —
  Equity Required, GP IRR (15-yr), GP MOIC, GP Net Profit, Total IRR, Tiebreak Score
  (per the `Cell Mapping` sheet, which documents Pro_Forma cell addresses + a 1-pager).
- **`Market Inputs`** — CTCAC 100% AMI rents + HUD FMR by **County** (and CDLAC Region),
  bedroom columns 0B–4B. The rent side is driven by the DD county/region.
- **`Sheet1`** — 5-scenario sandbox; currently holds a stale **San Diego** sample
  (not the canonical entry point for a deal). Has its own copy of the site/scenario inputs.
- **`Tiebreak`, `Draws_Module`, `UA`** — supporting calcs (CTCAC tiebreaker, construction
  draws, utility allowances).
- Dropdowns of note: `Pro_Forma!A36` Modular/Stick · `C5` QCT/DDA/None · `C6`
  Low/Medium/High/Highest · `C9` Type I/III/Other · `D59` financing structure.

## DD checklist -> Pro_Forma input mapping (the hand-off)
7 of the model's site inputs come straight from `collect.py` output:

| Pro_Forma cell | DD field | Transform |
|---|---|---|
| B2 Project Name | address | none |
| C3 County | county | strip " County" ("Los Angeles County" -> "Los Angeles") |
| C4 PHA | pha | map full name -> model's short jurisdiction label (NEEDS the canonical list) |
| C5 QCT/DDA | qct / dda | collapse two fields -> one of {QCT, DDA, None}; pass governing-year value |
| C6 Resource Area | resource_area | "Highest Resource"->"Highest"; **"Moderate"->"Medium"** |
| C7 Neighborhood Change | neighborhood_change_area | none |
| C12 Lot SF | land_sf | none — automation gave 35,783 vs model's 35,796 (~0.04% match) |

Rent lookups then key off the DD County/Region automatically (Market Inputs).

## NOT from the DD checklist (stays manual / analyst choice)
- Construction Type (Type I/III), **Modular/Stick** (`A36`) — engineering/method.
- Prevailing Wage, BIPOC, CRA — policy flags.
- Acquisition price (`C33`/`S16`, $5M here) — deal/OM fact (DD field `acquisition_price`
  is desk-sourced, not automatable).
- Unit mix %, AMI income mix, rent/expense growth, financing structure — the template's
  assumed "deal mix."

## Automatability verdict: EASY / high-confidence for the hand-off
The bridge = "write ~7 values into `Pro_Forma` B2:C12" (4 verbatim, 3 trivial maps);
the model computes the rest and surfaces outputs at C24:C30. The Lot-SF match is strong
evidence the bridge reproduces a human's first pass.

## Open questions to resolve before building (ask/confirm with the user's guide)
1. **PHA / jurisdiction short-list** — the dropdown source (`AG29:AH40`) is empty in this
   copy; need the canonical PHA/jurisdiction value list to map `pha` correctly.
2. **QCT/DDA year** — model takes one value; pass the governing-year value and flag if the
   two designation years differ (Kinzie QCT = Yes both years, so fine here).
3. **Canonical input surface** — target `Pro_Forma` (real per-deal data), not the `Sheet1`
   San Diego sandbox; confirm.
4. **Recalc** — `.xlsm` with macros/LAMBDA; safe to *write inputs* via openpyxl, but
   **outputs recalc only when opened in Excel**. Don't replicate the credit math in Python.

## Proposed next step (NOT built)
A small exporter: take a finished DD checklist (or `collect.py` output) -> apply the 3
mappings -> write `Pro_Forma!B2,C3:C7,C12` (leave construction choices + acq price +
assumptions to the analyst) -> hand back the model for the analyst to open & recalc.
Then a finished checklist yields a first-pass underwriting in one step.
