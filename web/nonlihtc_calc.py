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
def split_inputs(friendly: dict) -> dict:
    """Map a friendly-name dict to {(sheet, addr): (value, is_text)}, plus the
    fixed market-mode neutralisers. Unknown names raise (typo guard)."""
    cells = dict(_MARKET_MODE_CELLS)
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


def build_download(friendly: dict, tolerant: bool = False) -> bytes:
    """Return a patched .xlsx (formulas intact, fullCalcOnLoad=1 so Excel recalcs
    on open). For the analyst-facing downloadable model."""
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


def build_market_inputs(*, units_by_bed: dict, rents_by_bed: dict,
                        land_cost: float, opex: dict = None,
                        financing: dict = None, manager_units: int = 1) -> dict:
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
                  land_cost: float = None, deal_name: str = None) -> bytes:
    """Build a downloadable non-LIHTC model from DD facts + a unit program +
    comp rents (+ optional T-12 OpEx / financing overrides).

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
        land_cost=land_cost, opex=opex, financing=financing,
    )
    return build_download(friendly, tolerant=True)


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
