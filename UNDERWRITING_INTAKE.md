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

## Part B — Draft projection logic (decision tables) — RED-LINE THESE

> All values **[CONFIRM]**. Inputs in **bold** are ones we already have from the DD checklist.

### B1. Unit mix (bedroom %) — keyed on product type
| Product | 0B | 1B | 2B | 3B | Notes |
|---|---|---|---|---|---|
| Large Family | 0% | 50% | 25% | 25% | matches the Kinzie example; assumes a 3BR floor **[CONFIRM CTCAC min]** |
| Senior | ~15% | 85% | 0% | 0% | placeholder **[CONFIRM]** |
| SRO / Special Needs | 100% 0B | — | — | — | placeholder **[CONFIRM]** |
- Unit **count** = model-derived (NRSF ÷ avg unit size); we just set the **%** split.
- Manager's unit: 1 per ~? units, 1BR **[CONFIRM ratio]**.

### B2. AMI / income mix — default first pass
| Band | 30% | 50% | 60% | 70% | Notes |
|---|---|---|---|---|---|
| Default % of units | ? | ? | ? | ? | **[CONFIRM]** — model shows 30/50/60/70 bands present |
- Adjust by **9% vs 4%** and tiebreaker target **[CONFIRM rule]**.

### B3. Construction type — keyed on stories (from lot SF + zoning)
| Residential stories | Type | Notes |
|---|---|---|
| ≤ 5–6 | **Type III** | stick-framed, default for mid-rise **[CONFIRM cutoff]** |
| ≥ 6–7 or podium | **Type I** | concrete/podium **[CONFIRM]** |
| special | Other | analyst override |
- Stories/FAR projected from **lot SF** + zoning (model: FAR ≈ 3.5/5 × stories; NRSF = acres×43,560×FAR×0.8).

### B4. Build method — ALWAYS produce both (Stick + Modular)
- No decision — generate both. Only `A36` differs unless seniors say type/stories/timeline also flip (Q4).

### B5. Financing structure — first-pass default
| Condition | Structure | Notes |
|---|---|---|
| Default | 4% + tax-exempt bond, `D59 = None` | **[CONFIRM default]** |
| Small / competitive | 9% | **[CONFIRM size threshold]** |
| SoLa contributes land | add Ground Lessor (`D59`) | **[CONFIRM]** |
| Jurisdiction soft funds available | add Soft Debt | **[CONFIRM]** |
| Large gap | add State Credits / B-Bond | **[CONFIRM]** |

### B6. Policy flags — defaults
| Flag | Default | Driver to confirm |
|---|---|---|
| Prevailing Wage (`C10`) | No | deal size / financing **[CONFIRM]** |
| BIPOC (`C11`) | No | **[CONFIRM]** |
| CRA (`C8`) | No | **[CONFIRM]** |

---

## Part C — Dual-model output spec (Stick + Modular)
For each deal the exporter will:
1. Fill the DD-derived **site inputs** (`Pro_Forma B2,C3:C7,C12` — see `UNDERWRITING_AUTOMATION.md`).
2. Fill the **assumption inputs** from the confirmed Part-B logic (unit mix `H3:H6`/`I3:I6`,
   AMI mix, construction type `C9`, financing `D59`, stories/FAR, policy flags).
3. Produce **two files**, identical except `A36`:
   - `<deal> — Stick.xlsm`  (`A36 = "Stick"`)
   - `<deal> — Modular.xlsm` (`A36 = "Modular"`)
   …and any other method-dependent inputs seniors flag in Q4.
4. Hand both to the analyst to open & recalc in Excel (outputs at `C24:C30`).

## Status
Draft prepared for senior review. Once Part A is answered / Part B red-lined, the rules
become the exporter's assumption layer and the DD→underwriting→dual-model hand-off can be built.
