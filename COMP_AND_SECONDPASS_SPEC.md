# Build Spec — Comp stage → Second-pass model → IC memo

**Status:** DRAFT for red-line · 2026-06-22
**Scope:** everything needed to round out the underwriting flow *past* the
first-pass model, **excluding** consistent rent-comp sourcing (treated as a
solved/in-progress input). Maps to stages 05–07 of
`SOLA — Underwriting Automation Flow`, plus the two flagged discrepancies.

---

## 0. Where we are (repo-verified)

| Flow stage | State | Code |
|---|---|---|
| 02 DD checklist engine | **Built** | `build/collect.py`, `build/sources/*` |
| 03 First-pass model (Stick + Modular) | **Built** | `build/underwrite.py`, `build/sources/uw_logic.py` → `Pro_Forma` |
| 04 Approval gate | Human; criteria **undefined** | — |
| 05 Comp process | **Tier-A only**; adjustments blank by design | `build/comps.py`, `build/sources/rentcast.py` |
| 06 Second-pass model | **Blocked** — rents hardcoded | `web/build_modularz.py`, `(Z+) Rent Roll` |
| 07 IC memo | **Aspirational** | — |

**Engine decision — RESOLVED (Decision A, 2026-06-22): pass 2 = the same SoLa
`Pro_Forma`.** Pass 2 is *not* ModularZ. It is the same `Pro_Forma` engine used
in pass 1, with its regional **Market Inputs** rent lookup swapped for the
comp-derived market rents from the grid. (ModularZ / `RENT_ROLL_HANDOFF.md` is
now out of scope for this flow.) This means pass 1 and pass 2 share one model;
the only difference is the rent source — assumed/regional in pass 1, comp-backed
in pass 2.

The comp grid (the uploaded Kinzie file) is stage 05's *output* and the *input*
to `Pro_Forma`'s rent cells in pass 2.

---

## 1. The seven gaps (what "rounding out" means)

### N1 — Comp adjustment engine (the grid's value-add)  ✅ ENGINE + WRITER BUILT 2026-06-22
`build/sources/comp_adjust.py` = the ruleset + math (size = subj $/SF × 0.10;
age = $5/yr; per-line amenity/utility $), the single source of truth; verified to
reproduce all three Kinzie 1-BR adjusted rents to the cent. `comps.py
write_ctcac_grid()` (+ `--ctcac`) renders the formatted grid (subject + comps,
Char/Adj pairs, Adjusted Rent / ratio / differential, 110% guardrail). Remaining:
the web matrix editor (adapter 2) that seeds these defaults and lets the analyst
edit live. Original scope below.

Turn the Tier-A comp rows `comps.py` already produces into a **defensible
Adjusted Rent**, mirroring the uploaded HUD-92273 / CTCAC grid (size $/SF, age,
amenity/utility/parking line items → Adjusted Rent → differential vs. subject).

- **Inputs:** Tier-A comp rows (`comps.py`), subject characteristics (DD +
  proforma), a **SoLa adjustment ruleset** (Decision B).
- **Output:** the *formatted* CTCAC template populated (not the clean grid
  `write_grid()` writes today), one tab per bed count, with a comp-supported
  market rent per bed type.
- **Code:** new `build/sources/comp_adjust.py` (pure rules) + extend
  `comps.py` to write the formatted template.
- **Automatability:** size/age/$/SF math = auto; per-line amenity/utility $ =
  ruleset-driven but human-confirmable. Comp **selection** stays human-in-loop.
- **Watch:** the uploaded 2BR tab has a broken age adjustment (`-9920`
  cascading to negative rents). Model the **1BR** logic; do **not** replicate
  the 2BR tab. Encode the 110%-of-base guardrail (grid row 84).

### N2 — Tier-B input gaps that drive N1
The adjustments need fields sourcing doesn't reliably give: # units, # stories,
elevator, amenities, utility-paid-by-tenant split, renovation year, concessions.

