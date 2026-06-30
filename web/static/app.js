"use strict";

const SECTIONS = window.SECTIONS || [];
const SECTION_LABEL = Object.fromEntries(SECTIONS.map(s => [s.id, s.label]));
const SECTION_ORDER = SECTIONS.map(s => s.id);

let mode = "single";
let pollTimer = null;
let lastDDJob = null;       // most recent completed DD run, for "Generate financial model"
let lastDDAddress = "";     // matched address from the most recent completed DD run
let lastScnJob = null;      // most recent completed scenario job, for "Generate PDF summary"

const $ = sel => document.querySelector(sel);

// ---------- view nav (New deal / Sources) ----------
document.querySelectorAll(".vnav").forEach(b => {
  b.addEventListener("click", () => {
    const isSources = b.dataset.view === "sources";
    document.querySelectorAll(".vnav").forEach(x => x.classList.toggle("active", x === b));
    $("#run-form").classList.toggle("hidden", isSources);
    document.querySelector(".adv").classList.toggle("hidden", isSources);
    $("#run-extras").classList.toggle("hidden", isSources);
    $("#sources-panel").classList.toggle("hidden", !isSources);
  });
});

// Toggle APN entry within the New-deal intake (an assemblage runs by parcel number).
$("#use-apns").addEventListener("change", (e) => {
  $("#apn-wrap").classList.toggle("hidden", !e.target.checked);
});

// ---------- run ----------
$("#run-form").addEventListener("submit", (e) => {
  e.preventDefault();
  runMode($("#use-apns").checked ? "assemblage" : "single");
});
$("#adv-model").addEventListener("click", () => runMode("underwrite"));
$("#adv-comps").addEventListener("click", () => runMode("comps"));

// Build the payload for a run mode and launch it. Single/assemblage start a deal;
// underwrite/comps are the "Other tools" shortcuts.
async function runMode(m) {
  showError(null);
  let fetchOpts;
  if (m === "underwrite") {
    const ddFile = $("#dd").files[0] || null;
    if (!ddFile) { showError("Upload a completed DD checklist (.xlsx)."); return; }
    const fd = new FormData();
    fd.append("mode", "underwrite");
    fd.append("dd", ddFile);
    fd.append("name", $("#uw-name").value.trim());
    fetchOpts = { method: "POST", body: fd };
  } else if (m === "comps") {
    const address = $("#comp-address").value.trim();
    if (!address) { showError("Enter the subject address to find rent comps."); return; }
    const beds = [...document.querySelectorAll(".comp-bed:checked")].map(c => Number(c.value));
    if (!beds.length) { showError("Pick at least one bed type."); return; }
    fetchOpts = { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ mode: "comps", address, beds }) };
  } else if (m === "assemblage") {
    const apns = $("#apns").value.trim();
    if (!apns) { showError("Enter at least one APN, or uncheck APN entry."); return; }
    fetchOpts = { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ mode: "assemblage", apns }) };
  } else {
    const omFile = $("#om").files[0] || null;
    const address = $("#address").value.trim();
    if (!address && !omFile) { showError("Enter an address or upload an OM."); return; }
    if (omFile) {
      const fd = new FormData();
      fd.append("mode", "single");
      fd.append("address", address);
      fd.append("om", omFile);
      fetchOpts = { method: "POST", body: fd };           // browser sets multipart boundary
    } else {
      fetchOpts = { method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mode: "single", address }) };
    }
  }
  await launch(fetchOpts);
}

// POST a run request and start polling. Shared by the form + the chain button.
async function launch(fetchOpts) {
  setRunning(true);
  resetStatus();
  try {
    const res = await fetch("/api/run", fetchOpts);
    const data = await res.json();
    if (!res.ok) { throw new Error(data.error || "Request failed."); }
    poll(data.job_id);
  } catch (err) {
    setRunning(false);
    showError(err.message);
  }
}

// "Generate financial model" from the just-completed DD run (no re-upload).
$("#gen-model").addEventListener("click", () => {
  if (!lastDDJob) return;
  genModelFrom(lastDDJob);
});

// "→ Rent comps" from the just-completed DD run.
$("#gen-comps").addEventListener("click", () => {
  if (!lastDDJob) return;
  genCompsFrom(lastDDJob, lastDDAddress);
});

// "Generate PDF summary" from the just-completed scenario job.
$("#gen-pdf").addEventListener("click", async () => {
  if (!lastScnJob) return;
  setRunning(true);
  resetStatus();
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mode: "pdf_summary", from_job: lastScnJob}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Request failed.");
    poll(data.job_id);
  } catch (err) {
    setRunning(false);
    showError(err.message);
  }
});

// "→ Financial model" / "→ Rent comps" next to any previously completed checklist in Recent runs.
$("#recent-body").addEventListener("click", (e) => {
  const openBtn = e.target.closest(".rc-open");
  if (openBtn && openBtn.dataset.job) { DealWorkspace.open(openBtn.dataset.job); return; }
  // Back-compat: the inline chain buttons (if any remain) still work.
  const btn = e.target.closest(".rc-gen");
  if (btn && btn.dataset.job) genModelFrom(btn.dataset.job);
  const compsBtn = e.target.closest(".rc-comps");
  if (compsBtn && compsBtn.dataset.job) genCompsFrom(compsBtn.dataset.job, compsBtn.dataset.addr || "");
});

