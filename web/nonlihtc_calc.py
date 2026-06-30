#!/usr/bin/env python3
"""
nonlihtc_calc.py — server-side engine for NON-LIHTC (market / mixed) deals.

Parallel to modularz_calc.py (the LIHTC v30 engine). Drives the clean pre-v28
ModularZ market workbook (`web/models/NonLIHTC_engine_template.xlsx`) by patching
input cells via surgical worksheet-XML rewrites, recalculating with LibreOffice
headless, and reading the return outputs. The interactive `/modularz` tool keeps
its own embedded copy of this workbook and is untouched.

Why this engine (not the v5.0.7 pro forma): v5.0.7 carries 52 external-workbook
links + structural #REF! + scattered #DIV/0!, which break under unattended
headless recalc. This workbook is self-contained (0 errors / 0 external links) and
recalcs cleanly. Full cell-map + rationale in repo `NONLIHTC_ENGINE_SPEC.md`.

KEY behaviour — MARKET MODE: the engine defaults to a 100%-affordable allocation
via two independent systems that BOTH must be neutralised, else units double-count:
  (a) the restricted set-aside  (Inputs!O27/O28 -> O32), and
  (b) the affordable unit rows   ((Z+) Rent Roll!E12:E19, own H14x0.8/x0.2 formulas).
`_MARKET_MODE_CELLS` zeroes both on every build.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "NonLIHTC_engine_template.xlsx")

# Worksheet names in the engine workbook.
SH_INPUTS = "Inputs"
SH_DASH = "Dashboard"
SH_BUDGET = "(Z+) Dev Budget"
SH_OPEX = "(Z+) OpEx"
SH_RENT = "(Z+) Rent Roll"
SH_FIN = "(Z+) Financing"

# Share the LIHTC engine's process cap so both engines together never OOM Railway.
_RECALC_SEM = threading.Semaphore(2)


# --------------------------------------------------------------------------
# LibreOffice plumbing (self-contained; mirrors modularz_calc)
# --------------------------------------------------------------------------
def _soffice_bin():
    env = os.environ.get("LIBREOFFICE_BIN")
    if env and os.path.exists(env):
        return env
    for cand in ("soffice", "libreoffice"):
        p = shutil.which(cand)
        if p:
            return p
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if os.path.exists(mac):
        return mac
    raise RuntimeError("LibreOffice not found. Set LIBREOFFICE_BIN or install 'libreoffice'.")


def _make_profile():
    """Throwaway LibreOffice profile that forces full recalc on load."""
    d = tempfile.mkdtemp(prefix="nonlihtc_loprofile_")
    user = os.path.join(d, "user")
    os.makedirs(user, exist_ok=True)
    with open(os.path.join(user, "registrymodifications.xcu"), "w") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
            'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
            '<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
            ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
            '<prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
            "</oor:items>\n"
        )
    return d


def _sheet_target(zin, sheet_name):
    """Resolve a sheet name -> 'xl/worksheets/sheetN.xml' via the workbook rels."""
    wb = zin.read("xl/workbook.xml").decode("utf-8")
    m = re.search(r'<sheet name="%s"[^>]*r:id="([^"]+)"' % re.escape(sheet_name), wb)
    if not m:
        raise ValueError(f"sheet {sheet_name!r} not found")
    rid = m.group(1)
    rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rm = re.search(r'Id="%s"[^>]*Target="([^"]+)"' % re.escape(rid), rels)
    if not rm:
        raise ValueError(f"rel {rid} not found")
    tgt = rm.group(1)
    return tgt if tgt.startswith("xl/") else "xl/" + tgt.lstrip("/")


def _set_cell_xml(xml, addr, value, is_text):
    """Surgically set a cell's value in worksheet XML, dropping any formula."""
    if is_text:
        safe = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        newc = f'<c r="{addr}" t="inlineStr"><is><t>{safe}</t></is></c>'
    else:
        newc = f'<c r="{addr}"><v>{value}</v></c>'
    pat = re.compile(r'<c r="%s"(?:[^>]*?)(?:/>|>.*?</c>)' % re.escape(addr), re.S)
    if not pat.search(xml):
        raise ValueError(f"cell {addr} not present in sheet XML (cannot patch)")
    return pat.sub(newc, xml, count=1)


