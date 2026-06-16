# Underwriting Intake — Senior-Analyst Questions + Projection Logic Guide (DRAFT)

Companion to `UNDERWRITING_AUTOMATION.md`. The DD checklist gives us the **site
inputs** (county, PHA, QCT/DDA, resource area, neighborhood change, lot SF). It does
**not** give us the **deal assumptions** the pro forma needs: unit mix, AMI/income
mix, construction type, build method, and financing structure. To automate the
first-pass model we need to encode the heuristics seniors apply for those.

This doc has two halves:
- **Part A — questions** to ask senior analysts (each aimed at extracting a *rule*,
  not a one-off answer).
- **Part B — a draft projection-logic guide** (decision tables) as a starting point
  for them to correct. It's easier to red-line a concrete draft than answer blank.

**Dual-model requirement:** the team wants **two models per deal — one Stick, one
Modular — saved separately.** So the exporter will set `Pro_Forma!A36` to each method
and write two files (`<deal> — Stick.xlsm`, `<deal> — Modular.xlsm`). See Part C.

Everything in Part B marked **[CONFIRM]** is my hypothesis to validate, not fact —
especially CTCAC/program thresholds, which change and must be checked against the
current QAP.

---

## Part A — Questions for senior analysts

**Goal:** for each decision below I just need *which checklist outputs you read and the rule* —
answer in the form **"if [field] is X → do Y,"** and flag anything the checklist doesn't give you.

**Checklist outputs you have to work from:** jurisdiction · county · geographic pool (CDLAC
region) · lot SF · QCT · DDA · resource area (Highest/High/Mod/Low) · neighborhood change ·
opportunity zone · zoning + height district · TOC tier · ½-mile transit · specific plan/[Q] ·
flood · very-high fire · methane · liquefaction · A-P fault · wells · USTs · slope · (SB8 /
existing units, if desk-filled).

### 1. Unit mix  (model: bedroom split `H3:H6`/`I3:I6`, AMI bands `J`, avg unit sizes; *count* is model-derived from lot SF × FAR)
1. **Product type** (Large Family / Senior / SRO…) — which fields decide it, and is there a default?
2. **Bedroom split** — your default per product type, and what moves it (resource area? jurisdiction? a CTCAC Large-Family 3BR minimum — current %?).
3. **Count ceiling** — do lot SF + height district + TOC bonus drive the unit count, or do parking / max-units cap it? Which field sets the cap?
4. **Avg unit sizes** (model 402/497/700/900 NRSF, 0–3BR) — standard, or flex by jurisdiction/method? Manager's units — how many / what type?
5. **AMI mix** (30/50/60/70%) — default split, and which fields move it (resource area / CDLAC region, QCT/DDA, jurisdiction) vs. purely 9%-vs-4%?
6. **SB8 / existing tenancy** — if the checklist shows replacement units, does that constrain the mix?

### 2. Construction type  (model: `C9` = Type I/III/Other; stories/FAR → NRSF, default ~5 stories / FAR 3.5)
1. **Stories & FAR** — how do you read the achievable envelope from zoning + height district + lot SF + TOC bonus? (Is ~5 stories a real read or a placeholder?)
2. **Type I vs III** — purely stories/podium (e.g., III ≤ ~5–6, I above/podium), or do other fields weigh in? Where's the cutoff; when "Other"?
3. **Hazards — type or just cost?** For each, does it change the structure/type or only add a cost line: methane · liquefaction · A-P fault · slope · flood?
4. Does construction **type** differ between the Stick and Modular versions, or stay constant?

### 3. Build method — Stick & Modular  (toggle `A36`; both saved)
1. Always model both, or are there checklist conditions where only one is viable?
2. Besides `A36`, does Modular change any other input (stories, type, timeline, contingency), or does the template absorb the delta?
3. Ballpark cost/schedule delta vs Stick?

### 4. Financing structure  (model: 4% vs 9%; layers `D59` = Ground Lessor / Soft Debt / State Credits / B-Bond / None; bond test 27.5%)
1. **9% vs 4%+bond** — which fields decide it: deal size (lot SF/units)? QCT/DDA basis boost? resource area / CDLAC region? Rule of thumb + any thresholds.
2. **`D59` layers** — what triggers each, and which are inferable from the checklist (SoLa land → Ground Lessor? jurisdiction → Soft Debt?) vs. purely deal-side?
3. **Default** structure when nothing special applies?
4. Are **bond-test limit / applicable % / credit factor** fixed, or set per deal?
5. **Acquisition price** is from the OM (not derived) — any placeholder before it's set?

### 5. Policy flags  (`C8` CRA · `C10` Prevailing Wage · `C11` BIPOC)
- For each — what sets it, and is any checklist-derivable? (Esp.: is **CRA** a public designation we could pull, or a manual call?)

---

## Part A2 — Every value the tool would change: automate or hand-enter? (mark each)