// Open the Review & Edit step seeded with the auto-derived model inputs; on
// confirm it auto-chains into the underwrite run with the analyst's overrides.
async function genModelFrom(jobId) {
  showError(null);
  try {
    const res = await fetch(`/api/underwrite/intake/${jobId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not load model inputs.");
    openModelReview(jobId, data);
  } catch (err) {
    showError(err.message);
  }
}

// Open the comp pre-flight panel seeded with the DD job's matched address.
function genCompsFrom(jobId, address) {
  showError(null);
  CompsPreFlight.open(jobId, address || "");
}

// ---------- comp pre-flight — address + bed-type confirmation before launching a comp run ----------
const CompsPreFlight = {
  jobId: null,
  open(jobId, address) {
    this.jobId = jobId;
    // Strip assemblage suffix, e.g. "123 Main St (+2 parcels)" → "123 Main St"
    const addr = address.replace(/\s*\(\+\d+ parcels?\)\s*$/, "").trim();
    $("#cpf-address").value = addr;
    // Default to 1BR + 2BR
    document.querySelectorAll(".cpf-bed").forEach(cb => {
      cb.checked = cb.value === "1" || cb.value === "2";
    });
    $("#cpf-error").classList.add("hidden");
    $("#cpf-panel").classList.remove("hidden");
    $("#cpf-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  },
  close() { $("#cpf-panel").classList.add("hidden"); },
};
$("#cpf-cancel").addEventListener("click", () => CompsPreFlight.close());
$("#cpf-go").addEventListener("click", () => {
  const addr = $("#cpf-address").value.trim();
  const beds = [...document.querySelectorAll(".cpf-bed:checked")].map(c => Number(c.value));
  const err = $("#cpf-error");
  if (!addr) { err.textContent = "Enter the subject address."; err.classList.remove("hidden"); return; }
  if (!beds.length) { err.textContent = "Select at least one bed type."; err.classList.remove("hidden"); return; }
  err.classList.add("hidden");
  CompsPreFlight.close();
  launch({ method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ mode: "comps", address: addr, beds }) });
});

// ---------- Deal workspace (pipeline stepper) ----------
// One screen per deal: DD → rent comps → financial model → one-pager, each stage
// showing its status, action, and the hand-off to the next. Reads /api/deal/<dd>
// (the live job store) so it survives reloads. Reuses the existing chain actions.
let _activeDealId = null;

const DealWorkspace = {
  async open(ddJobId) {
    _activeDealId = ddJobId;
    try {
      const res = await fetch(`/api/deal/${ddJobId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Couldn't load this deal.");
      this.render(data);
      const p = $("#deal-workspace");
      p.classList.remove("hidden");
      p.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) { showError(err.message); }
  },
  async refresh() { if (_activeDealId) await this.open(_activeDealId); },
  close() { _activeDealId = null; $("#deal-workspace").classList.add("hidden"); },

  render(d) {
    const dd = d.dd || {}, comps = d.comps || {}, model = d.model || {}, summary = d.summary || {};
    const addr = (dd.address || dd.label || "Deal").replace(/\s*—.*$/, "");
    $("#dw-title").textContent = addr;
    $("#dw-meta").textContent = dd.label || "";

    const html = [];
    html.push(stageRow(1, {
      state: "done", name: "Due diligence", sub: "Site readers complete",
      actions: dd.downloadable ? [dlBtn(dd.id, "Checklist .xlsx")] : [],
    }, "passes site facts → county, PHA, QCT/DDA, resource, lot SF"));

    const cState = jobState(comps);
    html.push(stageRow(2, {
      state: cState || "ready", name: "Rent comps",
      sub: cState === "done" ? `Comp grid ready${comps.beds ? " · beds " + comps.beds.join("/") : ""}`
        : "Zillow scrape, then a CTCAC grid you confirm",
      actions: [
        actBtn(`DealWorkspace.runComps('${dd.id}')`, cState === "done" ? "Re-run comps" : "Run rent comps", cState !== "done"),
        ...(comps.downloadable ? [dlBtn(comps.id, "Grid .xlsx")] : []),
      ],
    }, "passes adjusted market rents → pre-fills the model"));

    const mState = jobState(model);
    const compsDone = jobState(comps) === "done";
    const mActions = [actBtn(`DealWorkspace.buildModel('${dd.id}')`,
      mState === "done" ? "Rebuild model" : "Review inputs, then build", mState !== "done")];
    if (model.downloadable) mActions.push(dlBtn(model.id, "Model .zip"));
    html.push(stageRow(3, {
      state: mState || "ready", name: "Financial model",
      sub: mState === "done" ? modelSummary(model)
        : compsDone ? "LIHTC, or non-LIHTC market / mixed-income / debt stack"
        : "LIHTC, or non-LIHTC. For a market or mixed-income deal, run rent comps first — the concluded rents pre-fill it.",
      actions: mActions, returns: mState === "done" ? returnsLine(model) : "",
    }, "passes returns and deal facts → the one-pager"));

    const sState = jobState(summary);
    const modelDone = mState === "done";
    const fromScenarios = model.kind === "lihtc_scenarios";
    let s4;
    if (sState === "done" || sState === "running" || sState === "error") {
      s4 = { state: sState, name: "One-pager", sub: "3-page investment PDF",
             actions: summary.downloadable ? [dlBtn(summary.id, "One-pager .pdf")] : [] };
    } else if (modelDone && fromScenarios) {
      s4 = { state: "ready", name: "One-pager", sub: "3-page investment PDF — KPIs, returns, debt, comps",
             actions: [actBtn(`DealWorkspace.buildSummary('${model.id}')`, "Generate one-pager", false)] };
    } else if (modelDone) {
      s4 = { state: "locked", name: "One-pager", muted: true,
             sub: "Available from a LIHTC scenario set — build scenarios in step 3" };
    } else {
      s4 = { state: "locked", name: "One-pager", muted: true, sub: "Build a model first" };
    }
    html.push(stageRow(4, s4, null, true));

    $("#dw-stages").innerHTML = html.join("");
  },

  runComps(ddId) { genCompsFrom(ddId, _activeDealId === ddId ? ($("#dw-title").textContent || "") : ""); },
  buildModel(ddId) { genModelFrom(ddId); },
  buildSummary(modelId) { genSummaryFrom(modelId); },
};
window.DealWorkspace = DealWorkspace;
$("#dw-close").addEventListener("click", () => DealWorkspace.close());

function jobState(s) {
  const v = s && s.status;
  if (v === "done") return "done";
  if (v === "running") return "running";
  if (v === "error") return "error";
  return null;
}
function dlBtn(id, label) { return `<a class="download-btn" href="/api/download/${esc(id)}">${esc(label)}</a>`; }
function actBtn(call, label, primary) {
  return `<button type="button" class="download-btn${primary ? "" : " ghost"}" onclick="${call}">${esc(label)}</button>`;
}
function modelSummary(m) {
  if (m.deal_type === "nonlihtc") return `Non-LIHTC · ${m.program || "market"}`;
  if (m.kind === "lihtc_scenarios") return `LIHTC scenario set${(m.models || []).length ? " · " + m.models.length + " models" : ""}`;
  return "LIHTC v28 · Modular + Stick";
}
function returnsLine(m) {
  const r = m.returns || {};
  const irr = r["Levered IRR"], noi = r["Net Operating Income"];
  if (irr == null && noi == null) return "";
  const parts = [];
  if (irr != null) parts.push(`Levered IRR ${(Number(irr) * 100).toFixed(1)}%`);
  if (noi != null) parts.push(`NOI $${fmt(Math.round(noi))}`);
  return parts.join(" · ");
}
// Render one stage row: status rail (circle + connector) + body (name, pill, sub, actions).
function stageRow(n, o, handoff, isLast) {
  const st = o.state || "ready";
  const PILL = { done: ["done", "Done"], ready: ["ready", "Ready"], running: ["run", "Running…"],
                 error: ["err", "Error"], locked: ["lock", o.muted && o.sub && o.sub.indexOf("scenario") >= 0 ? "From scenarios" : "Locked"] };
  const inner = st === "done" ? "✓" : st === "running" ? "…" : st === "error" ? "!" : String(n);
  const circleCls = st === "done" ? "done" : st === "running" ? "run" : st === "error" ? "err"
    : st === "locked" ? "lock" : "ready";
  const [pillCls, pillTxt] = PILL[st] || PILL.ready;
  const acts = (o.actions || []).join("");
  return `
    <div class="dw-stage">
      <div class="dw-rail"><div class="dw-circle ${circleCls}">${inner}</div>${isLast ? "" : `<div class="dw-line"></div>`}</div>
      <div class="dw-body">
        <div class="dw-titlerow"><span class="dw-name${o.muted ? " muted" : ""}">${esc(o.name)}</span><span class="dw-pill ${pillCls}">${esc(pillTxt)}</span></div>
        <div class="dw-sub${o.muted ? " muted" : ""}">${esc(o.sub || "")}</div>
        ${o.returns ? `<div class="dw-returns">${esc(o.returns)}</div>` : ""}
        ${acts ? `<div class="dw-actions">${acts}</div>` : ""}
      </div>
    </div>
    ${isLast || !handoff ? "" : `<div class="dw-handoff"><span>↓</span><span>${esc(handoff)}</span></div>`}`;
}
// Launch the one-pager from a LIHTC scenario job, then return to the workspace.
async function genSummaryFrom(modelJobId) {
  showError(null);
  await launch({ method: "POST", headers: { "Content-Type": "application/json" },
                 body: JSON.stringify({ mode: "pdf_summary", from_job: modelJobId }) });
}

// Holds the current model-review context so the deal-type toggle can re-render
// either review form against the same DD intake.
let _modelReview = { jobId: null, intake: null, dealType: "lihtc" };

// OpEx factors parsed from an uploaded T-12 (per-unit-per-month, plus mgmt %).
// Populated by mountNonLihtcT12(); folded into the non-LIHTC payload on confirm.
let _nlT12Opex = null;
// County FIPS for the non-LIHTC mixed-income AMI-rent preview (from intake).
let _nlCountyFips = null;
const AMI_PROGRAM = { MIXED: "Mixed-income (AMI)", MARKET: "Market rate" };
const AMI_LEVELS = ["50", "55", "60", "70", "80", "100"];

// Gross CTCAC AMI cap from window.HUD_RENTS for the live preview (server recomputes
// authoritatively at build). bed: 1/2/3. Returns null if data/county/tier missing.
function amiRentPreview(fips, ami, bed) {
  const h = (window.HUD_RENTS && window.HUD_RENTS.counties && fips
    && window.HUD_RENTS.counties[fips]);
  if (!h) return null;
  const tier = h.rents && h.rents[String(ami)];
  return tier ? (tier["br" + bed] ?? null) : null;
}

// Dispatcher: shows the LIHTC/Non-LIHTC toggle, then renders the chosen form.
function openModelReview(jobId, intake) {
  _modelReview = { jobId, intake, dealType: "lihtc" };
  _nlT12Opex = null;
  const wrap = $("#review-dealtype-wrap");
  if (wrap) wrap.classList.remove("hidden");
  const tg = $("#review-dealtype");
  if (tg) {
    tg.querySelectorAll(".dt-opt").forEach(b =>
      b.classList.toggle("active", b.dataset.dt === "lihtc"));
  }
  openLihtcReview(jobId, intake);
}

// The existing LIHTC review → scenario picker flow.
function openLihtcReview(jobId, intake) {
  const o = intake.options;
  ReviewEditor.open({
    subtitle: `${intake.label} — adjust the automated inputs, preview, then select scenarios. Defaults are the DD answers.`,
    confirmLabel: "Choose scenarios →",
    previewNote: "Derived live from the inputs (same rules the exporter uses). Residential stories and land price have sensible defaults when blank; NRSF is a formula in the model. BIPOC & prevailing wage stay analyst-entered in Excel.",
    values: intake.values,
    fields: [
      { id: "deal_name", label: "Deal name", type: "text" },
      { id: "county", label: "County", type: "text" },
      { id: "pha", label: "Public Housing Authority", type: "select", options: o.pha },
      { id: "qct_dda", label: "QCT / DDA", type: "select", options: o.qct_dda },
      { id: "resource", label: "Resource area", type: "select", options: o.resource, help: "drives product type & bedroom mix" },
      { id: "neighborhood_change", label: "Neighborhood change area", type: "select", options: o.neighborhood_change, help: "drives CRA eligibility" },
      { id: "land_sf", label: "Land area (SF)", type: "number" },
      { id: "acquisition_price", label: "Land purchase price ($)", type: "number",
        placeholder: "e.g. 10000000", help: "defaults to $150/SF of land if blank (written to S16)" },
      { id: "residential_stories", label: "Residential stories", type: "number",
        placeholder: String((intake.placeholders && intake.placeholders.residential_stories) ?? 5),
        help: "drives FAR, construction type & cost; defaults to 5 if blank" },
    ],
    derive: deriveModelPreview,
  }, (values) => {
    ScenarioPicker.open(jobId, values);
  });
}

// Non-LIHTC (market / mixed) review → directly launches the underwrite run on the
// clean pre-v28 ModularZ market engine. Unit program + comp rents drive it.
function openNonLihtcReview(jobId, intake) {
  _nlT12Opex = null;
  _nlCountyFips = intake.county_fips || null;
  const seed = intake.values || {};
  // Comp scraper rents (median $/mo per bed) — pre-fill when the analyst already
  // ran comps for this subject. Keys are bed ints (0=studio,1,2,3).
  const cr = (intake.comp_rents && intake.comp_rents.rents_by_bed) || {};
  const counts = (intake.comp_rents && intake.comp_rents.counts) || {};
  const ctcac = intake.comp_rents && intake.comp_rents.source === "ctcac_adjusted";
  const rentOf = (bed) => (cr[bed] != null ? Number(cr[bed]) : null);
  const compHelp = (bed) => (ctcac ? "CTCAC-adjusted concluded rent from your comp grid"
    : counts[bed] ? `auto-filled: median of ${counts[bed]} comp${counts[bed] > 1 ? "s" : ""} from the AI scraper`
    : "from comp scraper");
  const compNote = intake.comp_rents
    ? `Rents pre-filled from your ${ctcac ? "edited comp grid (CTCAC-adjusted concluded rents)" : "comp run (scraper median)"} on ${intake.comp_rents.address || "this subject"} — edit as needed. `
    : "";
  ReviewEditor.open({
    subtitle: `${intake.label} — non-LIHTC (market) model. ${intake.comp_rents ? "Rents pre-filled from the comp scraper; c" : "Enter the unit program and market rents (from the comp scraper). C"}onfirm the unit program. The pre-v28 ModularZ engine runs in market mode.`,
    confirmLabel: "Generate model →",
    previewNote: compNote + "Drives the clean ModularZ market engine: restricted set-aside + affordable rows are zeroed; rents are the comp $/mo. Modular cost book has no studio product, so studios aren't modeled. Blank OpEx lines fall back to the v5.0.7 PUPM defaults.",
    values: {
      deal_name: seed.deal_name || "",
      land_price: seed.acquisition_price ?? null,
      program: AMI_PROGRAM.MIXED,
      units_1br: null, units_2br: null, units_3br: null,
      ami1_pct: 20, ami1_level: "50",
      ami2_pct: 55, ami2_level: "80",
      ami3_pct: 25, ami3_level: "70",
      rent_1br: rentOf(1), rent_2br: rentOf(2), rent_3br: rentOf(3),
      exit_cap: 5,
      senior_basis: "DSCR", senior_value: 1.2, senior_rate: 5.75, senior_amort: 35,
      sub_amount: null, sub_rate: 3, sub_amort: 0,
    },
    fields: [
      { id: "deal_name", label: "Deal name", type: "text" },
      { id: "land_price", label: "Land purchase price ($)", type: "number",
        placeholder: "e.g. 5000000", help: "defaults to the DD acquisition price if blank" },
      { id: "program", label: "Program", type: "select",
        options: [AMI_PROGRAM.MIXED, AMI_PROGRAM.MARKET],
        help: "Mixed-income drives the restricted AMI tiers; Market rate zeroes them" },
      { id: "units_1br", label: "1-BR units", type: "number", required: true, help: "modular product" },
      { id: "units_2br", label: "2-BR units", type: "number" },
      { id: "units_3br", label: "3-BR units", type: "number" },
      { id: "ami1_pct", label: "AMI tier 1 — % of units", type: "number", help: "default 20%" },
      { id: "ami1_level", label: "AMI tier 1 — level (%)", type: "select", options: AMI_LEVELS },
      { id: "ami2_pct", label: "AMI tier 2 — % of units", type: "number", help: "default 55%" },
      { id: "ami2_level", label: "AMI tier 2 — level (%)", type: "select", options: AMI_LEVELS },
      { id: "ami3_pct", label: "AMI tier 3 — % of units", type: "number", help: "remainder; default 25%" },
      { id: "ami3_level", label: "AMI tier 3 — level (%)", type: "select", options: AMI_LEVELS },
      { id: "rent_1br", label: "1-BR market rent ($/mo)", type: "number",
        placeholder: "from comp scraper", help: "market remainder only — " + compHelp(1) },
      { id: "rent_2br", label: "2-BR market rent ($/mo)", type: "number", help: compHelp(2) },
      { id: "rent_3br", label: "3-BR market rent ($/mo)", type: "number", help: compHelp(3) },
      { id: "exit_cap", label: "Exit cap (%)", type: "number", help: "base-case exit cap; default 5.0" },
      { id: "senior_basis", label: "Senior loan — sizing", type: "select",
        options: ["DSCR", "LTV", "LTC", "Fixed $"], help: "how the senior perm loan is sized" },
      { id: "senior_value", label: "Senior — value", type: "number",
        help: "DSCR ratio (e.g. 1.20), LTV/LTC % (e.g. 75), or $ if Fixed" },
      { id: "senior_rate", label: "Senior — rate (%)", type: "number", help: "default 5.75" },
      { id: "senior_amort", label: "Senior — amort (yrs)", type: "number", help: "default 35" },
      { id: "sub_amount", label: "Subordinate / soft loan ($)", type: "number",
        placeholder: "blank = none", help: "a 2nd perm loan on top (city/gap/seller); reflected in Levered IRR" },
      { id: "sub_rate", label: "Subordinate — rate (%)", type: "number", help: "0 for a 0% soft loan" },
      { id: "sub_amort", label: "Subordinate — amort (yrs)", type: "number", help: "0 = interest-only / deferred" },
    ],
    derive: deriveNonLihtcPreview,
  }, (v) => {
    const units = {}, rents = {};
    const num = (x) => (x === null || x === undefined || x === "" ? null : Number(x));
    [["1", v.units_1br], ["2", v.units_2br], ["3", v.units_3br]].forEach(([b, n]) => {
      if (num(n) != null) units[b] = num(n);
    });
    [["1", v.rent_1br], ["2", v.rent_2br], ["3", v.rent_3br]].forEach(([b, r]) => {
      if (num(r) != null) rents[b] = num(r);
    });
    const financing = {};
    if (num(v.exit_cap) != null) financing.exit_cap = num(v.exit_cap) / 100;
    const nonlihtc = { units_by_bed: units, rents_by_bed: rents };
    if (num(v.land_price) != null) nonlihtc.land_cost = num(v.land_price);
    if (Object.keys(financing).length) nonlihtc.financing = financing;
    if (_nlT12Opex && Object.keys(_nlT12Opex).length) nonlihtc.opex = _nlT12Opex;
    // Debt stack: senior perm (sizing basis + rate/amort) + optional subordinate.
    const loans = [];
    const sb = (v.senior_basis || "DSCR").toLowerCase().replace(" $", "").replace("$", "");
    const sv = num(v.senior_value);
    const senior = { label: "Senior Perm", basis: sb === "fixed" ? "fixed" : sb,
      rate: num(v.senior_rate) != null ? num(v.senior_rate) / 100 : undefined,
      amort: num(v.senior_amort) };
    // LTV/LTC entered as a percent (75) -> fraction; DSCR/Fixed taken as-is.
    if (sv != null) senior.value = (sb === "ltv" || sb === "ltc") ? sv / 100 : sv;
    loans.push(senior);
    if (num(v.sub_amount) != null && num(v.sub_amount) > 0) {
      const sa = num(v.sub_amort);
      loans.push({ label: "Subordinate / Soft", basis: "fixed", value: num(v.sub_amount),
        rate: num(v.sub_rate) != null ? num(v.sub_rate) / 100 : 0,
        amort: sa || 0, io: !sa });
    }
    nonlihtc.loans = loans;
    // Mixed-income: send the AMI allocation (pct as fraction, ami as int). Tiers
    // with 0% are dropped; the server nets restricted units out of the market mix.
    if (v.program === AMI_PROGRAM.MIXED) {
      const alloc = [[v.ami1_pct, v.ami1_level], [v.ami2_pct, v.ami2_level], [v.ami3_pct, v.ami3_level]]
        .map(([p, a]) => ({ pct: num(p), ami: Number(a) }))
        .filter(t => t.pct != null && t.pct > 0);
      if (alloc.length) {
        nonlihtc.ami_allocation = alloc.map(t => ({ pct: t.pct / 100, ami: t.ami }));
        if (_nlCountyFips) nonlihtc.county_fips = _nlCountyFips;
      }
    }
    launch({
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "underwrite", from_job: jobId, name: v.deal_name || null,
        deal_type: "nonlihtc", nonlihtc,
      }),
    });
  });
  mountNonLihtcT12();
}