def _force_full_recalc(wbxml):
    m = re.search(r"<calcPr[^>]*?/?>", wbxml)
    if not m:
        return wbxml
    tag = m.group(0)
    if "fullCalcOnLoad" in tag:
        new = re.sub(r'fullCalcOnLoad="[^"]*"', 'fullCalcOnLoad="1"', tag)
    elif tag.endswith("/>"):
        new = tag[:-2] + ' fullCalcOnLoad="1"/>'
    else:
        new = tag[:-1] + ' fullCalcOnLoad="1">'
    return wbxml.replace(tag, new, 1)


# --------------------------------------------------------------------------
# Input cell-map  (friendly name -> (sheet, cell, is_text))
# --------------------------------------------------------------------------
INPUT_CELLS = {
    # --- unit program (counts drive BOTH cost and revenue; H14 = O10 = SUM(O11:O13))
    "units_1br":        (SH_INPUTS, "O11", False),
    "units_2br":        (SH_INPUTS, "O12", False),
    "units_3br":        (SH_INPUTS, "O13", False),
    "staircase_units":  (SH_INPUTS, "O15", False),
    "podium_sf":        (SH_INPUTS, "O7",  False),
    "podium_levels":    (SH_INPUTS, "O8",  False),
    "parking_stalls":   (SH_INPUTS, "O9",  False),
    "manager_units":    (SH_RENT,   "E7",  False),
    # --- market bed-mix (% of non-manager units; studio kept 0 — no modular studio)
    "mix_studio":       (SH_RENT,   "M24", False),
    "mix_1br":          (SH_RENT,   "M25", False),
    "mix_2br":          (SH_RENT,   "M26", False),
    "mix_3br":          (SH_RENT,   "M27", False),
    # --- market gross rents $/mo (from the AI comp scraper)
    "rent_studio":      (SH_RENT,   "G8",  False),
    "rent_1br":         (SH_RENT,   "G9",  False),
    "rent_2br":         (SH_RENT,   "G10", False),
    "rent_3br":         (SH_RENT,   "G11", False),
    # --- OpEx factors (PUPM = per-unit-per-month; management is % of revenue)
    "opex_insurance":   (SH_OPEX,   "D9",  False),
    "opex_management":  (SH_OPEX,   "D10", False),
    "opex_electric":    (SH_OPEX,   "D14", False),
    "opex_water_sewer": (SH_OPEX,   "D15", False),
    "opex_gas":         (SH_OPEX,   "D16", False),
    "opex_trash":       (SH_OPEX,   "D17", False),
    "opex_landscape":   (SH_OPEX,   "D18", False),
    "opex_mr_turnover": (SH_OPEX,   "D19", False),
    "opex_payroll":     (SH_OPEX,   "D20", False),
    "opex_hcid":        (SH_OPEX,   "D21", False),
    "opex_elevator":    (SH_OPEX,   "D22", False),
    "opex_legal":       (SH_OPEX,   "D23", False),
    "opex_misc":        (SH_OPEX,   "D24", False),
    "opex_reserves":    (SH_OPEX,   "D26", False),
    # --- cost
    "land_cost":        (SH_BUDGET, "G7",  False),
    "modular_1br":      (SH_BUDGET, "E14", False),
    "modular_2br":      (SH_BUDGET, "E15", False),
    "modular_3br":      (SH_BUDGET, "E16", False),
    "onsite_per_unit":  (SH_DASH,   "W18", False),
    "podium_psf":       (SH_BUDGET, "E20", False),
    # --- financing
    "exit_cap":         (SH_DASH,   "J5",  False),
    "constr_ltc":       (SH_DASH,   "J11", False),
    "constr_rate":      (SH_DASH,   "J12", False),
    "perm_ltc":         (SH_DASH,   "K11", False),
    "perm_ltv":         (SH_DASH,   "K10", False),
    "perm_rate":        (SH_DASH,   "K12", False),
    "perm_dscr":        (SH_DASH,   "K13", False),
    "hold_months":      (SH_DASH,   "W20", False),
    "rent_growth":      (SH_DASH,   "W21", False),
    # --- debt stack: senior perm sizing knobs + subordinate (soft/gap) loan
    # (subordinate rows 106-109 + D43:D45 added by build_mixedincome_template.py)
    "perm_min_dscr":    (SH_FIN,    "H11", False),  # senior sized by MIN(DSCR,LTV,LTC)
    "perm_max_ltv":     (SH_FIN,    "H14", False),
    "perm_max_ltc":     (SH_FIN,    "H16", False),
    "perm_amort":       (SH_FIN,    "H21", False),
    "perm_proceeds":    (SH_FIN,    "H19", False),  # override = fixed senior $ amount
    "sub_amount":       (SH_FIN,    "D43", False),  # subordinate loan $ (0 = none)
    "sub_rate":         (SH_FIN,    "D44", False),
    "sub_amort":        (SH_FIN,    "D45", False),  # years; 0 = interest-only/deferred
}

