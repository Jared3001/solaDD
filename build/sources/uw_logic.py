#!/usr/bin/env python3
"""
uw_logic.py — pure projection logic for the underwriting exporter.

Given the DD checklist outputs (a plain {field: value} dict), produce the
{(sheet, cell): value} maps that underwrite.py writes into SoLa's pro-forma
template. NO file I/O here — this module is just the confirmed rules from
UNDERWRITING_INTAKE.md Part B (senior review 2026-06-16), so it stays unit-
testable and the cell mechanics live in underwrite.py.

Two kinds of output:
  base_cells(dd)        -> method-INDEPENDENT inputs (Auto from DD + Logic).
  method_cells(method)  -> the Stick/Modular overlay (A36, sizes, build time).

Everything the analyst still owns (acquisition price, BIPOC, residential
stories C15, prevailing wage) is deliberately NOT emitted -> left at the
template's value for the analyst to fill.
"""

# ---- canonical dropdown vocabularies (read from the template's data validations) ----
# Pro_Forma!C6  list = Low, Medium, High, Highest      (DD says "Moderate" -> "Medium")
# Pro_Forma!C5  list = QCT, DDA, None
# Pro_Forma!C4  list = $AH$29:$AH$40 (the PHA short labels below)
PHA_CANONICAL = [
    "Los Angeles", "San Diego County", "Oakland", "Orange County",
    "Sacramento (City/County)", "San Diego", "Los Angeles County",
    "Santa Ana", "Riverside County", "San Francisco", "Santa Clara County",
]

# C9 build-method-aware construction-type formula (template change, approved).
# References the hand-entered residential-stories cell C15 and the file's A36.
C9_FORMULA = '=IF(C15>5,"Type I",IF(AND(A36="Stick",C15=5),"Type III","Other"))'

# AMI / income mix — exporter sets 10% @30, 10% @50, 80% @60 (no 70% band).
# R37 (@60%) is a remainder formula in the template; R38 (@70%) we zero out.
AMI_SHARES = {"R35": 0.10, "R36": 0.10, "R38": 0}

# Method-dependent assumptions (UNDERWRITING_INTAKE.md B4/B5).
CONSTRUCTION_TIME = {"Stick": 24, "Modular": 18}      # Draws_Module!B5, months
MODULAR_SIZES = {"L5": 804, "L6": 994}                # 2B / 3B avg NRSF; Stick keeps 700/900

# First-pass envelope placeholders (Pro_Forma C15 / C17). The DD can't supply
# these, and with them blank the whole stories -> FAR (C16) -> NRSF (C17) ->
# Units (C14) -> cost (D36) cascade collapses to zero, which silently breaks the
# model. So the exporter seeds a generic building the analyst overrides with the
# real envelope. Writing C17 as a literal intentionally replaces the template's
# lot x FAR formula (=D12*43560*C16*0.8) — NRSF becomes a hand input, not derived.
DEFAULT_STORIES = 3        # Pro_Forma!C15 (residential stories) — drives the C9 type formula
DEFAULT_NRSF    = 20000    # Pro_Forma!C17 (building NRSF)


# ---------- field transforms ----------
def project_name(address: str) -> str:
    """Deal name = the street portion of the DD address (before the first comma)."""
    return (address or "").split(",")[0].strip()


def county(county_text: str) -> str:
    """Strip the ' County' suffix DD emits ('Los Angeles County' -> 'Los Angeles')."""
    s = (county_text or "").strip()
    return s[:-7].strip() if s.lower().endswith(" county") else s


def qct_dda(qct, dda) -> str:
    """Collapse the two DD booleans to the model's single QCT/DDA/None cell."""
    if _yes(qct):
        return "QCT"          # QCT and DDA give the same basis boost; prefer QCT label
    if _yes(dda):
        return "DDA"
    return "None"


def resource(resource_text: str) -> str:
    """Map the DD CTCAC category to the model's Low/Medium/High/Highest vocabulary."""
    s = (resource_text or "").strip().lower()
    if s.startswith("highest"):
        return "Highest"
    if s.startswith("high"):                 # "High Resource" (and "High Segregation"->High? no)
        return "High"
    if s.startswith("moderate") or s.startswith("medium"):
        return "Medium"
    if s.startswith("low"):
        return "Low"
    if "segregation" in s:                   # High Segregation & Poverty -> treat as Low resource
        return "Low"
    return ""                                # unknown -> leave for analyst (flagged by caller)


