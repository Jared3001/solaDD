# Non-LIHTC feasibility engine — parameterization spec (steps 1–2)

**Engine:** the clean pre-v28 ModularZ market workbook, extracted to
`web/models/NonLIHTC_engine_template.xlsx` (7 sheets, 0 errors, 0 external links).
The live `/modularz` tool keeps its own embedded copy and is untouched.

**Why this engine (not v5.0.7):** v5.0.7 has 52 external-workbook links + structural
`#REF!` (deleted-row refs, incl. its Data Validation logic) + scattered `#DIV/0!` — unfit
for unattended recalc. The ModularZ engine is self-contained and recalcs cleanly under
LibreOffice. Same SoLa lineage / identical Operating-Summary structure, so v5.0.7 is used
only as an assumptions source + validation cross-check.

## How it computes
`units × bed-mix → market rows → rents → GPR − vacancy + other income = EGI`;
`EGI − OpEx (PUPM factors) = NOI`; then valuation / returns. Recalc engine = LibreOffice
headless (forced full recalc), same harness pattern as the LIHTC v30 path.

## Control surface — REVENUE (drive a market / non-LIHTC deal)
The engine defaults to a **100% affordable allocation** via TWO independent systems that
BOTH must be neutralized for market mode (this was the key finding — zeroing only the
restricted set-aside double-counted units 3.2×):

| Input | Cell | Set for market | Notes |
|---|---|---|---|
| Total dwelling units | `Inputs!H14` | deal units | drives all allocation |
| Manager units | `(Z+) Rent Roll!E7` | 1 (default) | non-revenue |
| Required LI units | `Inputs!O27` | **0** | kills restricted set-aside (`O32=SUM(O25:O28)`) |
| Required Mod units | `Inputs!O28` | **0** | " |
| Affordable unit rows | `(Z+) Rent Roll!E12:E19` | **0** | independent `H14×0.8 / ×0.2` formulas — must also zero |
| Market bed-mix % (0/1/2/3B) | `(Z+) Rent Roll!M24:M27` | mix % | DD/analyst; sums to ~100% of non-manager units |
| Market gross rent (0/1/2/3B) | `(Z+) Rent Roll!G8:G11` | $/mo | **from the AI comp scraper** |
| Affordable flag | `Inputs!O29` | "No" | "ED1/100% Affordable?" |

## Control surface — OPEX (`(Z+) OpEx`, column D = per-line factor)
Engine factors are **PUPM** (per-unit-per-month); v5.0.7 / T-12 give **PUPY** → divide by 12.
Management is a % of revenue. Prop tax is a formula (% of dev budget) — leave or override.

| Line | Cell | Unit | Source (v5.0.7 5300 Crenshaw PUPY → PUPM) |
|---|---|---|---|
| Prop. Taxes | `D8` | formula (% dev budget) | leave / override |
| Insurance | `D9` | $/unit/mo | $400 → 33.33 |
| Management | `D10` | % of revenue | 5% |
| CMFA Fee | `D11` | $/unit/mo | 0 (affordable-only) |
| Non-Profit Partner | `D12` | $/unit/mo | 0 (affordable-only) |
| Electric | `D14` | $/unit/mo | from T-12 (v5 combines utilities $1,224 PUPY) |
| Water/Sewer | `D15` | $/unit/mo | from T-12 |
| Gas | `D16` | $/unit/mo | from T-12 |
| Trash | `D17` | $/unit/mo | from T-12 |
| Landscape | `D18` | $/unit/mo | from T-12 |
| M&R/Turnover | `D19` | $/unit/mo | $553 → 46.08 |
| Payroll/Security | `D20` | $/unit/mo | $1,475 → 122.92 |
| HCID Fee | `D21` | $/unit/mo | $19 → 1.58 |
| Elevator Maint. | `D22` | $/unit/mo | from T-12 |
| Legal | `D23` | $/unit/mo | $60 → 5.00 |
| Misc. | `D24` | $/unit/mo | from T-12 |
| Mgr's Rent Credit | `D25` | $/unit/mo | optional |
| Reserves | `D26` | $/unit/mo | $240 → 20.00 |

## Proven (LibreOffice recalc, 50-unit market deal)
Patched H14=50, O27/O28=0, E12:E19=0, bed-mix 20/40/35/5%, rents 1900/2400/3000/3800,
5 OpEx lines from v5.0.7. Result: market units **10/20/17/2 = 49** (+1 mgr = 50 total,
affordable rows 0); GPR **$1.536M**; EGI **$1.629M**; OpEx **−$458k (28.1% ratio**, vs
v5.0.7 29.06%); **NOI $1.171M**. Revenue + OpEx chain confirmed.