- **Decision C:** field-by-field, mark each **auto** (HelloData) / **OM** /
  **analyst**. Anything not auto becomes a labeled blank in the template, not a
  silent zero.

### N3 — Route comp rents into `Pro_Forma` (the critical bridge)
Per Decision A, pass 2 = `Pro_Forma`. Today `Pro_Forma` pulls rents from the
regional **Market Inputs** tab by County/Region. N3 = let comp-derived market
rents (from N1) override that lookup for the market/workforce units, while
restricted units keep their CTCAC/HUD AMI ceilings.

- **Approach:** confirm the exact rent cells `Pro_Forma` reads (Market Inputs
  lookup vs. direct input), then have `underwrite.py` write comp rents into the
  market-rate rent inputs (mirrors how it already writes the 7 site inputs).
- **Output:** returns become market-responsive without a second engine.
- **Owner:** us, in `underwrite.py` / `uw_logic.py` — no separate model owner.
- **Blocks:** N4, N6. **Nothing consumes comp rents until this lands.**
- **Open:** does `Pro_Forma` already expose per-bed market-rent input cells, or
  is rent fully formula-driven off Market Inputs? (Verify before coding N6.)

### N4 — Per-unit revenue routing (`revenue_classification`)
Reconcile the flagged discrepancy: design routes revenue per unit; built
first-pass uses a fixed 10/10/80 AMI mix.

- **Target logic:** restricted units → CTCAC/HUD AMI ceilings (**already
  built** — affordable rent caps); market/workforce units → **comp-supported
  rent from N1**.
- **Code:** extend `uw_logic.py` revenue path; depends on N1 (market rents) and
  N3 (input cells, for pass 2).
- **Decision D:** affordable rows track market how — AMI cap vs. fixed discount?

### N5 — Go/no-go criteria (approval gate 04)
Write the screening thresholds (min IRR / yield-on-cost / MOIC, max equity,
tiebreaker) so a model run emits a **recommendation + auto-flag of clear
no-gos**, not just numbers. Human sign-off stays.

- **Decision E:** the actual threshold values (analyst input).
- Independent of N1–N4; can be done in parallel.

### N6 — Second-pass model run (stage 06)
With N3 done, run `Pro_Forma` a second time with comp-derived market rents (N1)
+ restricted AMI rents (N4) → returns/profit prediction. Pass 1 (assumed rents)
and pass 2 (comp rents) are the same model run twice; the delta between them is
the comp impact on returns.

- **Depends on:** N1, N3, N4.

### N7 — IC memo / underwriting output (stage 07)
Generate the recommendation memo: DD facts + first-pass returns + comp
conclusion + second-pass returns, standard format.

- **Depends on:** N6 (+ N5 for the recommendation line). Needs a template
  (Decision F).

### N0 — Operational glue (cross-cutting)
Chain checklist → first-pass → gate → comps → second-pass → memo in one place
(comps is a standalone CLI today; wire into `collect.py`/web). Carry over the
assemblage parcel-selection watch-item. Vintage-stamp comp data.

---

## 2. Dependency graph & suggested sequence

```
N3 (un-hardcode rents) ─────┐
                            ├─► N6 (pass-2 run) ─► N7 (IC memo)
N1 (adjust engine) ─► N4 ───┘                        ▲
   ▲                                                 │
N2 (Tier-B inputs)                       N5 (go/no-go) ┘  [parallel]
N0 (glue) ............................. cross-cutting
```

**Recommended order:**
1. **N3** — unblocks everything downstream; now in-house (`Pro_Forma` rent
   routing) since Decision A picked the shared engine. First step: verify how
   `Pro_Forma` sources rent (Market Inputs lookup vs. input cells).
2. **N1 + N2** — the comp adjustment engine + its input contract (this is where
   the uploaded comp data lands).
3. **N4** — wire restricted (AMI caps) + market (comp) rents together.
4. **N6** — first real second-pass run on a live deal.
5. **N5** — go/no-go criteria (can slot in any time; needed before N7 emits a
   recommendation).
