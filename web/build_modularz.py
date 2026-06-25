#!/usr/bin/env python3
"""
build_modularz.py — one-shot generator for web/templates/modularz.html

Unifies the two coworker prototypes:
  - LOOK  : Model_Z_Dashboard_4.html      (polished multi-tab live dashboard)
  - ENGINE: Model_Z_Engine_Final VF.html  (working Google Gemini chat backend)

It takes the Dashboard file verbatim (it already computes the full live
dashboard via its deterministic market DB) and makes three surgical edits:
  1. swap the broken Anthropic "AI bridge" for working Gemini calls
  2. add a site nav bar (Feasibility Study | ModularZ) + wrap the app shell
  3. inject the Gemini key from the Flask route ({{ gemini_key }})

Re-runnable: regenerates modularz.html from the source each time.
Usage:  python3 web/build_modularz.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.expanduser("~/Downloads")
SRC_DASH = os.path.join(DOWNLOADS, "Model_Z_Dashboard_4.html")
SRC_ENGINE = os.path.join(DOWNLOADS, "Model_Z_Engine_Final VF.html")
OUT = os.path.join(HERE, "templates", "modularz.html")


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def main():
    if not os.path.exists(SRC_DASH):
        sys.exit(f"Source not found: {SRC_DASH}")
    html = read(SRC_DASH)

    # ---- 1. AI BRIDGE: Anthropic (needs artifact runtime) -> Gemini -------
    new_bridge = r'''/* =====================================================================
   AI BRIDGE — Google Gemini (gemini-2.5-flash). Used when an unknown
   location or fuzzy command appears. Returns null on ANY failure so the
   deterministic market DB / regex parser remains the safety net.
   GEMINI_API_KEY is injected by the Flask route (client-side; see app.py).
   ===================================================================== */
async function geminiJSON(prompt) {
    if (!GEMINI_API_KEY) return null;
    try {
        const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                contents: [{ role: "user", parts: [{ text: prompt }] }],
                generationConfig: { temperature: 0.2, maxOutputTokens: 800, responseMimeType: "application/json" }
            })
        });
        if (!r.ok) throw new Error("Gemini HTTP " + r.status);
        const data = await r.json();
        const t = data && data.candidates && data.candidates[0] &&
                  data.candidates[0].content && data.candidates[0].content.parts &&
                  data.candidates[0].content.parts[0] && data.candidates[0].content.parts[0].text;
        if (!t) return null;
        const clean = t.replace(/```json\s*/gi, '').replace(/```\s*/g, '').trim();
        return JSON.parse(clean);
    } catch (e) { console.warn('Gemini unavailable', e.message); return null; }
}

async function aiResearchLocation(locationText) {
    const out = await geminiJSON(`You are a real estate development underwriting analyst. The user wants to underwrite a NEW-CONSTRUCTION multifamily project in: "${locationText}".

Return REALISTIC 2025-26 market comps as a JSON object only. No preamble.

Schema (every field required):
{
  "name": "Display name e.g. 'Sherman Oaks, CA'",
  "addr": "Address with zip",
  "zone": "Typical zoning",
  "rentPerUnit": 2500,
  "rentPerSf": 3.85,
  "cap": 0.0525,
  "hardCost": 290,
  "landPerSf": 95,
  "opex": 0.30,
  "rg3yr": 0.026,
  "comps": 12
}

Calibration guardrails:
- rentPerUnit: avg new Class B+ $/mo
- rentPerSf: $/SF/mo (implied unit size = rentPerUnit / rentPerSf, should be 550-900 SF)
- hardCost: $/GSF. Type V walkup $200-280, podium $280-340, high-rise $360+. Match typology to market.
- landPerSf: $/buildable GSF. Tertiary $25-50, mid $50-130, premium coastal $200-400.
- cap: 0.040-0.065. Premium coastal lower, tertiary higher.
- opex: 0.27-0.35 of EGI.

ONLY JSON, no explanation.`);
    return (out && out.rentPerUnit) ? out : null;
}

async function aiParseCommand(text) {
    return await geminiJSON(`Parse this real-estate underwriting command into a JSON change object.

Command: "${text}"

Current values: rentPerUnit=${model.rentPerUnit}, vacancy=${model.vacancy}, capRate=${model.capRate}, intRate=${model.intRate}, permLtc=${model.permLtc}, hardCostPerSf=${model.hardCostPerSf}, rentGrowth=${model.rentGrowth}, opexRatio=${model.opexRatio}, landCost=${model.landCost}, holdYears=${model.holdYears}, units=${model.units}.

Output JSON only:
{ "changes": { "paramId": newValue }, "description": "human-readable summary" }

Rules: percent fields stored as decimals (5% -> 0.05). Compute relative changes against current values. If no actionable change, return {"changes":{},"description":"unclear"}.`);
}

'''
    pattern = re.compile(
        r"/\* =+\n   OPTIONAL AI BRIDGE.*?\n(/\* =+\n   UNDERWRITING ENGINE)",
        re.DOTALL,
    )
    html, n = pattern.subn(lambda m: new_bridge + m.group(1), html)
    if n != 1:
        sys.exit(f"AI bridge replace matched {n} times (expected 1) — source changed?")

    # ---- 2. Inject the Gemini key const at the top of the main <script> ----
    key_line = '<script>\nconst GEMINI_API_KEY = "{{ gemini_key }}";\n'
    html, n = re.subn(
        r"<script>\n/\* =+\n   MODEL Z ENGINE",
        key_line + "/* =====================================================================\n   MODEL Z ENGINE",
        html,
        count=1,
    )
    if n != 1:
        sys.exit(f"key-const inject matched {n} times (expected 1) — source changed?")

    # ---- 3. Site nav bar + app-shell wrapper ------------------------------
    nav = '''<!-- Injected by build_modularz.py: cross-tool site navigation -->
<nav class="site-nav">
  <div class="site-nav-brand"><span class="snb-mark">SoLa Impact</span><span class="snb-sep">/</span><span class="snb-sub">Tools</span></div>
  <div class="site-nav-tools">
    <a href="/" class="snav-link">Feasibility Study</a>
    <a href="/modularz" class="snav-link active">ModularZ</a>
  </div>
  <a class="site-nav-out" href="/logout">Sign out</a>
</nav>
<div class="z-shell">
'''
    html, n = re.subn(r"<body>\n", "<body>\n" + nav, html, count=1)
    if n != 1:
        sys.exit(f"<body> nav inject matched {n} times (expected 1)")

    html, n = re.subn(r"</main>\n\n<script>",
                      "</main>\n</div><!-- /z-shell -->\n\n<script>",
                      html, count=1)
    if n != 1:
        sys.exit(f"</main> wrapper close matched {n} times (expected 1)")

    # ---- 4. Nav CSS + flex-column body override (appended before </style>) -
    nav_css = '''
/* ============== SITE NAV (cross-tool, injected) ============== */
body { flex-direction: column; }
.z-shell { flex: 1; display: flex; min-height: 0; overflow: hidden; }
.site-nav { display: flex; align-items: center; gap: 24px; flex-shrink: 0; height: 48px; padding: 0 20px; background: #1B2A4A; color: #fff; border-bottom: 3px solid #E0A237; font-family: var(--font-sans); }
.site-nav-brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; }
.site-nav-brand .snb-sep { color: #E0A237; }
.site-nav-brand .snb-sub { color: #cdd6e6; font-weight: 500; }
.site-nav-tools { display: flex; gap: 6px; }
.snav-link { color: #cdd6e6; text-decoration: none; font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 6px; transition: 0.15s; }
.snav-link:hover { background: rgba(255,255,255,0.08); color: #fff; }
.snav-link.active { background: #E0A237; color: #1B2A4A; }
.site-nav-out { margin-left: auto; color: #cdd6e6; text-decoration: none; font-size: 13px; }
.site-nav-out:hover { color: #fff; text-decoration: underline; }
.sensi-note { font-size: 10.5px; color: var(--text-muted); margin-top: 8px; font-style: italic; }
#affordability-panel select { font-family: var(--font-sans); font-size: 11.5px; border: 1px solid var(--border-strong); border-radius: 4px; padding: 2px 5px; background: var(--bg-subtle); color: var(--text-main); }
#affordability-panel .detail-list input { width: 88px; }
</style>'''
    html, n = re.subn(r"</style>", nav_css, html, count=1)
    if n != 1:
        sys.exit(f"nav CSS inject matched {n} times (expected 1)")

    # ---- 5. PROFORMA ENGINE: adopt the validated Engine template + mapping --
    # 5a. Swap the embedded workbook for the Engine file's (the validated one).
    if not os.path.exists(SRC_ENGINE):
        sys.exit(f"Source not found: {SRC_ENGINE}")
    eng = read(SRC_ENGINE)
    m = re.search(r'TEMPLATE_B64\s*=\s*"([A-Za-z0-9+/=]+)"', eng)
    if not m:
        sys.exit("Could not find TEMPLATE_B64 in the Engine file")
    engine_b64 = m.group(1)
    html, n = re.subn(
        r'(const PROFORMA_TEMPLATE_B64 = ")[A-Za-z0-9+/=]+(";)',
        lambda mm: mm.group(1) + engine_b64 + mm.group(2),
        html, count=1,
    )
    if n != 1:
        sys.exit(f"template swap matched {n} times (expected 1)")

    # 5b. Data-table helpers (ported from the Engine) so the .xlsx download can
    #     install the one sensitivity table the template ships un-installed.
    dt_helpers = '''function __dtColToIdx(col){let i=0;for(const c of col)i=i*26+(c.charCodeAt(0)-64);return i;}
function __dtIdxToCol(i){let s='';while(i>0){let r;r=(i-1)%26;i=Math.floor((i-1)/26);s=String.fromCharCode(r+65)+s;}return s;}
function installDataTable(xml, tl, ref, r1, r2) {
    const m = ref.match(/([A-Z]+)(\\d+):([A-Z]+)(\\d+)/);
    const c1=__dtColToIdx(m[1]), rs=+m[2], c2=__dtColToIdx(m[3]), re_=+m[4];
    const p = new RegExp('(<c r="'+tl+'"[^>]*?)(/>|>[\\\\s\\\\S]*?</c>)','');
    xml = xml.replace(p, (mm,a) => a.replace(/\\s*t="[^"]*"/,'') +
        '><f t="dataTable" ref="'+ref+'" dt2D="1" r1="'+r1+'" r2="'+r2+'"/><v>0</v></c>');
    for (let r=rs; r<=re_; r++) for (let c=c1; c<=c2; c++) {
        const cell=__dtIdxToCol(c)+r; if(cell===tl) continue;
        const q=new RegExp('(<c r="'+cell+'"[^>]*?)(/>|>[\\\\s\\\\S]*?</c>)','');
        xml=xml.replace(q,(mm,a)=>a.replace(/\\s*t="[^"]*"/,'')+'><v>0</v></c>');
    }
    return xml;
}

function excelDateSerial(d) {'''
    html, n = re.subn(r"function excelDateSerial\(d\) \{", lambda mm: dt_helpers, html, count=1)
    if n != 1:
        sys.exit(f"dt-helpers inject matched {n} times (expected 1)")

    # 5c. Replace buildInputPatches with a COMPLETE Engine-faithful mapping.
    new_patches = '''function modelToInp(model) {
    // Translate the dashboard's model into the Engine proforma's input schema.
    // Fields the model doesn't carry fall back to the Engine's own defaults so
    // the workbook receives exactly what the validated Engine build would write.
    const { line, city, state, zip } = parseAddressParts(model.address);
    let u1 = model.units1BR || 0, u2 = model.units2BR || 0, u3 = model.units3BR || 0;
    if (u1 + u2 + u3 !== (model.units || 0)) { u1 = model.units || 0; u2 = 0; u3 = 0; }
    const eff = model.efficiency || 0.82;
    const nrsf = model.nrsf || 0;
    const leaseMo = Math.max(1, model.leaseUpMonths || 6);
    return {
        address: line || (model.address || ''), city, state, zip,
        zoning: model.zoning || '',
        lotSF: model.lotSize || 0, lotLength: 0, lotWidth: 0,
        gsfBuilding: Math.round(nrsf / eff), nrsf,
        buildings: 1, podiumSF: 0, podiumLevels: 1,
        parkingStalls: Math.round((model.units || 0) * (model.parkingRatio || 0.75)),
        unit1br: u1, unit2br: u2, unit3br: u3, staircaseUnits: 0,
        preconMonths: model.preconMonths || 6,
        constrMonths: model.constructionMonths || 12,
        holdMonths: (model.holdYears || 5) * 12,
        leaseupPerMo: Math.max(1, Math.round((model.units || 1) / leaseMo)),
        vacancy: model.vacancy || 0.05,
        rentGrowth: model.rentGrowth || 0.025,
        costEscalation: model.escalationRate || 0.04,
        landCost: model.landCost || 0,
        onsiteCostPU: (model.onsiteCostPerUnit != null ? model.onsiteCostPerUnit : 90000),
        exitCap: model.capRate || 0.0675,
        constrLTC: model.constLtc || 0.70,
        constrRate: model.constRate || 0.09,
        permRate: model.intRate || 0.0575,         // Dashboard!K12 (input value cell)
        permLTV: model.permLtc || 0.75,            // closest the model carries (LTC->LTV)
        permDSCR: 1.20,
        permAmort: model.amort || 35
    };
}

// SINGLE SOURCE OF TRUTH for every input that flows into the proforma. Returns
// [{sheet, addr, value, isStr}] consumed by BOTH the in-browser HyperFormula
// engine and the .xlsx download, so the displayed returns and the downloaded
// workbook can never diverge. Mirrors the validated Engine build cell-for-cell.
function buildInputPatches(model) {
    const I = modelToInp(model);
    const P = [];
    const add = (sheet, addr, value, isStr) => P.push({ sheet, addr, value, isStr: !!isStr });
    const now = new Date();
    const diligSerial = excelDateSerial(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 6, 1)));

    // ----- Inputs sheet (sheet1) -----
    add('Inputs', 'D6', I.address, true);
    add('Inputs', 'D7', I.city, true);
    add('Inputs', 'D8', I.state, true);
    add('Inputs', 'D9', I.zip, true);
    add('Inputs', 'D12', I.zoning, true);
    add('Inputs', 'D13', I.lotSF);
    add('Inputs', 'D14', I.lotLength);
    add('Inputs', 'D15', I.lotWidth);
    add('Inputs', 'D16', I.gsfBuilding);
    add('Inputs', 'D17', I.nrsf);
    add('Inputs', 'O6', I.buildings);
    add('Inputs', 'O7', I.podiumSF);
    add('Inputs', 'O8', I.podiumLevels);
    add('Inputs', 'O9', I.parkingStalls);
    add('Inputs', 'O11', I.unit1br);
    add('Inputs', 'O12', I.unit2br);
    add('Inputs', 'O13', I.unit3br);
    add('Inputs', 'O15', I.staircaseUnits);
    add('Inputs', 'E20', diligSerial);
    add('Inputs', 'E23', I.preconMonths);
    add('Inputs', 'E30', I.leaseupPerMo);
    add('Inputs', 'L6', I.vacancy);
    add('Inputs', 'L9', I.costEscalation);
    // E26 = =Dashboard!W19 and L7 = =Dashboard!W21 are formulas — never overwrite.

    // ----- Dashboard sheet (sheet2): live model drivers -----
    add('Dashboard', 'W18', I.onsiteCostPU);
    add('Dashboard', 'W19', I.constrMonths);
    add('Dashboard', 'W20', I.holdMonths);
    add('Dashboard', 'W21', I.rentGrowth);
    add('Dashboard', 'J5', I.exitCap);
    add('Dashboard', 'J11', I.constrLTC);
    add('Dashboard', 'J12', I.constrRate);
    add('Dashboard', 'K12', I.permRate);

    // Sensitivity data-table AXIS CENTERS. The .xlsx what-if tables (Exit Cap x
    // Hold, Exit Cap x Rent Growth, etc.) center their axes on these cells; the
    // template hard-codes them to the baked deal (~6.75% cap, 84mo hold), so for
    // an off-baseline deal the Exit-Cap tables sit far above the deal's cap, the
    // IRR has no solution there, and IFERROR(...,0) renders the whole table as 0.
    // Recenter each axis on the deal's actual values (neighbors are formulas off
    // these centers, so writing the center recenters the axis).
    add('Dashboard', 'E19', I.constrRate);   // C20 table: interest-rate axis
    add('Dashboard', 'B22', I.constrLTC);    // C20 table: LTC axis
    add('Dashboard', 'M19', I.exitCap);      // K20 table: Exit Cap axis (x Hold)
    add('Dashboard', 'J22', I.holdMonths);   // K20 table: Hold axis
    add('Dashboard', 'E28', I.onsiteCostPU); // C29 table: onsite axis
    add('Dashboard', 'B31', I.constrMonths); // C29 table: construction-months axis
    add('Dashboard', 'M28', I.permRate);     // K29 table: perm-rate axis
    add('Dashboard', 'J31', I.holdMonths);   // K29 table: Hold axis
    add('Dashboard', 'E37', I.exitCap);      // C38 table: Exit Cap axis (x Rent Growth)
    add('Dashboard', 'B40', I.rentGrowth);   // C38 table: Rent Growth axis

    // ----- (Z+) Dev Budget sheet (sheet3) -----
    add('(Z+) Dev Budget', 'G7', I.landCost);
    // Modular construction cost per unit by bed type (the modular price book).
    add('(Z+) Dev Budget', 'E14', model.modCost1BR != null ? model.modCost1BR : 95000);
    add('(Z+) Dev Budget', 'E15', model.modCost2BR != null ? model.modCost2BR : 140000);
    add('(Z+) Dev Budget', 'E16', model.modCost3BR != null ? model.modCost3BR : 185000);

    // ----- (Z+) Financing sheet (sheet5) -----
    add('(Z+) Financing', 'D34', I.permLTV);
    add('(Z+) Financing', 'H11', I.permDSCR);
    add('(Z+) Financing', 'H21', I.permAmort);

    // ----- (Z+) Rent Roll: affordable (CTCAC AMI) rents + bed-mix allocation -----
    for (const ap of affRentRollPatches(model)) P.push(ap);

    return P;
}

// When an AMI tier is selected (affordable mode), drive the Rent Roll directly:
//  (1) allocate the deal's bed mix into the affordable rows 12/13/14/15
//      (1-BR/studio/2-BR/3-BR), overriding the template's studio-forced default;
//  (2) write the CTCAC net caps (gross cap minus utility allowance) as the
//      per-row rents (I = Voucher Pmt, K = Adj. Rents -> feed the K20 blended
//      rent that drives revenue).
// Returns [] in 'market' mode or when the county can't be resolved, leaving the
// template's existing (baked) behavior untouched.
function affRentRollPatches(model) {
    if (typeof window.HUD_RENTS === 'undefined') return [];
    const tierSel = document.getElementById('aff-tier');
    const tier = tierSel ? tierSel.value : 'market';
    if (tier === 'market') return [];
    const fips = (typeof affResolveFips === 'function') ? affResolveFips(model) : null;
    const c = fips ? HUD_RENTS.counties[fips] : null;
    if (!c || !c.rents[tier]) return [];
    const utilEl = document.getElementById('aff-util');
    const util = utilEl ? (parseFloat(utilEl.value) || 0) : 0;
    const r = c.rents[tier];
    const net = v => Math.max(0, Math.round((v || 0) - util));
    const RR = '(Z+) Rent Roll';
    const P = [];
    const add = (addr, val) => P.push({ sheet: RR, addr, value: val, isStr: false });
    let u1 = model.units1BR || 0, u2 = model.units2BR || 0, u3 = model.units3BR || 0;
    if (u1 + u2 + u3 !== (model.units || 0)) { u1 = model.units || 0; u2 = 0; u3 = 0; }
    // (1) allocation — all units into the affordable block by bed type; zero the
    //     rest (incl. row 7, a template base row that otherwise leaves a stray unit).
    ['E7', 'E8', 'E9', 'E10', 'E11', 'E16', 'E17', 'E18', 'E19'].forEach(a => add(a, 0));
    add('E12', u1); add('E13', 0); add('E14', u2); add('E15', u3);
    // (2) rents (net caps) by bed: row12=1BR, row13=studio, row14=2BR, row15=3BR.
    add('I12', net(r.br1)); add('K12', net(r.br1));
    add('I13', net(r.studio)); add('K13', net(r.studio));
    add('I14', net(r.br2)); add('K14', net(r.br2));
    add('I15', net(r.br3)); add('K15', net(r.br3));
    return P;
}'''
    html, n = re.subn(
        r"function buildInputPatches\(model\) \{.*?\n    return P;\n\}",
        lambda mm: new_patches,
        html, count=1, flags=re.DOTALL,
    )
    if n != 1:
        sys.exit(f"buildInputPatches replace matched {n} times (expected 1)")

    # 5d. Download: write the Financing sheet too, install the C29 data table,
    #     and force a full recalc on open (all per the validated Engine build).
    old_fileof = """    const FILE_OF = {
        'Inputs': 'xl/worksheets/sheet1.xml',
        'Dashboard': 'xl/worksheets/sheet2.xml',
        '(Z+) Dev Budget': 'xl/worksheets/sheet3.xml'
    };"""
    new_fileof = """    const FILE_OF = {
        'Inputs': 'xl/worksheets/sheet1.xml',
        'Dashboard': 'xl/worksheets/sheet2.xml',
        '(Z+) Dev Budget': 'xl/worksheets/sheet3.xml',
        '(Z+) Financing': 'xl/worksheets/sheet5.xml',
        '(Z+) Rent Roll': 'xl/worksheets/sheet6.xml'
    };"""
    if html.count(old_fileof) != 1:
        sys.exit("FILE_OF block not found uniquely")
    html = html.replace(old_fileof, new_fileof, 1)

    old_tail = """        for (const p of bySheet[sheet]) xml = patchCell(xml, p.addr, p.value, p.isStr);
        zip.file(file, xml);
    }
