#!/usr/bin/env python3
"""
build_mixedincome_template.py — Workstream A of NONLIHTC_MIXED_INCOME_SPEC.md.

Appends a THIRD restricted tier block (rows 46-49 = 0/1/2/3BR) to the non-LIHTC
engine's `(Z+) Rent Roll`, so a mixed-income deal can carry three AMI tiers
(default 50 / 80 / 70%) instead of the workbook's two native blocks
(rows 12-15 "80% AMI", 16-19 "110% AMI").

Method — RAW XML surgery on the Rent Roll sheet ONLY (not openpyxl):
  * openpyxl round-trips the whole package and reformats workbook rels / cell XML,
    which breaks `nonlihtc_calc`'s regex-based runtime patcher. Raw surgery keeps
    every other part byte-identical, so the engine's _sheet_target / _set_cell_xml
    keep working.
  * The cloned cells must be DE-SHARED: the template rows use shared formulas
    (<f t="shared" si=N/>) whose master `ref` ranges (e.g. G12:G19) don't cover
    rows 46-49, so we emit explicit formula text instead.

APPEND, don't insert: cross-sheet refs target Rent Roll rows 20/24/36, so a
mid-sheet insert would ripple across Inputs/OpEx/Financing/Monthly CF. Rows
46-49 are beyond the current used range (max row 45) — no collision, no shift.

Tier-C `E` (count) and `I` (rent) default to 0, so an unpatched / market-mode
build is output-identical to the original (recalc-parity guard below).

Run:  python3 web/models/build_mixedincome_template.py
      python3 web/models/build_mixedincome_template.py --verify   # parity + smoke
Produces:  NonLIHTC_engine_template.xlsx (in place; original kept as *.orig.xlsx)
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "NonLIHTC_engine_template.xlsx")
BACKUP = os.path.join(HERE, "NonLIHTC_engine_template.orig.xlsx")
SHEET6 = "xl/worksheets/sheet6.xml"  # (Z+) Rent Roll

DST_ROWS = [46, 47, 48, 49]                  # tier-C block (0/1/2/3BR), empty band
BED_LABEL = {0: "0BR", 1: "1BR", 2: "2BR", 3: "3BR"}
D_CODE = {0: 1, 1: 0, 2: 2, 3: 3}            # the template's per-bed "D" code
O_SRC = {0: 8, 1: 9, 2: 10, 3: 11}           # avg-SF source row by bed
# per-column style index, copied from the row-12 template
STY = {"B": 189, "C": 354, "D": 340, "E": 340, "F": 342, "G": 342, "H": 342,
       "I": 342, "J": 343, "K": 342, "L": 342, "M": 343, "N": 343, "O": 340,
       "P": 340, "Q": 342, "R": 340, "S": 340, "T": 191, "U": 190}


def _cell(col: str, row: int, formula: str | None, cached="0") -> str:
    s = STY[col]
    if formula is None:  # framing cell, no content
        return f'<c r="{col}{row}" s="{s}"/>'
    return f'<c r="{col}{row}" s="{s}"><f>{formula}</f><v>{cached}</v></c>'


def _tier_c_row(row: int, bed: int) -> str:
    d = row
    o = O_SRC[bed]
    cells = [
        _cell("B", d, None),
        f'<c r="C{d}" s="{STY["C"]}" t="inlineStr"><is><t>Restricted Tier C {BED_LABEL[bed]}</t></is></c>',
        _cell("D", d, f"IFERROR({D_CODE[bed]},0)", cached=str(D_CODE[bed])),
        _cell("E", d, "IFERROR(0,0)"),               # unit count — patch target
        _cell("F", d, "IFERROR(0,0)"),
        _cell("G", d, "IFERROR(0,0)"),
        _cell("H", d, f"IFERROR(G{d}*E{d},0)"),
        _cell("I", d, "IFERROR(0,0)"),               # restricted rent — patch target
        _cell("J", d, "IFERROR(100/100,0)", cached="1"),
        _cell("K", d, f"IFERROR((I{d}-G{d})*J{d}+G{d},0)"),
        _cell("L", d, f"IFERROR(K{d}*E{d},0)"),
        _cell("M", d, "IFERROR(+Inputs!$L$7,0)", cached="2.5E-2"),
        _cell("N", d, "IFERROR(+Inputs!$L$6,0)", cached="0.03"),
        _cell("O", d, f"IFERROR(O{o},0)"),
        _cell("P", d, f"IFERROR(O{d}*E{d},0)"),
        _cell("Q", d, f"IFERROR(K{d}/O{d},0)"),
        _cell("R", d, "IFERROR(100,0)", cached="100"),
        _cell("S", d, f"IFERROR(R{d}*E{d},0)"),
        _cell("T", d, None),
        _cell("U", d, None),
    ]
    return (f'<row r="{d}" spans="2:21" ht="16.5" customHeight="1" '
            f'x14ac:dyDescent="0.25">' + "".join(cells) + "</row>")


# row-20 / unit-mix / restricted-stat aggregates, extended to include 46:49
AGG = {
    "D20": "IFERROR(SUMPRODUCT(D7:D19,E7:E19)+SUMPRODUCT(D46:D49,E46:E49),0)",
    "E20": "IFERROR(SUM(E7:E19,E46:E49),0)",
    "F20": "IFERROR((SUMPRODUCT(E7:E19,F7:F19)+SUMPRODUCT(E46:E49,F46:F49))/E20,0)",
    "G20": "IFERROR((SUMPRODUCT(E7:E19,G7:G19)+SUMPRODUCT(E46:E49,G46:G49))/E20,0)",
    "H20": "IFERROR(SUM(H7:H19,H46:H49),0)",
    "I20": "IFERROR((SUMPRODUCT($E$7:$E$19,I7:I19)+SUMPRODUCT($E$46:$E$49,I46:I49))/Inputs!H14,0)",
    "J20": "IFERROR((SUMPRODUCT(E7:E19,J7:J19)+SUMPRODUCT(E46:E49,J46:J49))/E20,0)",
    "K20": "IFERROR((SUMPRODUCT($E$7:$E$19,K7:K19)+SUMPRODUCT($E$46:$E$49,K46:K49))/Inputs!H14,0)",
    "M20": "IFERROR((SUMPRODUCT(M7:M19,$L$7:$L$19)+SUMPRODUCT(M46:M49,L46:L49))/$L$20,0)",
    "N20": "IFERROR((SUMPRODUCT(N7:N19,$L$7:$L$19)+SUMPRODUCT(N46:N49,L46:L49))/$L$20,0)",
    "P20": "IFERROR(SUM(P7:P19,P46:P49),0)",
    "S20": "IFERROR(SUM(S7:S19,S46:S49),0)",
    "N24": "IFERROR(+E8+E12+E16+E46,0)",
    "N25": "IFERROR(+E9+E13+E17+E7+E47,0)",
    "N26": "IFERROR(+E10+E14+E18+E48,0)",
    "N27": "IFERROR(+E11+E15+E19+E49,0)",
    "R28": "IFERROR(+SUM(H12:H19,H46:H49)/SUM(E12:E19,E46:E49),0)",
    "S28": "IFERROR(+SUM(L12:L19,L46:L49)/SUM(E12:E19,E46:E49),0)",
    "T28": "IFERROR(+SUM(L12:L19,L46:L49)/(SUM(P12:P19,P46:P49)),0)",
    "R36": "IFERROR(+SUM(H12:H19,H46:H49)/SUM(E12:E19,E46:E49)*Inputs!$F$34,0)",
    "S36": "IFERROR(+SUM(L12:L19,L46:L49)/SUM(E12:E19,E46:E49)*Inputs!$F$34,0)",
}


def _replace_cell_formula(xml: str, addr: str, formula: str) -> str:
    """Replace cell `addr`'s formula, preserving its style attr; drop cached <v>
    (recalc rebuilds). Raises if the cell isn't present."""
    m = re.search(r'<c r="%s"([^>]*?)>.*?</c>' % re.escape(addr), xml, re.S)
    if not m:
        raise ValueError(f"aggregate cell {addr} not found")
    attrs = m.group(1)
    sm = re.search(r's="(\d+)"', attrs)
    s = f' s="{sm.group(1)}"' if sm else ""
    new = f'<c r="{addr}"{s}><f>{formula}</f><v>0</v></c>'
    return xml[:m.start()] + new + xml[m.end():]


