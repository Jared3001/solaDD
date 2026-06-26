#!/usr/bin/env python3
"""
deal_onepager.py — SoLa Impact deal one-pager PDF generator.

Produces a 3-page branded PDF from a structured deal dict:
  Page 1: Project facts · financial metrics · key dates · status
  Page 2: Development budget (sources & uses) · TDC trending · change orders
  Page 3: Milestone schedule · debt structure · leasing · key metric callouts

Usage (standalone):
    python3 deal_onepager.py            # generates from Avalon demo data
    python3 deal_onepager.py out.pdf    # custom output path
"""
import sys
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Brand palette ────────────────────────────────────────────────────────────────
NAVY     = colors.HexColor("#1B2A4A")
BLUE     = colors.HexColor("#2E5E8C")
AMBER    = colors.HexColor("#E0A237")
INK      = colors.HexColor("#14181F")
PAPER    = colors.HexColor("#F7F5F0")
GRAY     = colors.HexColor("#6B6F76")
LINE     = colors.HexColor("#D9D5CC")
WHITE    = colors.white
GREEN    = colors.HexColor("#2F7D4F")
RED      = colors.HexColor("#B23A33")
MID_GRAY = colors.HexColor("#A0B4CC")

# ── Fonts ─────────────────────────────────────────────────────────────────────────
_FONT_DIR = Path.home() / "Library" / "Fonts"
pdfmetrics.registerFont(TTFont("Archivo",  str(_FONT_DIR / "Archivo.ttf")))
pdfmetrics.registerFont(TTFont("Mono",     str(_FONT_DIR / "IBMPlexMono-Regular.ttf")))
pdfmetrics.registerFont(TTFont("MonoBold", str(_FONT_DIR / "IBMPlexMono-SemiBold.ttf")))
pdfmetrics.registerFont(TTFont("Serif",    str(_FONT_DIR / "SourceSerif4.ttf")))

# ── Page geometry ─────────────────────────────────────────────────────────────────
W, H = letter   # 612 × 792 pt
M    = 36       # margin
CW   = W - 2*M  # content width 540


# ─────────────────────────────────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────────────────────────────────

def _money(v, unit="M", dp=1):
    if v is None:
        return "—"
    if unit == "M":
        return f"${v/1e6:.{dp}f}M"
    if unit == "K":
        return f"${v/1e3:.{dp}f}K"
    return f"${v:,.0f}"

def _pct(v, dp=1):
    return f"{v*100:.{dp}f}%" if v is not None else "—"

def _mult(v, dp=2):
    return f"{v:.{dp}f}×" if v is not None else "—"

def _date(d):
    if d is None:
        return "TBD"
    return d.strftime("%b %Y") if isinstance(d, (datetime.date, datetime.datetime)) else str(d)


# ─────────────────────────────────────────────────────────────────────────────────
# Shared drawing primitives
# ─────────────────────────────────────────────────────────────────────────────────

def _rule(c, y, color=LINE, lw=0.5):
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.line(M, y, W - M, y)


def _section_label(c, x, y, text):
    """Small all-caps section label with amber underrule."""
    c.setFillColor(GRAY)
    c.setFont("Archivo", 7)
    c.drawString(x, y, text.upper())
    w = c.stringWidth(text.upper(), "Archivo", 7)
    c.setStrokeColor(AMBER)
    c.setLineWidth(1.2)
    c.line(x, y - 2, x + w, y - 2)


def _kv(c, x, y, key, val, key_w=110, key_font="Serif", val_font="Mono", key_sz=8, val_sz=8):
    c.setFont(key_font, key_sz)
    c.setFillColor(GRAY)
    c.drawString(x, y, key)
    c.setFont(val_font, val_sz)
    c.setFillColor(INK)
    c.drawString(x + key_w, y, str(val))


def _header_small(c, deal, subtitle):
    """Compact navy header for pages 2 & 3."""
    BAR_H = 48
    c.setFillColor(NAVY)
    c.rect(0, H - BAR_H, W, BAR_H, fill=1, stroke=0)
    c.setFillColor(AMBER)
    c.rect(0, H - BAR_H, W, 3, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Archivo", 13)
    c.drawString(M, H - 29, deal["name"].upper() + "  —  " + subtitle.upper())
    c.setFont("Archivo", 8)
    c.setFillColor(MID_GRAY)
    c.drawRightString(W - M, H - 29, "SoLa Impact")
    c.setFont("Serif", 7)
    c.drawRightString(W - M, H - 42, "CONFIDENTIAL — INTERNAL USE ONLY")


def _footer(c, page, total=3, as_of=None):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, 26, fill=1, stroke=0)
    c.setFillColor(MID_GRAY)
    c.setFont("Archivo", 7.5)
    c.drawString(M, 9, "SoLa Impact  ·  Confidential — Internal Use Only"
                 + (f"  ·  As of {_date(as_of)}" if as_of else ""))
    c.drawRightString(W - M, 9, f"{page} / {total}")


def _table_header_row(c, y, cols, widths, x0=M):
    """Navy-background column headers."""
    row_h = 16
    c.setFillColor(NAVY)
    c.rect(x0 - 2, y - row_h + 4, sum(widths) + 4, row_h, fill=1, stroke=0)
    cx = x0
    for j, (label, w) in enumerate(zip(cols, widths)):
        c.setFont("Archivo", 7)
        c.setFillColor(WHITE)
        if j == 0:
            c.drawString(cx + 4, y - row_h + 7, label)
        else:
            tw = c.stringWidth(label, "Archivo", 7)
            c.drawString(cx + w - tw - 4, y - row_h + 7, label)
        cx += w
    return y - row_h