// Append a T-12 uploader to the non-LIHTC review form. The analyst optionally
// drops an operating statement; we POST it to /api/t12/parse with the current
// total unit count, then store the parsed PUPM OpEx in _nlT12Opex (folded into
// the payload on confirm) and show what matched. Blank = engine PUPM defaults.
function mountNonLihtcT12() {
  const host = $("#review-inputs");
  if (!host || host.querySelector("#nl-t12")) return;
  const box = document.createElement("div");
  box.id = "nl-t12";
  box.className = "field nl-t12";
  box.innerHTML = `
    <label>Operating statement (T-12) — optional</label>
    <div class="t12-row">
      <input type="file" id="nl-t12-file" accept=".xlsx,.xls" />
      <button type="button" id="nl-t12-parse" class="btn-secondary">Parse T-12</button>
    </div>
    <div class="help">Pulls real OpEx (per-unit-per-month) from a trailing-12-month statement. Property tax is skipped (the engine derives it); management becomes a % of revenue. Leave blank to use the v5.0.7 PUPM defaults.</div>
    <div id="nl-t12-status" class="t12-status"></div>`;
  host.appendChild(box);

  const fileEl = box.querySelector("#nl-t12-file");
  const btn = box.querySelector("#nl-t12-parse");
  const status = box.querySelector("#nl-t12-status");

  const totalUnits = () => {
    const n = (fid) => {
      const el = host.querySelector(`[data-fid="${fid}"]`);
      const v = el ? Number(el.value) : 0;
      return Number.isFinite(v) ? v : 0;
    };
    return n("units_1br") + n("units_2br") + n("units_3br");
  };

  btn.addEventListener("click", async () => {
    const f = fileEl.files && fileEl.files[0];
    if (!f) { status.innerHTML = `<span class="t12-err">Choose a T-12 .xlsx first.</span>`; return; }
    const units = totalUnits();
    if (!units || units <= 0) {
      status.innerHTML = `<span class="t12-err">Enter the unit program (1/2/3-BR counts) first — needed to convert annual $ to per-unit-per-month.</span>`;
      return;
    }
    status.innerHTML = `<span class="t12-muted">Parsing ${f.name} against ${units} units…</span>`;
    btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("t12", f);
      fd.append("units", String(units));
      const res = await fetch("/api/t12/parse", { method: "POST", body: fd });
      const j = await res.json();
      if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
      _nlT12Opex = j.opex || {};
      renderT12Result(status, j);
    } catch (e) {
      _nlT12Opex = null;
      status.innerHTML = `<span class="t12-err">Couldn't parse that T-12: ${e.message}. The model will use the PUPM defaults.</span>`;
    } finally {
      btn.disabled = false;
    }
  });
}