6. **N7** — IC memo.
7. **N0** — chain it all once the pieces work standalone.

---

## 3. Open decisions to red-line

- **A. Pass-2 engine.** ✅ RESOLVED — extend the same SoLa `Pro_Forma` (swap its
  Market Inputs rent lookup for comp rents). ModularZ out of scope.
- **B. Adjustment ruleset.** ✅ RESOLVED — reverse-engineer from the Kinzie 1BR
  tab as a starting draft → delivered as `SOLA_Comp_Adjustment_Review.xlsx` for
  boss red-line. Confirmed rules: size = subj $/SF ÷ 10 ($0.4286/SF); age =
  $5/yr; per-line amenity/utility $ table. Awaiting boss notes on blanks
  (bathrooms $, unobserved amenities).
- **C. Tier-B field routing.** → boss checklist (tab 2 of the review workbook).
- **D. Affordable-rent tracking.** TBD — AMI cap vs. fixed discount for set-aside
  rows. Park until boss input.
- **E. Go/no-go thresholds.** → boss questions (tab 3 of the review workbook).
- **F. IC memo format.** User to provide template.

---

## 3a. Manual edit/preview step (reusable) — DECIDED 2026-06-22

A human-in-the-loop **Review & Edit** step inserted before each Excel output, so
an analyst can adjust the automated inputs (defaults) and preview before export.
Scoping answers:

- **Pattern:** ONE reusable component, applied to each stage (model intake first,
  comps next).
- **Compute:** **live in the browser** (mirror the derive rules in JS); Python
  only writes the final Excel — single source of truth for the file, JS for the
  preview.
- **State:** **ephemeral** (edit → preview → generate; nothing persisted).
- **Flow:** **auto-chain** — confirm runs the next stage; no intermediate
  download unless asked.

**Data contract (reusable editor).** Server emits an *intake payload*:
`{ values:{editable defaults}, options:{select vocabularies}, derived:{live-preview
values} }`. The JS editor renders `values` as editable inputs, recomputes
`derived` on every edit (JS mirror of the Python logic), and on confirm POSTs the
edited `values` as `overrides` to the stage's run endpoint.

**Adapter 1 — model intake. ✅ BUILT + verified 2026-06-22.** Between a completed
DD run and the Stick/Modular export. Editable: deal name, county, PHA, QCT/DDA,
resource, neighborhood-change, land SF. Live-derived: product (Large Family vs
Standard), CRA, bedroom mix, AMI mix. `GET /api/underwrite/intake/<job>` returns
`{values, options, derived}`; `POST /api/run` underwrite mode takes `overrides`
→ `uw_logic.apply_overrides()` folds them into the DD dict before
`base_cells()`. Reusable `ReviewEditor` (static/app.js) renders any
`{fields, derive}` schema; `deriveModelPreview()` is the JS mirror of uw_logic.
Clicking "→ Financial model" (gen-model / recent) now opens the editor →
"Generate Stick + Modular models" auto-chains. Edited deal name now also writes
`Pro_Forma!B2` (underwrite.export). Verified: backend logic, browser live-derive
(Low→Highest flips product/CRA/mix), and full server route producing correct
overridden models with macros preserved.

**Adapter 2 — comp grid (next).** Between the auto comp-shortlist and the CTCAC
grid. Editable: comp selection, Tier-A corrections, Tier-B fields, adjustment $
(ruleset defaults from `SOLA_Comp_Adjustment_Review.xlsx`). Live-derived:
Adjusted Rent, differential, 110% flag. Needs N1's grid writer.

## 4. First build target (proposed)

Pending red-line: **N1 draft** — reverse-engineer the adjustment ruleset from
the Kinzie 1BR tab into `comp_adjust.py`, and write the formatted CTCAC template
from `comps.py` output, so the rent-comp data you upload produces an Adjusted
Rent end-to-end. In parallel, hand **N3** to the model owner (it's the gating
dependency for returns).