def _table_data_row(c, y, vals, widths, fonts=None, colors_=None, x0=M, row_idx=0, is_total=False):
    """Striped data row. vals[0] is left-aligned; rest right-aligned."""
    row_h = 14
    if is_total:
        c.setFillColor(NAVY)
        c.rect(x0 - 2, y - row_h + 2, sum(widths) + 4, row_h + 2, fill=1, stroke=0)
    else:
        c.setFillColor(PAPER if row_idx % 2 == 0 else WHITE)
        c.rect(x0 - 2, y - row_h + 2, sum(widths) + 4, row_h, fill=1, stroke=0)

    cx = x0
    for j, (val, w) in enumerate(zip(vals, widths)):
        font = (fonts or [])[j] if fonts and j < len(fonts) else ("Serif" if j == 0 else "Mono")
        sz   = 8.5
        fg   = WHITE if is_total else ((colors_ or [])[j] if colors_ and j < len(colors_) else (INK if j == 0 else GRAY))

        c.setFont(font, sz)
        c.setFillColor(fg)
        if j == 0:
            c.drawString(cx + 4, y - row_h + 5, str(val))
        else:
            tw = c.stringWidth(str(val), font, sz)
            c.drawString(cx + w - tw - 4, y - row_h + 5, str(val))
        cx += w
    return y - row_h


# ─────────────────────────────────────────────────────────────────────────────────
# Page 1 — Deal Overview
# ─────────────────────────────────────────────────────────────────────────────────

