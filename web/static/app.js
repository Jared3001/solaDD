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

// ---------- tab switching ----------
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t === tab));
    const isSources = mode === "sources";
    // Sources is a reference view — swap the run UI for the catalog.
    $("#run-form").classList.toggle("hidden", isSources);
    $("#run-extras").classList.toggle("hidden", isSources);
    $("#sources-panel").classList.toggle("hidden", !isSources);
    if (!isSources) {
      document.querySelectorAll("[data-for]").forEach(f => {
        f.classList.toggle("hidden", f.dataset.for !== mode);
      });
      $("#run-btn").textContent = mode === "underwrite" ? "Generate model"
        : mode === "comps" ? "Find rent comps" : "Run feasibility";
    }
  });
});

// ---------- run ----------
$("#run-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError(null);

  let fetchOpts;
  if (mode === "underwrite") {
    const ddFile = $("#dd").files[0] || null;
    if (!ddFile) { showError("Upload a completed DD checklist (.xlsx)."); return; }
    const fd = new FormData();
    fd.append("mode", "underwrite");
    fd.append("dd", ddFile);
    fd.append("name", $("#uw-name").value.trim());
    fetchOpts = { method: "POST", body: fd };
  } else if (mode === "comps") {
    const address = $("#comp-address").value.trim();
    if (!address) { showError("Enter the subject address to find rent comps."); return; }
    const beds = [...document.querySelectorAll(".comp-bed:checked")].map(c => Number(c.value));
    if (!beds.length) { showError("Pick at least one bed type."); return; }
    fetchOpts = { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ mode: "comps", address, beds }) };
  } else {
    const omFile = mode === "single" ? ($("#om").files[0] || null) : null;
    const address = mode === "single" ? $("#address").value.trim() : "";
    if (mode === "single" && !address && !omFile) {
      showError("Enter an address or upload an OM."); return;
    }
    if (omFile) {
      const fd = new FormData();
      fd.append("mode", "single");
      fd.append("address", address);
      fd.append("om", omFile);
      fetchOpts = { method: "POST", body: fd };           // browser sets multipart boundary
    } else {
      const body = { mode };
      if (mode === "single") body.address = address;
      else body.apns = $("#apns").value;
      fetchOpts = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    }
  }

  await launch(fetchOpts);
});

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

// Holds the current model-review context so the deal-type toggle can re-render
// either review form against the same DD intake.
let _modelReview = { jobId: null, intake: null, dealType: "lihtc" };

// OpEx factors parsed from an uploaded T-12 (per-unit-per-month, plus mgmt %).
// Populated by mountNonLihtcT12(); folded into the non-LIHTC payload on confirm.
let _nlT12Opex = null;