# Always applied for a non-LIHTC deal: zero BOTH affordable-allocation systems.
_MARKET_MODE_CELLS = {
    (SH_INPUTS, "O27"): (0, False),   # Required LI units  -> 0
    (SH_INPUTS, "O28"): (0, False),   # Required Mod units -> 0
    (SH_INPUTS, "O29"): ("No", True), # ED1/100% Affordable? -> No
    **{(SH_RENT, f"E{r}"): (0, False) for r in range(12, 20)},  # affordable rows
}

# Return outputs (friendly -> (sheet, cell)).
HEADLINE = {
    "Levered IRR":            (SH_DASH, "B5"),
    "Equity Multiple":        (SH_DASH, "B6"),
    "Cash-on-Cash":           (SH_DASH, "B7"),
    "Untrended Yield-on-Cost": (SH_DASH, "B8"),
    "Total Profit":           (SH_DASH, "B9"),
    "Total Dev Cost":         (SH_DASH, "B13"),
    "Price per Unit":         (SH_DASH, "B14"),
    "Equity Required":        (SH_DASH, "E13"),
    "Debt":                   (SH_DASH, "E14"),
    "Effective Gross Income": (SH_OPEX, "G35"),
    "Operating Expenses":     (SH_OPEX, "G36"),
    "Net Operating Income":   (SH_OPEX, "G37"),
}


# --------------------------------------------------------------------------
# assemble friendly inputs -> {(sheet, addr): (value, is_text)}
# --------------------------------------------------------------------------
def split_inputs(friendly: dict, market_mode: bool = True) -> dict:
    """Map a friendly-name dict to {(sheet, addr): (value, is_text)}, plus the
    fixed market-mode neutralisers. Unknown names raise (typo guard).

    market_mode=True zeroes BOTH affordable systems (pure-market deals). Set
    False for mixed-income builds that drive the restricted rent-roll rows
    directly (build_mixed_income_inputs supplies its own neutralisers)."""
    cells = dict(_MARKET_MODE_CELLS) if market_mode else {}
    for name, val in (friendly or {}).items():
        if name not in INPUT_CELLS:
            raise KeyError(f"unknown non-LIHTC input {name!r}")
        sheet, addr, is_text = INPUT_CELLS[name]
        cells[(sheet, addr)] = (val, is_text)
    return cells


