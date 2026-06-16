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

### 0. Product / set-aside type (the upstream driver)
The filename ("Stick **Large Family**") shows product type drives a lot. Pin it first.
- How do you decide a site's product type — **Large Family vs Senior vs Special
  Needs / SRO / At-Risk** — from what we know at first pass (resource area, jurisdiction,
  lot size, neighborhood, surrounding need)?
- Is there a **default product type** for a typical SoLa acquisition, or is it always a judgment call?
- Does product type get locked before underwriting, or do you sometimes run more than one?

### 1. Unit mix — bedroom distribution  (model: `Pro_Forma!H3:H6` counts, `I3:I6` %)
- For a **Large Family** deal, what's your **default bedroom split** (0/1/2/3BR)? Is there
  a minimum 3BR (or 2BR+) share you hold to (CTCAC set-aside / jurisdiction)?
- Does the split change with **resource area** (e.g., more family units in High/Highest),
  **jurisdiction**, or **site size / unit count**? How?
- Do you ever model **studios (0B)** for Large Family, or only Senior/SRO?
- What **average unit sizes (NRSF)** do you assume per bedroom? (Model currently:
  0B≈402, 1B≈497, 2B≈700, 3B≈900 NRSF.) Are these standard or do they flex by method/site?
- The **manager's unit(s)** — how many, and which bedroom type, by unit count?

### 2. Unit mix — AMI / income mix  (model: `Pro_Forma!J` column AMI bands; `Sheet1!E24` 0.3/0.5/0.6/0.7)
- What's your **default AMI band mix** (% of units at 30 / 50 / 60 / 70% AMI) for a
  first pass? Does it differ 9% vs 4%?
- What drives shifts in the AMI mix — **tiebreaker optimization, AHSC/program overlays,
  jurisdiction requirements**, a target average affordability?
- Any **hard floors/ceilings** (e.g., min % at ≤30% AMI for a program)? **[CONFIRM]**
- Is the **70% band** a real target or just a model placeholder?

### 3. Construction type — Type I / III / Other  (model: `Pro_Forma!C9`)
- What's the rule of thumb for **Type III vs Type I**? Is it purely **stories / height /
  podium**, or also density, cost, or unit count? (Common heuristic: Type III stick up to
  ~5–6 stories; Type I concrete above, or with podium. **[CONFIRM]**)
- When would you pick **"Other"**?
- Does construction **type** ever differ between the Stick and Modular versions of the
  same deal, or is type held constant and only the **method** (A36) changes?
- What **residential stories / FAR** do you assume at first pass from lot size + zoning?
  (Model: stories≈5, FAR≈3.5/5×stories, NRSF = acres×43,560×FAR×0.8.)

### 4. Build method — Stick vs Modular  (model: `Pro_Forma!A36`; always BOTH)
- Confirm: you want **both** modeled and saved every time? Any deal where only one applies?
- Besides the A36 toggle, does switching to Modular change any **other inputs** we'd set
  (stories, type, unit sizes, timeline, contingency), or does the template handle the full
  cost/time delta off A36 alone?
- Roughly, what **cost and schedule delta** should Modular show vs Stick (sanity check)?

### 5. Financing structure  (model: `Pro_Forma!D59` {Ground Lessor, Soft Debt, State Credits, B-Bond, None}; 4%/9%; bond test `C21`/`Sheet1!F16`)
- How do you decide **9% vs 4%+tax-exempt bonds** at first pass? Is there a **deal-size or
  gap threshold**? (Common: larger deals → 4%/bond; smaller/competitive → 9%. **[CONFIRM]**)
- When do you layer **Ground Lessor / Soft Debt / State Credits / B-Bond** (D59)? What signals
  each (gap size, jurisdiction soft funds, SoLa land contribution, state credit availability)?
- What's the **default financing structure** for a typical first pass if nothing special applies?
- **Bond test limit** (model 27.5%) and **applicable percentage / tax-credit factor** — are
  these fixed assumptions or do you set them per deal?
- **Acquisition price** — confirmed source is the OM/broker (we won't derive it); any default
  (e.g., land residual) when price isn't set yet?

### 6. Policy flags  (model: `Pro_Forma!C8` CRA, `C10` Prevailing Wage, `C11` BIPOC)
- **Prevailing Wage** — when is it Yes (deal size, financing, jurisdiction)? **[CONFIRM]**
- **BIPOC** and **CRA** — what determines each, and do they change costs/scoring materially?

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