def transform_sheet6(xml: str) -> str:
    # 1) append the four tier-C rows before </sheetData>
    rows = "".join(_tier_c_row(r, b) for b, r in enumerate(DST_ROWS))
    xml = xml.replace("</sheetData>", rows + "</sheetData>", 1)
    # 2) extend dimension
    xml = re.sub(r'<dimension ref="B2:U45"/>', '<dimension ref="B2:U49"/>', xml, count=1)
    # 3) extend aggregates
    for addr, formula in AGG.items():
        xml = _replace_cell_formula(xml, addr, formula)
    return xml


# --------------------------------------------------------------------------
# FEATURE 2 — subordinate (soft/gap) PERMANENT loan
# Adds a 2nd perm loan whose proceeds enter at refi and whose debt service hits
# the levered cash flow, so Levered IRR/CoC faithfully reflect the added leverage.
#   * params on (Z+) Financing: D43 amount, D44 rate, D45 amort-years (0 = IO/deferred)
#   * 4 new (Z+) Monthly CF rows 106-109 (proceeds / interest / principal / payoff),
#     mirroring the senior perm rows 95-98 but reading the D43:D45 params
#   * row-100 (levered CF) shared masters get the 4 new rows appended
# Amount D43 defaults to 0 -> every new cell computes 0 -> output-identical to the
# original (recalc-parity guard). The senior path is untouched.
# --------------------------------------------------------------------------
SHEET5 = "xl/worksheets/sheet5.xml"  # (Z+) Financing
SHEET7 = "xl/worksheets/sheet7.xml"  # (Z+) Monthly CF
SUB_ROWS = {"proceeds": 106, "interest": 107, "principal": 108, "payoff": 109}
# row-100 shared masters: (master col, si)
CF100_MASTERS = [("F", 134), ("AL", 135), ("BR", 136), ("CX", 137)]


