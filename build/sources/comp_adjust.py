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

# ---- amenity / utility auto-detection from scraped free-text ----------------------
# Each label maps to a list of lowercase substrings that trigger it.
# Matching is case-insensitive substring — acceptable imprecision since the
# analyst reviews every box in the web editor before generating the grid.
_LABEL_PATTERNS = {
    "Central Heat/Cool":       ["central a/c", "central air", "central heat", "central cool",
                                 "air conditioning", "hvac", "forced air"],
    "Blinds":                  ["blind", "window covering", "window treatment"],
    "Carpet":                  ["carpet"],
    "Ceiling Fan":             ["ceiling fan"],
    "Skylight":                ["skylight"],
    "Storage Closet":          ["storage clos", "storage unit", "extra storage"],
    "Coat Closet":             ["coat closet"],
    "Walk-In Closet":          ["walk-in closet", "walk in closet"],
    "Fireplace":               ["fireplace"],
    "Patio/Balcony":           ["patio", "balcony", "terrace"],
    "Refrigerator":            ["refrigerator", "fridge"],
    "Stove/Oven":              ["stove", "oven", "range", "cooktop"],
    "Dishwasher":              ["dishwasher"],
    "Garbage Disposal":        ["garbage disposal", "disposal"],
    "Microwave":               ["microwave"],
    # "in-unit" / "included" patterns checked before bare "washer/dryer" to avoid
    # matching "Washer/Dryer Hookups" strings at both labels.
    "Washer/Dryer":            ["in-unit washer", "in unit washer", "washer/dryer in",
                                 "w/d in unit", "in-unit laundry", "in unit laundry",
                                 "washer and dryer", "washer/dryer included",
                                 "laundry in unit"],
    "Washer/Dryer Hook-ups":   ["hookup", "hook-up", "hook up", "w/d connection",
                                 "washer/dryer hook"],
    "Surface Parking":         ["surface parking", "open parking", "uncovered parking",
                                 "parking lot"],
    "Carport":                 ["carport", "covered parking"],
    "Underground Parking":     ["underground parking", "subterranean", "below grade"],
    "Detached Garage":         ["detached garage"],
    "Attached Garage":         ["attached garage"],
    "Tuck-under Garage":       ["tuck-under", "tuck under"],
    "Parking Garage":          ["parking garage", "parking structure"],
    "Clubhouse/Community Room":["clubhouse", "community room", "club house",
                                 "community center"],
    "Swimming Pool":           ["swimming pool", " pool", "pool "],
    "Spa/Jacuzzi":             ["spa", "jacuzzi", "hot tub", "whirlpool"],
    "Exercise Room":           ["fitness center", "exercise room", "exercise facilit",
                                 "fitness room", "workout room", " gym", "gym "],
    "Picnic Area":             ["picnic", "bbq", "barbecue", "outdoor grill", "grill area"],
    "Tot Lot/Playground":      ["playground", "tot lot", "play area"],
    "Tennis Court":            ["tennis"],
    "Basketball Court":        ["basketball"],
    "Volleyball Court":        ["volleyball"],
    "On Site Manager":         ["on site manager", "onsite manager", "resident manager",
                                 "on-site manager"],
    "Laundry Room":            ["laundry room", "shared laundry", "on-site laundry",
                                 "common laundry", "laundry facilit", "community laundry",
                                 "coin laundry", "laundry on site", "laundry on premises"],
    "Computer Room":           ["computer room"],
    "Business Center":         ["business center"],
    "Car Wash Area":           ["car wash"],
    "Gated":                   ["gated", "controlled access", "security gate",
                                 "gate entry", "key fob", "key-fob"],
    "Courtesy Patrol":         ["courtesy patrol", "security patrol", "security guard"],
    "Surveillance Camera":     ["surveillance", "security camera", "cctv"],
}

# Utility: patterns that indicate the utility is INCLUDED in rent (landlord pays).
# Matched → flag set to "" (not truthy = landlord pays, no tenant adjustment).
# No match → key absent from result (unknown — analyst fills in the editor).
_UTILITY_INCLUDED = {
    "Water": ["water included", "water paid", "water/sewer", "water & sewer",
              "utilities included", "all utilities", "all util"],
    "Sewer": ["sewer included", "sewer paid", "water/sewer", "water & sewer",
              "utilities included", "all utilities", "all util"],
    "Trash": ["trash included", "trash paid", "trash service included",
              "garbage included", "utilities included", "all utilities", "all util"],
}


def map_amenities(raw_list):
    """amenities_raw (list of free-text strings) → {CTCAC_label: 'X'} dict.

    Case-insensitive substring match against _LABEL_PATTERNS. Multiple labels can
    fire from one raw string. False positives are acceptable — the analyst reviews
    every checkbox in the web editor before the grid is generated."""
    if not raw_list:
        return {}
    flags = {}
    normalized = [" " + s.lower() + " " for s in raw_list if isinstance(s, str)]
    for label, patterns in _LABEL_PATTERNS.items():
        for text in normalized:
            if any(pat in text for pat in patterns):
                flags[label] = "X"
                break
    return flags


def map_utilities(raw_list):
    """amenities_raw → {utility_label: ''} for utilities detected as landlord-paid.

    '' (falsy) = included in rent; absent key = unknown (analyst fills).
    'X' (tenant pays) would require explicit 'tenant pays X' text — rare on Zillow,
    so we only emit the landlord-pays signal here."""
    if not raw_list:
        return {}
    flags = {}
    normalized = [" " + s.lower() + " " for s in raw_list if isinstance(s, str)]
    for label, patterns in _UTILITY_INCLUDED.items():
        for text in normalized:
            if any(pat in text for pat in patterns):
                flags[label] = ""   # included → landlord pays
                break
    return flags


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
