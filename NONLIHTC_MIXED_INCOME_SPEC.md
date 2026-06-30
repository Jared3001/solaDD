# Non-LIHTC: AMI unit allocation + N-tranche debt stack — build spec

Extends the non-LIHTC feasibility engine (`NONLIHTC_ENGINE_SPEC.md`,
`web/nonlihtc_calc.py`) with two boss-requested capabilities:

1. **AMI unit allocation** — a mixed-income tier program (default
   **20% @ 50% AMI, 55% @ 80% AMI, 25% @ 70% AMI**; tier %s and AMI levels
   editable), instead of today's pure-market mode.
2. **Multiple loans** — an N-tranche permanent-period capital stack (senior +
   subordinate/soft/gap/seller), replacing the single perm loan.

Both are **editable in the review/preview panel before the model runs**, and
both are **additive**: omit the AMI table → today's market behavior; omit
`loans[]` → today's single perm loan. The LIHTC v30 path is untouched.

## Locked decisions (2026-06-30)
- **AMI tiers:** *extend the workbook* with a 3rd restricted tier block (each AMI
  tier stays a visible line in the deliverable).
- **Debt stack:** *full N-tranche Python stack* (Phase 2), payload designed so the
  2-loan native path is a strict subset.
- **UX:** *extend the existing non-LIHTC review form* (no separate mode toggle).

---

## Where it plugs into the flow
```
DD run → "→ Financial model" → GET /api/underwrite/intake/<job>  (jobs.underwrite_intake)
  → app.js openNonLihtcReview  [PREVIEW PANEL: + AMI table + loan rows]  → deriveNonLihtcPreview
  → POST /api/run {deal_type:"nonlihtc", nonlihtc:{… ami_allocation, loans …}}
  → jobs._run_underwrite_nonlihtc → nonlihtc_calc (mixed-income + stack)
  → LibreOffice recalc → headline returns + downloadable .xlsx
```
Touched files: `web/models/NonLIHTC_engine_template.xlsx` (tier-C block),
`web/nonlihtc_calc.py`, `web/jobs.py`, `web/static/app.js`, `web/static/style.css`.

---

## Payload contract (panel → backend)
```jsonc
{ "deal_type": "nonlihtc",
  "nonlihtc": {
    "units_by_bed": { "1": 45, "2": 5, "3": 0 },
    "rents_by_bed": { "1": 2400, "2": 3000 },   // market rents (comp scraper)
    "land_cost": 5000000,
    "ami_allocation": [                          // omit → pure market mode
      { "pct": 0.20, "ami": 50 },
      { "pct": 0.55, "ami": 80 },
      { "pct": 0.25, "ami": 70 }
    ],
    "loans": [                                   // omit → single perm loan
      { "label": "Senior Perm", "basis": "dscr", "value": 1.20, "rate": 0.0575, "amort": 35 },
      { "label": "Soft/Gap",    "basis": "fixed","value": 2000000, "rate": 0.03, "amort": 0, "io": true }
    ],
    "financing": { "exit_cap": 0.05 },
    "opex": { } // optional T-12 overrides
  } }
```
`ami` is an AMI tier present in `web/static/hud_rents.json` (20/30/35/40/45/50/55/
60/70/80/100/110). Tier %s must sum to ≤ 1.0; any shortfall is unrestricted
(market) units. The unrestricted remainder uses the market rows + comp rents.

---

## Feature 1 — AMI allocation

### Engine reality
The engine already models affordability; non-LIHTC mode *suppresses* it
(`_MARKET_MODE_CELLS` zeroes `Inputs!O27/O28`, sets `O29="No"`, zeroes
`(Z+) Rent Roll!E12:E19`). Mixed-income mode **re-activates the restricted rows**
with an analyst-driven allocation instead of the workbook's built-in 80/20
density-bonus formulas.

Rent Roll restricted rows: per-bed **unit count = column `E`**, per-bed
**restricted rent = column `I`**, label = column `C`. Revenue flows
`I → K (effective) → L = K×E →` row-20 blended aggregates → OpEx → NOI.

### The 3rd tier (workbook change — Workstream A)
The workbook ships **two** restricted tier blocks (rows 12–15 "80% AMI",
16–19 "110% AMI"); the spec needs **three**. We append a **tier-C block in the
empty band, rows 44–47** (0/1/2/3BR), mirroring the row-12 template with
self-refs repointed to the new rows and `E`/`I` defaulting to `0` (so an
unpatched / market-mode build is byte-for-byte identical in output).

**Why append, not insert:** cross-sheet refs target Rent Roll rows 20/24/36; a
mid-sheet insert would shift them across Inputs/OpEx/Financing/Monthly CF. The
append touches **only the Rent Roll sheet** — no row renumber, no cross-sheet edits.