def _xesc(f: str) -> str:
    return f.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def add_sub_loan_financing(s5: str) -> str:
    """Append the subordinate-loan param cells (amount/rate/amort, default 0)."""
    rows = (
        '<row r="43" spans="2:12" x14ac:dyDescent="0.25">'
        '<c r="C43" s="248" t="inlineStr"><is><t>Subordinate / Soft Debt — Amount</t></is></c>'
        '<c r="D43" s="338"><v>0</v></c></row>'
        '<row r="44" spans="2:12" x14ac:dyDescent="0.25">'
        '<c r="C44" s="248" t="inlineStr"><is><t>Sub Rate</t></is></c>'
        '<c r="D44" s="338"><v>0</v></c></row>'
        '<row r="45" spans="2:12" x14ac:dyDescent="0.25">'
        '<c r="C45" s="248" t="inlineStr"><is><t>Sub Amort (yrs; 0 = IO/deferred)</t></is></c>'
        '<c r="D45" s="338"><v>0</v></c></row>'
    )
    s5 = s5.replace("</sheetData>", rows + "</sheetData>", 1)
    return re.sub(r'<dimension ref="B2:L42"/>', '<dimension ref="B2:L45"/>', s5, count=1)


# explicit per-column sub-loan formulas (no leading '='; XML-escaped at emit).
# FIN = the sub-loan param cells; mirror the senior perm rows 95-98 exactly.
_FIN_AMT = "'(Z+) Financing'!$D$43"
_FIN_RT = "'(Z+) Financing'!$D$44"
_FIN_AM = "'(Z+) Financing'!$D$45"
_RM = _FIN_RT + "*365.25/360/12"  # monthly rate


def _sub_formula(kind: str, c: str) -> str:
    if kind == "proceeds":
        return f"({c}4=refinance_date)*({_FIN_AMT})"
    if kind == "interest":
        return (f"IF(AND({c}4>refinance_date,{c}4<=sale_month),"
                f"IF({_FIN_AM}>0,"
                f"IPMT({_RM},ROUND(DAYS360(refinance_date,{c}4)/30,0),{_FIN_AM}*12,{_FIN_AMT}),"
                f"-{_FIN_AMT}*{_RM}),0)")
    if kind == "principal":
        return (f"IF(AND({c}4>refinance_date,{c}4<=sale_month),"
                f"IF({_FIN_AM}>0,"
                f"PMT({_RM},{_FIN_AM}*12,{_FIN_AMT})-{c}107,0),0)")
    if kind == "payoff":
        return f"({c}4=sale_month)*(-{_FIN_AMT}-SUM($F$108:{c}108))"
    raise ValueError(kind)