# --------------------------------------------------------------------------
# recalc: patch (multi-sheet) -> LibreOffice -> read
# --------------------------------------------------------------------------
def recalc(friendly: dict = None, cells: dict = None, read=None, timeout=120):
    """Patch input cells, recalc with LibreOffice, return {friendly_out: value}.

    Pass either `friendly` (name->value) or a pre-split `cells`
    ({(sheet,addr):(value,is_text)}). `read` defaults to HEADLINE.
    """
    if cells is None:
        cells = split_inputs(friendly)
    read = dict(read) if read else dict(HEADLINE)  # friendly_out -> (sheet, addr)

    # group patches by sheet
    by_sheet: dict[str, dict] = {}
    for (sheet, addr), (val, is_text) in cells.items():
        by_sheet.setdefault(sheet, {})[addr] = (val, is_text)

    with _RECALC_SEM:
        profile = _make_profile()
        work = tempfile.mkdtemp(prefix="nonlihtc_calc_")
        try:
            clean = os.path.join(work, "model.xlsx")
            with zipfile.ZipFile(MODEL_PATH, "r") as zin:
                targets = {sh: _sheet_target(zin, sh) for sh in by_sheet}
                patched = {}
                for sh, sheet_cells in by_sheet.items():
                    xml = zin.read(targets[sh]).decode("utf-8")
                    for addr, (val, is_text) in sheet_cells.items():
                        xml = _set_cell_xml(xml, addr, val, is_text)
                    patched[targets[sh]] = xml.encode("utf-8")
                with zipfile.ZipFile(clean, "w", zipfile.ZIP_DEFLATED) as zout:
                    for it in zin.infolist():
                        data = patched.get(it.filename, zin.read(it.filename))
                        zout.writestr(it, data)

            outdir = os.path.join(work, "out")
            os.makedirs(outdir, exist_ok=True)
            proc = subprocess.run(
                [_soffice_bin(), "--headless", "--nologo", "--nofirststartwizard",
                 f"-env:UserInstallation=file://{profile}",
                 "--convert-to", "xlsx", "--outdir", outdir, clean],
                capture_output=True, timeout=timeout,
            )
            out_xlsx = os.path.join(outdir, "model.xlsx")
            if not os.path.exists(out_xlsx):
                raise RuntimeError(
                    "LibreOffice recalc produced no output. stderr=%r"
                    % proc.stderr.decode("utf-8", "replace")[:500]
                )
            wb = openpyxl.load_workbook(out_xlsx, data_only=True)
            return {name: wb[sheet][addr].value for name, (sheet, addr) in read.items()}
        finally:
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(profile, ignore_errors=True)


def build_download(friendly: dict = None, tolerant: bool = False,
                   cells: dict = None) -> bytes:
    """Return a patched .xlsx (formulas intact, fullCalcOnLoad=1 so Excel recalcs
    on open). For the analyst-facing downloadable model. Pass either `friendly`
    (market mode) or a pre-split `cells` dict (e.g. mixed-income)."""
    if cells is None:
        cells = split_inputs(friendly)
    by_sheet: dict[str, dict] = {}
    for (sheet, addr), (val, is_text) in cells.items():
        by_sheet.setdefault(sheet, {})[addr] = (val, is_text)
    with zipfile.ZipFile(MODEL_PATH, "r") as zin:
        targets = {sh: _sheet_target(zin, sh) for sh in by_sheet}
        patched = {}
        for sh, sheet_cells in by_sheet.items():
            xml = zin.read(targets[sh]).decode("utf-8")
            for addr, (val, is_text) in sheet_cells.items():
                try:
                    xml = _set_cell_xml(xml, addr, val, is_text)
                except ValueError:
                    if not tolerant:
                        raise
            patched[targets[sh]] = xml.encode("utf-8")
        wbxml = _force_full_recalc(zin.read("xl/workbook.xml").decode("utf-8"))
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                if it.filename == "xl/workbook.xml":
                    data = wbxml.encode("utf-8")
                else:
                    data = patched.get(it.filename, zin.read(it.filename))
                zout.writestr(it, data)
        return buf.getvalue()


# --------------------------------------------------------------------------
# DD -> model bridge
# --------------------------------------------------------------------------
# Default OpEx factors (PUPM) derived from the v5.0.7 5300 Crenshaw operating
# statement (PUPY / 12); overridable per-deal by a T-12.
DEFAULT_OPEX_PUPM = {
    "opex_insurance": round(400 / 12, 2),
    "opex_management": 0.05,           # % of revenue
    "opex_mr_turnover": round(553 / 12, 2),
    "opex_payroll": round(1475 / 12, 2),
    "opex_legal": round(60 / 12, 2),
    "opex_hcid": round(19 / 12, 2),
    "opex_reserves": round(240 / 12, 2),
}

DEFAULT_FINANCING = {
    "exit_cap": 0.05, "perm_rate": 0.0575, "perm_ltv": 0.70,
    "perm_dscr": 1.15, "constr_rate": 0.064,
}


def _bed_lookup(d: dict, bed: int, default=0):
    """Read a per-bed value tolerant of every key convention the callers use:
    the engine's own "Nbr" strings, plus the numeric keys the review form and the
    AI comp scraper emit (int 1 / str "1" / "1BR" / "studio"|"0"). Bed 0 = studio."""
    if not d:
        return default
    aliases = ([ "studio", "0", 0, "0br" ] if bed == 0
               else [ f"{bed}br", f"{bed}BR", str(bed), bed, f"{bed}b" ])
    for k in aliases:
        if k in d and d[k] is not None:
            return d[k]
    return default