In-sheet aggregates extended to include rows 44–47:
- Row-20 blended: `D20 E20 F20 G20 H20 I20 J20 K20 M20 N20 P20 S20`
  (`L/O/Q/R20` are derived from those, no change).
- Unit-mix tally: `N24 N25 N26 N27` (+ tier-C row per bed).
- Restricted-average display stats: `R28 S28 T28 R36 S36 Q36` (display only —
  not read cross-sheet — extended for correctness).

Tier blocks are mapped tier-A=rows12–15, tier-B=rows16–19, tier-C=rows44–47.
The C-column **labels are patched per run** to the chosen AMI (e.g.
"Restricted 50% AMI 1BR") since AMI levels are editable.

### Python (`nonlihtc_calc.py`)
- `resolve_county_fips(dd)` — ZIP→FIPS via `web/static/ca_zip_county.json`,
  fallback county-name match (mirror the `/modularz` `affResolveFips`).
- `ami_rent(fips, ami_pct, bed)` — `web/static/hud_rents.json` gross cap (optional
  net-of-utility-allowance).
- `build_mixed_income_inputs(units_by_bed, ami_allocation, fips, market_rents, …)`:
  1. total units → split by tier %; remainder = market.
  2. distribute each tier across beds ∝ `units_by_bed`.
  3. per (tier,bed): count → `E`, `ami_rent` → `I`, label → `C`.
  4. market rows = unrestricted remainder at comp rents.
  5. **skip `_MARKET_MODE_CELLS`**; apply a `mixed_mode_cells()` neutralizer
     (leave `O27/O28` at 0 — we drive rows directly, not the native O32 split).
- Caps at 3 tiers (3 blocks). A 4th tier needs another appended block.

---

## Feature 2 — N-tranche debt stack

### Engine reality
`(Z+) Financing` already models **Acquisition**, a toggle-able **Mezzanine**
(`D12` ON/OFF, sized Max-LTC `D18`/Debt-Yield `D20`, rate `D16`), **Construction**,
and **Permanent** (`MIN(DSCR H13, LTV H15, LTC H17)`, rate `H18=Dashboard!K12`,
amort `H21`). So **2 perm-period loans are reachable with zero template work**.

### Python stack engine (`nonlihtc_calc.py`)
- `size_stack(loans, basis_value, stabilized_noi, …)`: ordered tranches, each
  `{label, basis: fixed|ltc|ltv|dscr, value, rate, amort, io, position}`, sized
  sequentially against remaining basis/value with an **aggregate min-DSCR test**;
  returns total proceeds, blended rate, combined annual debt service, equity plug.
- **Engine mapping:**
  - tranche 1 → senior perm cells (`Dashboard!K12/K13`, Financing `F`-col),
  - tranche 2 → native mezzanine (`Financing!D12="ON"`, `D16/D18/D20`),
  - **tranche 3+** → parameterized N-source block appended to `(Z+) Financing`
    feeding `(Z+) Monthly CF` (same append-don't-insert pattern as Workstream A),
    so extra tranches flow through IRR. Until that block exists, 3+ tranches are
    folded into a blended subordinate (total debt + equity plug patched), flagged
    in the UI as "blended (not in monthly CF)".

---

## Review panel (`app.js` + `style.css`)
Extend `openNonLihtcReview`:
- **AMI allocation table** — editable rows, default `[20%/50%, 55%/80%, 25%/70%]`,
  %-and-AMI both editable, "tiers sum ≤ 100%" guard (reuse `missingRequired`).
- **Loan rows** — Add/Remove group: `{label, basis, amount/%, rate, amort, io}`.
- `deriveNonLihtcPreview` adds: units-per-tier + AMI rent/bed; total proceeds,
  blended rate, combined LTV/LTC, equity plug — live.
- `underwrite_intake` adds `county_fips` so the panel can show live AMI rents.

---

## Build sequence
- **A. Workbook tier-C block** (this step) — append rows 44–47 + extend aggregates;
  repeatable script `web/models/build_mixedincome_template.py`; **recalc-parity
  guard** (tier C = 0 ⇒ outputs identical to original) + a mixed-income smoke test.
- **B.** `nonlihtc_calc` mixed-income (FIPS, ami_rent, build_mixed_income_inputs).
- **C.** `nonlihtc_calc` stack engine (+ Financing N-source block if >2 must hit IRR).
- **D.** `jobs._run_underwrite_nonlihtc` + `underwrite_intake` wiring.
- **E.** review panel + preview + CSS.

## Risks / guards
- Workbook change is the long pole. Mitigated by **append-not-insert** (single
  sheet) + **recalc parity** before any Python wiring.
- AMI rents are MTSP/LIHTC caps (not market) — correct for restricted units only.
- Studio/0BR: no modular studio cost product; keep tier 0BR counts 0 unless a
  studio module price is added (same constraint as market mode).