// Render the parsed-T-12 summary: matched OpEx lines (with $/unit/mo or mgmt %),
// any unmatched expense rows, and the parser's notes.
function renderT12Result(status, j) {
  const matched = j.matched || [];
  if (!matched.length) {
    status.innerHTML = `<span class="t12-err">No OpEx lines recognized in “${j.sheet || "?"}” — check the layout. Using the PUPM defaults.</span>`;
    return;
  }
  const money = (n) => "$" + Math.round(n).toLocaleString();
  const rows = matched.map((m) => {
    const name = m.friendly.replace(/^opex_/, "").replace(/_/g, " ");
    const val = m.friendly === "opex_management"
      ? ((m.pupm != null ? (m.pupm * 100).toFixed(1) : "—") + "% of revenue")
      : (m.pupm != null ? money(m.pupm) + "/unit/mo" : "—");
    return `<tr><td>${name}</td><td class="t12-amt">${val}</td><td class="t12-src">${money(m.annual)}/yr</td></tr>`;
  }).join("");
  const notes = (j.notes || []).map((n) => `<li>${n}</li>`).join("");
  const unmatched = (j.unmatched || []).length
    ? `<div class="t12-muted t12-unmatched">Not mapped (left at default): ${j.unmatched.map((u) => u.line).join(", ")}.</div>`
    : "";
  status.innerHTML = `
    <div class="t12-ok">Parsed “${j.sheet}” — ${matched.length} OpEx line${matched.length > 1 ? "s" : ""} mapped${j.revenue ? `, revenue ${money(j.revenue)}` : ""}.</div>
    <table class="t12-table"><thead><tr><th>Line</th><th>Engine factor</th><th>T-12 annual</th></tr></thead><tbody>${rows}</tbody></table>
    ${unmatched}
    ${notes ? `<ul class="t12-notes">${notes}</ul>` : ""}`;
}

// Live preview for the non-LIHTC form — mirrors the engine's allocation rules.
function deriveNonLihtcPreview(v) {
  const num = (x) => (x === null || x === undefined || x === "" ? 0 : Number(x));
  const u1 = num(v.units_1br), u2 = num(v.units_2br), u3 = num(v.units_3br);
  const total = u1 + u2 + u3;
  const mix = total > 0
    ? `${Math.round(u1 / total * 100)}% 1B · ${Math.round(u2 / total * 100)}% 2B · ${Math.round(u3 / total * 100)}% 3B`
    : "—";
  const mixed = v.program === AMI_PROGRAM.MIXED;
  const rows = [
    { label: "Deal", value: v.deal_name || "—" },
    { label: "Land price (Dev Budget G7)", value: num(v.land_price) > 0 ? "$" + fmt(v.land_price) : "— DD default" },
    { label: "Program", value: mixed ? "Mixed-income (AMI tiers)" : "Market rate" },
    { label: "Unit program (O11/O12/O13)", value: total > 0 ? `${u1} / ${u2} / ${u3} = ${total} units (+1 mgr)` : "— enter 1-BR" },
    { label: "→ Bed mix", value: mix },
  ];

  if (mixed) {
    const tiers = [[num(v.ami1_pct), v.ami1_level], [num(v.ami2_pct), v.ami2_level],
      [num(v.ami3_pct), v.ami3_level]].filter(([p]) => p > 0);
    const sumPct = tiers.reduce((s, [p]) => s + p, 0);
    rows.push({ label: "AMI tiers", value: tiers.length
      ? tiers.map(([p, a]) => `${p}% @ ${a}% AMI`).join(" · ") : "— none" });
    rows.push({ label: "→ Restricted / market split",
      value: `${Math.min(sumPct, 100)}% restricted · ${Math.max(0, 100 - sumPct)}% market`
        + (sumPct > 100 ? "  ⚠ over 100%" : "") });
    // per-tier unit counts + AMI rents (1BR, from window.HUD_RENTS when loaded)
    tiers.forEach(([p, a], i) => {
      const units = total > 0 ? Math.round(total * p / 100) : 0;
      const r1 = amiRentPreview(_nlCountyFips, a, 1);
      rows.push({ label: `  Tier ${i + 1} (${a}% AMI)`,
        value: `${units} units` + (r1 ? ` · 1BR cap ~$${fmt(r1)}/mo` : "") });
    });
    if (!_nlCountyFips) rows.push({ label: "  AMI rents",
      value: "resolved from county at build (no ZIP on this DD)" });
  } else {
    const gpr = (u1 * num(v.rent_1br) + u2 * num(v.rent_2br) + u3 * num(v.rent_3br)) * 12;
    rows.push({ label: "Market rents 1B/2B/3B",
      value: `$${fmt(v.rent_1br || 0)} / $${fmt(v.rent_2br || 0)} / $${fmt(v.rent_3br || 0)}` });
    rows.push({ label: "→ Annual GPR (approx)", value: gpr > 0 ? "$" + fmt(Math.round(gpr)) : "—" });
  }
  rows.push({ label: "Exit cap (Dashboard J5)", value: (num(v.exit_cap) || 5) + "%" });
  // Debt stack
  const sb = v.senior_basis || "DSCR";
  const sval = v.senior_value;
  const seniorDesc = sb === "Fixed $" ? `$${fmt(sval || 0)}`
    : sb === "DSCR" ? `${sval || 1.2}x` : `${sval || 75}%`;
  rows.push({ label: "Senior loan", value: `${sb} ${seniorDesc} @ ${num(v.senior_rate) || 5.75}% / ${num(v.senior_amort) || 35}yr` });
  if (num(v.sub_amount) > 0) {
    const io = !num(v.sub_amort);
    rows.push({ label: "+ Subordinate / soft", value: `$${fmt(v.sub_amount)} @ ${num(v.sub_rate) || 0}% · ${io ? "IO/deferred" : (num(v.sub_amort) + "yr amort")}` });
    rows.push({ label: "  → effect", value: "reflected in Levered IRR & Equity Multiple (CoC shows senior only)" });
  }
  return rows;
}

// ---------- scenario definitions (mirrors Python's run_lihtc_scenarios logic) ----------
function defaultScenarios(resource) {
  const lf = resource === "High" || resource === "Highest";
  const base = [
    { constr: "Modular", stories: 5,  podium: 1, lf: "No",  shStudio: 0, sh2B: 0,    sh3B: 0    },
    { constr: "Stick",   stories: 5,  podium: 1, lf: "No",  shStudio: 0, sh2B: 0.5,  sh3B: 0    },
    { constr: "Modular", stories: 12, podium: 1, lf: "No",  shStudio: 0, sh2B: 0,    sh3B: 0    },
  ];
  if (lf) {
    base.push(
      { constr: "Modular", stories: 5,  podium: 1, lf: "Yes", shStudio: 0, sh2B: 0.25, sh3B: 0.25 },
      { constr: "Stick",   stories: 5,  podium: 1, lf: "Yes", shStudio: 0, sh2B: 0.25, sh3B: 0.25 },
      { constr: "Modular", stories: 12, podium: 1, lf: "Yes", shStudio: 0, sh2B: 0.25, sh3B: 0.25 },
    );
  }
  base.forEach(s => { s.name = scenarioLabel(s); });
  return base;
}

// Build a human label from the scenario's LIVE params so the filename and PDF
// always match what was actually run. The old static names caused an 82/18 mix
// to download as "50% 2B" because the label never tracked the edited inputs.
function scenarioLabel(s) {
  const podium = Number(s.podium) > 0 ? `, podium ${Math.round(s.podium)}` : ", no podium";
  if (s.lf === "Yes")
    return `${s.constr} ${s.stories}st${podium} — Large Family (50% 1B · 25% 2B · 25% 3B)`;
  const st = Math.round((s.shStudio || 0) * 100);
  const b2 = Math.round((s.sh2B || 0) * 100);
  const b3 = Math.round((s.sh3B || 0) * 100);
  const b1 = Math.max(0, 100 - st - b2 - b3);
  const parts = [];
  if (st) parts.push(`${st}% Studio`);
  if (b1) parts.push(`${b1}% 1B`);
  if (b2) parts.push(`${b2}% 2B`);
  if (b3) parts.push(`${b3}% 3B`);
  return `${s.constr} ${s.stories}st${podium} — ${parts.join(" · ") || "—"}`;
}

