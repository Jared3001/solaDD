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

**Framing.** The automated DD checklist hands the model a fixed set of site facts. What it
*can't* do is decide the deal's unit mix, construction type, and financing structure — those
are your calls. My goal with these questions is to learn **which DD outputs you actually read
to make each of those calls, and the rule you apply**, so I can encode "DD checklist → deal
assumptions" instead of guessing. So please answer in the form *"I look at X (and Y) on the
checklist, and if it's ___ then ___."* Where a decision needs something the checklist doesn't
capture, tell me what that missing input is and where it comes from.

**What the checklist already gives you (the inputs you have to work from):**
- *Site/identity:* address, APN, **city/jurisdiction**, **county**, **geographic pool**
  (CDLAC region — City of LA vs Balance of LA County, etc.), **lot SF / land area**.
- *Programs & affordability geography:* **QCT**, **DDA** (each with current + prior year),
  **resource area** (Highest / High / Moderate / Low), **neighborhood change area**,
  **opportunity zone**.
- *Zoning / entitlement (LA City):* **zoning + height district**, **TOC tier**, **½-mile
  major transit**, **specific plan / overlay**, **[Q] conditions**, council district.
- *Hazards / physical:* **flood zone**, **very-high fire**, **methane zone**, **liquefaction**,
  **Alquist-Priolo fault**, **oil/gas wells**, **USTs/contamination**, **slope/grade**.
- *Tenancy (when desk-filled):* existing residential units, units to vacate at COE,
  rent-stabilized, owner-occupied, **SB8 replacement units**.

---

### 1. Unit mix — how the DD checklist shapes the unit program
**What the model needs:** product/set-aside type, the bedroom split (`Pro_Forma!H3:H6` counts,
`I3:I6` %), the AMI/income band mix (`J` column: 30/50/60/70% AMI), average unit sizes per
bedroom, and the manager's unit(s). The model derives the unit *count* from NRSF (lot area ×
FAR × efficiency); we set the *mix*.

1. **Reading product type off the checklist.** This site is a "Large Family" deal. Walk me
   through how you land on a product type (Large Family vs Senior vs Special-Needs/SRO vs
   At-Risk) from the checklist alone — which fields tip it? For example, does **resource area**,
   **jurisdiction / geographic pool**, achievable **density (zoning + lot SF)**, **TOC tier**,
   or the **surrounding neighborhood** push you toward family vs senior? Is there a default
   product type for a typical SoLa acquisition, and do you ever carry more than one product
   type forward?
2. **Bedroom split, and what moves it.** Once the product type is set, what bedroom split do
   you start from (e.g., for Large Family), and **which checklist outputs change it**? Concretely:
   does a **Highest/High resource area** push more 3BR (family-friendly / tiebreaker)? Does the
   **jurisdiction, specific-plan overlay, or [Q] conditions** impose or cap a bedroom mix? Does
   the **CTCAC Large-Family set-aside** dictate a minimum 3BR (or 2BR+) share — and what's the
   current threshold? Do you ever model studios (0B) for Large Family, or are studios only for
   Senior/SRO?
3. **How the site bounds the count and therefore the mix.** The model sizes units from lot SF
   and FAR. In practice, do you let **lot SF + zoning/height district + TOC density bonus**
   drive the count the way the model does, or do you cap it by **parking, jurisdiction max-units,
   or a unit-size floor**? Which checklist fields set that ceiling, and does hitting a cap change
   the bedroom mix (e.g., fewer large units to fit the count)?
4. **Average unit sizes (NRSF per bedroom).** The model uses ~402 / 497 / 700 / 900 NRSF for
   0/1/2/3BR. Are those your standard assumptions, or do they flex by **jurisdiction, resource
   area, product type, or build method (Stick vs Modular)**? Same question for the **manager's
   unit(s)** — how many and which bedroom type, scaled to unit count?
5. **AMI / income band mix.** What's your first-pass split across 30/50/60/70% AMI, and **which
   checklist outputs inform it** versus what's purely program-driven? Specifically: do
   **resource area + geographic pool / CDLAC region** (tiebreaker competitiveness), **QCT/DDA**,
   or **jurisdiction overlays (AHSC, local requirements)** move the AMI mix? Are there hard
   floors/ceilings (e.g., a minimum ≤30% AMI share), and is the 70% band a real target or a
   placeholder?
6. **Existing tenancy / SB8.** When the checklist shows existing residential, rent-stabilized,
   or SB8 replacement units, does that constrain the mix (e.g., bedroom-matched replacement
   units, or a deeper-affordability requirement)? How should I fold that in?

---

