"use strict";

const SECTIONS = window.SECTIONS || [];
const SECTION_LABEL = Object.fromEntries(SECTIONS.map(s => [s.id, s.label]));
const SECTION_ORDER = SECTIONS.map(s => s.id);

let mode = "single";
let pollTimer = null;

const $ = sel => document.querySelector(sel);

// ---------- tab switching ----------
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t === tab));
    document.querySelectorAll("[data-for]").forEach(f => {
      f.classList.toggle("hidden", f.dataset.for !== mode);
    });
  });
});

// ---------- run ----------
$("#run-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { mode };
  if (mode === "single") body.address = $("#address").value.trim();
  else body.apns = $("#apns").value;

  showError(null);
  setRunning(true);
  resetStatus();

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) { throw new Error(data.error || "Request failed."); }
    poll(data.job_id);
  } catch (err) {
    setRunning(false);
    showError(err.message);
  }
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
    dl.classList.remove("hidden");
  }

  if (job.parcels) renderParcels(job);
  renderFields(job.fields || []);
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
  else if (s === "NA") cls = "na";
  else if (s.startsWith("TOOL-FAIL")) cls = "toolfail";
  else if (s === "MANUAL-VERIFY") cls = "manual";
  return `<span class="badge ${cls}">${esc(state || "")}</span>`;
}

// ---------- helpers ----------
function setRunning(on) {
  const btn = $("#run-btn");
  btn.disabled = on;
  btn.textContent = on ? "Running…" : "Run feasibility";
}
function resetStatus() {
  $("#results").innerHTML = "";
  $("#parcels").classList.add("hidden");
  $("#parcels").innerHTML = "";
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