// Dispatcher: shows the LIHTC/Non-LIHTC toggle, then renders the chosen form.
function openModelReview(jobId, intake) {
  _modelReview = { jobId, intake, dealType: "lihtc" };
  _nlT12Opex = null;
  const tg = $("#review-dealtype");
  if (tg) {
    tg.classList.remove("hidden");
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
  const seed = intake.values || {};
  // Comp scraper rents (median $/mo per bed) — pre-fill when the analyst already
  // ran comps for this subject. Keys are bed ints (0=studio,1,2,3).
  const cr = (intake.comp_rents && intake.comp_rents.rents_by_bed) || {};
  const counts = (intake.comp_rents && intake.comp_rents.counts) || {};
  const rentOf = (bed) => (cr[bed] != null ? Number(cr[bed]) : null);
  const compHelp = (bed) => (counts[bed]
    ? `auto-filled: median of ${counts[bed]} comp${counts[bed] > 1 ? "s" : ""} from the AI scraper`
    : "from comp scraper");
  const compNote = intake.comp_rents
    ? `Rents pre-filled from your comp run on ${intake.comp_rents.address || "this subject"} (median $/mo per bed) — edit as needed. `
    : "";
  ReviewEditor.open({
    subtitle: `${intake.label} — non-LIHTC (market) model. ${intake.comp_rents ? "Rents pre-filled from the comp scraper; c" : "Enter the unit program and market rents (from the comp scraper). C"}onfirm the unit program. The pre-v28 ModularZ engine runs in market mode.`,
    confirmLabel: "Generate model →",
    previewNote: compNote + "Drives the clean ModularZ market engine: restricted set-aside + affordable rows are zeroed; rents are the comp $/mo. Modular cost book has no studio product, so studios aren't modeled. Blank OpEx lines fall back to the v5.0.7 PUPM defaults.",
    values: {
      deal_name: seed.deal_name || "",
      land_price: seed.acquisition_price ?? null,
      units_1br: null, units_2br: null, units_3br: null,
      rent_1br: rentOf(1), rent_2br: rentOf(2), rent_3br: rentOf(3),
      exit_cap: 5, perm_rate: 5.75,
    },
    fields: [
      { id: "deal_name", label: "Deal name", type: "text" },
      { id: "land_price", label: "Land purchase price ($)", type: "number",
        placeholder: "e.g. 5000000", help: "defaults to the DD acquisition price if blank" },
      { id: "units_1br", label: "1-BR units", type: "number", required: true, help: "modular product" },
      { id: "units_2br", label: "2-BR units", type: "number" },
      { id: "units_3br", label: "3-BR units", type: "number" },
      { id: "rent_1br", label: "1-BR market rent ($/mo)", type: "number", required: true,
        placeholder: "from comp scraper", help: compHelp(1) },
      { id: "rent_2br", label: "2-BR market rent ($/mo)", type: "number", help: compHelp(2) },
      { id: "rent_3br", label: "3-BR market rent ($/mo)", type: "number", help: compHelp(3) },
      { id: "exit_cap", label: "Exit cap (%)", type: "number", help: "base-case exit cap; default 5.0" },
      { id: "perm_rate", label: "Perm loan rate (%)", type: "number", help: "default 5.75" },
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
    if (num(v.perm_rate) != null) financing.perm_rate = num(v.perm_rate) / 100;
    const nonlihtc = { units_by_bed: units, rents_by_bed: rents };
    if (num(v.land_price) != null) nonlihtc.land_cost = num(v.land_price);
    if (Object.keys(financing).length) nonlihtc.financing = financing;
    if (_nlT12Opex && Object.keys(_nlT12Opex).length) nonlihtc.opex = _nlT12Opex;
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

// Live preview for the non-LIHTC form — mirrors the engine's market-mode rules.
function deriveNonLihtcPreview(v) {
  const num = (x) => (x === null || x === undefined || x === "" ? 0 : Number(x));
  const u1 = num(v.units_1br), u2 = num(v.units_2br), u3 = num(v.units_3br);
  const total = u1 + u2 + u3;
  const mix = total > 0
    ? `${Math.round(u1 / total * 100)}% 1B · ${Math.round(u2 / total * 100)}% 2B · ${Math.round(u3 / total * 100)}% 3B`
    : "—";
  const gpr = (u1 * num(v.rent_1br) + u2 * num(v.rent_2br) + u3 * num(v.rent_3br)) * 12;
  return [
    { label: "Deal", value: v.deal_name || "—" },
    { label: "Land price (Dev Budget G7)", value: num(v.land_price) > 0 ? "$" + fmt(v.land_price) : "— DD default" },
    { label: "Unit program (O11/O12/O13)", value: total > 0 ? `${u1} / ${u2} / ${u3} = ${total} units (+1 mgr)` : "— enter 1-BR" },
    { label: "→ Bed mix", value: mix },
    { label: "Market rents 1B/2B/3B", value: `$${fmt(v.rent_1br || 0)} / $${fmt(v.rent_2br || 0)} / $${fmt(v.rent_3br || 0)}` },
    { label: "→ Annual GPR (approx)", value: gpr > 0 ? "$" + fmt(Math.round(gpr)) : "—" },
    { label: "Exit cap (Dashboard J5)", value: (num(v.exit_cap) || 5) + "%" },
    { label: "Perm rate (Dashboard K12)", value: (num(v.perm_rate) || 5.75) + "%" },
    { label: "Mode", value: "Market (restricted + affordable rows zeroed)" },
  ];
}

// ---------- scenario definitions (mirrors Python's run_lihtc_scenarios logic) ----------
function defaultScenarios(resource) {
  const lf = resource === "High" || resource === "Highest";
  const base = [
    { name: "Modular 5st — 100% 1B",        constr: "Modular", stories: 5,  podium: 1, lf: "No",  sh2B: 0,    sh3B: 0    },
    { name: "Stick 5st — 50% 1B / 50% 2B",  constr: "Stick",   stories: 5,  podium: 1, lf: "No",  sh2B: 0.5,  sh3B: 0    },
    { name: "Modular 12st — 100% 1B",        constr: "Modular", stories: 12, podium: 1, lf: "No",  sh2B: 0,    sh3B: 0    },
  ];
  if (lf) {
    base.push(
      { name: "Modular 5st — Large Family",  constr: "Modular", stories: 5,  podium: 1, lf: "Yes", sh2B: 0.25, sh3B: 0.25 },
      { name: "Stick 5st — Large Family",    constr: "Stick",   stories: 5,  podium: 1, lf: "Yes", sh2B: 0.25, sh3B: 0.25 },
      { name: "Modular 12st — Large Family", constr: "Modular", stories: 12, podium: 1, lf: "Yes", sh2B: 0.25, sh3B: 0.25 },
    );
  }
  return base;
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
    const TAGS = { "Modular": "Modular", "Stick": "Stick" };
    $("#scn-list").innerHTML = [
      `<div class="scn-selall"><label><input type="checkbox" id="scn-all" checked> Select / deselect all</label></div>`,
      ...this.scenarios.map((s, i) => {
        const sfNote = s.constr === "Modular"
          ? "1B 497 · 2B 804 · 3B 994 SF"
          : (s.lf === "Yes" ? "1B 475 · 2B 735 · 3B 945 SF" : "1B 450 · 2B 700 · 3B 900 SF");
        const mixHtml = s.lf === "Yes"
          ? `<span class="scn-mix"><span class="scn-mix-locked">50% 1B · 25% 2B · 25% 3B (locked — Large Family)</span></span>`
          : `<span class="scn-mix">
              <span class="scn-mix-field"><span class="scn-mix-1b" id="scn-1b-${i}">${Math.round((1-s.sh2B-s.sh3B)*100)}%</span><span class="scn-mix-bed">1B</span></span>
              <span class="scn-mix-sep">·</span>
              <span class="scn-mix-field"><input type="number" class="scn-mix-inp" data-idx="${i}" data-bed="2" min="0" max="100" step="5" value="${Math.round(s.sh2B*100)}"><span class="scn-mix-bed">2B %</span></span>
              <span class="scn-mix-sep">·</span>
              <span class="scn-mix-field"><input type="number" class="scn-mix-inp" data-idx="${i}" data-bed="3" min="0" max="100" step="5" value="${Math.round(s.sh3B*100)}"><span class="scn-mix-bed">3B %</span></span>
             </span>`;
        return `<label class="scn-row">
          <input type="checkbox" class="scn-chk" data-idx="${i}" checked>
          <span class="scn-name">${esc(s.name)}</span>
          <span class="scn-tag scn-tag-${s.constr.toLowerCase()}">${esc(s.constr)}</span>
          <span class="scn-meta">${esc(s.stories)} stories · podium ${s.podium} · ${esc(sfNote)}</span>
          ${mixHtml}
        </label>`;
      }),
    ].join("");

    document.getElementById("scn-all").addEventListener("change", (e) => {
      $("#scn-list").querySelectorAll(".scn-chk").forEach(cb => { cb.checked = e.target.checked; });
    });
    $("#scn-list").querySelectorAll(".scn-mix-inp").forEach(inp => {
      inp.addEventListener("input", () => {
        const idx = inp.dataset.idx;
        const i2 = $("#scn-list").querySelector(`.scn-mix-inp[data-idx="${idx}"][data-bed="2"]`);
        const i3 = $("#scn-list").querySelector(`.scn-mix-inp[data-idx="${idx}"][data-bed="3"]`);
        const v2 = Math.min(100, Math.max(0, Number(i2.value) || 0));
        const v3 = Math.min(100, Math.max(0, Number(i3.value) || 0));
        const el1 = document.getElementById(`scn-1b-${idx}`);
        if (el1) el1.textContent = Math.max(0, 100 - v2 - v3) + "%";
      });
    });
  },

  selected() {
    const checks = [...($("#scn-list").querySelectorAll(".scn-chk"))];
    return checks
      .filter(cb => cb.checked)
      .map(cb => {
        const i = Number(cb.dataset.idx);
        const s = { ...this.scenarios[i] };
        if (s.lf !== "Yes") {
          const i2 = $("#scn-list").querySelector(`.scn-mix-inp[data-idx="${i}"][data-bed="2"]`);
          const i3 = $("#scn-list").querySelector(`.scn-mix-inp[data-idx="${i}"][data-bed="3"]`);
          if (i2) s.sh2B = Math.min(1, Math.max(0, Number(i2.value) / 100));
          if (i3) s.sh3B = Math.min(1, Math.max(0, Number(i3.value) / 100));
        }
        return s;
      });
  },
};

$("#scn-cancel").addEventListener("click", () => ScenarioPicker.close());
$("#scn-go").addEventListener("click", () => {
  const sel = ScenarioPicker.selected();
  const err = $("#scn-error");
  if (!sel.length) {
    err.textContent = "Select at least one scenario.";
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

  // Offer "Generate financial model" and "→ Rent comps" once a DD run is downloadable.
  const isDD = job.kind === "single" || job.kind === "assemblage";
  if (isDD && job.downloadable) {
    lastDDJob = job.id;
    lastDDAddress = job.geo ? job.geo.matched_address : "";
    $("#gen-model").classList.remove("hidden");
    $("#gen-comps").classList.remove("hidden");
  }

  // Offer "Generate PDF summary" once a scenario job is downloadable.
  if (job.kind === "lihtc_scenarios" && job.downloadable) {
    lastScnJob = job.id;
    $("#gen-pdf").classList.remove("hidden");
  }

  if (job.parcels) renderParcels(job);
  if (job.om) renderOM(job.om);
  if (job.underwrite) renderUnderwrite(job.underwrite);
  renderFields(job.fields || []);
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
  $("#uw-sub").textContent = `${uw.deal} · Non-LIHTC (market) · pre-v28 ModularZ engine`;

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
  $("#uw-body").innerHTML = `
    <p class="combined">Market model generated on the clean pre-v28 ModularZ engine — download is a .zip:</p>
    <ul class="uw-models">${models}</ul>
    ${haveReturns
      ? `<h3 class="section-head">Headline returns</h3><table>${retRows}</table>`
      : `<p class="hint">Returns didn't recalc server-side — open the .xlsx (it recalcs on load).</p>`}
    <p class="hint">Market mode: restricted set-aside &amp; affordable unit rows zeroed; rents are the comp $/mo. Studios aren't modeled (no modular studio product).</p>`;
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
          ${run.can_model ? `<button class="rc-gen" type="button" data-job="${esc(run.id)}" title="Build LIHTC v28 model from this checklist">→ Financial model</button>` : ""}
          ${run.can_comps ? `<button class="rc-comps" type="button" data-job="${esc(run.id)}" data-addr="${esc(run.label)}" title="Collect rent comps for this site">→ Rent comps</button>` : ""}
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
