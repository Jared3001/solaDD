#!/usr/bin/env python3
"""
build_hud_rents.py — parse the official CTCAC statewide MTSP rent table into the
ModularZ affordable-rent data layer.

Source of truth: California Tax Credit Allocation Committee (CTCAC) "Maximum
Multifamily Tax Subsidy (MTSP) Rents for LIHTC Projects", projects placed in
service on/after 4/1/2025. Public PDF:
  https://www.treasurer.ca.gov/sites/default/files/2025-10/rent_040125.pdf
A copy is kept in source/rent_040125.pdf for reproducibility.

Output (consumed client-side by ModularZ):
  web/static/hud_rents.js    -> window.HUD_RENTS = {...}
  web/static/hud_rents.json  -> same payload as JSON

Covers all 58 CA counties, AMI tiers 20/30/35/40/45/50/55/60/70/80/100%
(official) plus a derived, clearly-flagged 110% (= 100% x 1.10), and bedroom
sizes studio/1-5 BR. All values are GROSS rent caps (include a utility
allowance); the proforma nets them by its Utility Allowance input.

Annual refresh: drop next year's rent_040125-equivalent PDF in source/, update
VINTAGE/SOURCE_URL below, and re-run:  python3 web/hud_rents/build_hud_rents.py

Requires `pdftotext` (poppler) on PATH.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_PDF = os.path.join(HERE, "source", "rent_040125.pdf")
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "static"))
OUT_JS = os.path.join(OUT_DIR, "hud_rents.js")
OUT_JSON = os.path.join(OUT_DIR, "hud_rents.json")

SOURCE = "California Tax Credit Allocation Committee (CTCAC) 2025 Maximum MTSP Rents for LIHTC Projects"
VINTAGE = "Projects placed in service on/after 4/1/2025 (per HUD 2025 income limits)"
SOURCE_URL = "https://www.treasurer.ca.gov/sites/default/files/2025-10/rent_040125.pdf"
YEAR = "2025"
GENERATED = "2026-06 build"

# All 58 California counties -> 5-digit FIPS (06 + county code).
CA_FIPS = {
    "ALAMEDA": "06001", "ALPINE": "06003", "AMADOR": "06005", "BUTTE": "06007",
    "CALAVERAS": "06009", "COLUSA": "06011", "CONTRA COSTA": "06013", "DEL NORTE": "06015",
    "EL DORADO": "06017", "FRESNO": "06019", "GLENN": "06021", "HUMBOLDT": "06023",
    "IMPERIAL": "06025", "INYO": "06027", "KERN": "06029", "KINGS": "06031",
    "LAKE": "06033", "LASSEN": "06035", "LOS ANGELES": "06037", "MADERA": "06039",
    "MARIN": "06041", "MARIPOSA": "06043", "MENDOCINO": "06045", "MERCED": "06047",
    "MODOC": "06049", "MONO": "06051", "MONTEREY": "06053", "NAPA": "06055",
    "NEVADA": "06057", "ORANGE": "06059", "PLACER": "06061", "PLUMAS": "06063",
    "RIVERSIDE": "06065", "SACRAMENTO": "06067", "SAN BENITO": "06069",
    "SAN BERNARDINO": "06071", "SAN DIEGO": "06073", "SAN FRANCISCO": "06075",
    "SAN JOAQUIN": "06077", "SAN LUIS OBISPO": "06079", "SAN MATEO": "06081",
    "SANTA BARBARA": "06083", "SANTA CLARA": "06085", "SANTA CRUZ": "06087",
    "SHASTA": "06089", "SIERRA": "06091", "SISKIYOU": "06093", "SOLANO": "06095",
    "SONOMA": "06097", "STANISLAUS": "06099", "SUTTER": "06101", "TEHAMA": "06103",
    "TRINITY": "06105", "TULARE": "06107", "TUOLUMNE": "06109", "VENTURA": "06111",
    "YOLO": "06113", "YUBA": "06115",
}

BEDS = ["studio", "br1", "br2", "br3", "br4", "br5"]  # Efficiency, 1-5 BR (PDF column order)

# Known-good values to assert against (from the official PDF / cross-checked file).
SPOTCHECKS = {
    "06037": ("80", "br1", 2272), "06037_100": ("100", "br1", 2840),
    "06073": ("80", "br1", 2481), "06001": ("100", "br3", 4154),
}


def pdf_to_text(pdf_path):
    try:
        return subprocess.check_output(["pdftotext", "-layout", pdf_path, "-"],
                                       text=True, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        sys.exit("pdftotext not found — install poppler (brew install poppler) and retry.")


def parse(text):
    counties = {}
    current = None
    tier_re = re.compile(r"^(\d+)%\s*Income\s*Level\s+(.*)$")
    money_re = re.compile(r"\$([\d,]+)")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key = line.upper()
        if key in CA_FIPS:                       # county header
            current = CA_FIPS[key]
            counties[current] = {
                "county": line.title() + " County, CA",
                "fips": current, "year": YEAR, "rents": {},
            }
            continue
        m = tier_re.match(line)
        if m and current:
            tier = m.group(1)
            amounts = [int(x.replace(",", "")) for x in money_re.findall(m.group(2))]
            if len(amounts) >= 4:                # need at least studio..3BR
                counties[current]["rents"][tier] = {
                    BEDS[i]: amounts[i] for i in range(min(len(amounts), len(BEDS)))
                }
    return counties


def add_derived_110(counties):
    # 110% is NOT an official CTCAC tier; derive = 100% x 1.10 (linear basis),
    # flagged so consumers can warn. Rounded to whole dollars like the source.
    for fips, c in counties.items():
        base = c["rents"].get("100")
        if base:
            c["rents"]["110"] = {b: round(v * 1.10) for b, v in base.items()}
    return counties


def validate(counties):
    errs = []
    for label, (tier, bed, expected) in SPOTCHECKS.items():
        fips = label.split("_")[0]
        got = counties.get(fips, {}).get("rents", {}).get(tier, {}).get(bed)
        if got != expected:
            errs.append(f"  {fips} {tier}% {bed}: expected {expected}, got {got}")
    missing = sorted(set(CA_FIPS.values()) - set(counties))
    if missing:
        errs.append(f"  missing counties: {len(missing)} -> {missing[:5]}…")
    for fips, c in counties.items():
        tiers = c["rents"]
        if "100" not in tiers or "80" not in tiers:
            errs.append(f"  {fips} missing core tiers")
        # linearity check the file claims: 80% should equal 0.80 x 100% (±$1 rounding)
        if "100" in tiers and "80" in tiers:
            exp = round(tiers["100"]["br1"] * 0.80)
            if abs(tiers["80"]["br1"] - exp) > 1:
                errs.append(f"  {fips} 80% br1 non-linear: {tiers['80']['br1']} vs {exp}")
    return errs


def main():
    if not os.path.exists(SRC_PDF):
        sys.exit(f"Source PDF not found: {SRC_PDF}")
    counties = add_derived_110(parse(pdf_to_text(SRC_PDF)))

    errs = validate(counties)
    if errs:
        print("VALIDATION FAILED:")
        print("\n".join(errs))
        sys.exit(1)

    payload = {
        "_meta": {
            "source": SOURCE, "vintage": VINTAGE, "sourceUrl": SOURCE_URL,
            "tiers": "Official CTCAC tiers 20-100%; 110% is derived = 100% x 1.10 (ami110Approx).",
            "grossVsNet": "GROSS caps (include utility allowance). The proforma applies its "
                          "Utility Allowance input to net them down.",
            "basis": "MTSP / LIHTC. NOT market rent, and differs from city CRL/SB341 or HCD "
                     "'Moderate' caps — use only for tax-credit/affordable underwriting.",
            "beds": "studio = Efficiency; br1..br5 = 1-5 bedroom.",
            "generated": GENERATED,
        },
        "counties": counties,
    }
    # SF 110% caveat carried over from the prior dataset.
    if "06075" in counties:
        counties["06075"]["ami110Note"] = (
            "A real 110% rent exists via SF MOHCD inclusionary/BMR on a DIFFERENT methodology "
            "(occupancy BR+1, MOHCD AMI hold-harmless) than the CTCAC basis used here. Switch "
            "to MOHCD figures only for MOHCD BMR deals.")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    with open(OUT_JS, "w") as f:
        f.write("// AUTO-GENERATED by web/hud_rents/build_hud_rents.py — do not edit by hand.\n")
        f.write(f"// {SOURCE}\n// Re-run the builder to refresh (annual ~April release).\n")
        f.write("window.HUD_RENTS = ")
        json.dump(payload, f, indent=2)
        f.write(";\n")

    n_tiers = len(next(iter(counties.values()))["rents"])
    print(f"OK — {len(counties)} CA counties, {n_tiers} AMI tiers (incl. derived 110%), "
          f"{len(BEDS)} bed sizes.")
    print(f"  {OUT_JS}")
    print(f"  {OUT_JSON}")
    print("Spot-checks passed: LA 80% 1BR=$2,272 / LA 100% 1BR=$2,840 / SD 80% 1BR=$2,481 / "
          "Alameda 100% 3BR=$4,154.")


if __name__ == "__main__":
    main()