const ScenarioPicker = {
  jobId: null, overrides: null, scenarios: null,

  open(jobId, overrides) {
    this.jobId = jobId;
    this.overrides = overrides;
    const resource = (overrides && overrides.resource) || "";
    this.scenarios = defaultScenarios(resource);

    const lf = resource === "High" || resource === "Highest";
    const lfNote = lf
      ? "Large Family scenarios included because Resource Area is " + resource + ". Mix: 50% 1B · 25% 2B · 25% 3B."
      : "Large Family scenarios are not shown (Resource Area is not High or Highest).";
    $("#scn-sub").textContent = lfNote;

    this._render();
    $("#scn-error").classList.add("hidden");
    $("#scenario-panel").classList.remove("hidden");
    $("#scenario-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  },

  close() { $("#scenario-panel").classList.add("hidden"); },

  _render() {
    const beds = (i, bed, label, val) =>
      `<span class="scn-mix-field"><input type="number" class="scn-mix-inp" data-idx="${i}" data-bed="${bed}" min="0" max="100" step="5" value="${val}"><span class="scn-mix-bed">${label}</span></span>`;
    $("#scn-list").innerHTML = [
      `<div class="scn-selall"><label><input type="checkbox" id="scn-all" checked> Select / deselect all</label></div>`,
      ...this.scenarios.map((s, i) => {
        const sfNote = s.constr === "Modular"
          ? "1B 497 · 2B 804 · 3B 994 SF"
          : (s.lf === "Yes" ? "1B 475 · 2B 735 · 3B 945 SF" : "1B 450 · 2B 700 · 3B 900 SF");
        const b1 = Math.max(0, 100 - Math.round(s.shStudio*100) - Math.round(s.sh2B*100) - Math.round(s.sh3B*100));
        const mixHtml = s.lf === "Yes"
          ? `<span class="scn-mix"><span class="scn-mix-locked">50% 1B · 25% 2B · 25% 3B (locked — Large Family)</span></span>`
          : `<span class="scn-mix">
              ${beds(i, "studio", "Studio", Math.round(s.shStudio*100))}
              ${beds(i, "1", "1B", b1)}
              ${beds(i, "2", "2B", Math.round(s.sh2B*100))}
              ${beds(i, "3", "3B", Math.round(s.sh3B*100))}
              <span class="scn-mix-total" id="scn-total-${i}">= 100%</span>
             </span>`;
        return `<label class="scn-row">
          <input type="checkbox" class="scn-chk" data-idx="${i}" checked>
          <span class="scn-name" id="scn-name-${i}">${esc(s.name)}</span>
          <span class="scn-tag scn-tag-${s.constr.toLowerCase()}">${esc(s.constr)}</span>
          <span class="scn-controls">
            <span class="scn-ctl"><span class="scn-ctl-lbl">Stories</span><input type="number" class="scn-num" data-idx="${i}" data-k="stories" min="1" max="40" step="1" value="${esc(s.stories)}"></span>
            <span class="scn-ctl"><span class="scn-ctl-lbl">Podium</span><input type="number" class="scn-num" data-idx="${i}" data-k="podium" min="0" max="6" step="1" value="${esc(s.podium)}"></span>
            <span class="scn-sf">${esc(sfNote)}</span>
          </span>
          ${mixHtml}
        </label>`;
      }),
    ].join("");

    document.getElementById("scn-all").addEventListener("change", (e) => {
      $("#scn-list").querySelectorAll(".scn-chk").forEach(cb => { cb.checked = e.target.checked; });
    });
    // One delegated listener: any stories/podium/mix edit refreshes that row's
    // live label + the running mix total.
    $("#scn-list").addEventListener("input", (e) => {
      const idx = e.target && e.target.dataset && e.target.dataset.idx;
      if (idx != null) updateScnRow(idx);
    });
    this.scenarios.forEach((_, i) => updateScnRow(i));
  },

  selected() {
    return [...$("#scn-list").querySelectorAll(".scn-chk")]
      .filter(cb => cb.checked)
      .map(cb => scnRowFromDom(cb.dataset.idx));
  },
};

// Read one scenario row's current values straight from the DOM (the inputs are
// the source of truth once rendered) and recompute its derived label + mix total.
function scnRowFromDom(idx) {
  const root = $("#scn-list");
  const numv = (k, d) => {
    const el = root.querySelector(`.scn-num[data-idx="${idx}"][data-k="${k}"]`);
    const v = el ? Number(el.value) : d;
    return Number.isFinite(v) ? v : d;
  };
  const base = ScenarioPicker.scenarios[idx] || {};
  const s = {
    constr: base.constr, lf: base.lf,
    stories: Math.max(1, Math.round(numv("stories", base.stories))),
    podium: Math.max(0, Math.round(numv("podium", base.podium))),
    shStudio: 0, sh2B: 0, sh3B: 0,
  };
  if (s.lf === "Yes") {
    s.sh2B = 0.25; s.sh3B = 0.25; s.mixTotal = 100;
  } else {
    const bedv = (b) => {
      const el = root.querySelector(`.scn-mix-inp[data-idx="${idx}"][data-bed="${b}"]`);
      const v = el ? Number(el.value) : 0;
      return Number.isFinite(v) ? Math.min(100, Math.max(0, v)) : 0;
    };
    const st = bedv("studio"), one = bedv("1"), two = bedv("2"), three = bedv("3");
    s.shStudio = st / 100; s.sh2B = two / 100; s.sh3B = three / 100;
    s.mixTotal = st + one + two + three;
  }
  s.name = scenarioLabel(s);
  return s;
}

function updateScnRow(idx) {
  const s = scnRowFromDom(idx);
  const nameEl = document.getElementById(`scn-name-${idx}`);
  if (nameEl) nameEl.textContent = s.name;
  const tot = document.getElementById(`scn-total-${idx}`);
  if (tot && s.lf !== "Yes") {
    const ok = s.mixTotal === 100;
    tot.textContent = ok ? "= 100%" : `= ${s.mixTotal}% ⚠`;
    tot.classList.toggle("scn-total-bad", !ok);
  }
}

$("#scn-cancel").addEventListener("click", () => ScenarioPicker.close());
$("#scn-go").addEventListener("click", () => {
  const sel = ScenarioPicker.selected();
  const err = $("#scn-error");
  if (!sel.length) {
    err.textContent = "Select at least one scenario.";
    err.classList.remove("hidden");
    return;
  }
  const badMix = sel.filter(s => s.lf !== "Yes" && s.mixTotal !== 100);
  if (badMix.length) {
    err.textContent = "Unit mix must total 100% — fix: " + badMix.map(s => `${s.name} (= ${s.mixTotal}%)`).join("; ");
    err.classList.remove("hidden");
    return;
  }
  err.classList.add("hidden");
  ScenarioPicker.close();
  launch({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: "lihtc_scenarios",
      from_job: ScenarioPicker.jobId,
      overrides: ScenarioPicker.overrides,
      scenarios: sel,
    }),
  });
});

// JS mirror of uw_logic's derive rules — live preview only; Python writes the file.
function deriveModelPreview(v) {
  const lf = v.resource === "High" || v.resource === "Highest";
  const cra = (String(v.neighborhood_change).toLowerCase() !== "yes" && !lf) ? "Yes" : "No";
  const mix = lf ? "0% Studio · 50% 1B · 25% 2B · 25% 3B" : "100% 1B";
  const sf = (v.land_sf != null && v.land_sf !== "") ? fmt(v.land_sf) : "—";
  const pos = (x) => (x != null && x !== "" && Number(x) > 0);
  const stories = pos(v.residential_stories) ? Number(v.residential_stories) : 5;
  const dflt = (real) => (real ? "" : " (default)");
  return [
    { label: "Project (B2)", value: v.deal_name || "—" },
    { label: "County (C3)", value: v.county || "—" },
    { label: "PHA (C4)", value: v.pha || "—" },
    { label: "QCT/DDA (C5)", value: v.qct_dda || "—" },
    { label: "Resource (C6)", value: v.resource || "—" },
    { label: "Neighborhood change (C7)", value: v.neighborhood_change || "—" },
    { label: "Land SF (C12)", value: sf },
    { label: "Land purchase price (S16)", value: pos(v.acquisition_price) ? "$" + fmt(v.acquisition_price) : "— defaults to $150/SF" },
    { label: "Residential stories (C15)", value: stories + dflt(pos(v.residential_stories)) },
    { label: "→ Product", value: lf ? "Large Family" : "Standard (1B)" },
    { label: "→ CRA (C8)", value: cra },
    { label: "→ Bedroom mix", value: mix },
    { label: "→ AMI mix", value: "10% @30% · 10% @50% · 80% @60%" },
  ];
}