def pha(pha_text: str, county_text: str = "", city_text: str = "") -> tuple:
    """Map the DD responsible-PHA text to one canonical C4 label.

    Returns (label, confident). When nothing matches we fall back to the
    county/city short name and mark it not-confident so the caller can flag it.
    """
    # an explicit canonical pick (e.g. from the review/edit step) is authoritative
    if (pha_text or "").strip() in PHA_CANONICAL:
        return (pha_text or "").strip(), True
    t = (pha_text or "").lower()
    has = lambda *ws: all(w in t for w in ws)
    # city authorities first (more specific than the county catch-alls)
    if "hacla" in t or has("city of los angeles") or has("housing authority", "los angeles") and "county" not in t:
        return "Los Angeles", True
    if "lacda" in t or has("los angeles", "county"):
        return "Los Angeles County", True
    if has("city of san diego") or has("san diego") and "county" not in t and "hacsd" not in t:
        return "San Diego", True
    if has("san diego", "county"):
        return "San Diego County", True
    if "oakland" in t:
        return "Oakland", True
    if "orange county" in t or has("orange", "county"):
        return "Orange County", True
    if "sacramento" in t:
        return "Sacramento (City/County)", True
    if "santa ana" in t:
        return "Santa Ana", True
    if "riverside" in t:
        return "Riverside County", True
    if "san francisco" in t or "sfha" in t:
        return "San Francisco", True
    if "santa clara" in t:
        return "Santa Clara County", True
    # fallback: try the county / city short name against the canonical list
    for cand in (county(county_text), (city_text or "").strip()):
        if cand and cand in PHA_CANONICAL:
            return cand, False
    return (pha_text or "").strip(), False


def is_large_family(resource_mapped: str) -> bool:
    """Large Family product in High/Highest resource; standard (1B) in Low/Medium."""
    return resource_mapped in ("High", "Highest")


def bedroom_mix(large_family: bool) -> dict:
    """Mix % into I3/I5/I6 (I4 1B is the template's =1-I3-I5-I6 remainder).

    Large Family -> 0/50/25/25 (I4 auto 0.50).  Standard -> 100% 1B (I4 auto 1.0).
    """
    if large_family:
        return {"I3": 0, "I5": 0.25, "I6": 0.25}   # 0B / 2B / 3B ; I4 -> 0.50
    return {"I3": 0, "I5": 0, "I6": 0}             # 0B / 2B / 3B ; I4 -> 1.00


def cra(neighborhood_change, large_family: bool) -> str:
    """CRA = Yes if neighborhood change = No AND not Large Family; else No."""
    return "Yes" if (not _yes(neighborhood_change) and not large_family) else "No"


def _yes(v) -> bool:
    return str(v).strip().lower().startswith("y")


# ---------- assembled cell maps ----------
def base_cells(dd: dict):
    """Method-independent inputs. Returns (cells, meta).

    cells: {(sheet, cell): value} for the Pro_Forma inputs that are the same in
    both the Stick and Modular files.  meta: notes/flags for the caller to log.
    """
    res = resource(dd.get("resource_area", ""))
    lf = is_large_family(res)
    pha_label, pha_ok = pha(dd.get("pha", ""), dd.get("county", ""), dd.get("city_jurisdiction", ""))

    cells = {}
    def put(cell, val):
        cells[("Pro_Forma", cell)] = val

    put("B2", project_name(dd.get("address", "")))
    put("C3", county(dd.get("county", "")))
    put("C4", pha_label)
    put("C5", qct_dda(dd.get("qct"), dd.get("dda")))
    put("C6", res)
    put("C7", "Yes" if _yes(dd.get("neighborhood_change_area")) else "No")
    put("C8", cra(dd.get("neighborhood_change_area"), lf))
    put("C9", C9_FORMULA)
    put("C12", _num(dd.get("land_sf")))
    for c, v in bedroom_mix(lf).items():
        put(c, v)
    for c, v in AMI_SHARES.items():
        put(c, v)
    # Envelope placeholders — use the analyst override when supplied, else default
    # (see DEFAULT_STORIES / DEFAULT_NRSF). Without these the model is broken.
    put("C15", _int_or(dd.get("residential_stories"), DEFAULT_STORIES))
    put("C17", _int_or(dd.get("building_nrsf"), DEFAULT_NRSF))
    # Land / acquisition purchase price (Pro_Forma!S16). Collected as a REQUIRED
    # input on the web review step; only written when supplied so the CLI/DD path
    # (which can't know the price) leaves it blank for the analyst to fill.
    acq = _num(dd.get("acquisition_price"))
    if acq is not None:
        put("S16", acq)

    meta = {
        "product": "Large Family" if lf else "Standard (1B)",
        "resource_mapped": res,
        "flags": [],
    }
    if not res:
        meta["flags"].append(f"resource_area '{dd.get('resource_area')}' did not map to a C6 value (left blank)")
    if not pha_ok:
        meta["flags"].append(f"PHA '{dd.get('pha')}' -> '{pha_label}' (review: not a confident match)")
    return cells, meta


def method_cells(method: str):
    """The Stick/Modular overlay: A36, build time, and (Modular) unit sizes."""
    if method not in ("Stick", "Modular"):
        raise ValueError(f"method must be Stick or Modular, got {method!r}")
    cells = {
        ("Pro_Forma", "A36"): method,
        ("Draws_Module", "B5"): CONSTRUCTION_TIME[method],
    }
    if method == "Modular":
        for c, v in MODULAR_SIZES.items():
            cells[("Pro_Forma", c)] = v
    return cells


