"use strict";

const SECTIONS = window.SECTIONS || [];
const SECTION_LABEL = Object.fromEntries(SECTIONS.map(s => [s.id, s.label]));
const SECTION_ORDER = SECTIONS.map(s => s.id);

let mode = "single";
let pollTimer = null;
let lastDDJob = null;       // most recent completed DD run, for "Generate financial model"

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
      $("#run-btn").textContent = mode === "underwrite" ? "Generate model" : "Run feasibility";
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

// "→ Financial model" next to any previously completed checklist in Recent runs.
$("#recent-body").addEventListener("click", (e) => {
  const btn = e.target.closest(".rc-gen");
  if (btn && btn.dataset.job) genModelFrom(btn.dataset.job);
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

function openModelReview(jobId, intake) {
  const o = intake.options;
  ReviewEditor.open({
    subtitle: `${intake.label} — adjust the automated inputs, preview, then generate. Defaults are the DD answers.`,
    confirmLabel: "Generate Stick + Modular models",
    previewNote: "Derived live from the inputs (same rules the exporter uses). Acquisition price, residential stories, BIPOC & prevailing wage stay analyst-entered in Excel.",
    values: intake.values,
    fields: [
      { id: "deal_name", label: "Deal name", type: "text" },
      { id: "county", label: "County", type: "text" },
      { id: "pha", label: "Public Housing Authority", type: "select", options: o.pha },
      { id: "qct_dda", label: "QCT / DDA", type: "select", options: o.qct_dda },
      { id: "resource", label: "Resource area", type: "select", options: o.resource, help: "drives product type & bedroom mix" },
      { id: "neighborhood_change", label: "Neighborhood change area", type: "select", options: o.neighborhood_change, help: "drives CRA eligibility" },
      { id: "land_sf", label: "Land area (SF)", type: "number" },
    ],
    derive: deriveModelPreview,
  }, (values) => {
    launch({ method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify({ mode: "underwrite", from_job: jobId, overrides: values }) });
  });
}

// JS mirror of uw_logic's derive rules — live preview only; Python writes the file.
function deriveModelPreview(v) {
  const lf = v.resource === "High" || v.resource === "Highest";
  const cra = (String(v.neighborhood_change).toLowerCase() !== "yes" && !lf) ? "Yes" : "No";
  const mix = lf ? "0% Studio · 50% 1B · 25% 2B · 25% 3B" : "100% 1B";
  const sf = (v.land_sf != null && v.land_sf !== "") ? fmt(v.land_sf) : "—";
  return [
    { label: "Project (B2)", value: v.deal_name || "—" },
    { label: "County (C3)", value: v.county || "—" },
    { label: "PHA (C4)", value: v.pha || "—" },
    { label: "QCT/DDA (C5)", value: v.qct_dda || "—" },
    { label: "Resource (C6)", value: v.resource || "—" },
    { label: "Neighborhood change (C7)", value: v.neighborhood_change || "—" },
    { label: "Land SF (C12)", value: sf },
    { label: "→ Product", value: lf ? "Large Family" : "Standard (1B)" },
    { label: "→ CRA (C8)", value: cra },
    { label: "→ Bedroom mix", value: mix },
    { label: "→ AMI mix", value: "10% @30% · 10% @50% · 80% @60%" },
  ];
}

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
        ctrl = `<input type="${f.type === "number" ? "number" : "text"}" data-fid="${esc(f.id)}" value="${esc(v)}">`;
      }
      return `<div class="rv-field"><label>${esc(f.label)}</label>${ctrl}${f.help ? `<span class="rv-help">${esc(f.help)}</span>` : ""}</div>`;
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
  renderPreview() {
    const rows = this.schema.derive(this.values);
    $("#review-preview").innerHTML = `<h3 class="section-head">Model will use</h3>`
      + `<table>${rows.map(r => `<tr><td class="col-field">${esc(r.label)}</td><td class="col-answer">${esc(r.value)}</td></tr>`).join("")}</table>`
      + (this.schema.previewNote ? `<p class="hint">${esc(this.schema.previewNote)}</p>` : "");
  },
};
$("#review-cancel").addEventListener("click", () => ReviewEditor.close());
$("#review-go").addEventListener("click", () => {
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
    $("#matched").textContent = `${job.geo.matched_address}  ·  tract ${job.geo.geoid}`;
  }

  const pct = job.total ? Math.round((job.completed / job.total) * 100) : (job.status === "running" ? 8 : 0);
  $("#progress-bar").style.width = pct + "%";
  $("#counts").textContent = job.total ? `${job.completed} / ${job.total} fields` : "";

  if (job.downloadable) {
    const dl = $("#download");
    dl.href = `/api/download/${job.id}`;
    dl.textContent = job.underwrite ? "Download models (.zip)" : "Download .xlsx";
    dl.classList.remove("hidden");
  }

  // Offer "Generate financial model" once a DD run (single/assemblage) is downloadable.
  const isDD = job.kind === "single" || job.kind === "assemblage";
  if (isDD && job.downloadable) {
    lastDDJob = job.id;
    $("#gen-model").classList.remove("hidden");
  }

  if (job.parcels) renderParcels(job);
  if (job.om) renderOM(job.om);
  if (job.underwrite) renderUnderwrite(job.underwrite);
  renderFields(job.fields || []);
}

function renderUnderwrite(uw) {
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
  btn.textContent = on ? "Running…" : (mode === "underwrite" ? "Generate model" : "Run feasibility");
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
  $("#gen-model").classList.add("hidden");
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

// ---------- time-saved metric ----------
async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) return;
    const s = await r.json();
    $("#hours-saved").textContent = fmt(s.hours_saved);
    $("#total-automated").textContent = fmt(s.total_automated);
    $("#per-min").textContent = s.minutes_per;
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
        <td class="rc-when">${esc((run.finished || "").replace("T", " "))}</td>
        <td class="rc-actions">
          ${run.can_model ? `<button class="rc-gen" type="button" data-job="${esc(run.id)}" title="Build Stick + Modular pro-forma from this checklist">→ Financial model</button>` : ""}
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