def _page1(c, deal):
    # ── Header ───────────────────────────────────────────────────────────────────
    BAR_H = 82
    c.setFillColor(NAVY)
    c.rect(0, H - BAR_H, W, BAR_H, fill=1, stroke=0)
    # Amber accent line
    c.setFillColor(AMBER)
    c.rect(0, H - BAR_H, W, 3, fill=1, stroke=0)
    # Deal name
    c.setFillColor(WHITE)
    c.setFont("Archivo", 22)
    c.drawString(M, H - 38, deal["name"].upper())
    # Subtitle (amber)
    c.setFont("Archivo", 9)
    c.setFillColor(AMBER)
    c.drawString(M, H - 54, deal["subtitle"].upper())
    # Fund · submarket · as-of
    c.setFont("Serif", 8.5)
    c.setFillColor(MID_GRAY)
    c.drawString(M, H - 68, f"{deal['fund']}  ·  {deal['submarket']}  ·  As of {_date(deal['as_of'])}")
    # SoLa Impact top-right
    c.setFont("Archivo", 9)
    c.setFillColor(WHITE)
    tw = c.stringWidth("SoLa Impact", "Archivo", 9)
    c.drawString(W - M - tw, H - 38, "SoLa Impact")
    c.setFont("Serif", 7)
    c.setFillColor(MID_GRAY)
    c.drawRightString(W - M, H - 52, "CONFIDENTIAL — INTERNAL USE ONLY")

    _footer(c, 1, as_of=deal["as_of"])

    TOP = H - BAR_H - 10  # 700

    # ── Status chips strip (full width, directly below header) ───────────────────
    CHIPS = [
        ("Const. Compl.", _pct(deal["status"]["const_compl_pct"], 0)),
        ("Buyout Compl.", _pct(deal["status"]["buyout_compl_pct"], 0)),
        ("Occupancy",     _pct(deal["status"]["occupancy"], 0)),
        ("Section 8",     _pct(deal["status"]["sec8_pct"], 0)),
    ]
    CHIP_H, GAP, CHIP_W = 34, 6, (CW - 3 * 6) / 4
    cy = TOP - CHIP_H
    for i, (label, val) in enumerate(CHIPS):
        cx = M + i * (CHIP_W + GAP)
        c.setFillColor(PAPER)
        c.roundRect(cx, cy, CHIP_W, CHIP_H, 4, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.roundRect(cx, cy, CHIP_W, CHIP_H, 4, fill=0, stroke=1)
        # value
        c.setFont("MonoBold", 13)
        c.setFillColor(GREEN if val == "100%" else GRAY if val == "—" else INK)
        vw = c.stringWidth(val, "MonoBold", 13)
        c.drawString(cx + CHIP_W / 2 - vw / 2, cy + 14, val)
        # label
        c.setFont("Serif", 7)
        c.setFillColor(GRAY)
        lw = c.stringWidth(label, "Serif", 7)
        c.drawString(cx + CHIP_W / 2 - lw / 2, cy + 4, label)

    TOP = cy - 14  # ~652

    # ── Two-column body ───────────────────────────────────────────────────────────
    LX, LW = M, 285
    RX      = M + LW + 14
    RW      = CW - LW - 14

    # ── LEFT: Project Facts ───────────────────────────────────────────────────────
    y = TOP
    _section_label(c, LX, y, "Project")
    y -= 14

    c.setFont("Archivo", 11)
    c.setFillColor(INK)
    c.drawString(LX, y, deal["name"])
    y -= 13
    c.setFont("Serif", 9)
    c.setFillColor(GRAY)
    c.drawString(LX, y, deal["address"])
    y -= 12
    c.drawString(LX, y, deal["city_state"])
    y -= 12
    c.drawString(LX, y, f"{deal['cross_streets']}  ·  {deal['submarket']}")
    y -= 16
    _rule(c, y)
    y -= 12

    KW = 108
    INFO = [
        ("Fund",             deal["fund"] or "—"),
        ("Project Type",     deal["project_type"] or "—"),
        ("Dev. Type",        deal["dev_type"] or "—"),
        ("Product",          deal["product_type"] or "—"),
        ("# of Units",       f"{deal['n_units']} units" if deal['n_units'] else "—"),
        ("Avg Unit Size",    f"{deal['avg_unit_sf']:,.0f} SF" if deal['avg_unit_sf'] else "—"),
        ("Lot Area",         (f"{deal['lot_sf']:,} SF / {deal['lot_acres']:.3f} ac"
                              if deal['lot_sf'] and deal['lot_acres'] else "—")),
        ("Density",          f"{deal['density']:.1f} units/ac" if deal['density'] else "—"),
        ("Gross / Net SF",   (f"{deal['gross_sf']:,} / {deal['net_sf']:,} ({deal['efficiency']*100:.0f}% eff.)"
                              if deal['gross_sf'] and deal['net_sf'] else "—")),
    ]
    for key, val in INFO:
        _kv(c, LX, y, key, val, key_w=KW)
        y -= 12

    y -= 4
    _rule(c, y)
    y -= 12

    _section_label(c, LX, y, "Unit Mix")
    y -= 12
    if deal["unit_mix"]:
        for um in deal["unit_mix"]:
            cnt  = f"{um['count']} units" if um.get('count') else "—"
            pct  = f"({um['pct']*100:.0f}%)" if um.get('pct') is not None else ""
            sf   = f"  ·  {um['sf']} SF avg" if um.get('sf') else ""
            _kv(c, LX, y, um["type"], f"{cnt} {pct}{sf}".strip(), key_w=55)
            y -= 12
    else:
        _kv(c, LX, y, "Mix", "TBD — see model", key_w=55)
        y -= 12

    y -= 4
    _rule(c, y)
    y -= 12

    _section_label(c, LX, y, "Affordability")
    y -= 12
    for af in deal["affordability"]:
        cnt = f"{af['units']} units" if af.get('units') else "—"
        pct = f" ({af['pct']*100:.0f}%)" if af.get('pct') is not None else ""
        _kv(c, LX, y, af["desc"], cnt + pct, key_w=KW)
        y -= 12

    LEFT_BOTTOM = y  # remember where left col ends

    # ── RIGHT: Financial Metrics ──────────────────────────────────────────────────
    y_r = TOP
    _section_label(c, RX, y_r, "Financial Metrics  (IC vs. Current)")
    y_r -= 14

    # Column headers: blank | IC | CURRENT
    C1 = RX
    C2 = RX + 110
    C3 = RX + 178

    c.setFont("Archivo", 7)
    c.setFillColor(GRAY)
    c.drawString(C2, y_r, "AT IC")
    c.drawString(C3, y_r, "CURRENT")
    # Amber underline for CURRENT column header
    cw = c.stringWidth("CURRENT", "Archivo", 7)
    c.setStrokeColor(AMBER)
    c.setLineWidth(1.5)
    c.line(C3, y_r - 2, C3 + cw + 10, y_r - 2)
    y_r -= 4
    _rule(c, y_r, color=LINE)
    y_r -= 12

    def _rent(v): return f"${v:,.0f}" if v is not None else "—"
    def _psf(v):  return f"${v:.2f}" if v is not None else "—"
    METRICS = [
        ("Avg Rent",          _rent(deal['metrics']['avg_rent'][0]),           _rent(deal['metrics']['avg_rent'][1])),
        ("Avg Rent (PSF)",    _psf(deal['metrics']['avg_rent_psf'][0]),        _psf(deal['metrics']['avg_rent_psf'][1])),
        ("TDC",               _money(deal['metrics']['tdc'][0]),               _money(deal['metrics']['tdc'][1])),
        ("TDC / Unit",        _money(deal['metrics']['tdc_per_unit'][0], "K"), _money(deal['metrics']['tdc_per_unit'][1], "K")),
        ("Land / Unit",       _money(deal['metrics']['land_per_unit'][0], "K"),_money(deal['metrics']['land_per_unit'][1], "K")),
        ("Project IRR",       _pct(deal['metrics']['project_irr'][0]),         _pct(deal['metrics']['project_irr'][1])),
        ("RoC (Trended)",     _pct(deal['metrics']['roc_trended'][0]),         _pct(deal['metrics']['roc_trended'][1])),
        ("Stabilized CoC",    _pct(deal['metrics']['stabilized_coc'][0]),      _pct(deal['metrics']['stabilized_coc'][1])),
        ("MOIC",              _mult(deal['metrics']['moic'][0]),                _mult(deal['metrics']['moic'][1])),
    ]
    for i, (label, ic, cur) in enumerate(METRICS):
        c.setFillColor(PAPER if i % 2 == 0 else WHITE)
        c.rect(RX - 2, y_r - 3, RW + 2, 14, fill=1, stroke=0)
        c.setFont("Serif", 8.5)
        c.setFillColor(INK)
        c.drawString(C1, y_r, label)
        c.setFont("Mono", 8.5)
        c.setFillColor(GRAY)
        c.drawString(C2, y_r, ic)
        c.setFont("MonoBold", 8.5)
        c.setFillColor(INK)
        c.drawString(C3, y_r, cur)
        y_r -= 13

    y_r -= 6
    _rule(c, y_r)
    y_r -= 12

    _section_label(c, RX, y_r, "Leasing")
    y_r -= 12
    _avg_rent = deal['leasing']['avg_rent']
    _vel      = deal['leasing']['velocity_units']
    LEASING = [
        ("Avg Rent (Actual)",   f"${_avg_rent:,}/mo" if _avg_rent else "TBD"),
        ("Master Lessee",       deal['leasing']['master_lessee'] or "TBD"),
        ("Lease-up Velocity",   f"{_vel} units/mo" if _vel else "TBD"),
        ("Fully Stabilized",    _date(deal['schedule']['fully_stabilized'][1])),
    ]
    for key, val in LEASING:
        _kv(c, RX, y_r, key, val, key_w=110)
        y_r -= 12

    y_r -= 4
    _rule(c, y_r)
    y_r -= 12

    _section_label(c, RX, y_r, "Debt")
    y_r -= 12
    _cl = deal['debt']['construction']
    _cl_str = (f"${_cl['amount']:,.0f}  ·  {_pct(_cl['rate'])}  ·  LTC {_pct(_cl['ltc'])}"
               if _cl.get('amount') else "TBD")
    _kv(c, RX, y_r, "Const. Loan", _cl_str, key_w=80, val_sz=7.5)
    y_r -= 12
    _pl = deal['debt']['permanent']
    _kv(c, RX, y_r, "Perm Debt",
        f"{_pl.get('status','TBD')}  ·  est. {_pct(_pl.get('rate'))}",
        key_w=80)

    # ── Schedule timeline ─────────────────────────────────────────────────────────
    TL_TOP = min(LEFT_BOTTOM, y_r) - 16
    BOX_H  = 52
    TL_Y   = TL_TOP  # top of timeline box

    c.setFillColor(PAPER)
    c.roundRect(M, TL_Y - BOX_H, CW, BOX_H, 4, fill=1, stroke=0)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.roundRect(M, TL_Y - BOX_H, CW, BOX_H, 4, fill=0, stroke=1)

    _section_label(c, M + 8, TL_Y - 6, "Key Dates")

    MILESTONES = [
        ("CoE",          deal["schedule"]["coe"][1]),
        ("RTI",          deal["schedule"]["rti"][1]),
        ("Const. Start", deal["schedule"]["constr_start"][1]),
        ("TCO",          deal["schedule"]["tco"][1]),
        ("Stabilized",   deal["schedule"]["fully_stabilized"][1]),
    ]
    N = len(MILESTONES)
    TL_LINE_Y  = TL_Y - 28
    TL_X_START = M + 48
    TL_X_END   = W - M - 48
    TL_SPAN    = TL_X_END - TL_X_START

    c.setStrokeColor(BLUE)
    c.setLineWidth(1.5)
    c.line(TL_X_START, TL_LINE_Y, TL_X_END, TL_LINE_Y)

    for i, (label, d) in enumerate(MILESTONES):
        xd = TL_X_START + (i / (N - 1)) * TL_SPAN
        # outer dot
        c.setFillColor(NAVY)
        c.circle(xd, TL_LINE_Y, 5, fill=1, stroke=0)
        # inner amber
        c.setFillColor(AMBER)
        c.circle(xd, TL_LINE_Y, 2.5, fill=1, stroke=0)
        # label above
        c.setFont("Serif", 7)
        c.setFillColor(INK)
        lw = c.stringWidth(label, "Serif", 7)
        c.drawString(xd - lw / 2, TL_LINE_Y + 9, label)
        # date below
        c.setFont("Mono", 7)
        c.setFillColor(GRAY)
        dw = c.stringWidth(_date(d), "Mono", 7)
        c.drawString(xd - dw / 2, TL_LINE_Y - 18, _date(d))


# ─────────────────────────────────────────────────────────────────────────────────
# Page 2 — Development Budget
# ─────────────────────────────────────────────────────────────────────────────────

def _page2(c, deal):
    has_budget = bool((deal.get("budget") or {}).get("sources"))
    has_uses   = bool((deal.get("budget") or {}).get("uses"))
    _header_small(c, deal, "Development Budget" if has_budget else "Model Scenarios")
    _footer(c, 2, as_of=deal["as_of"])

    y = H - 65
    LX = M

    if has_budget:
        # ── Sources ─────────────────────────────────────────────────────────────────
        _section_label(c, LX, y, "Sources of Capital")
        y -= 13

        SRC_COLS   = ["Source", "IC %", "IC $", "Current $", "Change"]
        SRC_WIDTHS = [175, 50, 95, 95, 125]
        y = _table_header_row(c, y, SRC_COLS, SRC_WIDTHS)

        for i, (label, ic_pct, ic_amt, cur_amt) in enumerate(deal["budget"]["sources"]):
            is_total = "Total" in label
            chg      = cur_amt - ic_amt
            chg_str  = (f"+{_money(chg)}" if chg > 0 else _money(chg)) if chg != 0 else "—"
            chg_col  = RED if chg > 0 else GREEN
            vals  = [label, _pct(ic_pct), _money(ic_amt), _money(cur_amt), chg_str]
            fonts = ["Archivo" if is_total else "Serif", "Mono", "Mono", "MonoBold", "Mono"]
            clrs  = [INK, GRAY, GRAY, AMBER, chg_col]
            y = _table_data_row(c, y, vals, SRC_WIDTHS, fonts=fonts, colors_=clrs, row_idx=i, is_total=is_total)

        y -= 14
        _rule(c, y)
        y -= 14

    if has_uses:
        # ── Uses ────────────────────────────────────────────────────────────────────
        _section_label(c, LX, y, "Uses of Capital")
        y -= 13

        USE_COLS   = ["Cost Category", "IC (Board)", "Lender Budget", "Current", "Spent to Date", "% Compl."]
        USE_WIDTHS = [168, 70, 78, 78, 78, 68]
        y = _table_header_row(c, y, USE_COLS, USE_WIDTHS)

        for i, row in enumerate(deal["budget"]["uses"]):
            label, ic, lender, cur, spent, compl = row
            is_total  = "Total" in label
            compl_str = _pct(compl, 0) if compl is not None else "—"
            vals  = [label, _money(ic), _money(lender), _money(cur), _money(spent), compl_str]
            fonts = ["Archivo" if is_total else "Serif"] + ["Mono"] * 4 + ["MonoBold" if compl == 1.0 else "Mono"]
            clrs  = [INK, GRAY, GRAY, AMBER, GRAY, GREEN if compl == 1.0 else GRAY]
            y = _table_data_row(c, y, vals, USE_WIDTHS, fonts=fonts, colors_=clrs, row_idx=i, is_total=is_total)

        y -= 16
        _rule(c, y)
        y -= 16

    if not has_budget:
        # ── Scenario summary (when no budget data yet — preliminary mode) ───────────
        _section_label(c, LX, y, "Scenarios Generated")
        y -= 14
        for scn_name in (deal.get("_scenarios") or ["(none selected)"]):
            c.setFont("Serif", 8.5)
            c.setFillColor(INK)
            c.drawString(LX + 8, y, f"• {scn_name}")
            y -= 12

        y -= 6
        _rule(c, y)
        y -= 14

        # Model input summary
        _section_label(c, LX, y, "Model Inputs Used")
        y -= 14
        for key, val in (deal.get("_model_inputs") or {}).items():
            _kv(c, LX, y, key, str(val) if val is not None else "—", key_w=140)
            y -= 12

        y -= 6
        _rule(c, y)
        y -= 16

    # ── Two cards: TDC Trending + Change Orders ───────────────────────────────────
    half_w = (CW - 14) / 2
    td = deal.get("tdc_trending") or {}
    co = deal.get("change_orders") or {}
    _inc = td.get('increase')
    inc_str = (f"+{_money(_inc)}" if _inc and _inc > 0 else _money(_inc)) if _inc is not None else "—"

    for card_x, title, items in [
        (M,                 "TDC TRENDING TO COMPLETION", [
            ("IC TDC",               _money(td.get('ic_tdc'))),
            ("Current TDC",          _money(td.get('current_tdc'))),
            ("Increase from IC",     inc_str),
            ("% Increase from IC",   _pct(td.get('pct_increase'))),
            ("Current TDC / Unit",   _money(deal['metrics']['tdc_per_unit'][1], "K")),
            ("IC TDC / Unit",        _money(deal['metrics']['tdc_per_unit'][0], "K")),
        ]),
        (M + half_w + 14,   "CHANGE ORDERS", [
            ("Approved Total",        _money(co.get('approved_total')) if co.get('approved_total') else "—"),
            ("  GMAX COs",           _money(co.get('gmax_cos')) if co.get('gmax_cos') else "—"),
            ("  SoLa Direct COs",    _money(co.get('sola_direct')) if co.get('sola_direct') else "—"),
            ("PCCOs",                _money(co.get('pccos')) if co.get('pccos') else "—"),
            ("Soft Cost COs",        _money(co.get('soft_cost_cos')) if co.get('soft_cost_cos') else "—"),
            ("Owner Contingency",    _money(co.get('owner_con_left')) if co.get('owner_con_left') else "—"),
        ]),
    ]:
        n_rows = len(items)
        card_h = 18 + n_rows * 14 + 8
        # card background
        c.setFillColor(PAPER)
        c.roundRect(card_x, y - card_h, half_w, card_h, 4, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.roundRect(card_x, y - card_h, half_w, card_h, 4, fill=0, stroke=1)
        # card header
        c.setFillColor(NAVY)
        c.roundRect(card_x, y - 18, half_w, 18, 4, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Archivo", 7)
        c.drawString(card_x + 8, y - 12, title)
        # rows
        row_y = y - 32
        for key, val in items:
            is_indent = key.startswith("  ")
            c.setFont("Serif", 8)
            c.setFillColor(GRAY)
            c.drawString(card_x + (16 if is_indent else 8), row_y, key.strip())
            highlight = key in ("Current TDC", "Approved Total", "% Increase from IC")
            c.setFont("MonoBold" if highlight else "Mono", 8)
            c.setFillColor(RED if "Increase" in key and "%" not in key else
                           AMBER if highlight else INK)
            tw = c.stringWidth(val, "MonoBold" if highlight else "Mono", 8)
            c.drawString(card_x + half_w - tw - 8, row_y, val)
            row_y -= 14


# ─────────────────────────────────────────────────────────────────────────────────
# Page 3 — Schedule & Debt
# ─────────────────────────────────────────────────────────────────────────────────

def _page3(c, deal):
    _header_small(c, deal, "Schedule & Debt")
    _footer(c, 3, as_of=deal["as_of"])

    y = H - 65
    LX = M

    # ── Milestone schedule table ───────────────────────────────────────────────────
    _section_label(c, LX, y, "Milestone Schedule")
    y -= 13

    MS_COLS   = ["Milestone", "IC Date", "Actual / Current", "Variance (Days)"]
    MS_WIDTHS = [200, 115, 115, 110]
    y = _table_header_row(c, y, MS_COLS, MS_WIDTHS)

    for i, (label, ic_d, act_d) in enumerate(deal["milestones"]):
        if ic_d and act_d:
            diff = (act_d - ic_d).days if isinstance(ic_d, datetime.date) else 0
            if abs(diff) < 5:
                var_str, var_col = "On time", GREEN
            elif diff > 0:
                var_str, var_col = f"+{diff} days", RED
            else:
                var_str, var_col = f"{diff} days", GREEN
        else:
            var_str, var_col = "TBD", GRAY
        vals  = [label, _date(ic_d), _date(act_d), var_str]
        fonts = ["Serif", "Mono", "Mono", "MonoBold"]
        clrs  = [INK, GRAY, INK, var_col]
        y = _table_data_row(c, y, vals, MS_WIDTHS, fonts=fonts, colors_=clrs, row_idx=i)

    y -= 14
    _rule(c, y)
    y -= 14

    # ── Two columns: Debt + Leasing/Tax ───────────────────────────────────────────
    half_w = (CW - 14) / 2
    LX2    = M + half_w + 14

    # Left: Debt Structure
    _section_label(c, LX, y, "Debt Structure")
    y_l = y - 13

    def _debt_header(c, x, y, txt):
        c.setFillColor(NAVY)
        c.rect(x, y - 2, half_w, 14, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Archivo", 8)
        c.drawString(x + 4, y, txt)
        return y - 16

    y_l = _debt_header(c, LX, y_l, "Construction Loan")
    CONSTR_ITEMS = [
        ("Lender",            deal["debt"]["construction"].get("lender", "TBD")),
        ("Loan Amount",       _money(deal['debt']['construction']['amount'], "raw")),
        ("Interest Rate",     _pct(deal['debt']['construction']['rate'])),
        ("LTC at Close",      _pct(deal['debt']['construction']['ltc'])),
        ("Drawn to Date",     "100%"),
        ("Maturity",          _date(deal['debt']['construction'].get('maturity'))),
    ]
    for key, val in CONSTR_ITEMS:
        _kv(c, LX, y_l, key, val, key_w=100)
        y_l -= 12

    y_l -= 8
    y_l = _debt_header(c, LX, y_l, "Permanent Debt")
    PERM_ITEMS = [
        ("Status",    deal['debt']['permanent']['status']),
        ("Rate",      _pct(deal['debt']['permanent']['rate']) + " (est.)"),
        ("LTV",       _pct(deal['debt']['permanent'].get('ltv')) if deal['debt']['permanent'].get('ltv') else "TBD"),
    ]
    for key, val in PERM_ITEMS:
        _kv(c, LX, y_l, key, val, key_w=100)
        y_l -= 12

    # Right: Leasing + Property Tax Exemption
    _section_label(c, LX2, y, "Leasing & Occupancy")
    y_r = y - 13

    _ar  = deal['leasing'].get('avg_rent')
    _vel = deal['leasing'].get('velocity_units')
    LEASING_ITEMS = [
        ("Master Lessee",     deal['leasing'].get('master_lessee') or "TBD"),
        ("Avg Rent (Actual)", f"${_ar:,}/mo" if _ar else "TBD"),
        ("Occupancy",         _pct(deal['status']['occupancy'], 0)),
        ("Section 8 %",       _pct(deal['status']['sec8_pct'], 0)),
        ("Lease-up Velocity", f"{_vel} units/mo" if _vel else "TBD"),
        ("Fully Stabilized",  _date(deal['schedule']['fully_stabilized'][1])),
        ("Pre-leasing Date",  _date(deal['leasing'].get('pre_lease_date'))),
        ("First Move-Ins",    _date(deal['leasing'].get('first_move_ins'))),
    ]
    for key, val in LEASING_ITEMS:
        _kv(c, LX2, y_r, key, val, key_w=115)
        y_r -= 12

    y_r -= 8
    _rule(c, y_r, color=LINE)
    y_r -= 12

    _section_label(c, LX2, y_r, "Property Tax Exemption")
    y_r -= 13
    TAX_ITEMS = [
        ("Non-Profit Partner",  deal['tax_exemption'].get('non_profit', "TBD")),
        ("CMFA Grant Date",     _date(deal['tax_exemption'].get('cmfa_date'))),
        ("BofE Date",           _date(deal['tax_exemption'].get('bofe_date'))),
        ("Assessor Date",       _date(deal['tax_exemption'].get('assessor_date'))),
        ("Est. Annual Savings", deal['tax_exemption'].get('est_savings', "TBD")),
    ]
    for key, val in TAX_ITEMS:
        _kv(c, LX2, y_r, key, val, key_w=115)
        y_r -= 12

    # ── Key metric callout bar (bottom of page) ───────────────────────────────────
    BAR_Y, BAR_H = 38, 60
    c.setFillColor(NAVY)
    c.rect(0, BAR_Y, W, BAR_H, fill=1, stroke=0)
    c.setFillColor(AMBER)
    c.rect(0, BAR_Y + BAR_H - 3, W, 3, fill=1, stroke=0)

    _co_ar = deal['leasing'].get('avg_rent')
    CALLOUTS = [
        ("Project IRR",    _pct(deal['metrics']['project_irr'][1]),        "Current"),
        ("MOIC",           _mult(deal['metrics']['moic'][1]),               "At Completion"),
        ("TDC / Unit",     _money(deal['metrics']['tdc_per_unit'][1], "K"),"Current"),
        ("Occupancy",      _pct(deal['status']['occupancy'], 0),            f"As of {_date(deal['as_of'])}"),
        ("Avg Rent",       f"${_co_ar:,}" if _co_ar else "TBD",            "Monthly, Actual"),
    ]
    chip_w = W / len(CALLOUTS)
    for i, (label, val, sub) in enumerate(CALLOUTS):
        cx = i * chip_w
        if i > 0:
            c.setStrokeColor(colors.HexColor("#2E3F5E"))
            c.setLineWidth(0.5)
            c.line(cx, BAR_Y + 6, cx, BAR_Y + BAR_H - 6)
        c.setFont("MonoBold", 16)
        c.setFillColor(AMBER)
        vw = c.stringWidth(val, "MonoBold", 16)
        c.drawString(cx + chip_w / 2 - vw / 2, BAR_Y + 28, val)
        c.setFont("Archivo", 8)
        c.setFillColor(WHITE)
        lw = c.stringWidth(label, "Archivo", 8)
        c.drawString(cx + chip_w / 2 - lw / 2, BAR_Y + 15, label)
        c.setFont("Serif", 6.5)
        c.setFillColor(MID_GRAY)
        sw = c.stringWidth(sub, "Serif", 6.5)
        c.drawString(cx + chip_w / 2 - sw / 2, BAR_Y + 5, sub)


# ─────────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────────

def generate(deal: dict, out_path: str) -> str:
    """Render the 3-page PDF and return the output path."""
    c = rl_canvas.Canvas(out_path, pagesize=letter)
    c.setTitle(f"{deal['name']} — SoLa Impact One Pager")
    c.setAuthor("SoLa Impact")

    _page1(c, deal)
    c.showPage()
    _page2(c, deal)
    c.showPage()
    _page3(c, deal)
    c.showPage()
    c.save()
    return out_path


# ─────────────────────────────────────────────────────────────────────────────────
# Demo: 6401 Avalon
# ─────────────────────────────────────────────────────────────────────────────────

AVALON = {
    "name":         "6401 Avalon",
    "subtitle":     "Internal One Pager",
    "fund":         "Fund 3 (OZ)",
    "address":      "6401–6403 S Avalon Blvd",
    "city_state":   "Los Angeles, CA 90003",
    "cross_streets":"64th & Avalon",
    "submarket":    "South LA  ·  Opportunity Zone",
    "project_type": "Ground Up",
    "dev_type":     "Restricted Section 8",
    "product_type": "4-story Type III-A (with elevator)",
    "n_units":      28,
    "unit_mix": [
        {"type": "Studio",  "count": 6,  "pct": 0.21, "sf": 274},
        {"type": "1 Bed",   "count": 22, "pct": 0.79, "sf": 362},
    ],
    "avg_unit_sf":  407,
    "lot_sf":       7150,
    "lot_acres":    0.164,
    "density":      170.6,
    "gross_sf":     14417,
    "net_sf":       11401,
    "efficiency":   0.791,
    "affordability": [
        {"desc": "60% AMI",       "units": 24, "pct": 0.857},
        {"desc": "30% AMI",       "units": 3,  "pct": 0.107},
        {"desc": "Manager Unit",  "units": 1,  "pct": 0.036},
    ],
    "metrics": {
        "avg_rent_psf":      (4.11,    4.13),
        "avg_rent":          (1455,    1559),
        "tdc":               (5409850, 6306934),
        "tdc_per_unit":      (193209,  225248),
        "land_per_unit":     (18773,   19051),
        "roc_trended":       (0.063,   0.0538),
        "project_irr":       (0.123,   0.131),
        "stabilized_coc":    (0.087,   0.045),
        "moic":              (2.25,    2.42),
    },
    "schedule": {
        "coe":               (datetime.date(2018, 12, 31), datetime.date(2018, 12, 31)),
        "rti":               (datetime.date(2020,  1, 31), datetime.date(2020,  1, 31)),
        "constr_start":      (datetime.date(2020,  1, 31), datetime.date(2020,  1, 31)),
        "tco":               (datetime.date(2021,  1,  1), datetime.date(2021,  1, 10)),
        "fully_stabilized":  (datetime.date(2021,  4, 30), datetime.date(2021,  5, 31)),
    },
    "status": {
        "const_compl_pct":  1.0,
        "buyout_compl_pct": 1.0,
        "occupancy":        1.0,
        "sec8_pct":         1.0,
    },
    "leasing": {
        "avg_rent":         1559,
        "master_lessee":    "HOPICS",
        "velocity_units":   20,
        "pre_lease_date":   datetime.date(2021, 1, 10),
        "first_move_ins":   datetime.date(2021, 1, 10),
    },
    "debt": {
        "construction": {
            "lender":       "TBD",
            "amount":       3453539,
            "rate":         0.035,
            "ltc":          0.5476,
            "maturity":     None,
        },
        "permanent": {
            "status":       "In Process",
            "rate":         0.035,
            "ltv":          None,
        },
    },
    "budget": {
        "sources": [
            ("Equity",             0.52, 2716885, 2853395),
            ("Construction Loan",  0.48, 2507894, 3453539),
            ("Total Sources",      1.00, 5224779, 6306934),
        ],
        "uses": [
            ("Acquisition Costs",  533000,   533442,   533442,  533442, 1.0),
            ("Hard Costs (GC)",   3390162,  3700876,  3666171, 3666171, 1.0),
            ("Soft Costs",         534376,   679355,   679310,  679310, 1.0),
            ("Admin Costs",        572459,  1434482,  1428011, 1428011, 1.0),
            ("Contingency",        194782,        0,        0,       0, None),
            ("Total Uses",        5224779,  6553431,  6306934, 6306934, 1.0),
        ],
    },
    "change_orders": {
        "approved_total":   380270,
        "gmax_cos":         333770,
        "sola_direct":       22239,
        "pccos":                 0,
        "soft_cost_cos":     24261,
        "owner_con_left":        0,
    },
    "tdc_trending": {
        "ic_tdc":           5224779,
        "current_tdc":      6306934,
        "increase":         1082155,
        "pct_increase":     0.2071,
    },
    "milestones": [
        ("Acquisition",         datetime.date(2018, 12, 31), datetime.date(2018, 12, 31)),
        ("RTI",                 datetime.date(2020,  1, 31), datetime.date(2020,  1, 31)),
        ("Contract Executed",   datetime.date(2020,  1, 31), datetime.date(2020,  1, 31)),
        ("Notice to Proceed",   None,                        None),
        ("Construction Start",  datetime.date(2020,  1, 31), datetime.date(2020,  1, 31)),
        ("Anticipated TCO",     datetime.date(2021,  1,  1), datetime.date(2021,  1, 10)),
        ("Anticipated CO",      datetime.date(2021,  1, 31), datetime.date(2021,  9, 21)),
    ],
    "tax_exemption": {
        "non_profit":       "TBD",
        "cmfa_date":        None,
        "bofe_date":        None,
        "assessor_date":    None,
        "est_savings":      "TBD",
    },
    "as_of": datetime.date(2024, 6, 7),
}


def preliminary_deal(name, address, dd=None, overrides=None, scenarios=None, as_of=None):
    """Build a minimal deal dict from DD data + model overrides for a preliminary PDF.

    Financial metrics, budget, and status fields are left as None (render as '—' or TBD).
    Scenarios generated are stored under '_scenarios' for page 2's scenario-summary block.
    Call generate(preliminary_deal(...), out_path) to produce the PDF."""
    dd = dd or {}
    overrides = overrides or {}
    lot_sf = (overrides.get("land_sf") or dd.get("land_sf") or None)
    lot_acres = round(lot_sf / 43560, 3) if lot_sf else None
    acq_price = overrides.get("acquisition_price")
    stories   = overrides.get("residential_stories") or 5
    resource  = overrides.get("resource") or dd.get("resource_area") or "—"
    qct_dda   = overrides.get("qct_dda") or ("QCT" if dd.get("qct") == "Yes" else
                                              "DDA" if dd.get("dda") == "Yes" else "—")
    county    = overrides.get("county") or dd.get("county") or "—"
    pha       = overrides.get("pha") or dd.get("pha") or "—"
    return {
        "name":         name or "Untitled Deal",
        "subtitle":     "Preliminary Model Summary",
        "fund":         "—",
        "address":      address or "—",
        "city_state":   "",
        "cross_streets":"—",
        "submarket":    resource,
        "project_type": "Ground Up",
        "dev_type":     "LIHTC / Section 8",
        "product_type": f"{stories}-story",
        "n_units":      None,
        "unit_mix":     [],
        "avg_unit_sf":  None,
        "lot_sf":       lot_sf,
        "lot_acres":    lot_acres,
        "density":      None,
        "gross_sf":     None,
        "net_sf":       None,
        "efficiency":   None,
        "affordability": [
            {"desc": "60% AMI",       "units": None, "pct": 0.80},
            {"desc": "30% AMI",       "units": None, "pct": 0.10},
            {"desc": "50% AMI",       "units": None, "pct": 0.10},
        ],
        "metrics": {k: (None, None) for k in (
            "avg_rent_psf", "avg_rent", "tdc", "tdc_per_unit", "land_per_unit",
            "roc_trended", "project_irr", "stabilized_coc", "moic")},
        "schedule": {k: (None, None) for k in (
            "coe", "rti", "constr_start", "tco", "fully_stabilized")},
        "status": {k: None for k in (
            "const_compl_pct", "buyout_compl_pct", "occupancy", "sec8_pct")},
        "leasing": {"avg_rent": None, "master_lessee": None,
                    "velocity_units": None, "pre_lease_date": None, "first_move_ins": None},
        "debt": {
            "construction": {"lender": "TBD", "amount": None, "rate": None, "ltc": None, "maturity": None},
            "permanent":    {"status": "TBD", "rate": None, "ltv": None},
        },
        "budget":        {"sources": [], "uses": []},
        "change_orders": {k: 0 for k in (
            "approved_total", "gmax_cos", "sola_direct", "pccos", "soft_cost_cos", "owner_con_left")},
        "tdc_trending":  {"ic_tdc": None, "current_tdc": None, "increase": None, "pct_increase": None},
        "milestones": [
            ("Acquisition",       None, None),
            ("RTI",               None, None),
            ("Construction Start",None, None),
            ("TCO",               None, None),
            ("Stabilization",     None, None),
        ],
        "tax_exemption": {"non_profit": "TBD", "cmfa_date": None, "bofe_date": None,
                          "assessor_date": None, "est_savings": "TBD"},
        "as_of":         as_of or datetime.date.today(),
        "_scenarios":    scenarios or [],
        "_model_inputs": {
            "County":               county,
            "PHA":                  pha,
            "QCT / DDA":            qct_dda,
            "Resource Area":        resource,
            "Land Area (SF)":       f"{lot_sf:,}" if lot_sf else "—",
            "Acquisition Price":    f"${acq_price:,.0f}" if acq_price else "— (default $150/SF)",
            "Residential Stories":  stories,
        },
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "Downloads" / "6401_Avalon_OnePager.pdf")
    path = generate(AVALON, out)
    print(f"PDF written → {path}")
