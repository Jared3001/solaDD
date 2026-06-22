#!/usr/bin/env python3
"""
comp_adjust.py — N1 rent-comp adjustment engine (CTCAC / HUD-92273 style).

The canonical SoLa adjustment ruleset, reverse-engineered from the boss's
"Stick Rent Comp – 17719 Kinzie" model (1-Bedroom tab — the clean one; the 2-BR
tab's age formula is broken and the Studio tab applies age as raw years, so
neither was used). Confirmed exact across all three Kinzie comps:

  * Unit size : (subject SF - comp SF) x rate, where rate = subject $/SF x 0.10
  * Age       : (subject year - comp year) x $5/year  (newer subject -> comps up)
  * Amenities : per-line $; comp-superior -> negative, subject-superior -> positive
  * Utilities : Water/Sewer/Trash $ /mo, applied only when tenant-pay differs

This module is the SINGLE SOURCE OF TRUTH for the math. The web editor mirrors
these same rules in JS for the live preview; the Excel writer (comps.py) sums the
final (possibly analyst-edited) values. Values still pending the boss's red-line
on SOLA_Comp_Adjustment_Review.xlsx (bathrooms $, a few unobserved amenities) use
the conservative defaults below.
"""

# ---- rates ----
AGE_PER_YEAR = 5.0
SIZE_RATE_FRACTION = 0.10          # per-SF size adj = SIZE_RATE_FRACTION x subject $/SF
BATH_ADJ = 0                       # $/bath difference — NOT set in Kinzie; boss to confirm

# ---- per-line amenity $ (default 5; explicit overrides from the Kinzie 1-BR) ----
AMENITY_DEFAULT = 5
AMENITY_OVERRIDE = {
    "Central Heat/Cool": 25, "Refrigerator": 25, "Stove/Oven": 25,
    "Washer/Dryer": 25, "Dishwasher": 15, "Tuck-under Garage": 15,
    "Washer/Dryer Hook-ups": 10, "Surface Parking": 0,
}
# Ordered to match the CTCAC template's rows (Unit / Appliances / Parking / Project).
AMENITY_LABELS = [
    "Central Heat/Cool", "Blinds", "Carpet", "Ceiling Fan", "Skylight",
    "Storage Closet", "Coat Closet", "Walk-In Closet", "Fireplace", "Patio/Balcony",
    "Refrigerator", "Stove/Oven", "Dishwasher", "Garbage Disposal", "Microwave",
    "Washer/Dryer", "Washer/Dryer Hook-ups",
    "Surface Parking", "Carport", "Underground Parking", "Detached Garage",
    "Attached Garage", "Tuck-under Garage", "Parking Garage",
    "Clubhouse/Community Room", "Swimming Pool", "Spa/Jacuzzi", "Exercise Room",
    "Picnic Area", "Tot Lot/Playground", "Tennis Court", "Basketball Court",
    "Volleyball Court", "On Site Manager", "Laundry Room", "Computer Room",
    "Business Center", "Car Wash Area", "Gated", "Courtesy Patrol",
    "Surveillance Camera",
]

# Utilities adjusted by $ when tenant-pay responsibility differs (monthly).
UTILITY_VALUES = {"Water": 96, "Sewer": 64, "Trash": 10}
UTILITY_LABELS = list(UTILITY_VALUES)

# Comps whose Adjusted Rent / Base Rent exceeds this must be justified (grid row 84).
GUARDRAIL = 1.10


def amenity_value(label):
    return AMENITY_OVERRIDE.get(label, AMENITY_DEFAULT)


def _truthy(v):
    """A characteristic is 'present' if it's an 'X' flag or a non-zero number."""
    if isinstance(v, str):
        return v.strip().upper() == "X"
    return bool(v)


# ---- individual adjustments ----
def size_adj(subj_sf, comp_sf, subj_rent):
    if not (subj_sf and comp_sf and subj_rent):
        return 0.0
    rate = (subj_rent / subj_sf) * SIZE_RATE_FRACTION
    return (subj_sf - comp_sf) * rate


def age_adj(subj_year, comp_year):
    if not (subj_year and comp_year):
        return 0.0
    return (subj_year - comp_year) * AGE_PER_YEAR


def line_adj(subj_has, comp_has, value):
    """Comp superior (has it, subject doesn't) -> -value; subject superior -> +value."""
    if comp_has and not subj_has:
        return -value
    if subj_has and not comp_has:
        return value
    return 0


def default_adjustments(subject, comp):
    """Compute the default per-line adjustments for one comp vs. the subject.

    subject / comp are dicts: {sf, rent, year, baths, amenities:{label:flag},
    utilities:{label:flag}}. Flags are 'X'/truthy = present (amenity) or
    tenant-paid (utility). Returns an ordered list of (label, $) — the rows the
    grid shows, defaulted from the ruleset (the analyst may then edit them).
    """
    s_am, c_am = subject.get("amenities", {}), comp.get("amenities", {})
    s_ut, c_ut = subject.get("utilities", {}), comp.get("utilities", {})
    rows = []
    rows.append(("Unit Size Adjustment",
                 round(size_adj(subject.get("sf"), comp.get("sf"), subject.get("rent")), 2)))
    rows.append(("Bathrooms",
                 line_adj(_truthy(subject.get("baths")), _truthy(comp.get("baths")), BATH_ADJ)))
    rows.append(("Age (built or last renovated)",
                 round(age_adj(subject.get("year"), comp.get("year")), 2)))
    for label in UTILITY_LABELS:
        rows.append((label, line_adj(_truthy(s_ut.get(label)), _truthy(c_ut.get(label)),
                                     UTILITY_VALUES[label])))
    for label in AMENITY_LABELS:
        rows.append((label, line_adj(_truthy(s_am.get(label)), _truthy(c_am.get(label)),
                                     amenity_value(label))))
    return rows


def adjusted_rent(base_rent, adjustments):
    """Adjusted Rent = base rent + sum of adjustment $ (list of (label, $) or $)."""
    total = 0.0
    for a in adjustments:
        total += a[1] if isinstance(a, (tuple, list)) else a
    return (base_rent or 0) + total


def assess(subject, comps):
    """Full grid math for a subject + list of comps. Returns per-comp dicts with
    the default adjustments, adjusted rent, $/SF ratio, differential, and the
    110%-guardrail flag — everything the editor seeds and the writer renders."""
    out = []
    for comp in comps:
        adjs = default_adjustments(subject, comp)
        adj_rent = adjusted_rent(comp.get("rent"), adjs)
        base = comp.get("rent") or 0
        out.append({
            "comp": comp,
            "adjustments": adjs,
            "adjusted_rent": round(adj_rent, 2),
            "adjusted_ratio": round(adj_rent / comp["sf"], 4) if comp.get("sf") else None,
            "ratio_to_base": round(adj_rent / base, 4) if base else None,
            "over_guardrail": bool(base) and (adj_rent / base) > GUARDRAIL,
        })
    return out