def loans_to_friendly(loans: list):
    """Map an ordered loan stack to engine inputs + a summary.

    loans[0] = SENIOR perm (sized in-model by MIN(DSCR,LTV,LTC); basis picks the
    binding constraint, or basis='fixed' overrides the proceeds). loans[1] =
    SUBORDINATE soft/gap loan (a fixed $ amount with rate + amort; amort 0 =
    interest-only/deferred). Each loan: {label, basis, value, rate, amort, io}.
    Only the senior + ONE subordinate flow through the workbook's Monthly CF
    (Levered IRR & Equity Multiple). 3rd+ tranches are returned in the summary
    but NOT modelled (no workbook slot) — caller should surface that.
    """
    friendly, summary, unmodelled = {}, [], []
    for i, ln in enumerate(loans or []):
        basis = (ln.get("basis") or "").lower()
        val, rate = ln.get("value"), ln.get("rate")
        amort = 0 if ln.get("io") else (ln.get("amort") or 0)
        if i == 0:  # senior
            if rate is not None:
                friendly["perm_rate"] = rate
            if amort:
                friendly["perm_amort"] = amort
            if val is not None:
                if basis == "dscr":
                    friendly["perm_min_dscr"] = val
                elif basis == "ltv":
                    friendly["perm_max_ltv"] = val
                elif basis == "ltc":
                    friendly["perm_max_ltc"] = val
                elif basis == "fixed":
                    friendly["perm_proceeds"] = val
            summary.append({"role": "senior", "label": ln.get("label", "Senior Perm"),
                            "basis": basis, "value": val, "rate": rate, "amort": amort})
        elif i == 1:  # subordinate / soft-gap (fixed $)
            friendly["sub_amount"] = val or 0
            friendly["sub_rate"] = rate or 0
            friendly["sub_amort"] = amort
            summary.append({"role": "subordinate", "label": ln.get("label", "Soft/Gap"),
                            "amount": val, "rate": rate, "amort": amort,
                            "io": amort == 0})
        else:
            unmodelled.append(ln.get("label", f"Loan {i + 1}"))
    return friendly, {"loans": summary, "unmodelled": unmodelled}


def build_market_inputs(*, units_by_bed: dict, rents_by_bed: dict,
                        land_cost: float, opex: dict = None,
                        financing: dict = None, manager_units: int = 1,
                        loans: list = None) -> dict:
    """Assemble a friendly-input dict for a market/non-LIHTC deal.

    units_by_bed / rents_by_bed accept any bed-key convention (1 | "1" | "1br" |
    "1BR"; studio = 0 | "studio"). Modular cost book has no studio product, so
    studio UNITS are ignored on the cost side (revenue studio row stays at 0).
    """
    u1 = int(_bed_lookup(units_by_bed, 1, 0))
    u2 = int(_bed_lookup(units_by_bed, 2, 0))
    u3 = int(_bed_lookup(units_by_bed, 3, 0))
    total = u1 + u2 + u3
    market = max(total - manager_units, 1)  # manager carved out of revenue rows

    f = {
        "units_1br": u1, "units_2br": u2, "units_3br": u3,
        "manager_units": manager_units,
        # revenue bed-mix derived from the counts (consistent with cost side)
        "mix_studio": 0.0,
        "mix_1br": round(max(u1 - manager_units, 0) / market, 4),
        "mix_2br": round(u2 / market, 4),
        "mix_3br": round(u3 / market, 4),
        "rent_studio": _bed_lookup(rents_by_bed, 0, 0),
        "rent_1br": _bed_lookup(rents_by_bed, 1, 0),
        "rent_2br": _bed_lookup(rents_by_bed, 2, 0),
        "rent_3br": _bed_lookup(rents_by_bed, 3, 0),
        "land_cost": land_cost,
    }
    f.update(DEFAULT_OPEX_PUPM)
    f.update(opex or {})
    f.update(DEFAULT_FINANCING)
    f.update(financing or {})
    if loans:
        lf, _ = loans_to_friendly(loans)
        f.update(lf)
    return f


def _parse_num(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"-?\d[\d,]*\.?\d*", str(s).replace("$", ""))
    return float(m.group().replace(",", "")) if m else None