### 2. Construction type — how the DD checklist drives structure
**What the model needs:** construction type (`Pro_Forma!C9` = Type I / III / Other) and the
residential stories / FAR that flow into NRSF (model defaults: ~5 stories, FAR ≈ 3.5/5 × stories,
NRSF = acres × 43,560 × FAR × 0.8). Build *method* (Stick/Modular) is handled separately in §3.

1. **Stories & FAR from the checklist.** How do you project **residential stories and FAR** at
   first pass from the DD outputs — specifically the **zoning + height district**, **lot SF**,
   **TOC tier / density bonus**, and any **specific-plan/overlay**? Is the model's ~5-story /
   FAR-3.5 default just a placeholder, or do you actually read the achievable envelope off the
   height district and bonuses per site?
2. **Type I vs Type III — the rule.** Is the Type I vs III call essentially a function of the
   stories/height you just derived (e.g., Type III stick up to ~5–6 stories, Type I concrete
   above that or whenever there's a podium), or do other checklist factors weigh in? Where's
   the cutoff, and when would you ever pick "Other"?
3. **Do hazards change the *type* or just the *cost*?** This is the key one for me — for each
   hazard the checklist flags, tell me whether it **changes construction type/structure** or just
   **adds a cost line**: **methane zone** (sub-slab membrane / podium?), **liquefaction** and
   **Alquist-Priolo fault** (foundation/structural system?), **slope/grade** (stepped foundation,
   retaining?), **flood zone** (raised finished floor / podium?). I want to know which of these
   should flip Type III → Type I (or "Other") versus which I should leave to the cost side.
4. **Does type differ between the two models?** For the Stick vs Modular pair (§3) — do you hold
   construction *type* constant and only change the method, or can the type itself differ between
   the Stick and Modular versions of the same site?

---

### 3. Build method — Stick & Modular (always produce both)
**What the model needs:** the method toggle `Pro_Forma!A36` = "Stick" or "Modular"; the team
wants both saved separately.

1. Confirm you want **both** modeled every time — or are there site conditions (from the
   checklist) where only one method is viable (e.g., a constrained/odd-shaped lot, height, or
   jurisdiction that rules modular in/out)?
2. Besides flipping `A36`, does switching to Modular require changing any **other inputs** we'd
   set — stories, construction type, unit sizes, timeline, contingency — or does the template
   absorb the full cost/schedule delta from the toggle alone?
3. As a sanity check, what cost and schedule delta should Modular show vs Stick?

---

### 4. Financing structure — how the DD checklist informs the capital stack
**What the model needs:** the 4% vs 9% path, the financing layers (`Pro_Forma!D59` =
{Ground Lessor, Soft Debt, State Credits, B-Bond, None}), and the bond-test limit
(`C21` / `Sheet1!F16`, model 27.5%).

1. **9% vs 4%+bond — from the checklist.** At first pass, which DD outputs push a deal toward
   **9% (competitive) vs 4% + tax-exempt bonds**? Specifically: does **deal size** (inferred from
   **lot SF / unit count**) drive it (larger → 4%/bond)? Does **QCT/DDA** (the 30% basis boost)
   tilt you toward 4%? Do **resource area + geographic pool / CDLAC region** (9% tiebreaker
   competitiveness) decide it? Give me the rule of thumb and any thresholds.
2. **What triggers each financing layer (`D59`).** For each — **Ground Lessor, Soft Debt, State
   Credits, B-Bond** — what signals it, and **can I infer that signal from the checklist**? E.g.:
   does SoLa owning/contributing the land (ground lease) trigger Ground Lessor? Does the
   **jurisdiction / geographic pool** (City of LA vs Balance of County soft-funds availability)
   trigger Soft Debt? When do State Credits or a B-Bond come in — gap size, or something
   checklist-visible? I want to separate "inferable from DD" from "purely deal-side."
3. **Default structure.** If nothing special applies, what's the default financing structure for
   a first pass?
4. **Fixed vs per-deal knobs.** Are the **bond-test limit (27.5%)** and the **applicable
   percentage / tax-credit factor** fixed assumptions, or do you set them per deal (and off what)?
5. **Acquisition price.** Confirmed this comes from the OM/broker and isn't something we derive —
   but is there a fallback (e.g., a land-residual or $/unit placeholder) you use before a price
   is set, and does any checklist field inform that placeholder?

---

### 5. Policy flags  (model: `Pro_Forma!C8` CRA, `C10` Prevailing Wage, `C11` BIPOC)
- **Prevailing Wage** — what determines Yes/No, and is any of it checklist-visible (deal size,
  financing path, jurisdiction)?
- **CRA** — is this a designation we could *derive* (a community-revitalization/reinvestment area
  with a public layer), or is it a manual/local call? What sets it?
- **BIPOC** — what determines it, and does it materially move cost or scoring?

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