def add_sub_loan_cf(s7: str) -> str:
    from openpyxl.utils import get_column_letter, column_index_from_string
    # per-column style from senior row 95 (default 441 for cash-flow cells)
    r95 = re.search(r'<row r="95"[ >].*?</row>', s7, re.S).group(0)
    sty = dict(re.findall(r'<c r="([A-Z]+)95"(?: s="(\d+)")?', r95))
    cols = [get_column_letter(i) for i in range(column_index_from_string("F"),
                                                column_index_from_string("DU") + 1)]

    # 1) build the 4 new rows (explicit formulas over F..DU + a label in col D)
    new_rows = ""
    for kind, rnum in SUB_ROWS.items():
        label = {"proceeds": "Sub Loan Proceeds", "interest": "Sub Interest",
                 "principal": "Sub Principal", "payoff": "Sub Payoff"}[kind]
        cells = [f'<c r="D{rnum}" s="387" t="inlineStr"><is><t>{label}</t></is></c>']
        for c in cols:
            s = sty.get(c, "441")
            cells.append(f'<c r="{c}{rnum}" s="{s}"><f>{_xesc(_sub_formula(kind, c))}</f><v>0</v></c>')
        new_rows += (f'<row r="{rnum}" spans="1:125" x14ac:dyDescent="0.25">'
                     + "".join(cells) + "</row>")
    s7 = s7.replace("</sheetData>", new_rows + "</sheetData>", 1)

    # 2) extend the 4 levered-CF (row 100) shared masters; refs translate per column
    for col, si in CF100_MASTERS:
        add = f"+{col}106+{col}107+{col}108+{col}109"
        pat = re.compile(r'(<f t="shared" ref="[^"]*" si="%d">)([^<]*)(</f>)' % si)
        m = pat.search(s7)
        if not m:
            raise ValueError(f"row-100 master si={si} not found")
        s7 = s7[:m.start()] + m.group(1) + m.group(2) + add + m.group(3) + s7[m.end():]

    # 3) extend dimension to row 109
    return re.sub(r'<dimension ref="A1:DU104"/>', '<dimension ref="A1:DU109"/>', s7, count=1)