// ---------- rent-comp grid editor (matrix; reuses the edit→preview→auto-chain pattern) ----------
async function openCompEditor(jobId) {
  showError(null);
  try {
    const res = await fetch(`/api/comps/intake/${jobId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not load comps.");
    CompEditor.open(jobId, data);
  } catch (err) { showError(err.message); }
}

const CompEditor = {
  jobId: null, ruleset: null, beds: null, active: 0,
  open(jobId, intake) {
    this.jobId = jobId;
    this.ruleset = intake.ruleset;
    // seed editable state: subject (blank chars) + comps per bed
    this.beds = {};
    intake.beds.forEach(bt => {
      this.beds[bt.bed] = {
        subject: { sf: null, rent: null, year: null, baths: null, city: "",
                   amenities: {}, utilities: {} },
        comps: bt.comps.map(c => ({ ...c, include: true, amenities: c.amenity_flags || {}, utilities: c.utility_flags || {} })),
      };
    });
    this.active = intake.beds[0] ? intake.beds[0].bed : 0;
    $("#comp-sub").textContent = `${intake.label} — confirm the comps, set each one's characteristics; adjustments compute live from the ruleset, then export.`;
    this.renderTabs();
    this.renderMatrix();
    $("#comp-error").classList.add("hidden");
    $("#comp-panel").classList.remove("hidden");
    $("#comp-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  },
  close() { $("#comp-panel").classList.add("hidden"); },
  BED_LABEL: { 0: "Studio", 1: "1BR", 2: "2BR", 3: "3BR", 4: "4BR" },
  renderTabs() {
    $("#comp-bedtabs").innerHTML = Object.keys(this.beds).map(b =>
      `<button type="button" class="comp-bedtab${Number(b) === this.active ? " active" : ""}" data-bed="${b}">${this.BED_LABEL[b] || b + "BR"} (${this.beds[b].comps.length})</button>`).join("");
    $("#comp-bedtabs").querySelectorAll(".comp-bedtab").forEach(t =>
      t.addEventListener("click", () => { this.active = Number(t.dataset.bed); this.renderTabs(); this.renderMatrix(); }));
  },
  // JS mirror of comp_adjust (live preview only; Python writes the file)
  adj(subj, comp) {
    const rs = this.ruleset;
    const size = (subj.sf && comp.sf && subj.rent) ? (subj.sf - comp.sf) * (subj.rent / subj.sf * rs.size_rate_fraction) : 0;
    const age = (subj.year && comp.year) ? (subj.year - comp.year) * rs.age_per_year : 0;
    const line = (sh, ch, v) => (ch && !sh) ? -v : (sh && !ch) ? v : 0;
    let lines = 0;
    rs.utility_labels.forEach(l => lines += line(subj.utilities[l], comp.utilities[l], rs.utility_values[l]));
    rs.amenity_labels.forEach(l => lines += line(subj.amenities[l], comp.amenities[l], rs.amenity_values[l]));
    const total = size + age + lines;
    const adjRent = (comp.rent || 0) + total;
    return { size, age, lines, total, adjRent, ratio: comp.rent ? adjRent / comp.rent : null };
  },
  renderMatrix() {
    const bed = this.beds[this.active];
    const subj = bed.subject;
    const comps = bed.comps;
    const colH = `<th class="cm-rowlab">Line</th><th class="cm-subj">Subject</th>` +
      comps.map((c, i) => `<th>${esc(c.address || "Comp " + (i + 1))}</th>`).join("");
    const numRow = (label, key) =>
      `<tr><td class="cm-rowlab">${label}</td>` +
      `<td><input type="number" data-who="subject" data-k="${key}" value="${subj[key] ?? ""}"></td>` +
      comps.map((c, i) => `<td><input type="number" data-who="${i}" data-k="${key}" value="${c[key] ?? ""}"></td>`).join("") + `</tr>`;
    const txtRow = (label, key) =>
      `<tr><td class="cm-rowlab">${label}</td>` +
      `<td><input type="text" data-who="subject" data-k="${key}" data-txt="1" value="${esc(subj[key] ?? "")}"></td>` +
      comps.map((c, i) => `<td>${esc(c[key] ?? "—")}</td>`).join("") + `</tr>`;
    const infoRow = (label, vals) =>
      `<tr class="cm-info"><td class="cm-rowlab">${label}</td><td>—</td>` +
      vals.map(v => `<td>${esc(v ?? "—")}</td>`).join("") + `</tr>`;
    const chkRow = (label, group) =>
      `<tr><td class="cm-rowlab cm-amen">${esc(label)}</td>` +
      `<td><input type="checkbox" data-who="subject" data-g="${group}" data-l="${esc(label)}"${subj[group][label] ? " checked" : ""}></td>` +
      comps.map((c, i) => `<td><input type="checkbox" data-who="${i}" data-g="${group}" data-l="${esc(label)}"${c[group][label] ? " checked" : ""}></td>`).join("") + `</tr>`;
    const incRow = `<tr><td class="cm-rowlab">Include in grid</td><td>—</td>` +
      comps.map((c, i) => `<td><input type="checkbox" data-who="${i}" data-inc="1"${c.include ? " checked" : ""}></td>`).join("") + `</tr>`;
    const sub = (t) => `<tr class="cm-sub"><td colspan="${comps.length + 2}">${t}</td></tr>`;
    const computed = `<tbody id="cm-computed">${this.computedRows()}</tbody>`;

    $("#comp-matrix").innerHTML = `<table class="comp-matrix"><thead><tr>${colH}</tr></thead>
      <tbody>
        ${incRow}
        ${txtRow("City", "city")}
        ${infoRow("Distance (mi)", comps.map(c => c.distance_mi))}
        ${numRow("Unit Size (SF)", "sf")}
        ${numRow("Base Rent ($)", "rent")}
        ${numRow("Year built/renov.", "year")}
        ${numRow("# Bathrooms", "baths")}
        ${sub("Utilities paid by tenant")}
        ${this.ruleset.utility_labels.map(l => chkRow(l, "utilities")).join("")}
        ${sub("Amenities (check what each HAS)")}
        ${this.ruleset.amenity_labels.map(l => chkRow(l, "amenities")).join("")}
      </tbody>
      ${computed}
    </table>`;
    this.bind();
  },
  computedRows() {
    const bed = this.beds[this.active], subj = bed.subject, comps = bed.comps;
    const cell = (fn, cls = "") => `<td class="${cls}">—</td>` /*subject col*/;
    const line = (label, pick, fmtFn, flag) =>
      `<tr class="cm-calc"><td class="cm-rowlab">${label}</td><td>${label === "Adjusted Rent" && subj.rent ? "$" + fmt(subj.rent) : "—"}</td>` +
      comps.map(c => {
        const a = this.adj(subj, c);
        const over = flag && c.rent && (a.adjRent / c.rent) > this.ruleset.guardrail;
        return `<td class="${over ? "cm-over" : ""}">${fmtFn(a, c)}</td>`;
      }).join("") + `</tr>`;
    const money = v => v == null ? "—" : (v < 0 ? "-$" + fmt(-v) : "$" + fmt(v));
    return (
      line("Size adj", null, a => money(a.size)) +
      line("Age adj", null, a => money(a.age)) +
      line("Amenity/utility adj", null, a => money(a.lines)) +
      line("Adjusted Rent", null, a => money(a.adjRent), false) +
      line("Adj rent ÷ base", null, (a, c) => c.rent ? (a.adjRent / c.rent * 100).toFixed(1) + "%" : "—", true)
    );
  },
  refreshComputed() { $("#cm-computed").innerHTML = this.computedRows(); },
  bind() {
    const bed = this.beds[this.active];
    $("#comp-matrix").querySelectorAll("input").forEach(el => {
      const ev = el.type === "checkbox" ? "change" : "input";
      el.addEventListener(ev, () => {
        const who = el.dataset.who;
        const target = who === "subject" ? bed.subject : bed.comps[Number(who)];
        if (el.dataset.inc) { target.include = el.checked; return; }
        if (el.dataset.g) { target[el.dataset.g][el.dataset.l] = el.checked; }
        else if (el.dataset.k) {
          target[el.dataset.k] = el.dataset.txt
            ? el.value
            : (el.value === "" ? null : Number(el.value));
        }
        this.refreshComputed();
      });
    });
  },
  collect() {
    const grid = {};
    for (const [b, bed] of Object.entries(this.beds)) {
      const comps = bed.comps.filter(c => c.include);
      if (!comps.length) continue;
      grid[b] = {
        subject: { ...bed.subject },
        comps: comps.map(c => ({ address: c.address, city: c.city, distance_mi: c.distance_mi,
                                 sf: c.sf, rent: c.rent, year: c.year, baths: c.baths,
                                 amenities: c.amenities, utilities: c.utilities })),
      };
    }
    return grid;
  },
};
$("#comp-cancel").addEventListener("click", () => CompEditor.close());
$("#comp-go").addEventListener("click", () => {
  const grid = CompEditor.collect();
  if (!Object.keys(grid).length) { const e = $("#comp-error"); e.textContent = "Include at least one comp."; e.classList.remove("hidden"); return; }
  CompEditor.close();
  launch({ method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ mode: "comps_grid", from_job: CompEditor.jobId, grid }) });
});

// ---------- reusable Review & Edit step ----------
// schema = { subtitle, confirmLabel, previewNote, values:{}, fields:[{id,label,type,options,help}], derive:(values)->[{label,value}] }
const ReviewEditor = {
  schema: null, values: null, onConfirm: null,
  open(schema, onConfirm) {
    this.schema = schema;
    this.values = { ...schema.values };
    this.onConfirm = onConfirm;
    $("#review-sub").textContent = schema.subtitle || "";
    $("#review-go").textContent = schema.confirmLabel || "Generate";
    $("#review-error").classList.add("hidden");
    this.renderInputs();
    this.renderPreview();
    $("#review-panel").classList.remove("hidden");
    $("#review-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  },
  close() { $("#review-panel").classList.add("hidden"); },
  renderInputs() {
    $("#review-inputs").innerHTML = this.schema.fields.map(f => {
      const v = this.values[f.id] ?? "";
      let ctrl;
      if (f.type === "select") {
        ctrl = `<select data-fid="${esc(f.id)}">${f.options.map(opt =>
          `<option value="${esc(opt)}"${String(opt) === String(v) ? " selected" : ""}>${esc(opt)}</option>`).join("")}</select>`;
      } else {
        const ph = f.placeholder != null ? ` placeholder="${esc(f.placeholder)}"` : "";
        ctrl = `<input type="${f.type === "number" ? "number" : "text"}" data-fid="${esc(f.id)}" value="${esc(v)}"${ph}>`;
      }
      const lbl = esc(f.label) + (f.required ? ` <span class="rv-req">*</span>` : "");
      return `<div class="rv-field"><label>${lbl}</label>${ctrl}${f.help ? `<span class="rv-help">${esc(f.help)}</span>` : ""}</div>`;
    }).join("");
    $("#review-inputs").querySelectorAll("[data-fid]").forEach(el => {
      el.addEventListener("input", () => {
        const f = this.schema.fields.find(x => x.id === el.dataset.fid);
        this.values[el.dataset.fid] = (f.type === "number")
          ? (el.value === "" ? null : Number(el.value)) : el.value;
        this.renderPreview();
      });
    });
  },
  missingRequired() {
    return (this.schema.fields || [])
      .filter(f => f.required)
      .filter(f => { const v = this.values[f.id]; return v === null || v === undefined || v === ""; })
      .map(f => f.label);
  },
  renderPreview() {
    const rows = this.schema.derive(this.values);
    $("#review-preview").innerHTML = `<h3 class="section-head">Model will use</h3>`
      + `<table>${rows.map(r => `<tr><td class="col-field">${esc(r.label)}</td><td class="col-answer">${esc(r.value)}</td></tr>`).join("")}</table>`
      + (this.schema.previewNote ? `<p class="hint">${esc(this.schema.previewNote)}</p>` : "");
  },
};
// Deal-type toggle inside the model-review panel — re-renders the matching form.
$("#review-dealtype").addEventListener("click", (e) => {
  const btn = e.target.closest(".dt-opt");
  if (!btn || !_modelReview.intake) return;
  const dt = btn.dataset.dt;
  if (dt === _modelReview.dealType) return;
  _modelReview.dealType = dt;
  $("#review-dealtype").querySelectorAll(".dt-opt").forEach(b =>
    b.classList.toggle("active", b === btn));
  if (dt === "nonlihtc") openNonLihtcReview(_modelReview.jobId, _modelReview.intake);
  else openLihtcReview(_modelReview.jobId, _modelReview.intake);
});

$("#review-cancel").addEventListener("click", () => ReviewEditor.close());
$("#review-go").addEventListener("click", () => {
  const missing = ReviewEditor.missingRequired();
  const err = $("#review-error");
  if (missing.length) {
    err.textContent = `Please fill required field${missing.length > 1 ? "s" : ""}: ${missing.join(", ")}.`;
    err.classList.remove("hidden");
    return;
  }
  err.classList.add("hidden");
  ReviewEditor.close();
  if (ReviewEditor.onConfirm) ReviewEditor.onConfirm(ReviewEditor.values);
});

// ---------- polling ----------
function poll(jobId) {
  $("#status-panel").classList.remove("hidden");
  const tick = async () => {
    let job;
    try {
      const res = await fetch(`/api/job/${jobId}`);
      job = await res.json();
      if (!res.ok) throw new Error(job.error || "Lost the job.");
    } catch (err) {
      clearInterval(pollTimer);
      setRunning(false);
      showError(err.message);
      return;
    }
    render(job);
    if (job.status !== "running") {
      clearInterval(pollTimer);
      setRunning(false);
      if (job.status === "error") showError(job.error || "The run failed.");
      // a finished comp shortlist auto-opens the editable grid (the in-between step)
      if (job.status === "done" && job.kind === "comps") openCompEditor(job.id);
      loadStats();
      loadRecent();
    }
  };
  tick();
  pollTimer = setInterval(tick, 1200);
}

// ---------- render ----------
function render(job) {
  $("#phase").textContent = job.phase || "";
  if (job.geo) {
    $("#matched").textContent = job.geo.matched_address
      + (job.geo.geoid ? `  ·  tract ${job.geo.geoid}` : "");
  }

  const pct = job.total ? Math.round((job.completed / job.total) * 100) : (job.status === "running" ? 8 : 0);
  $("#progress-bar").style.width = pct + "%";
  $("#counts").textContent = job.total ? `${job.completed} / ${job.total} fields` : "";

  if (job.downloadable) {
    const dl = $("#download");
    dl.href = `/api/download/${job.id}`;
    dl.textContent = job.kind === "pdf_summary"    ? "Download PDF"
                   : job.kind === "lihtc_scenarios" ? "Download models (.zip)"
                   : job.underwrite                  ? "Download models (.zip)"
                   : "Download .xlsx";
    dl.classList.remove("hidden");
  }

  // Track the latest DD / scenario job for chaining. The per-stage actions now
  // live in the deal workspace (opened below), so the loose status-panel buttons
  // stay hidden — kept in the DOM only as a fallback.
  const isDD = job.kind === "single" || job.kind === "assemblage";
  if (isDD && job.downloadable) {
    lastDDJob = job.id;
    lastDDAddress = job.geo ? job.geo.matched_address : "";
  }
  if (job.kind === "lihtc_scenarios" && job.downloadable) {
    lastScnJob = job.id;
  }

  if (job.parcels) renderParcels(job);
  if (job.om) renderOM(job.om);
  if (job.underwrite) renderUnderwrite(job.underwrite);
  renderFields(job.fields || []);

  // Deal workspace: a finished DD opens its workspace; a finished downstream
  // stage refreshes the workspace already on screen.
  if (isDD && job.downloadable) {
    DealWorkspace.open(job.id);
  } else if (_activeDealId && ["comps", "comps_grid", "underwrite", "lihtc_scenarios", "pdf_summary"].includes(job.kind)) {
    DealWorkspace.refresh();
  }
}

function renderUnderwrite(uw) {
  if (uw.deal_type === "nonlihtc") return renderUnderwriteNonLihtc(uw);
  const panel = $("#uw-panel");
  panel.classList.remove("hidden");
  $("#uw-sub").textContent = `${uw.deal} · product: ${uw.product || "—"}`
    + (uw.resource ? ` · resource ${uw.resource}` : "");
  const inRows = Object.entries(uw.inputs || {}).map(([k, v]) =>
    `<tr><td class="col-field">${esc(k)}</td><td class="col-answer">${esc(v === null || v === "" ? "—" : v)}</td></tr>`
  ).join("");
  const flags = (uw.flags || []).length
    ? `<div class="uw-flags">${uw.flags.map(f => `<p>⚑ ${esc(f)}</p>`).join("")}</div>` : "";
  const models = (uw.models || []).map(m => `<li>${esc(m)}</li>`).join("");
  $("#uw-body").innerHTML = `
    <p class="combined">Two models generated — download is a .zip:</p>
    <ul class="uw-models">${models}</ul>
    ${flags}
    <h3 class="section-head">DD inputs used</h3>
    <table>${inRows}</table>
    <p class="hint">Left blank for the analyst to fill, then recalc in Excel: ${esc((uw.hand_fields || []).join(", "))}.</p>`;
}

// Non-LIHTC (market) result — single ModularZ market model + headline returns.
function renderUnderwriteNonLihtc(uw) {
  const panel = $("#uw-panel");
  panel.classList.remove("hidden");
  const mixed = uw.program === "mixed-income";
  $("#uw-sub").textContent = `${uw.deal} · Non-LIHTC (${mixed ? "mixed-income" : "market"}) · pre-v28 ModularZ engine`;

  const PCT = new Set(["Levered IRR", "Cash-on-Cash", "Untrended Yield-on-Cost"]);
  const MULT = new Set(["Equity Multiple"]);
  const fmtReturn = (k, v) => {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return esc(v);
    if (PCT.has(k)) return (n * 100).toFixed(2) + "%";
    if (MULT.has(k)) return n.toFixed(2) + "x";
    return (n < 0 ? "-$" : "$") + fmt(Math.abs(Math.round(n)));
  };
  const ORDER = ["Levered IRR", "Equity Multiple", "Cash-on-Cash", "Untrended Yield-on-Cost",
    "Net Operating Income", "Effective Gross Income", "Operating Expenses",
    "Total Dev Cost", "Price per Unit", "Equity Required", "Debt", "Total Profit"];
  const ret = uw.returns || {};
  const keys = ORDER.filter(k => k in ret).concat(Object.keys(ret).filter(k => !ORDER.includes(k)));
  const retRows = keys.map(k =>
    `<tr><td class="col-field">${esc(k)}</td><td class="col-answer">${fmtReturn(k, ret[k])}</td></tr>`
  ).join("");
  const models = (uw.models || []).map(m => `<li>${esc(m)}</li>`).join("");
  const haveReturns = keys.length > 0;

  // Mixed-income AMI tier breakdown (from the server's allocation summary).
  let amiBlock = "";
  if (mixed && uw.ami && (uw.ami.tiers || []).length) {
    const a = uw.ami;
    const tierRows = a.tiers.map(t => {
      const beds = t.by_bed || {};
      const rents = t.rents || {};
      const bedStr = [1, 2, 3].filter(b => beds[b]).map(b =>
        `${beds[b]}×${b}BR@$${fmt(rents[b] || 0)}`).join(", ");
      return `<tr><td class="col-field">${esc(t.ami)}% AMI</td>`
        + `<td class="col-answer">${t.units} units — ${esc(bedStr || "—")}</td></tr>`;
    }).join("");
    amiBlock = `<h3 class="section-head">AMI allocation</h3>
      <table>${tierRows}
        <tr><td class="col-field">Restricted / market</td>
        <td class="col-answer">${a.restricted_units} restricted · ${a.market_units} market · ${a.manager_units} mgr</td></tr>
      </table>`;
  }
  // Debt stack (senior + optional subordinate).
  let loanBlock = "";
  if (uw.loans && (uw.loans.loans || []).length) {
    const loanRows = uw.loans.loans.map(l => {
      const desc = l.role === "senior"
        ? `${(l.basis || "").toUpperCase()} ${l.value ?? "—"} @ ${l.rate != null ? (l.rate * 100).toFixed(2) + "%" : "—"} / ${l.amort || "—"}yr`
        : `$${fmt(l.amount || 0)} @ ${l.rate != null ? (l.rate * 100).toFixed(2) + "%" : "0%"} · ${l.io ? "IO/deferred" : (l.amort + "yr")}`;
      return `<tr><td class="col-field">${esc(l.label)}</td><td class="col-answer">${esc(desc)}</td></tr>`;
    }).join("");
    const unmod = (uw.loans.unmodelled || []).length
      ? `<tr><td class="col-field">Not modelled</td><td class="col-answer">${esc(uw.loans.unmodelled.join(", "))} (no workbook slot)</td></tr>` : "";
    loanBlock = `<h3 class="section-head">Debt stack</h3><table>${loanRows}${unmod}</table>
      <p class="hint">Levered IRR &amp; Equity Multiple reflect the full stack (senior + subordinate). Cash-on-Cash &amp; Yield-on-Cost are senior-only / unlevered.</p>`;
  }
  const note = mixed
    ? "Mixed-income: restricted AMI units carry CTCAC/MTSP gross caps (by county); any market remainder uses comp $/mo. Restricted units are netted against the unit program. Studios aren't modeled."
    : "Market mode: restricted set-aside &amp; affordable unit rows zeroed; rents are the comp $/mo. Studios aren't modeled (no modular studio product).";
  $("#uw-body").innerHTML = `
    <p class="combined">${mixed ? "Mixed-income" : "Market"} model generated on the clean pre-v28 ModularZ engine — download is a .zip:</p>
    <ul class="uw-models">${models}</ul>
    ${amiBlock}
    ${loanBlock}
    ${haveReturns
      ? `<h3 class="section-head">Headline returns</h3><table>${retRows}</table>`
      : `<p class="hint">Returns didn't recalc server-side — open the .xlsx (it recalcs on load).</p>`}
    <p class="hint">${note}</p>`;
}

function renderOM(om) {
  const panel = $("#om-panel");
  const sub = $("#om-sub");
  if (om.error) {
    panel.classList.remove("hidden");
    sub.innerHTML = `<span class="om-err">OM not read: ${esc(om.error)}</span>`;
    $("#om-body").innerHTML = "";
    return;
  }
  const rows = om.extracted || [];
  if (!rows.length) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  const byId = Object.fromEntries((om.merged || []).map(m => [m.field_id, m]));
  const nConf = (om.merged || []).filter(m => m.outcome === "conflict").length;
  sub.textContent = `${rows.length} value(s) read from ${om.name || "the OM"}`
    + (nConf ? ` · ${nConf} conflict(s) — DD value kept, see notes` : "");
  $("#om-body").innerHTML = rows.map(r => {
    const m = byId[r.field_id] || {};
    const outcome = m.outcome || "om-sourced";
    const tag = { "agree": ["agree", "OM = DD ✓"], "conflict": ["conflict", `DD kept: ${esc(m.dd_value)}`],
                  "om-sourced": ["sourced", "OM-sourced"] }[outcome] || ["sourced", "OM-sourced"];
    return `<tr>
      <td class="src-name">${esc(r.field_id)}</td>
      <td>${esc(r.value)} <span class="om-conf om-conf-${esc(r.confidence)}">${esc(r.confidence)}</span></td>
      <td><span class="om-out om-out-${tag[0]}">${tag[1]}</span></td>
      <td class="src-detail">${esc(r.source_quote)}</td>
    </tr>`;
  }).join("");
}

function renderParcels(job) {
  const el = $("#parcels");
  el.classList.remove("hidden");
  const rows = job.parcels.map(p =>
    `<tr><td>${esc(p.apn)}</td><td>${p.n_lots} lot(s)</td><td>${fmt(p.land_sf)} sf</td><td>tract ${esc(p.geoid)}</td></tr>`
  ).join("");
  const combined = job.combined_sf
    ? `<p class="combined">Combined land area: ${fmt(job.combined_sf)} sf (${(job.combined_sf / 43560).toFixed(3)} ac)</p>` : "";
  el.innerHTML = `<table>${rows}</table>${combined}`;
}

function renderFields(fields) {
  const bySection = {};
  for (const f of fields) (bySection[f.section] ||= []).push(f);

  const order = [...SECTION_ORDER, ...Object.keys(bySection).filter(s => !SECTION_ORDER.includes(s))];
  const html = order.filter(s => bySection[s]).map(secId => {
    const rows = bySection[secId].map(f => `
      <tr>
        <td class="col-field">${esc(f.label)}</td>
        <td class="col-answer">${esc(f.answer === null || f.answer === "" ? "—" : f.answer)}</td>
        <td class="col-state">${badge(f.state)}</td>
        <td class="col-notes">${esc(f.notes)}</td>
      </tr>`).join("");
    return `
      <div class="section-block">
        <h3 class="section-head">${esc(SECTION_LABEL[secId] || secId)}</h3>
        <table>
          <thead><tr><th>Field</th><th>Answer</th><th>State</th><th>Notes</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }).join("");
  $("#results").innerHTML = html;
}

function badge(state) {
  const s = (state || "").toUpperCase();
  let cls = "other";
  if (s === "VERIFIED" || s === "COMPUTED" || s === "OM-SOURCED") cls = "verified";
  else if (s === "JUDGMENT") cls = "judgment";
  else if (s === "OM-SOURCED") cls = "omsourced";
  else if (s === "NA") cls = "na";
  else if (s.startsWith("TOOL-FAIL")) cls = "toolfail";
  else if (s === "MANUAL-VERIFY") cls = "manual";
  return `<span class="badge ${cls}">${esc(state || "")}</span>`;
}

// ---------- helpers ----------
function setRunning(on) {
  const btn = $("#run-btn");
  btn.disabled = on;
  btn.textContent = on ? "Running…" : (mode === "underwrite" ? "Generate model"
    : mode === "comps" ? "Find rent comps" : "Run feasibility");
}
function resetStatus() {
  $("#results").innerHTML = "";
  $("#om-panel").classList.add("hidden");
  $("#om-body").innerHTML = "";
  $("#parcels").classList.add("hidden");
  $("#parcels").innerHTML = "";
  $("#uw-panel").classList.add("hidden");
  $("#uw-body").innerHTML = "";
  $("#review-panel").classList.add("hidden");
  $("#cpf-panel").classList.add("hidden");
  $("#comp-panel").classList.add("hidden");
  $("#gen-model").classList.add("hidden");
  $("#gen-comps").classList.add("hidden");
  $("#gen-pdf").classList.add("hidden");
  $("#download").classList.add("hidden");
  $("#matched").textContent = "";
  $("#progress-bar").style.width = "0%";
  $("#counts").textContent = "";
}
function showError(msg) {
  const el = $("#form-error");
  if (!msg) { el.classList.add("hidden"); el.textContent = ""; return; }
  el.textContent = msg;
  el.classList.remove("hidden");
}
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmt(n) { return Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 }); }
// Render a stored timestamp in Pacific time on a 12-hour clock (e.g. "Jun 22,
// 2026, 11:38 AM PDT"). Stored stamps are UTC; legacy naive ones lack an offset,
// so assume UTC for those too (the server runs in UTC).
function fmtWhen(iso) {
  if (!iso) return "";
  const hasTz = /[zZ]$|[+-]\d\d:?\d\d$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  if (isNaN(d.getTime())) return iso.replace("T", " ");
  return d.toLocaleString("en-US", {
    timeZone: "America/Los_Angeles", month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true, timeZoneName: "short",
  });
}