def build_from_dd(dd: dict, *, units_by_bed: dict, rents_by_bed: dict,
                  opex: dict = None, financing: dict = None,
                  land_cost: float = None, deal_name: str = None,
                  loans: list = None) -> bytes:
    """Build a downloadable non-LIHTC model from DD facts + a unit program +
    comp rents (+ optional T-12 OpEx / financing / loan-stack overrides).

    DD supplies the land/acquisition price (if present); the unit program and
    rents come from the review step + comp scraper. Returns the .xlsx bytes.
    """
    if land_cost is None:
        land_cost = _parse_num(dd.get("acquisition_price")) or _parse_num(dd.get("land_cost"))
    if land_cost is None:
        # fall back to a placeholder so the model still computes; analyst overrides
        land_cost = 0
    friendly = build_market_inputs(
        units_by_bed=units_by_bed, rents_by_bed=rents_by_bed,
        land_cost=land_cost, opex=opex, financing=financing, loans=loans,
    )
    return build_download(friendly, tolerant=True)


# --------------------------------------------------------------------------
# MIXED-INCOME (AMI allocation)  — Workstream B of NONLIHTC_MIXED_INCOME_SPEC.md
# --------------------------------------------------------------------------
import json as _json

# Restricted tier blocks in (Z+) Rent Roll: tier slot -> {bed: row}.
# Slots 0/1 are native (12-15 "80% AMI", 16-19 "110% AMI"); slot 2 (46-49) is
# the tier-C block added by build_mixedincome_template.py. bed 0=studio,1,2,3.
TIER_ROWS = [
    {0: 12, 1: 13, 2: 14, 3: 15},
    {0: 16, 1: 17, 2: 18, 3: 19},
    {0: 46, 1: 47, 2: 48, 3: 49},
]
MAX_TIERS = len(TIER_ROWS)
# market rent-roll rows by bed (counts E, rents G); 0=studio
_MKT_COUNT = {0: "E8", 1: "E9", 2: "E10", 3: "E11"}
_BED_LABEL = {0: "Studio", 1: "1BR", 2: "2BR", 3: "3BR"}

_STATIC = os.path.join(os.path.dirname(HERE), "web", "static") \
    if os.path.basename(HERE) != "web" else os.path.join(HERE, "static")
_HUD = None
_ZIP2CO = None


def _load_ami_data():
    global _HUD, _ZIP2CO
    if _HUD is None:
        with open(os.path.join(_STATIC, "hud_rents.json")) as f:
            _HUD = _json.load(f)["counties"]
        with open(os.path.join(_STATIC, "ca_zip_county.json")) as f:
            _ZIP2CO = _json.load(f)["zipToCounty"]
    return _HUD, _ZIP2CO


def resolve_county_fips(dd: dict) -> str | None:
    """Resolve a county FIPS for AMI-rent lookup: ZIP from the DD address first
    (most precise), else a county-name match against the HUD county list."""
    hud, zip2co = _load_ami_data()
    addr = dd.get("address") or dd.get("matched_address") or ""
    m = re.search(r"\b(9\d{4})(?:-\d{4})?\b", str(addr))
    if m and m.group(1) in zip2co:
        return zip2co[m.group(1)]
    ctext = re.sub(r"\bcounty\b|,.*$", "", (dd.get("county") or ""), flags=re.I).strip().lower()
    if ctext:
        for fips, rec in hud.items():
            short = rec["county"].lower().split(" county")[0].strip()
            if short and (ctext == short or ctext.startswith(short) or short in ctext):
                return fips
    return None


def ami_rent(fips: str, ami: int, bed: int, utility_allowance: float = 0) -> float | None:
    """Gross CTCAC/MTSP cap for (county, AMI tier, bedroom), net of any utility
    allowance. ami is a tier present in hud_rents (20/30/35/40/45/50/55/60/70/
    80/100/110). bed 0=studio. Returns None if county/tier/bed missing."""
    hud, _ = _load_ami_data()
    rec = hud.get(str(fips))
    if not rec:
        return None
    tier = rec["rents"].get(str(int(ami)))
    if not tier:
        return None
    bedkey = "studio" if bed == 0 else f"br{bed}"
    gross = tier.get(bedkey)
    return None if gross is None else max(0.0, gross - (utility_allowance or 0))