## Control surface — UNIT PROGRAM (drives BOTH cost and revenue)
`Inputs!H14` (total units) = `O10` = `SUM(O11:O13)`, so drive the unit COUNTS, not H14:

| Input | Cell | Notes |
|---|---|---|
| 1-BR count | `Inputs!O11` | modular product |
| 2-BR count | `Inputs!O12` | |
| 3-BR count | `Inputs!O13` | |
| Staircase units | `Inputs!O15` | service modules |
| Podium SF / levels | `Inputs!O7` / `O8` | massing |
| Parking stalls | `Inputs!O9` | |

NOTE: the modular cost book has **no studio (0-BR) product** — `O11:O13` are 1/2/3-BR only.
The revenue side has a studio row (`Rent Roll!G8/E8`), so keep market-mix `M24`(studio)=0
unless a studio module price is added. Keep the revenue bed-mix (`M25:M27`) consistent with
`O11:O13` proportions.

## Control surface — COST (`(Z+) Dev Budget`; rolls up to `Inputs!G6:G11`)
| Input | Cell | Notes |
|---|---|---|
| Land / acquisition | `(Z+) Dev Budget!G7` | input $ |
| Modular price book 1-BR | `(Z+) Dev Budget!E14` | $/unit (× `Inputs!O11`) |
| Modular price book 2-BR | `E15` | $/unit (× `O12`) |
| Modular price book 3-BR | `E16` | $/unit (× `O13`) |
| Service-module / staircase | `E17` / `E18` | $/unit |
| On-site cost / unit | `Dashboard!W18` | (Dev Budget `E19` = `=Dashboard!W18`) |
| Podium $/SF | `(Z+) Dev Budget!E20` | × `O7`×`O8` |
Soft / Admin / Financing costs roll up in Dev Budget `G109/G115/G124` (formula-driven).

## Control surface — FINANCING (`Dashboard`)
| Input | Cell | Default |
|---|---|---|
| Exit cap (Best/Base/Worst) | `J4`/`J5`/`J6` | base 6.75% |
| Construction LTC | `J11` | 70% |
| Construction int. rate | `J12` | 9% |
| Perm LTC / LTV | `K11` / `K10` | 80% / 75% |
| Perm int. rate | `K12` | 5.75% |
| Perm DSCR | `K13` | 1.20 |
| Hold period (mo) | `W20` | 84 |
| Rent growth | `W21` | 2.5% |

## Return OUTPUTS (`Dashboard`)
Levered IRR `B5`, Equity Multiple `B6`, Cash-on-Cash `B7`, Untrended Yield-on-Cost `B8`,
Total Profit `B9`, Total Dev Cost `B13`, Price/Unit `B14`, Equity `E13`, Debt `E14`;
NOI `(Z+) OpEx!G37`, EGI `G35`, OpEx `G36`.

## Proven end-to-end (LibreOffice recalc, 50-unit market deal)
Drove O11=45/O12=5/O13=0, killed restricted + affordable rows, market mix 90/10,
rents 2400/3000, v5.0.7 OpEx, land $5M, exit cap 5%, perm 5.75%. Result — fully coherent:
TDC **$20.05M** ($400,980/unit), EGI **$1.472M**, OpEx **−$455k**, NOI **$1.017M**,
Equity $7.94M / Debt $12.1M, **Untrended YoC 5.85%, Levered IRR 9.31%, CoC 6.32%,
Equity Multiple 1.46x, Total Profit $3.68M.** Returns now respond to the full input surface.

## Step 4 — DONE (harness + DD bridge + selector)
- `web/nonlihtc_calc.py` — `INPUT_CELLS` map, `_MARKET_MODE_CELLS` (zeroes both affordable
  systems on every build), multi-sheet XML patch → LibreOffice recalc → `HEADLINE` outputs,
  `build_download` (fullCalcOnLoad=1), `build_market_inputs` / `build_from_dd`, `selftest()`.
- `jobs.run_underwrite` — deal-type selector: `deal_type='nonlihtc'` → `_run_underwrite_nonlihtc`
  (reads `inp['nonlihtc']`: units_by_bed, rents_by_bed, opex?, financing?, land_cost?); LIHTC
  path unchanged & default.