// ---------- time-saved metric ----------
async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) return;
    const s = await r.json();
    $("#hours-saved").textContent = fmt(s.hours_saved);
    const bd = $("#metric-breakdown");
    if (bd && Array.isArray(s.by_stage)) {
      bd.innerHTML = s.by_stage.map(st => {
        const runs = fmt(st.runs);
        const title = `${runs} run${st.runs === 1 ? "" : "s"} × ${st.minutes_per} min ≈ ${fmt(st.hours_saved)} hrs`;
        return `<span class="ms-stage" title="${esc(title)}">`
          + `<span class="ms-runs">${runs}</span> <span class="ms-label">${esc(st.label)}</span></span>`;
      }).join("");
    }
  } catch (_) { /* leave placeholders */ }
}

// ---------- recent runs ----------
async function loadRecent() {
  try {
    const r = await fetch("/api/recent");
    if (!r.ok) return;
    const { runs } = await r.json();
    const panel = $("#recent-panel");
    if (!runs.length) { panel.classList.add("hidden"); return; }
    panel.classList.remove("hidden");
    $("#recent-body").innerHTML = runs.map(run => `
      <tr>
        <td class="rc-site">${esc(run.label)}</td>
        <td>${run.kind === "assemblage" ? "Assemblage" : run.kind === "underwrite" ? "Model" : "Single"}</td>
        <td>${run.fields}${run.flags ? ` <span class="rc-flag" title="${run.flags} field(s) need manual verification">⚑ ${run.flags}</span>` : ""}</td>
        <td class="rc-when">${esc(fmtWhen(run.finished))}</td>
        <td class="rc-actions">
          ${run.can_model ? `<button class="rc-open" type="button" data-job="${esc(run.id)}" title="Open this deal's pipeline">Open deal →</button>` : ""}
          ${run.downloadable ? `<a class="rc-dl" href="/api/download/${run.id}">Download</a>` : ""}
        </td>
      </tr>`).join("");
  } catch (_) { /* ignore */ }
}

// ---------- health dot ----------
async function checkHealth() {
  const el = $("#health");
  try {
    const r = await fetch("/healthz", { cache: "no-store" });
    const ok = r.ok;
    el.classList.toggle("up", ok);
    el.classList.toggle("down", !ok);
    el.querySelector(".health-label").textContent = ok ? "Online" : "Degraded";
    el.title = ok ? "Service healthy" : "Health check failed";
  } catch (_) {
    el.classList.remove("up"); el.classList.add("down");
    el.querySelector(".health-label").textContent = "Offline";
    el.title = "Cannot reach the server";
  }
}

// ---------- boot ----------
loadStats();
loadRecent();
checkHealth();
setInterval(checkHealth, 30000);