These are all the model inputs the exporter would set. For each, tell me whether you want it
**automated** or **left for the analyst**. **Mark the last column.**
Legend: **Auto** = pulled from the DD checklist · **Logic** = projected from your Part-B rules ·
**Hand** = analyst enters · **Default** = leave the template's value untouched.

| Value | Cell | Proposed source | My rec | Auto / Logic / Hand / Default? |
|---|---|---|---|---|
| Project name | `B2` | DD address | Auto | ☐ |
| County | `C3` | DD county | Auto | ☐ |
| PHA | `C4` | DD pha | Auto | ☐ |
| QCT/DDA | `C5` | DD qct/dda | Auto | ☐ |
| Resource Area | `C6` | DD resource_area | Auto | ☐ |
| Neighborhood Change | `C7` | DD neighborhood_change | Auto | ☐ |
| CRA | `C8` | DD? (derivable?) or manual | Confirm | ☐ |
| Lot SF | `C12` | DD land_sf | Auto | ☐ |
| Construction Type (I/III) | `C9` | logic (stories + hazards) | Logic | ☐ |
| Residential stories / FAR | Sheet1 `E10`/`E11` (or PF) | logic (zoning + height district + TOC) | Logic | ☐ |
| Bedroom mix (counts + %) | `H3:H6` / `I3:I6` | logic (product type) | Logic | ☐ |
| Avg unit sizes (NRSF/bdrm) | rent roll `H10/H14/H18/H22` | assumption | Logic/Default | ☐ |
| Manager's unit(s) | `I26` | logic (ratio to units) | Logic | ☐ |
| AMI band mix (30/50/60/70) | `J` column | logic (program) | Logic | ☐ |
| Build method (Stick/Modular) | `A36` | always both (two files) | Auto (both) | ☐ |
| 4% vs 9% path | (financing) | logic | Logic | ☐ |
| Financing layers | `D59` | logic / manual | Confirm | ☐ |
| Acquisition price | `C33` / `S16` | OM / broker | Hand | ☐ |
| Prevailing Wage | `C10` | manual? | Hand/Confirm | ☐ |
| BIPOC | `C11` | manual | Hand | ☐ |
| Rent growth | Sheet1 `F14` (2.5%) | template | Default | ☐ |
| Expense growth | Sheet1 `F15` (3.5%) | template | Default | ☐ |
| Bond-test limit | `C21` (27.5%) | template | Default/Confirm | ☐ |
| Applicable % / credit factor | `D88` / `D89` | template | Default/Confirm | ☐ |

*(Market rents are auto-looked-up by County from the `Market Inputs` tab — not set directly.)*
Anything you mark **Hand** the exporter will leave blank/untouched for the analyst; anything
**Logic** depends on the Part-B rules being confirmed first.

---

## Part B — CONFIRMED projection logic (senior review 2026-06-16)

> Confirmed by senior review (Part A2 form + follow-up). Inputs in **bold** come from the DD
> checklist; the rest are rules the exporter applies. Two implementation details still to pin
> down at build time are flagged **[locate]**.

### B0. Final disposition of every value
- **Auto (from DD):** project name `B2` · county `C3` · PHA `C4` · QCT/DDA `C5` · resource area
  `C6` · neighborhood change `C7` · lot SF `C12`.
- **Logic (exporter computes):** CRA `C8` · construction type `C9` (as a formula) · bedroom mix
  `H3:H6`/`I3:I6` · AMI mix (`J`) · avg unit sizes (method-dependent) · construction time (method-dependent).
- **Hand (analyst enters):** acquisition price `C33`/`S16` · BIPOC `C11` · residential stories/FAR `E10`/`E11`.
- **Deferred to the model:** Prevailing Wage `C10` — being added to the model; exporter does NOT set it.
- **Default (left untouched):** manager's unit `I26` · 4% vs 9% path · financing layers `D59` ·
  rent growth · expense growth · bond-test limit · applicable %/credit factor.

### B1. Product type & bedroom mix — keyed on resource area
| Resource area (DD `C6`) | Product | 0B | 1B | 2B | 3B |
|---|---|---|---|---|---|
| **High / Highest** | Large Family | 0% | 50% | 25% | 25% |
| **Low / Moderate** | standard | 0% | 100% | 0% | 0% |
- We set the % split (`I3:I6`); unit **count** stays model-derived. Manager's unit = Default (model handles).

### B2. AMI / income mix — exporter sets
- **10% @30% AMI · 10% @50% · 80% @60%** (no 70% band).

### B3. Construction type `C9` — formula off stories + method (template change, approved)
Set `C9` to a live formula so it tracks the hand-entered stories and the file's build method:
`=IF(<stories> > 5, "Type I", IF(AND(A36="Stick", <stories> = 5), "Type III", "Other"))`
- `<stories>` = the residential-stories cell **[locate the `Pro_Forma` stories cell — intake noted Sheet1 `E10`]**.
- Consequence: a 5-story deal is **Type III in the Stick file but "Other" in the Modular file** —
  type legitimately differs by method (see B5).