def _largest_remainder(total: int, weights: list) -> list:
    """Apportion an integer `total` across buckets ∝ weights, summing EXACTLY
    to total (largest-remainder method). All-zero weights -> all zero."""
    tw = sum(weights)
    if total <= 0 or tw <= 0:
        return [0] * len(weights)
    raw = [total * w / tw for w in weights]
    base = [int(x) for x in raw]
    rem = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in range(rem):
        base[order[i]] += 1
    return base


def build_mixed_income_inputs(*, units_by_bed: dict, ami_allocation: list,
                              county_fips: str, market_rents: dict = None,
                              land_cost: float, opex: dict = None,
                              financing: dict = None, manager_units: int = 1,
                              utility_allowance: float = 0, loans: list = None):
    """Assemble a pre-split `cells` dict for a MIXED-INCOME (AMI) deal, plus a
    summary for the UI.

    `ami_allocation` = [{"pct": 0.20, "ami": 50}, ...] (≤ MAX_TIERS entries; pct
    is share of total units; remainder = market). Restricted units are NETTED out
    of the market allocation so the rent-roll total stays == the unit program
    (Inputs!H14) — otherwise the model's blended-rent formula (÷H14) over-scales.

    Beds: 1/2/3 only (modular has no studio product); studio rows stay 0.
    Returns (cells, summary).
    """
    if county_fips is None:
        raise ValueError("mixed-income build needs a county FIPS for AMI rents "
                         "(resolve_county_fips returned None — pass it explicitly)")
    tiers = [t for t in (ami_allocation or []) if (t.get("pct") or 0) > 0]
    if len(tiers) > MAX_TIERS:
        raise ValueError(f"engine supports {MAX_TIERS} AMI tiers; got {len(tiers)} "
                         "(add another tier block to the workbook)")
    if sum(t["pct"] for t in tiers) > 1.0 + 1e-9:
        raise ValueError("AMI tier percentages exceed 100% of units")

    beds = [1, 2, 3]
    tot = {b: int(_bed_lookup(units_by_bed, b, 0)) for b in beds}
    N = sum(tot.values())
    if N <= 0:
        raise ValueError("mixed-income build needs a unit program (units_by_bed)")
    mgr = max(0, int(manager_units))
    # manager is a 1BR carved from the program (matches the engine's Manager 1BR row)
    revenue = {b: tot[b] - (mgr if b == 1 else 0) for b in beds}
    R = sum(revenue.values())

    # tier building-wide totals; clamp the sum to revenue units, plug = market
    tier_tot = [round(N * t["pct"]) for t in tiers]
    while sum(tier_tot) > R and any(tier_tot):
        tier_tot[tier_tot.index(max(tier_tot))] -= 1

    # distribute each tier across beds ∝ revenue mix; market = per-bed residual
    weights = [revenue[b] for b in beds]
    tier_by_bed = [dict(zip(beds, _largest_remainder(tt, weights))) for tt in tier_tot]
    market_by_bed = {}
    for b in beds:
        used = sum(tb[b] for tb in tier_by_bed)
        market_by_bed[b] = max(0, revenue[b] - used)
        # if tiers over-filled this bed, claw back from the largest tier
        over = used - revenue[b]
        while over > 0:
            j = max(range(len(tier_by_bed)), key=lambda k: tier_by_bed[k][b])
            if tier_by_bed[j][b] <= 0:
                break
            tier_by_bed[j][b] -= 1
            over -= 1

    # ---- assemble cells -------------------------------------------------
    friendly = {
        "units_1br": tot[1], "units_2br": tot[2], "units_3br": tot[3],  # O11:O13 = H14
        "manager_units": mgr,
        "rent_studio": 0,
        "rent_1br": _bed_lookup(market_rents or {}, 1, 0),
        "rent_2br": _bed_lookup(market_rents or {}, 2, 0),
        "rent_3br": _bed_lookup(market_rents or {}, 3, 0),
        "land_cost": land_cost,
    }
    friendly.update(DEFAULT_OPEX_PUPM)
    friendly.update(opex or {})
    friendly.update(DEFAULT_FINANCING)
    friendly.update(financing or {})
    loan_summary = None
    if loans:
        lf, loan_summary = loans_to_friendly(loans)
        friendly.update(lf)
    cells = split_inputs(friendly, market_mode=False)

    # mixed-mode neutralisers: native set-aside off, not 100%-affordable flag
    cells[(SH_INPUTS, "O27")] = (0, False)
    cells[(SH_INPUTS, "O28")] = (0, False)
    cells[(SH_INPUTS, "O29")] = ("No", True)
    # market counts as literals (studio 0): the residual after restricted tiers
    cells[(SH_RENT, "E8")] = (0, False)
    cells[(SH_RENT, "E9")] = (market_by_bed[1], False)
    cells[(SH_RENT, "E10")] = (market_by_bed[2], False)
    cells[(SH_RENT, "E11")] = (market_by_bed[3], False)

    summary_tiers = []
    for slot in range(MAX_TIERS):
        rows = TIER_ROWS[slot]
        if slot < len(tiers):
            ami = int(tiers[slot]["ami"])
            tb = tier_by_bed[slot]
            rents = {}
            for bed in (0, 1, 2, 3):
                cnt = tb.get(bed, 0)
                cells[(SH_RENT, f"E{rows[bed]}")] = (cnt, False)
                if cnt > 0:
                    rent = ami_rent(county_fips, ami, bed, utility_allowance)
                    if rent is None:
                        raise ValueError(f"no AMI rent for county {county_fips} "
                                         f"tier {ami}% bed {bed}")
                    cells[(SH_RENT, f"I{rows[bed]}")] = (rent, False)
                    cells[(SH_RENT, f"C{rows[bed]}")] = (
                        f"Restricted {ami}% AMI {_BED_LABEL[bed]}", True)
                    rents[bed] = rent
            summary_tiers.append({"ami": ami, "pct": tiers[slot]["pct"],
                                  "units": sum(tb.values()), "by_bed": tb,
                                  "rents": rents})
        else:  # unused tier block -> zero its counts
            for bed in (0, 1, 2, 3):
                cells[(SH_RENT, f"E{rows[bed]}")] = (0, False)

    summary = {
        "county_fips": county_fips, "total_units": N, "manager_units": mgr,
        "restricted_units": sum(t["units"] for t in summary_tiers),
        "market_units": sum(market_by_bed.values()),
        "market_by_bed": market_by_bed, "tiers": summary_tiers,
        "loans": loan_summary,
    }
    return cells, summary