- Verified: self-test + integration test recalc clean (EGI $1.472M, NOI $1.03M); download
  recalcs to patched values in Excel / forced-profile LibreOffice.

## Step 5 — front-end DONE (toggle + non-LIHTC review form)
- `index.html` review panel: `#review-dealtype` LIHTC / Non-LIHTC toggle (shown only for model review).
- `app.js`: `openModelReview` is now a dispatcher → `openLihtcReview` (existing scenario flow,
  unchanged) or `openNonLihtcReview`. State in `_modelReview {jobId,intake,dealType}`; toggle
  click handler re-renders the matching form against the same DD intake.
- `openNonLihtcReview` fields: deal_name, land_price (seeded from DD acq price), units_1br*/2br/3br,
  rent_1br*/2br/3br, exit_cap (def 5), perm_rate (def 5.75). `deriveNonLihtcPreview` = live
  bed-mix + approx annual GPR. onConfirm builds `{mode:underwrite, from_job, name, deal_type:nonlihtc,
  nonlihtc:{units_by_bed, rents_by_bed, land_cost, financing:{exit_cap/100, perm_rate/100}}}` → `launch`.
- `renderUnderwrite` branches on `deal_type==="nonlihtc"` → `renderUnderwriteNonLihtc` (headline
  returns table: IRR/CoC/YoC as %, EqMult as x, rest $; negatives as -$).
- `style.css`: `.dealtype-toggle` / `.dt-opt` pill segment control.
- VERIFIED in-browser (fake intake injection): toggle swaps forms, seeds deal/land, preview GPR
  math correct (45/5/0 @ 2400/3000 → $1.476M), payload exactly matches `_run_underwrite_nonlihtc`
  (fractional cap/rate), results renderer formats all 12 headline returns, 0 console errors.

## Step 5 — comp-rent auto-population DONE + bed-key bug fixed (2026-06-29)
- `jobs.latest_comp_rents(address)` + `_norm_addr`: finds the most recent completed `comps` job
  whose subject matches the DD address (tolerant: lowercases, strips `(+N parcels)`, collapses
  punctuation) and returns `{rents_by_bed:{bed_int: median base_rent}, counts, source_job, address}`.
  Folded into `underwrite_intake` as `payload["comp_rents"]` (best-effort; only matches within a
  live session since `comps_data` isn't persisted across redeploy).
- `app.js openNonLihtcReview`: pre-fills rent_1br/2br/3br from `intake.comp_rents.rents_by_bed`,
  shows "auto-filled: median of N comps from the AI scraper" per field + a preview note naming the
  comp subject. Analyst can still edit.
- **BUG FOUND + FIXED via the live chain test:** `build_market_inputs` only read `"1br"/"2br"`
  keys, but the review form AND the comp scraper emit NUMERIC bed keys (`1` / `"1"`). Result was
  0 units / EGI $120. Added `_bed_lookup(d, bed)` — tolerant of `1|"1"|"1br"|"1BR"|"1b"` and
  studio=`0|"studio"|"0br"`. Both `build_market_inputs` and `selftest` ("1br" keys) now pass.

## Proven END-TO-END through the real job runner (2026-06-29)
Staged a DD job (sparse blank-master checklist) + a comps job for the same subject, ran
`underwrite_intake` → comp_rents auto-derived (medians 2400/3000), then `create_job("underwrite",
{deal_type:nonlihtc, nonlihtc:{units_by_bed:{"1":45,"2":5}, rents_by_bed, land $5M, exit 5% /
perm 5.75%}})` through `run_underwrite` → `_run_underwrite_nonlihtc`. Result (matches the proven
harness): **EGI $1.472M, OpEx −$442k, NOI $1.030M, TDC $20.71M, PPU $414k, Equity $7.71M /
Debt $13.0M, Levered IRR 6.96%, CoC 5.84%, YoC 5.73%, EqMult 1.37x, Profit $2.87M**; valid zip.
Front-end pre-fill re-verified in Chrome (rents 2400/3000 + "median of N comps" help, 0 console errors).

## Next (remaining step 5)
T-12 → OpEx parser (currently falls back to v5.0.7 PUPM defaults). Studio handling decided: NOT
modeled (no modular studio product). Deploy to Railway. Optional: a "→ Non-LIHTC model" button on
the comp editor that carries CTCAC-*adjusted* concluded rents (today uses raw median scraper rents).