def build() -> None:
    if not os.path.exists(BACKUP):
        shutil.copy2(TEMPLATE, BACKUP)
        print(f"backed up original -> {os.path.basename(BACKUP)}")

    with zipfile.ZipFile(BACKUP, "r") as zin:
        sheet5 = add_sub_loan_financing(zin.read(SHEET5).decode("utf-8"))
        sheet6 = transform_sheet6(zin.read(SHEET6).decode("utf-8"))
        sheet7 = add_sub_loan_cf(zin.read(SHEET7).decode("utf-8"))
        patched = {SHEET5: sheet5, SHEET6: sheet6, SHEET7: sheet7}
        # drop calcChain so Excel/LibreOffice rebuild it for the new cells
        ct = zin.read("[Content_Types].xml").decode("utf-8")
        ct = re.sub(r'<Override PartName="/xl/calcChain\.xml"[^>]*/>', "", ct, count=1)
        rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        rels = re.sub(r'<Relationship[^>]*calcChain[^>]*/>', "", rels, count=1)

        with zipfile.ZipFile(TEMPLATE, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                if it.filename == "xl/calcChain.xml":
                    continue
                if it.filename in patched:
                    zout.writestr(it, patched[it.filename])
                elif it.filename == "[Content_Types].xml":
                    zout.writestr(it, ct)
                elif it.filename == "xl/_rels/workbook.xml.rels":
                    zout.writestr(it, rels)
                else:
                    zout.writestr(it, zin.read(it.filename))
    print(f"wrote tier-C block (rows 46-49) + subordinate-loan rows -> {os.path.basename(TEMPLATE)}")


# --------------------------------------------------------------------------
# verification: recalc parity (market mode identical) + mixed smoke
# --------------------------------------------------------------------------
def verify() -> int:
    sys.path.insert(0, os.path.dirname(HERE))  # import web/nonlihtc_calc
    import importlib
    nl = importlib.import_module("nonlihtc_calc")

    def recalc_on(path, **kw):
        old = nl.MODEL_PATH
        try:
            nl.MODEL_PATH = path
            return nl.recalc(**kw)
        finally:
            nl.MODEL_PATH = old

    market = nl.build_market_inputs(
        units_by_bed={"1br": 45, "2br": 5, "3br": 0},
        rents_by_bed={"1br": 2400, "2br": 3000}, land_cost=5_000_000,
        opex={"opex_insurance": 33.33, "opex_mr_turnover": 46.08,
              "opex_payroll": 122.92, "opex_reserves": 20.0},
        financing={"exit_cap": 0.05, "perm_rate": 0.0575},
    )
    base = recalc_on(BACKUP, friendly=market)
    new = recalc_on(TEMPLATE, friendly=market)

    print("\n=== recalc parity (market mode: tier C zeroed) ===")
    ok = True
    for k in base:
        a, b = base[k], new[k]
        match = (a == b) or (isinstance(a, (int, float)) and isinstance(b, (int, float))
                             and abs(a - b) <= max(1e-6, abs(a) * 1e-9))
        ok = ok and match
        print(f"  {'OK ' if match else 'XX '} {k}: orig={a}  new={b}")
    print("PARITY:", "PASS" if ok else "FAIL")

    # mixed-income smoke: 10 restricted 1BR @ $1,500 in tier-C row 47 -> EGI rises
    cells = nl.split_inputs(market)
    cells[("(Z+) Rent Roll", "E47")] = (10, False)
    cells[("(Z+) Rent Roll", "I47")] = (1500, False)
    smoke = recalc_on(TEMPLATE, cells=cells)
    egi_base, egi_mixed = new["Effective Gross Income"], smoke["Effective Gross Income"]
    print("\n=== mixed-income smoke (tier-C row 47: 10 units @ $1500) ===")
    print(f"  EGI market-only={egi_base}  with tier-C={egi_mixed}")
    rose = (isinstance(egi_mixed, (int, float)) and isinstance(egi_base, (int, float))
            and egi_mixed > egi_base)
    print("TIER-C FEEDS REVENUE:", "PASS" if rose else "FAIL")

    # --- Feature 2: subordinate-loan parity (amount 0 -> identical to senior-only) ---
    FIN = "(Z+) Financing"
    sub0 = nl.split_inputs(market)
    sub0[(FIN, "D43")] = (0, False)
    out0 = recalc_on(TEMPLATE, cells=sub0)
    subok = all(
        (new[k] == out0[k]) or (isinstance(new[k], (int, float)) and isinstance(out0[k], (int, float))
                                and abs(new[k] - out0[k]) <= max(1e-6, abs(new[k]) * 1e-9))
        for k in new)
    print("\n=== sub-loan parity (amount=0 -> senior-only identical) ===", "PASS" if subok else "FAIL")

    # --- effect: add a $2M, 3% soft loan -> Levered IRR moves (faithful leverage) ---
    subL = nl.split_inputs(market)
    subL[(FIN, "D43")] = (2_000_000, False)  # amount
    subL[(FIN, "D44")] = (0.03, False)       # rate
    subL[(FIN, "D45")] = (30, False)         # amort yrs
    eff = recalc_on(TEMPLATE, cells=subL,
                    read={**nl.HEADLINE})
    irr0, irrL = new["Levered IRR"], eff["Levered IRR"]
    moved = (isinstance(irr0, (int, float)) and isinstance(irrL, (int, float))
             and abs(irrL - irr0) > 1e-6)
    print(f"=== sub-loan effect ($2M @ 3%): Levered IRR {irr0:.4%} -> {irrL:.4%}  "
          f"CoC {new['Cash-on-Cash']:.4%} -> {eff['Cash-on-Cash']:.4%} ===",
          "PASS" if moved else "FAIL")
    return 0 if (ok and rose and subok and moved) else 1


if __name__ == "__main__":
    if "--verify" in sys.argv:
        build()
        sys.exit(verify())
    build()