def _num(v):
    """Coerce a DD lot-SF answer to a number, tolerating '35,796 sf' style text."""
    if isinstance(v, (int, float)):
        return v
    if v is None:
        return None
    s = "".join(ch for ch in str(v) if ch.isdigit() or ch == ".")
    return float(s) if s else None


def _int_or(v, default):
    """A positive number from v (whole numbers stay int), else the placeholder default."""
    n = _num(v)
    if not n or n <= 0:
        return default
    return int(n) if float(n).is_integer() else n


# --------------------------------------------------------------------------- #
# Review & edit step — the editable intake the web front end shows BEFORE export.
# `intake(dd)` returns the editable defaults + the select vocabularies + a
# live-preview of the derived assumptions. The browser edits `values`, recomputes
# `derived` in JS (mirror of the rules above), and posts `values` back as
# overrides; `apply_overrides()` folds them into the dd dict before base_cells().
# --------------------------------------------------------------------------- #
INTAKE_OPTIONS = {
    "resource": ["Low", "Medium", "High", "Highest"],
    "qct_dda": ["QCT", "DDA", "None"],
    "neighborhood_change": ["Yes", "No"],
    "pha": PHA_CANONICAL,
}


def derived_preview(values: dict) -> dict:
    """The assumptions the model derives from the editable inputs (for preview)."""
    res = resource(values.get("resource", ""))
    lf = is_large_family(res)
    mix = bedroom_mix(lf)
    stories = _int_or(values.get("residential_stories"), DEFAULT_STORIES)
    nrsf = _int_or(values.get("building_nrsf"), DEFAULT_NRSF)
    acq = _num(values.get("acquisition_price"))
    return {
        "product": "Large Family" if lf else "Standard (1B)",
        "cra": cra(values.get("neighborhood_change"), lf),
        "construction_type": "Type I / III by stories (formula)",
        "bedroom_mix": ("0% Studio · 50% 1B · 25% 2B · 25% 3B" if lf
                        else "100% 1B"),
        "ami_mix": "10% @30% · 10% @50% · 80% @60%",
        "residential_stories": stories,
        "building_nrsf": nrsf,
        "acquisition_price": acq,
        "_mix_cells": mix,
    }


def intake(dd: dict) -> dict:
    """Editable defaults + options + derived preview for the review/edit step."""
    pha_label, _ = pha(dd.get("pha", ""), dd.get("county", ""), dd.get("city_jurisdiction", ""))
    values = {
        "deal_name": project_name(dd.get("address", "")),
        "county": county(dd.get("county", "")),
        "pha": pha_label,
        "qct_dda": qct_dda(dd.get("qct"), dd.get("dda")),
        "resource": resource(dd.get("resource_area", "")),
        "neighborhood_change": "Yes" if _yes(dd.get("neighborhood_change_area")) else "No",
        "land_sf": _num(dd.get("land_sf")),
        # left blank so the form shows the placeholder default (3 / 20,000); the
        # exporter fills DEFAULT_STORIES / DEFAULT_NRSF when the analyst doesn't.
        "residential_stories": _num(dd.get("residential_stories")),
        "building_nrsf": _num(dd.get("building_nrsf")),
        # required on the review step (no DD source) — analyst must enter it.
        "acquisition_price": _num(dd.get("acquisition_price")),
    }
    return {"values": values, "options": INTAKE_OPTIONS,
            "placeholders": {"residential_stories": DEFAULT_STORIES, "building_nrsf": DEFAULT_NRSF},
            "derived": derived_preview(values)}


def apply_overrides(dd: dict, ov: dict) -> tuple:
    """Fold edited review-step values back into a DD dict. Returns (dd, deal_name)."""
    dd = dict(dd or {})
    ov = ov or {}
    if ov.get("county") is not None:
        dd["county"] = ov["county"]
    if ov.get("pha") is not None:
        dd["pha"] = ov["pha"]
    if ov.get("resource") is not None:
        dd["resource_area"] = ov["resource"]
    if ov.get("neighborhood_change") is not None:
        dd["neighborhood_change_area"] = ov["neighborhood_change"]
    if ov.get("land_sf") not in (None, ""):
        dd["land_sf"] = ov["land_sf"]
    if ov.get("residential_stories") not in (None, ""):
        dd["residential_stories"] = ov["residential_stories"]
    if ov.get("building_nrsf") not in (None, ""):
        dd["building_nrsf"] = ov["building_nrsf"]
    if ov.get("acquisition_price") not in (None, ""):
        dd["acquisition_price"] = ov["acquisition_price"]
    if ov.get("qct_dda") is not None:
        v = ov["qct_dda"]
        dd["qct"] = "Yes" if v == "QCT" else "No"
        dd["dda"] = "Yes" if v == "DDA" else "No"
    return dd, (ov.get("deal_name") or None)