### B4. Avg unit sizes (NRSF/bdrm) — method-dependent
| Bedroom | Stick (= template default) | Modular |
|---|---|---|
| 1B | 497 | 497 |
| 2B | 700 | **804** |
| 3B | 900 | **994** |
- Stick file: leave defaults. Modular file: exporter overrides 2B→804, 3B→994.

### B5. Build method — produce BOTH; these inputs differ by method
| Input | Stick file | Modular file |
|---|---|---|
| `A36` | Stick | Modular |
| Construction type `C9` (via B3 formula) | Type III @5 stories | Other @≤5 stories |
| Avg 2B / 3B NRSF | 700 / 900 | 804 / 994 |
| Construction time | **24 months** | **18 months** — **[locate duration cell, likely `Draws_Module`]** |

### B6. CRA `C8` — derived
`CRA = Yes` if **neighborhood change `C7` = No** AND product is **not Large Family** (i.e.,
resource area is Low/Moderate); otherwise **No**.

### B7. Out of exporter scope (recap)
- **Prevailing Wage** — model will add it. **Acquisition price / BIPOC / stories-FAR** — analyst.
- **4%/9% · financing layers · growth · bond test · applicable %** — model defaults, untouched.

---

## Part C — Dual-model output spec (Stick + Modular) — confirmed
For each deal the exporter will:
1. Write the DD **Auto** site inputs (`Pro_Forma B2, C3:C7, C12`).
2. Compute the **Logic** inputs: CRA `C8`; bedroom mix `I3:I6` (B1); AMI mix (B2); construction
   type `C9` as a formula (B3); and the method-specific unit sizes (B4) + construction time (B5).
3. Leave **Hand** fields blank (acquisition price, BIPOC, stories/FAR) and **Default** /
   model-handled fields untouched (incl. Prevailing Wage until the model adds it).
4. Save **two files** — `<deal> — Stick.xlsm` and `<deal> — Modular.xlsm` — differing per B5.
5. Analyst opens each, enters the Hand fields (esp. **stories**, which drives the `C9` formula),
   recalcs in Excel; first-pass outputs at `C24:C30`.

## Status
**BUILT (2026-06-16).** Exporter shipped as `build/underwrite.py` (+ pure-logic
`build/sources/uw_logic.py`). Both build-time lookups are resolved and wired in:
- residential stories = `Pro_Forma!C15` (input, default 5; the `C9` formula keys on it) — left for the analyst.
- construction time = `Draws_Module!B5` ("Construction Time (m)") — set to 24 (Stick) / 18 (Modular).

Other cells confirmed against the template's data validations: PHA `C4` ← dropdown
`$AH$29:$AH$40` (11 canonical labels); resource `C6` ∈ {Low, Medium, High, Highest};
QCT/DDA `C5` ∈ {QCT, DDA, None}; type `C9` ∈ {Type I, Type III, Other}; `A36` ∈ {Modular, Stick}.
Bedroom mix writes `I3/I5/I6` (`I4` 1B is the template's `=1-I3-I5-I6` remainder; unit *counts*
`H3:H6` stay model-derived). AMI 10/10/80 writes `R35/R36` = 0.10 and `R38` = 0 (`R37` @60% is
the template's remainder). Modular overrides sizes `L5`=804 / `L6`=994. openpyxl `keep_vba` round-trip
verified safe (macros + 12 LAMBDA names + existing formulas preserved).

**Usage:** `python build/underwrite.py <DD_checklist.xlsx> [--template <master.xlsm>] [--out DIR] [--name "Deal"]`
→ writes `<deal> — Stick.xlsm` and `<deal> — Modular.xlsm`. `--selftest <example.xlsm>` round-trips
and asserts every written cell. Self-test PASS on Kinzie (Large Family) + demo (Standard/1B) branches.

**Clean master template:** `template/ProForma_BLANK_master.xlsm` (used by default when
`--template`/`$SOLA_UW_TEMPLATE` are omitted). Derived from the Kinzie model with the deal-specific
**hard inputs wiped** so nothing leaks: acquisition price `S16` (was $5M) and residential stories
`C15` (Hand fields the exporter doesn't set), plus the exporter-overwritten id cells (`B2`/`C3`/`C12`).
Dropdown cells (`C4`–`C9`, `A36`, `C10` PW, `C11` BIPOC) are left as-is — the exporter overwrites the
ones it owns, and the rest (`C10`/`C11` = "No") are neutral defaults. Template *defaults* are kept:
rent/expense growth, bond test, podium levels, unit sizes `L3:L6`, DD soft cost. Macros/LAMBDAs intact.