"""
    new_tail = old_tail + """
    // Install the one sensitivity data table the template ships un-installed,
    // then force Excel to recalc every formula on open (validated Engine steps).
    let __s2 = await zip.file('xl/worksheets/sheet2.xml').async('string');
    __s2 = installDataTable(__s2, 'C29', 'C29:G33', 'W18', 'W19');
    zip.file('xl/worksheets/sheet2.xml', __s2);
    let __wb = await zip.file('xl/workbook.xml').async('string');
    if (!/fullCalcOnLoad/.test(__wb)) {
        __wb = /<calcPr[^>]*\\/>/.test(__wb)
            ? __wb.replace(/<calcPr([^/]*)\\//, '<calcPr$1 fullCalcOnLoad="1"/')
            : __wb.replace('</workbook>', '<calcPr fullCalcOnLoad="1"/></workbook>');
    }
    zip.file('xl/workbook.xml', __wb);
"""
    if html.count(old_tail) != 1:
        sys.exit("download patch-loop tail not found uniquely")
    html = html.replace(old_tail, new_tail, 1)

    # 5e. Fix the swapped YoC/CoC metric cells. Per the proforma formulas:
    #   K8  = (Z+) OpEx!G39 = (NOI + IPMT debt interest)/equity  -> levered cash-on-cash
    #   K11 = (Z+) OpEx!J38 = NOI / TDC                          -> yield on cost
    # The Dashboard had them reversed (yoc<-K8, coc<-K11), which overstated the
    # negative dev spread. Point yoc->K11 and coc->K8.
    old_metrics = ("            coc: __engineNum(hf, '(Z+) Financing', 'K11'),  // stabilized cash-on-cash\n"
                   "            yoc: __engineNum(hf, '(Z+) Financing', 'K8'),   // going-in return on cost")
    new_metrics = ("            coc: __engineNum(hf, '(Z+) Financing', 'K8'),   // levered cash-on-cash: (NOI - debt svc)/equity\n"
                   "            yoc: __engineNum(hf, '(Z+) Financing', 'K11'),  // yield on cost: NOI / TDC")
    if html.count(old_metrics) != 1:
        sys.exit("YoC/CoC metric lines not found uniquely")
    html = html.replace(old_metrics, new_metrics, 1)

    # ---- 6. SENSITIVITY GRID + CHAT on the Excel engine ---------------------
    # 6a. Rename the original JS grid builder, add an Excel-engine dispatcher.
    #     Returns (Cap×RG→IRR) and Finance (LTC×Int→CoC) use HyperFormula so they
    #     agree with the tiles+download. Revenue/Rent stays JS (rent isn't a
    #     proforma input — see RENT_ROLL_HANDOFF.md) and is labeled as such.
    grid_dispatch = '''let __sensiTimer = null;

// Excel-engine sensitivity: build the workbook once, then mutate the two axis
// input cells per matrix cell and re-read the result (setCellContents recomputes).
function buildSensiEngine() {
    const container = document.getElementById('sensi-container');
    let hf = null;
    try {
        hf = __buildEngine(model);
        const sid = hf.getSheetId('(Z+) Monthly CF');
        const cF = __colToIdx('F'), cDM = __colToIdx('DM');
        const toNum = v => { if (v instanceof Date) return Math.round((Date.UTC(v.getFullYear(), v.getMonth(), v.getDate()) - Date.UTC(1899, 11, 30)) / 86400000); return (typeof v === 'number') ? v : null; };
        const setCell = (sheet, a1, val) => { const s = hf.getSheetId(sheet); const ad = XLSX.utils.decode_cell(a1); hf.setCellContents({ sheet: s, row: ad.r, col: ad.c }, [[val]]); };
        const leveredIRR = () => { const dates = [], vals = []; for (let c = cF; c <= cDM; c++) { dates.push(toNum(hf.getCellValue({ sheet: sid, row: 3, col: c }))); const vv = hf.getCellValue({ sheet: sid, row: 99, col: c }); vals.push(typeof vv === 'number' ? vv : 0); } return __xirr(vals, dates); };
        let html = '';
        if (activeSensi === 'returns') {
            const capSteps = [-0.0075, -0.0025, 0, 0.0025, 0.0075];
            const rgSteps = [-0.01, -0.005, 0, 0.005, 0.01];
            html = '<table class="sensi-table"><thead><tr><th class="corner">Levered IRR<br>Cap × Rent Growth</th>';
            rgSteps.forEach(rg => html += `<th>RG ${fPct(model.rentGrowth + rg, 2)}</th>`);
            html += '</tr></thead><tbody>';
            capSteps.forEach(capD => {
                const c = model.capRate + capD; setCell('Dashboard', 'J5', c);
                html += `<tr><td class="y-axis">Cap ${fPct(c)}</td>`;
                rgSteps.forEach(rgD => {
                    const r = model.rentGrowth + rgD; setCell('Dashboard', 'W21', r);
                    const irr = leveredIRR();
                    html += `<td class="${capD === 0 && rgD === 0 ? 'target' : ''}">${irr == null ? '—' : fPct(irr, 1)}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
        } else if (activeSensi === 'finance') {
            const ltcSteps = [-0.10, -0.05, 0, 0.05, 0.10];
            const intSteps = [-0.0075, -0.0025, 0, 0.0025, 0.0075];
            html = '<table class="sensi-table"><thead><tr><th class="corner">Cash-on-Cash<br>LTC × Interest</th>';
            intSteps.forEach(i => html += `<th>${fPct(model.intRate + i)}</th>`);
            html += '</tr></thead><tbody>';
            ltcSteps.forEach(lD => {
                const lv = Math.max(0.2, Math.min(0.85, model.permLtc + lD)); setCell('(Z+) Financing', 'D34', lv);
                html += `<tr><td class="y-axis">${fPct(lv, 0)} LTC</td>`;
                intSteps.forEach(iD => {
                    const iv = model.intRate + iD; setCell('Dashboard', 'K12', iv);
                    const coc = __engineNum(hf, '(Z+) Financing', 'K8');
                    html += `<td class="${lD === 0 && iD === 0 ? 'target' : ''}">${coc == null ? '—' : fPct(coc, 1)}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
        }
        container.innerHTML = html;
    } catch (e) { console.warn('sensi engine failed, JS fallback:', e && e.message); buildSensiTableJS(); }
    finally { if (hf) { try { hf.destroy(); } catch (e) {} } }
}

// Dispatcher: Excel engine for returns/finance; JS for revenue (rent not modeled).
function buildSensiTable() {
    const container = document.getElementById('sensi-container');
    if (!model.units || !model.nrsf || !model.rentPerUnit) {
        container.innerHTML = "<div class='sensi-empty'>Awaiting project data — initialize with the chat or load a sample.</div>";
        return;
    }
    if (activeSensi === 'revenue' || !__engineReady()) {
        buildSensiTableJS();
        if (activeSensi === 'revenue') {
            const cap = document.createElement('div'); cap.className = 'sensi-note';
            cap.textContent = 'Quick estimate — rent isn\\'t a proforma input yet, so this tab uses the JS model (not the institutional workbook).';
            container.appendChild(cap);
        }
        return;
    }
    if (!container.querySelector('table')) container.innerHTML = "<div class='sensi-empty'>Computing institutional grid…</div>";
    clearTimeout(__sensiTimer);
    __sensiTimer = setTimeout(buildSensiEngine, 180);
}

function buildSensiTableJS() {'''
    html, n = re.subn(r"function buildSensiTable\(\) \{", lambda mm: grid_dispatch, html, count=1)
    if n != 1:
        sys.exit(f"buildSensiTable rename matched {n} times (expected 1)")

    # 6b. Chat "what's the IRR" → Excel engine when available (falls back to JS).
    old_chat = "        const r = runUnderwriting(model); if (!r) return;\n        addMsg(`Here's where we stand:"
    new_chat = ("        const r = ((typeof computeEngineReturns === 'function' && __engineReady()) ? computeEngineReturns(model) : null) || runUnderwriting(model);\n"
                "        if (!r) return;\n"
                "        if (r.avgCoc == null) r.avgCoc = r.coc;\n"
                "        addMsg(`Here's where we stand:")
    if html.count(old_chat) != 1:
        sys.exit("chat IRR block not found uniquely")
    html = html.replace(old_chat, new_chat, 1)

    # ---- 6c. IRR sanity clamp: __xirr can blow up (e.g. 1e278%) when equity is
    #     ~wiped on a catastrophic deal. Treat non-finite / absurd (|IRR|>1000%)
    #     as null so the tile/grid show "—" instead of garbage.
    old_irr = "            irr: irrLev, irrUn,"
    new_irr = ("            irr: (isFinite(irrLev) && Math.abs(irrLev) <= 10) ? irrLev : null,\n"
               "            irrUn: (isFinite(irrUn) && Math.abs(irrUn) <= 10) ? irrUn : null,")
    if html.count(old_irr) != 1:
        sys.exit("IRR clamp anchor (computeEngineReturns) not found uniquely")
    html = html.replace(old_irr, new_irr, 1)

    old_grid_irr = "return __xirr(vals, dates); };"
    new_grid_irr = "const __ir = __xirr(vals, dates); return (isFinite(__ir) && Math.abs(__ir) <= 10) ? __ir : null; };"
    if html.count(old_grid_irr) != 1:
        sys.exit("IRR clamp anchor (grid) not found uniquely")
    html = html.replace(old_grid_irr, new_grid_irr, 1)

    # ---- 6d. Stabilized NOI tile: auto-scale to $M when >= $1M (was always "K",
    #     so $1.66M rendered as "$1664K"). Small (affordable) NOIs stay in "K".
    helper_anchor = "const fPct = (v, d = 2) =>"
    helper_def = ("const fMoneyMK = v => (v != null && Math.abs(v) >= 1e6) ? fMoneyM(v) : fMoneyK(v);\n"
                  "const fPct = (v, d = 2) =>")
    if html.count(helper_anchor) != 1:
        sys.exit("fMoneyMK helper anchor not found uniquely")
    html = html.replace(helper_anchor, helper_def, 1)

    for old_noi, label in [("noi: fMoneyK(res.noi),", "updateUI"),
                           ("set('noi', fMoneyK(k.noi));", "applyEngineKPIs")]:
        if html.count(old_noi) != 1:
            sys.exit(f"NOI formatter anchor ({label}) not found uniquely")
        html = html.replace(old_noi, old_noi.replace("fMoneyK", "fMoneyMK"), 1)

    # ---- 7. AFFORDABILITY (CTCAC AMI rents) preview — Workstreams B/C/E ------
    # 7a. Load the generated data layers (rents + ZIP->county crosswalk) before
    #     the main script. Served from Flask's /static.
    scripts = ('<script src="/static/hud_rents.js"></script>\n'
               '<script src="/static/ca_zip_county.js"></script>\n'
               '<script>\nconst GEMINI_API_KEY = "{{ gemini_key }}";')
    anchor = '<script>\nconst GEMINI_API_KEY = "{{ gemini_key }}";'
    if html.count(anchor) != 1:
        sys.exit("affordability script-tag anchor not found uniquely")
    html = html.replace(anchor, scripts, 1)

    # 7b. Affordability panel in the Backend tab (before the dark help panel).
    aff_panel = '''<div class="backend-panel" id="affordability-panel">
                <h4>Affordability — CTCAC AMI Rents</h4>
                <ul class="detail-list">
                    <li><span>County (from ZIP)</span><span id="aff-county">—</span></li>
                    <li><span>AMI tier</span><select id="aff-tier" onchange="applyAffordability()">
                        <option value="market">Market (use comp rent)</option>
                        <option value="110">110% AMI (approx)</option>
                        <option value="100">100% AMI</option>
                        <option value="80" selected>80% AMI</option>
                        <option value="60">60% AMI</option>
                        <option value="50">50% AMI</option>
                        <option value="40">40% AMI</option>
                        <option value="30">30% AMI</option>
                    </select></li>
                    <li><span>Utility allowance /unit/mo</span><input type="number" id="aff-util" min="0" value="0" oninput="applyAffordability()"></li>
                    <li><span>1-BR cap (net)</span><span id="aff-br1">—</span></li>
                    <li><span>2-BR cap (net)</span><span id="aff-br2">—</span></li>
                    <li><span>3-BR cap (net)</span><span id="aff-br3">—</span></li>
                    <li><span>Blended cap</span><span id="aff-blended">—</span></li>
                </ul>
                <p style="font-size: 10.5px; color: var(--text-muted); margin-top: 6px;">CTCAC 2025 MTSP gross caps, netted by the utility allowance. <b>Drives the proforma</b> — units are allocated by bed mix and these rents feed NOI/IRR + the download. Choose <i>Market</i> to use the comp rent instead.</p>
            </div>

            <div class="backend-panel" style="background: var(--bg-deep); color: white; border-color: var(--bg-deep);">'''
    dark_anchor = '<div class="backend-panel" style="background: var(--bg-deep); color: white; border-color: var(--bg-deep);">'
    if html.count(dark_anchor) != 1:
        sys.exit("affordability panel anchor not found uniquely")
    html = html.replace(dark_anchor, aff_panel, 1)

    # 7c. Affordability logic (uses window.HUD_RENTS + window.CA_ZIP_COUNTY).
    aff_js = '''/* ===== Affordability — CTCAC AMI rents (data: window.HUD_RENTS + window.CA_ZIP_COUNTY) ===== */
function affResolveFips(model) {
    const m = (model.address || '').match(/\\b(9\\d{4})\\b/);          // ZIP from the deal address
    if (m && window.CA_ZIP_COUNTY && CA_ZIP_COUNTY[m[1]]) return CA_ZIP_COUNTY[m[1]];
    if (model.countyFips && window.HUD_RENTS && HUD_RENTS.counties[model.countyFips]) return model.countyFips;
    return null;
}
function updateAffordability() {
    const panel = document.getElementById('affordability-panel');
    if (!panel || typeof window.HUD_RENTS === 'undefined') return;
    const tierSel = document.getElementById('aff-tier');
    const utilEl = document.getElementById('aff-util');
    const tier = tierSel ? tierSel.value : '80';
    const util = utilEl ? (parseFloat(utilEl.value) || 0) : 0;
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    const fips = affResolveFips(model);
    const c = fips ? HUD_RENTS.counties[fips] : null;
    set('aff-county', c ? c.county : (model.address ? 'Outside CA coverage' : '—'));
    if (!c || tier === 'market') {
        ['aff-br1', 'aff-br2', 'aff-br3'].forEach(id => set(id, '—'));
        set('aff-blended', (c && tier === 'market') ? 'Market (uses comp rent)' : '—');
        return;
    }
    const r = c.rents[tier];
    if (!r) { ['aff-br1', 'aff-br2', 'aff-br3', 'aff-blended'].forEach(id => set(id, '—')); return; }
    const net = v => Math.max(0, Math.round(v - util));
    set('aff-br1', fMoney(net(r.br1)));
    set('aff-br2', fMoney(net(r.br2)));
    set('aff-br3', fMoney(net(r.br3)));
    const u1 = model.units1BR || model.units || 0, u2 = model.units2BR || 0, u3 = model.units3BR || 0;
    const tot = (u1 + u2 + u3) || 1;
    const blended = Math.round((u1 * net(r.br1) + u2 * net(r.br2) + u3 * net(r.br3)) / tot);
    set('aff-blended', fMoney(blended) + ' /unit/mo');
}

// Changing the AMI tier / utility allowance refreshes the preview AND recomputes
// the proforma (buildInputPatches reads these controls), so tiles + grids + the
// download all reflect the selected affordable rents.
function applyAffordability() {
    updateAffordability();
    if (typeof scheduleEngine === 'function') scheduleEngine();
    if (typeof buildSensiTable === 'function') buildSensiTable();
}

function renderDeltas(res) {'''
    if html.count("function renderDeltas(res) {") != 1:
        sys.exit("renderDeltas anchor not found uniquely")
    html = html.replace("function renderDeltas(res) {", aff_js, 1)

    # 7d. Refresh the panel on every model change (central updateUI hook).
    old_hook = "    // Sensitivity\n    buildSensiTable();\n}"
    new_hook = "    // Sensitivity\n    buildSensiTable();\n    try { updateAffordability(); } catch (e) {}\n}"
    if html.count(old_hook) != 1:
        sys.exit("updateUI hook anchor not found uniquely")
    html = html.replace(old_hook, new_hook, 1)

    # ---- 8. COST MODEL: modular price book + land as residual to $350K/unit ---
    #     Construction is fixed by the modular $/unit price book; land becomes the
    #     derived "max supportable purchase price" so the team negotiates on land.
    # 8a. STATE defaults (the initial model object).
    old_state = ("    modCost1BR: 90000,   // proforma defaults\n"
                 "    modCost2BR: 160000,\n"
                 "    modCost3BR: 180000,\n"
                 "    onsiteCostPerUnit: 90000,")
    new_state = ("    modCost1BR: 95000,   // modular price book (total construction $/unit by bed)\n"
                 "    modCost2BR: 140000,\n"
                 "    modCost3BR: 185000,\n"
                 "    onsiteCostPerUnit: 0,   // construction captured fully in the modular $/unit above")
    if html.count(old_state) != 1:
        sys.exit("STATE cost defaults anchor not found uniquely")
    html = html.replace(old_state, new_state, 1)

    # 8b. loadDeal cost defaults: modular price book, onsite folded in (=0).
    old_ld_cost = ("        onsiteCostPerUnit: Math.max(40000, Math.round((m.hardCost * gsf - units * 90000 - units * 1500) / (units * 1.03))),\n"
                   "        modCost1BR: 90000, modCost2BR: 160000, modCost3BR: 180000,")
    new_ld_cost = ("        onsiteCostPerUnit: 0,\n"
                   "        modCost1BR: 95000, modCost2BR: 140000, modCost3BR: 185000,")
    if html.count(old_ld_cost) != 1:
        sys.exit("loadDeal cost defaults anchor not found uniquely")
    html = html.replace(old_ld_cost, new_ld_cost, 1)

    # 8c. Residual-land helper (max supportable purchase price at a target PPU).
    residual_helper = '''// Back-solve the land cost that brings all-in dev cost to targetPPU per unit, using
// the proforma engine (TDC is ~linear in land). Returns the max supportable land
// ("residual" / max purchase price), clamped >= 0, or null if the engine isn't ready.
function __residualLandForPPU(targetPPU) {
    if (typeof computeEngineReturns !== 'function' || typeof __engineReady !== 'function' || !__engineReady() || !model.units) return null;
    const tdcAt = (L) => { const e = computeEngineReturns({ ...model, landCost: L }); return e ? e.tdc : null; };
    const L1 = Math.max(1e6, model.landCost || 1e6), L2 = L1 * 0.5;
    const t1 = tdcAt(L1), t2 = tdcAt(L2);
    if (t1 == null || t2 == null || t1 === t2) return null;
    const slope = (t1 - t2) / (L1 - L2), intercept = t1 - slope * L1;
    const land = (targetPPU * model.units - intercept) / slope;
    return (isFinite(land)) ? Math.max(0, Math.round(land)) : null;
}

function loadDeal(m, units) {'''
    if html.count("function loadDeal(m, units) {") != 1:
        sys.exit("loadDeal anchor not found uniquely")
    html = html.replace("function loadDeal(m, units) {", residual_helper, 1)

    # 8d. In loadDeal, set land to the residual (max supportable) before snapshot.
    old_snap = ("    snapshot = runUnderwriting(model);\n\n"
                "    document.getElementById('projName').innerHTML = m.name;")
    new_snap = ("    // Land defaults to the MAX supportable purchase price at the target $/unit all-in —\n"
                "    // construction is fixed by the modular price book, so land is the lever.\n"
                "    try { const __rl = __residualLandForPPU(model.targetPPU || 350000); if (__rl != null) { model.landCost = __rl; __maxLand = __rl; } } catch (e) {}\n"
                "    snapshot = runUnderwriting(model);\n\n"
                "    document.getElementById('projName').innerHTML = m.name;")
    if html.count(old_snap) != 1:
        sys.exit("loadDeal snapshot anchor not found uniquely")
    html = html.replace(old_snap, new_snap, 1)

    # 8e. Market-research message: label the comp land as market asking (the modeled
    #     land is the residual, shown in the Backend), to avoid a contradictory total.
    old_landline = '<div class="data-line"><span>Land Basis</span><span>$${m.landPerSf}/buildable SF (~$${(landCost/1e6).toFixed(1)}M)</span></div>'
    new_landline = '<div class="data-line"><span>Market Land (asking)</span><span>$${m.landPerSf}/buildable SF</span></div>\n        <div class="data-line"><span>Modeled Land</span><span>max @ $${Math.round((model.targetPPU||350000)/1000)}K/unit · see Backend</span></div>'
    if html.count(old_landline) != 1:
        sys.exit("loadDeal land-basis message anchor not found uniquely")
    html = html.replace(old_landline, new_landline, 1)

    # ---- 9. LIVE "Land x Cap" sensitivity + tidy the dead Excel onsite table ---
    # 9a. Add the tab FIRST + active (purchase price is the primary lever now).
    old_tab = '<button class="sensi-tab active" data-sensi="returns" onclick="switchSensi(\'returns\')">Returns</button>'
    new_tab = ('<button class="sensi-tab active" data-sensi="land" onclick="switchSensi(\'land\')">Land × Cap</button>\n'
               '                        <button class="sensi-tab" data-sensi="returns" onclick="switchSensi(\'returns\')">Returns</button>')
    if html.count(old_tab) != 1:
        sys.exit("sensi-tab returns button anchor not found uniquely")
    html = html.replace(old_tab, new_tab, 1)
    # Default the active sensitivity view to Land × Cap.
    if html.count("let activeSensi = 'returns';") != 1:
        sys.exit("activeSensi default anchor not found uniquely")
    html = html.replace("let activeSensi = 'returns';", "let activeSensi = 'land';", 1)

    # ---- 10. LAND PURCHASE PRICE on the Dashboard: a max-price DISPLAY plus a
    #     combined $-field + %-of-max ADJUSTMENT lever (two separate mechanisms).
    #     Land is now the primary point of analysis for modular deals, so both the
    #     ceiling (max supportable @ $350K/unit) and the live knob live up front on
    #     the Dashboard tab rather than buried in the Backend.
    # 10a. Cache the residual so the lever's 100% anchor + the display are stable
    #      across redraws (the residual is invariant to the land lever itself).
    if html.count("let __engineKPIs = null;     // last computed return block") != 1:
        sys.exit("__engineKPIs decl anchor not found uniquely")
    html = html.replace(
        "let __engineKPIs = null;     // last computed return block",
        "let __engineKPIs = null;     // last computed return block\n"
        "let __maxLand = null;        // cached max supportable land @ $350K/unit (residual, total $)",
        1,
    )

    # 10b. UI: max-price display box + combined land lever, injected at the TOP of
    #      the Interactive Levers panel (above the rate/vacancy sliders).
    levers_anchor = '<div class="panel-header"><span>Interactive Levers</span><span class="badge">Live</span></div>'
    land_ui = levers_anchor + '''

                <!-- MAX LAND PRICE DISPLAY (mechanism 1): read-only ceiling -->
                <div class="maxland-box" id="maxland-box" title="The highest land price that still hits the all-in cost-per-unit target. Buy at or below this and the deal pencils (dev spread >= 0); pay more and returns go negative. Change the target in the Backend tab (Hard Costs).">
                    <div class="maxland-label">Max Land Price <span class="maxland-sub">to pencil @ <span id="maxland-target">$350K</span>/unit</span></div>
                    <div class="maxland-figs"><span class="maxland-val" id="maxland-val">&mdash;</span><span class="maxland-pu" id="maxland-pu"></span></div>
                </div>

                <!-- LAND PURCHASE PRICE LEVER (mechanism 2): $ field + %-of-max slider, kept in sync -->
                <div class="lever-group lever-land">
                    <div class="lever-header"><span>Land Purchase Price</span><span class="lever-val" id="val-land">&mdash;</span></div>
                    <div class="land-dollar-row"><span class="land-dollar-prefix">$</span><input type="text" inputmode="numeric" id="inp-land-dollar" oninput="updateLandFromDollar()" onblur="renderLandLever()" placeholder="land $"><span class="land-pu" id="land-pu"></span></div>
                    <input type="range" id="inp-land" min="0" max="120" step="1" value="100" oninput="updateLandFromSlider()">
                    <div class="lever-range"><span>$0</span><span class="land-mark">max</span><span>120%</span></div>
                </div>'''
    if html.count(levers_anchor) != 1:
        sys.exit("Interactive Levers panel-header anchor not found uniquely")
    html = html.replace(levers_anchor, land_ui, 1)

    # 10c. CSS for the display box + combined lever (re-uses the existing palette).
    land_css = '''
/* ============== LAND PRICE — max-price display + combined lever (injected) ============== */
.maxland-box { display: flex; flex-direction: column; gap: 1px; background: linear-gradient(180deg, rgba(224,162,55,0.13), rgba(224,162,55,0.03)); border: 1px solid var(--accent); border-radius: 6px; padding: 7px 10px; margin-bottom: 12px; }
.maxland-label { font-size: 10px; font-weight: 700; letter-spacing: .03em; text-transform: uppercase; color: var(--text-muted); }
.maxland-sub { font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--text-faint); }
.maxland-figs { display: flex; align-items: baseline; gap: 8px; }
.maxland-val { font-family: var(--font-mono); font-size: 18px; font-weight: 700; line-height: 1.1; color: var(--accent); }
.maxland-pu { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.lever-land { padding-bottom: 11px; margin-bottom: 11px; border-bottom: 1px solid var(--border); }
.land-dollar-row { display: flex; align-items: center; gap: 5px; margin-bottom: 6px; }
.land-dollar-prefix { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); }
.land-dollar-row input { flex: 1; min-width: 0; font-family: var(--font-mono); font-size: 12px; border: 1px solid var(--border-strong); border-radius: 4px; padding: 3px 6px; background: var(--bg-subtle); color: var(--text-main); }
.land-dollar-row input:focus { outline: none; border-color: var(--accent); }
.land-pu { font-family: var(--font-mono); font-size: 10px; color: var(--text-faint); white-space: nowrap; }
.lever-land .lever-range .land-mark { color: var(--accent); }
</style>'''
    if html.count("</style>") != 1:
        sys.exit("land CSS </style> anchor not found uniquely")
    html = html.replace("</style>", land_css, 1)

    # 10d. Logic: the display + the combined lever. Both write model.landCost and
    #      recompute; the % normalizes across deal sizes (100% = max), the $ field
    #      links straight to the actual purchase price. Injected before
    #      updateModelFromUI (the other Dashboard-lever handler).
    land_js = '''const fLandDollar = v => (v || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });

// MECHANISM 1 — read-only ceiling: the max supportable land at $350K/unit all-in.
function renderMaxLandDisplay() {
    const el = document.getElementById('maxland-val'); if (!el) return;
    const pu = document.getElementById('maxland-pu');
    const tgt = document.getElementById('maxland-target');
    if (tgt) tgt.textContent = '$' + Math.round((model.targetPPU || 350000) / 1000) + 'K';
    if (__maxLand == null || !model.units) { el.textContent = '\\u2014'; if (pu) pu.textContent = __engineReady() ? '' : 'computing\\u2026'; return; }
    el.textContent = fMoneyM(__maxLand);
    if (pu) pu.textContent = '$' + Math.round(__maxLand / model.units / 1000) + 'K/unit';
}

// MECHANISM 2 — combined lever: sync the $ field + the %-of-max slider to landCost.
function renderLandLever() {
    const slider = document.getElementById('inp-land'); if (!slider) return;
    const dollar = document.getElementById('inp-land-dollar');
    const pctEl = document.getElementById('val-land');
    const puEl = document.getElementById('land-pu');
    const land = model.landCost || 0;
    if (!model.units || !land) {
        slider.value = 100;
        if (pctEl) pctEl.textContent = '\\u2014';
        if (dollar && document.activeElement !== dollar) dollar.value = land ? fLandDollar(land) : '';
        if (puEl) puEl.textContent = '';
        return;
    }
    const max = (__maxLand && __maxLand > 0) ? __maxLand : land;
    const pct = (land / max) * 100;
    slider.value = Math.max(0, Math.min(120, pct));
    if (pctEl) pctEl.textContent = (__maxLand && __maxLand > 0) ? Math.round(pct) + '% of max' : fMoneyM(land);
    if (dollar && document.activeElement !== dollar) dollar.value = fLandDollar(Math.round(land));
    if (puEl) puEl.textContent = '$' + Math.round(land / model.units / 1000) + 'K/unit';
}

// Slider drag -> land = pct of the cached max (relative, deal-size-agnostic).
function updateLandFromSlider() {
    const pct = parseFloat(document.getElementById('inp-land').value) || 0;
    const max = (__maxLand && __maxLand > 0) ? __maxLand : (model.landCost || 0);
    model.landCost = Math.round(max * pct / 100);
    const be = document.getElementById('be-land'); if (be) be.value = model.landCost || '';
    updateUI();
}

// $ field edit -> land = the exact figure typed (dynamic, linked to purchase price).
function updateLandFromDollar() {
    const v = parseFloat((document.getElementById('inp-land-dollar').value + '').replace(/[^0-9.]/g, '')) || 0;
    model.landCost = Math.round(v);
    const be = document.getElementById('be-land'); if (be) be.value = model.landCost || '';
    updateUI();
}

function updateModelFromUI() {'''
    if html.count("function updateModelFromUI() {") != 1:
        sys.exit("updateModelFromUI anchor (land js inject) not found uniquely")
    html = html.replace("function updateModelFromUI() {", land_js, 1)

    # 10e. Keep both mechanisms live: sync them on every redraw (cached value, cheap)
    #      and recompute the residual when the engine recomputes the KPIs.
    old_uihook = "    document.getElementById('inp-ltc').value = model.permLtc * 100;"
    new_uihook = (old_uihook + "\n"
                  "    renderMaxLandDisplay();\n"
                  "    renderLandLever();")
    if html.count(old_uihook) != 1:
        sys.exit("updateUI land render hook anchor not found uniquely")
    html = html.replace(old_uihook, new_uihook, 1)

    old_sched = ("        __engineKPIs = computeEngineReturns(model);\n"
                 "        applyEngineKPIs();")
    new_sched = (old_sched + "\n"
                 "        try { const __ml = __residualLandForPPU(model.targetPPU || 350000); if (__ml != null) __maxLand = __ml; } catch (e) {}\n"
                 "        renderMaxLandDisplay();\n"
                 "        renderLandLever();")
    if html.count(old_sched) != 1:
        sys.exit("scheduleEngine residual-recompute anchor not found uniquely")
    html = html.replace(old_sched, new_sched, 1)

    # 9b. Engine branch: Levered IRR over Land $/unit (vary Dev Budget!G7) x Exit
    #     Cap (vary Dashboard!J5). The in-browser engine varies cells across sheets
    #     freely (no Excel data-table same-sheet limit), so land works here.
    land_branch = '''            html += '</tbody></table>';
        } else if (activeSensi === 'land') {
            const capSteps = [-0.0075, -0.0025, 0, 0.0025, 0.0075];
            const landSteps = [-50000, -25000, 0, 25000, 50000];   // $/unit around current
            const basePU = (model.landCost || 0) / (model.units || 1);
            html = '<table class="sensi-table"><thead><tr><th class="corner">Levered IRR<br>Land/unit × Exit Cap</th>';
            capSteps.forEach(c => html += `<th>Cap ${fPct(model.capRate + c)}</th>`);
            html += '</tr></thead><tbody>';
            landSteps.forEach(ls => {
                const lpu = Math.max(0, basePU + ls);
                setCell('(Z+) Dev Budget', 'G7', lpu * (model.units || 0));
                html += `<tr><td class="y-axis">$${Math.round(lpu / 1000)}K/u</td>`;
                capSteps.forEach(c => {
                    setCell('Dashboard', 'J5', model.capRate + c);
                    const irr = leveredIRR();
                    html += `<td class="${ls === 0 && c === 0 ? 'target' : ''}">${irr == null ? '—' : fPct(irr, 1)}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
        }
        container.innerHTML = html;'''
    old_engine_end = "            html += '</tbody></table>';\n        }\n        container.innerHTML = html;"
    if html.count(old_engine_end) != 1:
        sys.exit("buildSensiEngine finance-branch end anchor not found uniquely")
    html = html.replace(old_engine_end, land_branch, 1)

    # 9c. Tidy the download: don't install the vestigial onsite data table
    #     (construction is folded into the modular price book); blank its body.
    old_install = "    __s2 = installDataTable(__s2, 'C29', 'C29:G33', 'W18', 'W19');"
    new_install = ("    // Onsite sensitivity table is vestigial (construction folded into the modular\n"
                   "    // price book) — blank it instead of installing a misleading what-if.\n"
                   "    for (let __r = 29; __r <= 33; __r++) for (const __c of ['C','D','E','F','G']) __s2 = patchCell(__s2, __c + __r, '', true);\n"
                   "    __s2 = patchCell(__s2, 'E27', 'On-site (folded into modular cost)', true);")
    if html.count(old_install) != 1:
        sys.exit("onsite installDataTable anchor not found uniquely")
    html = html.replace(old_install, new_install, 1)

    # ---- 11. EDITABLE target cost/unit (the max-land basis). Default $350K, but
    #     now a model field with a Backend input so the team can dial the ceiling.
    # 11a. STATE default.
    old_costs = "    // Costs\n    landCost: 0,"
    new_costs = ("    // Costs\n"
                 "    targetPPU: 350000,   // all-in cost/unit target -> sets the max supportable land ceiling\n"
                 "    landCost: 0,")
    if html.count(old_costs) != 1:
        sys.exit("STATE // Costs landCost anchor not found uniquely")
    html = html.replace(old_costs, new_costs, 1)

    # 11b. Backend input in the Hard Costs panel, above Land Acquisition.
    land_li = '<li><span>Land Acquisition</span><input type="number" id="be-land" oninput="updateFromBackend()"></li>'
    target_li = ('<li title="The all-in cost-per-unit target that sets the Max Land Price ceiling on the Dashboard. Lower it to be more conservative; raise it to support a higher land price."><span>Target Cost / Unit <span style="color: var(--text-faint); font-size: 10px;">(max-land basis)</span></span><input type="number" step="5000" min="0" id="be-target-ppu" oninput="updateFromBackend()"></li>\n                    '
                 + land_li)
    if html.count(land_li) != 1:
        sys.exit("Hard Costs Land Acquisition <li> anchor not found uniquely")
    html = html.replace(land_li, target_li, 1)

    # 11c. updateFromBackend: read the target (sanity floor so a blank/0 doesn't
    #      collapse the ceiling). Changing it recomputes __maxLand via updateUI.
    old_readland = "    model.landCost = parseFloat(document.getElementById('be-land').value) || model.landCost;"
    new_readland = ("    const __tppu = parseFloat(document.getElementById('be-target-ppu').value);\n"
                    "    if (isFinite(__tppu) && __tppu > 0) model.targetPPU = Math.round(__tppu);\n"
                    + old_readland)
    if html.count(old_readland) != 1:
        sys.exit("updateFromBackend be-land read anchor not found uniquely")
    html = html.replace(old_readland, new_readland, 1)

    # 11d. updateUI: keep the Backend input in sync with the model.
    old_uiland = "    document.getElementById('be-land').value = model.landCost || '';"
    new_uiland = ("    document.getElementById('be-target-ppu').value = model.targetPPU || '';\n"
                  + old_uiland)
    if html.count(old_uiland) != 1:
        sys.exit("updateUI be-land sync anchor not found uniquely")
    html = html.replace(old_uiland, new_uiland, 1)

    # 12. Rename the user-facing "Backend" tab to "Inputs" (label + prose
    #     references only; the data-tab/switchTab/id identifiers stay 'backend').
    old_backend_btn = ('<button class="tab-btn" data-tab="backend" '
                       'onclick="switchTab(\'backend\')">Backend</button>')
    new_backend_btn = ('<button class="tab-btn" data-tab="backend" '
                       'onclick="switchTab(\'backend\')">Inputs</button>')
    if html.count(old_backend_btn) != 1:
        sys.exit("Backend tab button not found uniquely")
    html = html.replace(old_backend_btn, new_backend_btn, 1)
    # keep prose pointing at the tab consistent with its new name
    html = html.replace("the Backend tab", "the Inputs tab")
    html = html.replace("in Backend tab", "in Inputs tab")
    html = html.replace("· see Backend", "· see Inputs")

    # ====================================================================
    # 13. COWORKER FEEDBACK FIXES (Nick Caton, 2026-06-23)
    #     (a) Cost x Rent sensi -> YoC not MoIC
    #     (b) $15M / 750k shorthand parsing on the land inputs
    #     (c) save / restore previous underwritings
    #     (d) reconcile the Full Proforma tab to the institutional workbook
    #     (e) clearer max-supportable land labeling
    # ====================================================================

    # 13a. Cost x Rent sensitivity table: output Yield on Cost, not MoIC. ----
    html = html.replace(
        "        // Hard Cost vs Rent/Unit -> MOIC",
        "        // Hard Cost vs Rent/Unit -> Yield on Cost (per coworker note)", 1)
    html = html.replace("MOIC<br>Hard Cost × Rent", "YoC<br>Hard Cost × Rent", 1)
    html = html.replace(">${fNum(res.moic, 2)}x</td>", ">${fPct(res.yoc, 1)}</td>", 1)

    # 13b. parseMoney: honor k/m/mm shorthand so "$15M" == 15,000,000. The chat
    #      parser already did this; the manual land fields did not. -----------
    parse_money = '''// Parse a money string that may use k/m/b shorthand: "$15M"->15000000,
// "750k"->750000, "15,000,000"->15000000, "1.2mm"->1200000. 0 if nothing parses.
function parseMoney(raw) {
    const s = (raw == null ? '' : String(raw)).trim().toLowerCase().replace(/[$,\\s]/g, '');
    const m = s.match(/^(-?\\d*\\.?\\d+)\\s*(k|thousand|m|mm|million|b|billion)?$/);
    if (!m) { const f = parseFloat(s.replace(/[^0-9.\\-]/g, '')); return isFinite(f) ? f : 0; }
    let n = parseFloat(m[1]); if (!isFinite(n)) return 0;
    const u = m[2] || '';
    if (u === 'k' || u === 'thousand') n *= 1e3;
    else if (u === 'm' || u === 'mm' || u === 'million') n *= 1e6;
    else if (u === 'b' || u === 'billion') n *= 1e9;
    return n;
}

const fLandDollar = '''
    if html.count("const fLandDollar = ") != 1:
        sys.exit("13b: fLandDollar anchor not found uniquely")
    html = html.replace("const fLandDollar = ", parse_money, 1)

    html = html.replace(
        "    const v = parseFloat((document.getElementById('inp-land-dollar').value + '').replace(/[^0-9.]/g, '')) || 0;",
        "    const v = parseMoney(document.getElementById('inp-land-dollar').value);", 1)
    html = html.replace(
        "    model.landCost = parseFloat(document.getElementById('be-land').value) || model.landCost;",
        "    model.landCost = parseMoney(document.getElementById('be-land').value) || model.landCost;", 1)
    html = html.replace(
        "    const __tppu = parseFloat(document.getElementById('be-target-ppu').value);",
        "    const __tppu = parseMoney(document.getElementById('be-target-ppu').value);", 1)
    # Let the backend currency fields accept shorthand (number inputs reject "M").
    html = html.replace(
        '<li><span>Land Acquisition</span><input type="number" id="be-land" oninput="updateFromBackend()"></li>',
        '<li><span>Land Acquisition</span><input type="text" inputmode="numeric" id="be-land" oninput="updateFromBackend()" placeholder="e.g. 15M or 15,000,000"></li>', 1)
    html = html.replace(
        '<input type="number" step="5000" min="0" id="be-target-ppu" oninput="updateFromBackend()">',
        '<input type="text" inputmode="numeric" id="be-target-ppu" oninput="updateFromBackend()" placeholder="e.g. 350k">', 1)

    # 13c. SESSION SAVE / RESTORE — localStorage. Autosaves the working deal so a
    #      reload never loses it, plus named snapshots reloadable from a menu. ---
    sess_ctl = '''<div class="session-ctl">
            <button class="btn-session" onclick="toggleSessionMenu(event)" title="Save the current underwriting or reload a previous one">
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 9-9 9 9 0 0 0-6.3 2.6L3 8"></path><path d="M3 3v5h5"></path></svg>
                Sessions
            </button>
            <div class="session-menu hidden" id="sessionMenu"></div>
        </div>

        <button class="btn-generate" onclick="switchTab('proforma'); generateProforma();">'''
    gen_btn = '<button class="btn-generate" onclick="switchTab(\'proforma\'); generateProforma();">'
    if html.count(gen_btn) != 1:
        sys.exit("13c: generate-button anchor not found uniquely")
    html = html.replace(gen_btn, sess_ctl, 1)

    sess_js = '''const MZ_SESS_KEY = 'modularz_sessions_v1';
let __sessSaveTimer = null;
function mzLoadSessions() { try { return JSON.parse(localStorage.getItem(MZ_SESS_KEY) || '[]'); } catch (e) { return []; } }
function mzStoreSessions(list) { try { localStorage.setItem(MZ_SESS_KEY, JSON.stringify(list.slice(0, 30))); } catch (e) {} }
function mzSessLabel(s) {
    const d = new Date(s.ts);
    const when = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    return (s.name || 'Untitled') + ' \\u00b7 ' + when;
}
function esc(s) { return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// Debounced autosave of the working deal (id 'auto') so a reload/return is safe.
function autoSaveSession() {
    if (!model || !model.units) return;
    clearTimeout(__sessSaveTimer);
    __sessSaveTimer = setTimeout(() => {
        const list = mzLoadSessions().filter(s => s.id !== 'auto');
        list.unshift({ id: 'auto', name: (model.projectName || 'Working deal') + ' (autosave)', ts: Date.now(), model: JSON.parse(JSON.stringify(model)) });
        mzStoreSessions(list);
    }, 700);
}
function saveNamedSession() {
    if (!model || !model.units) { addMsg('Load a deal before saving a session.', 'system'); return; }
    const name = prompt('Name this underwriting:', model.projectName || 'Untitled deal');
    if (name == null) return;
    const list = mzLoadSessions();
    list.unshift({ id: 'sess_' + Date.now(), name: (name.trim() || 'Untitled'), ts: Date.now(), model: JSON.parse(JSON.stringify(model)) });
    mzStoreSessions(list);
    renderSessionMenu();
    addMsg('\\u2713 Saved session \\u201c' + esc(name.trim() || 'Untitled') + '\\u201d. Reload it anytime from the Sessions menu.', 'system', true);
}
function restoreSession(id) {
    const s = mzLoadSessions().find(x => x.id === id);
    if (!s) return;
    model = Object.assign({}, model, s.model);
    try { const __rl = __residualLandForPPU(model.targetPPU || 350000); if (__rl != null) __maxLand = __rl; } catch (e) {}
    snapshot = runUnderwriting(model);
    if (model.projectName) document.getElementById('projName').innerHTML = esc(model.projectName);
    if (model.address) document.getElementById('projSub').innerHTML = esc(model.address);
    updateUI({ flash: true });
    const menu = document.getElementById('sessionMenu'); if (menu) menu.classList.add('hidden');
    addMsg('\\u21a9 Restored \\u201c' + esc(s.name || 'session') + '\\u201d.', 'system', true);
}
function deleteSession(id, ev) {
    if (ev) ev.stopPropagation();
    mzStoreSessions(mzLoadSessions().filter(x => x.id !== id));
    renderSessionMenu();
}
function renderSessionMenu() {
    const menu = document.getElementById('sessionMenu'); if (!menu) return;
    const list = mzLoadSessions();
    let h = '<div class="session-menu-head"><span>Saved underwritings</span><button onclick="saveNamedSession()">+ Save current</button></div>';
    if (!list.length) h += '<div class="session-empty">No saved sessions yet. Load a deal, then \\u201cSave current.\\u201d</div>';
    else h += list.map(s => '<div class="session-row" onclick="restoreSession(\\'' + s.id + '\\')"><span class="session-name">' + esc(mzSessLabel(s)) + '</span><button class="session-del" title="Delete" onclick="deleteSession(\\'' + s.id + '\\', event)">\\u00d7</button></div>').join('');
    menu.innerHTML = h;
}
function toggleSessionMenu(ev) {
    if (ev) ev.stopPropagation();
    const menu = document.getElementById('sessionMenu'); if (!menu) return;
    renderSessionMenu();
    menu.classList.toggle('hidden');
}
document.addEventListener('click', (e) => {
    const m = document.getElementById('sessionMenu');
    const ctl = e.target.closest && e.target.closest('.session-ctl');
    if (m && !ctl) m.classList.add('hidden');
});
// On load: if a working deal was autosaved and nothing is loaded, offer it back.
setTimeout(() => {
    try {
        const auto = mzLoadSessions().find(s => s.id === 'auto');
        if (auto && (!model || !model.units)) {
            addMsg('You have a saved session: <b>' + esc(auto.name || 'Working deal') + '</b> (' + new Date(auto.ts).toLocaleString() + '). <a href="#" onclick="restoreSession(\\'auto\\'); return false;">Restore it</a> or open the Sessions menu (top right).', 'system', true);
        }
    } catch (e) {}
}, 500);

function generateProforma() {'''
    if html.count("function generateProforma() {") != 1:
        sys.exit("13c: generateProforma anchor not found uniquely")
    html = html.replace("function generateProforma() {", sess_js, 1)

    # Hook autosave into the central redraw (the 4-space land-render block in updateUI).
    ui_hook = "    renderMaxLandDisplay();\n    renderLandLever();"
    if html.count(ui_hook) != 1:
        sys.exit("13c: updateUI 4-space land-render hook not found uniquely")
    html = html.replace(ui_hook, ui_hook + "\n    autoSaveSession();", 1)

    # 13d. Reconcile the Full Proforma tab to the institutional workbook (same
    #      engine as the .xlsx download) so the tab can't disagree with Excel. --
    pf_recon = '''    const r = runUnderwriting(model);
    // Reconcile the headline returns + capital stack to the institutional
    // workbook (same engine as the .xlsx download) so this tab can't disagree
    // with the downloaded model. Falls back to the JS projection if the engine
    // isn't ready. The year-by-year schedule below stays an indicative JS build.
    const __eng = (typeof computeEngineReturns === 'function') ? computeEngineReturns(model) : null;
    if (__eng) {
        if (__eng.irr != null)      r.irr = __eng.irr;
        if (__eng.moic != null)     r.moic = __eng.moic;
        if (__eng.coc != null)      r.avgCoc = __eng.coc;
        if (__eng.yoc != null)      r.yoc = __eng.yoc;
        if (__eng.spread != null)   r.spread = __eng.spread;
        if (__eng.noi != null)      r.noi = __eng.noi;
        if (__eng.tdc != null)      r.tdc = __eng.tdc;
        if (__eng.ppu != null)      r.ppu = __eng.ppu;
        if (__eng.permLoan != null) r.loanAmt = __eng.permLoan;
        if (__eng.equity != null)   r.equity = __eng.equity;
        if (__eng.dscr != null)     r.dscr = __eng.dscr;
    }'''
    if html.count("    const r = runUnderwriting(model);") != 1:
        sys.exit("13d: generateProforma runUnderwriting anchor not found uniquely")
    html = html.replace("    const r = runUnderwriting(model);", pf_recon, 1)

    # Reconciliation note under the proforma title.
    doc_sub = '<div class="doc-sub">${model.address} · ${model.units} units · Generated ${date}</div>'
    doc_recon = doc_sub + '''
            <div class="doc-recon ${__eng ? 'ok' : 'warn'}">${__eng
                ? '\\u2713 Returns, TDC, equity, loan &amp; NOI reconciled to the institutional workbook \\u2014 these match the Excel download. The year-by-year schedule is an indicative projection.'
                : '\\u26a0 Workbook engine not loaded \\u2014 figures are the quick JS estimate and may differ from the Excel download.'}</div>'''
    if html.count(doc_sub) != 1:
        sys.exit("13d: proforma doc-sub anchor not found uniquely")
    html = html.replace(doc_sub, doc_recon, 1)

    # Dashboard engine-status strip above the KPI grid + the function that fills it.
    status_el = '<div class="engine-status" id="engineStatus"></div>\n        <!-- KPI GRID -->'
    if html.count("<!-- KPI GRID -->") != 1:
        sys.exit("13d: KPI GRID anchor not found uniquely")
    html = html.replace("<!-- KPI GRID -->", status_el, 1)

    status_fn = '''function renderEngineStatus(reconciled) {
    const el = document.getElementById('engineStatus'); if (!el) return;
    if (!model || !model.units) { el.textContent = ''; el.className = 'engine-status'; return; }
    if (reconciled) { el.innerHTML = '<span class="dot"></span> Live figures reconciled to the institutional workbook (match the Excel download).'; el.className = 'engine-status ok'; }
    else { el.innerHTML = '<span class="dot"></span> Quick estimate \\u2014 reconciling to the institutional workbook\\u2026'; el.className = 'engine-status warn'; }
}

function applyEngineKPIs() {'''
    if html.count("function applyEngineKPIs() {") != 1:
        sys.exit("13d: applyEngineKPIs anchor not found uniquely")
    html = html.replace("function applyEngineKPIs() {", status_fn, 1)
    html = html.replace(
        "    if (k.equity != null) set('equity', fMoneyM(k.equity));",
        "    if (k.equity != null) set('equity', fMoneyM(k.equity));\n    renderEngineStatus(true);", 1)
    html = html.replace(
        "    if (!__engineReady() || !model.units || !model.nrsf) return;",
        "    if (!__engineReady() || !model.units || !model.nrsf) { renderEngineStatus(false); return; }", 1)

    # 13e. Make it unmistakable the default land is the CEILING, not a real price.
    land_range = '<div class="lever-range"><span>$0</span><span class="land-mark">max</span><span>120%</span></div>'
    land_hint = land_range + '\n                    <div class="land-hint">Defaults to the <b>max you could pay</b> (ceiling @ target $/unit). Enter the actual asking / contract price to see true returns.</div>'
    if html.count(land_range) != 1:
        sys.exit("13e: land lever-range anchor not found uniquely")
    html = html.replace(land_range, land_hint, 1)

    # 13f. Hint that the per-unit target (the max-land basis) is editable in Inputs.
    maxland_figs = '<div class="maxland-figs"><span class="maxland-val" id="maxland-val">&mdash;</span><span class="maxland-pu" id="maxland-pu"></span></div>'
    maxland_hint = maxland_figs + '\n                    <div class="maxland-hint">Per-unit target is editable in the <b>Inputs</b> tab (Hard Costs → Target Cost / Unit).</div>'
    if html.count(maxland_figs) != 1:
        sys.exit("13f: maxland-figs anchor not found uniquely")
    html = html.replace(maxland_figs, maxland_hint, 1)

    # 13c/d/e/f CSS.
    fb_css = '''
/* ====== coworker-feedback fixes: sessions, engine status, land hint, recon note ====== */
.session-ctl { position: relative; }
.btn-session { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: var(--text-muted); background: var(--bg-subtle); border: 1px solid var(--border-strong); border-radius: 6px; padding: 7px 11px; cursor: pointer; }
.btn-session:hover { color: var(--text-main); border-color: var(--accent); }
.session-menu { position: absolute; top: calc(100% + 6px); right: 0; width: 290px; max-height: 360px; overflow-y: auto; background: var(--bg-panel, var(--bg-subtle)); border: 1px solid var(--border-strong); border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); z-index: 200; padding: 6px; }
.session-menu.hidden { display: none; }
.session-menu-head { display: flex; align-items: center; justify-content: space-between; font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--text-faint); padding: 6px 8px 8px; }
.session-menu-head button { font-size: 11px; font-weight: 600; color: var(--accent); background: none; border: none; cursor: pointer; }
.session-empty { font-size: 12px; color: var(--text-faint); padding: 8px 8px 12px; line-height: 1.4; }
.session-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px; border-radius: 6px; cursor: pointer; }
.session-row:hover { background: var(--bg-subtle); }
.session-name { font-size: 12px; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-del { font-size: 15px; line-height: 1; color: var(--text-faint); background: none; border: none; cursor: pointer; padding: 0 4px; }
.session-del:hover { color: #d9534f; }
.engine-status { display: flex; align-items: center; gap: 7px; font-size: 11.5px; margin: 0 0 12px; padding: 6px 10px; border-radius: 6px; }
.engine-status:empty { display: none; }
.engine-status .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.engine-status.ok { color: var(--text-muted); background: rgba(46,160,67,0.10); border: 1px solid rgba(46,160,67,0.30); }
.engine-status.ok .dot { background: #2ea043; }
.engine-status.warn { color: var(--text-muted); background: rgba(224,162,55,0.10); border: 1px solid rgba(224,162,55,0.30); }
.engine-status.warn .dot { background: var(--accent); }
.land-hint { font-size: 10px; line-height: 1.4; color: var(--text-faint); margin-top: 6px; }
.land-hint b { color: var(--text-muted); }
.maxland-hint { font-size: 9.5px; line-height: 1.35; color: var(--text-faint); margin-top: 5px; }
.maxland-hint b { color: var(--text-muted); font-weight: 600; }
.doc-recon { font-size: 11px; line-height: 1.45; margin-top: 8px; padding: 7px 11px; border-radius: 6px; }
.doc-recon.ok { color: var(--text-muted); background: rgba(46,160,67,0.08); border: 1px solid rgba(46,160,67,0.25); }
.doc-recon.warn { color: var(--text-muted); background: rgba(224,162,55,0.08); border: 1px solid rgba(224,162,55,0.25); }
</style>'''
    if html.count("</style>") != 1:
        sys.exit("13: feedback CSS </style> anchor not found uniquely")
    html = html.replace("</style>", fb_css, 1)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
