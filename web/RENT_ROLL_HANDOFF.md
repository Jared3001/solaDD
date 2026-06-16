# ModularZ — Rent Roll parameterization (handoff to the proforma owner)

## TL;DR
The ModularZ proforma template (`(Z+) Rent Roll`, i.e. `xl/worksheets/sheet6.xml`)
has **rents hardcoded as literal constants inside formulas**. No input cell feeds
rent, so the web tool cannot pass a market rent into the model. As a result the
proforma's **revenue is fixed by unit mix and independent of market** — every
location computes similar/marginal returns because costs vary by market but
revenue does not. Making returns market-responsive requires turning the rents
into inputs. That edits the financial model, so it needs the model owner.

## What the tool already does (no model change needed)
Everything that has a real input cell now flows from the front end into the
validated Engine template and is computed by Excel/HyperFormula:
- Units & mix → `Inputs!O11:O13`
- NRSF / massing → `Inputs!D13,D16,D17,O6..O9,O15`
- Vacancy, escalation, timing → `Inputs!L6,L9,E20,E23,E30`
- Exit cap, rent growth, onsite cost, constr LTC/rate, perm rate → `Dashboard!J5,W21,W18,J11,J12,K12`
- Land → `(Z+) Dev Budget!G7`
- Perm LTV / DSCR / amort → `(Z+) Financing!D34,H11,H21`

The headline tiles, the Returns and Finance sensitivity grids, and the .xlsx
download all use this and agree with each other.

## What's hardcoded (the gap)
On `(Z+) Rent Roll`, the **Natural Rent** column G holds literal monthly rents by
bed type, e.g.:

| Row | Bed type | Formula (rent is the literal) |
|-----|----------|-------------------------------|
| G8  | Studio   | `=IFERROR(2041-F8,0)`  → $2,041 |
| G9  | 1-BR     | `=IFERROR(2289-F9,0)`  → $2,289 |
| G10 | 2-BR     | `=IFERROR(2887-F10,0)` → $2,887 |
| G11 | 3-BR     | `=IFERROR(3668-F11,0)` → $3,668 |

Affordable/voucher rows (12–19) use similar baked figures in column I
(`2023.68`, `2289`, `2896.392`, `3718.512`, …). Column K (`Adj. Rents`) and L
(`Adj. Income`) derive from these; `L20` rolls up to revenue → NOI → every return.

## Recommended change (model owner)
Replace the literal rents with references to **new input cells** the tool can
write. Two clean options:

1. **$/unit by bed type** — add four input cells (e.g. on `Inputs`, near the unit
   mix at `O11:O13`) for studio/1BR/2BR/3BR market rent, and change `G8:G11`
   (and the affordable rows' references) to point at them.
2. **$/SF rent** — add one `rent $/SF/mo` input and compute each row's rent as
   `$/SF × avg unit SF for that bed type`. Matches how the front end thinks
   (`model.rentPerSf`).

Either way, also decide how affordable set-aside rents should track market rent
(AMI caps vs. a discount) so rows 12–19 update consistently.

## Then wire the front end (small, mechanical)
Once the input cells exist, add the writes in `web/build_modularz.py` →
`buildInputPatches()` (it already centralizes every input patch). Map from the
dashboard model: `model.rentPerUnit` / `model.rentPerSf` (and, if you keep a real
unit mix, per-bed rents). Re-run `python3 web/build_modularz.py`. After that the
Revenue/Rent sensitivity tab can be switched from JS to the Excel engine (remove
the `activeSensi === 'revenue'` special-case in `buildSensiTable()`), and the
"quick estimate" note can be dropped — all three grids will then be institutional.

## Why returns look marginal today
With rents frozen at the baked figures and costs reflecting real market land /
hard cost, going-in yield (~4.3% for the Sherman Oaks sample) sits below the exit
cap (~5.15%) → negative development spread → negative levered IRR. That's the
model being honest given fixed revenue; it should improve once rents reflect the
market.