def build_mixed_from_dd(dd: dict, *, units_by_bed: dict, ami_allocation: list,
                        market_rents: dict = None, opex: dict = None,
                        financing: dict = None, land_cost: float = None,
                        deal_name: str = None, county_fips: str = None,
                        utility_allowance: float = 0, loans: list = None):
    """Mixed-income downloadable model from DD facts + a unit program + an AMI
    allocation. Returns (xlsx_bytes, summary)."""
    if land_cost is None:
        land_cost = _parse_num(dd.get("acquisition_price")) or _parse_num(dd.get("land_cost")) or 0
    if county_fips is None:
        county_fips = resolve_county_fips(dd)
    cells, summary = build_mixed_income_inputs(
        units_by_bed=units_by_bed, ami_allocation=ami_allocation,
        county_fips=county_fips, market_rents=market_rents, land_cost=land_cost,
        opex=opex, financing=financing, utility_allowance=utility_allowance,
        loans=loans,
    )
    return build_download(cells=cells, tolerant=True), summary


def selftest():
    """Reproduce the NONLIHTC_ENGINE_SPEC.md proof (50-unit market deal)."""
    f = build_market_inputs(
        units_by_bed={"1br": 45, "2br": 5, "3br": 0},
        rents_by_bed={"1br": 2400, "2br": 3000},
        land_cost=5_000_000,
        opex={"opex_insurance": 33.33, "opex_mr_turnover": 46.08,
              "opex_payroll": 122.92, "opex_reserves": 20.0},
        financing={"exit_cap": 0.05, "perm_rate": 0.0575},
    )
    # override the derived mix to match the proof exactly (90/10)
    f.update({"mix_1br": 0.90, "mix_2br": 0.10, "mix_3br": 0.0,
              "podium_sf": 3500})
    return recalc(f)


if __name__ == "__main__":
    import json
    out = selftest()
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v)
                      for k, v in out.items()}, indent=2))
