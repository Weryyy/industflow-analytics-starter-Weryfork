"use strict";

const $ = (sel) => document.querySelector(sel);
const messages = $("#messages");

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Minimal, safe markdown-lite: escape first, then bold + bullet lists + breaks.
function formatText(raw) {
  let s = escapeHtml(raw);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const lines = s.split("\n");
  let html = "", inList = false;
  for (const line of lines) {
    const m = line.match(/^\s*[-*]\s+(.*)/) || line.match(/^\s*\d+\.\s+(.*)/);
    if (m) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${m[1]}</li>`;
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      html += line.trim() ? `${line}<br>` : "";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function addMessage(role, html, extra = "") {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  wrap.innerHTML = `<div class="bubble">${html}${extra}</div>`;
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
  return wrap;
}

function addSpinner() {
  return addMessage("assistant",
    `<span class="spinner"><i></i><i></i><i></i></span>`);
}

// --------------------------------------------------------------------------- //
// Health
// --------------------------------------------------------------------------- //
async function refreshHealth() {
  try {
    const h = await (await fetch("/health")).json();
    const setDot = (id, ok) => {
      const el = $(id);
      el.classList.toggle("ok", ok);
      el.classList.toggle("bad", !ok);
    };
    setDot("#dot-mongo", h.mongo === "ok");
    setDot("#dot-ollama", h.ollama === "ok" && h.modelLoaded);
    $("#model-name").textContent = h.model || "";
  } catch { /* ignore */ }
}

// --------------------------------------------------------------------------- //
// Chat
// --------------------------------------------------------------------------- //
let busy = false;

async function askQuestion(q) {
  if (busy || !q.trim()) return;
  busy = true; $("#send").disabled = true;
  addMessage("user", escapeHtml(q));
  const spin = addSpinner();
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    spin.remove();
    if (!res.ok) {
      addMessage("assistant", `<em>Error:</em> ${escapeHtml(data.detail || "request failed")}`);
    } else {
      const tools = (data.toolsUsed || []).length
        ? `<div class="tools">tools: ${data.toolsUsed.map((t) => `<span>${escapeHtml(t)}</span>`).join("")}</div>`
        : "";
      addMessage("assistant", formatText(data.answer || "(no answer)"), tools);
    }
  } catch (e) {
    spin.remove();
    addMessage("assistant", `<em>Network error:</em> ${escapeHtml(String(e))}`);
  } finally {
    busy = false; $("#send").disabled = false;
  }
}

async function generateReport(type) {
  if (busy) return;
  busy = true; $("#send").disabled = true;
  addMessage("user", `Generate ${type} report`);
  const spin = addSpinner();
  try {
    const res = await fetch("/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type }),
    });
    const data = await res.json();
    spin.remove();
    if (!res.ok) {
      addMessage("assistant", `<em>Error:</em> ${escapeHtml(data.detail || "report failed")}`);
    } else {
      addMessage("report", `<strong>${type === "trend" ? "Trend" : "Shift"} report</strong><br>${formatText(data.text || "")}`);
    }
  } catch (e) {
    spin.remove();
    addMessage("assistant", `<em>Network error:</em> ${escapeHtml(String(e))}`);
  } finally {
    busy = false; $("#send").disabled = false;
  }
}

// --------------------------------------------------------------------------- //
// Charts
// --------------------------------------------------------------------------- //
const charts = {};
// Brand palette (indusflow.com): crimson primary, deep blue secondary, light grids.
const C = { grid: "#e6e6e6", tick: "#6c7480", accent: "#c41230", blue: "#00499d", grey: "#a5a5a5" };

function baseOpts(extra = {}) {
  return {
    responsive: true,
    plugins: { legend: { labels: { color: C.tick } } },
    scales: {
      x: { ticks: { color: C.tick, maxRotation: 60, minRotation: 0 }, grid: { color: C.grid } },
      y: { ticks: { color: C.tick }, grid: { color: C.grid }, beginAtZero: true },
    },
    ...extra,
  };
}

function draw(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}

async function loadCharts() {
  try {
    const [scrap, defects, fpy, shifts] = await Promise.all([
      fetch("/metrics/scrap-trend").then((r) => r.json()),
      fetch("/metrics/defects").then((r) => r.json()),
      fetch("/metrics/worst-fpy").then((r) => r.json()),
      fetch("/metrics/shift-output").then((r) => r.json()),
    ]);

    draw("chart-scrap", {
      type: "line",
      data: {
        labels: scrap.points.map((p) => p.day),
        datasets: [{
          label: "Scrap rate %",
          data: scrap.points.map((p) => +(100 * (p.scrapRate || 0)).toFixed(2)),
          borderColor: C.accent, backgroundColor: "rgba(196,18,48,.12)",
          fill: true, tension: .3, pointRadius: 2,
        }],
      },
      options: baseOpts(),
    });

    draw("chart-defects", {
      type: "bar",
      data: {
        labels: defects.defects.map((d) => d.defectCode),
        datasets: [{ label: "Count", data: defects.defects.map((d) => d.count), backgroundColor: C.blue }],
      },
      options: baseOpts({ plugins: { legend: { display: false } } }),
    });

    draw("chart-fpy", {
      type: "bar",
      data: {
        labels: fpy.steps.map((s) => s.stepName),
        datasets: [{ label: "FPY %", data: fpy.steps.map((s) => +(100 * (s.fpy || 0)).toFixed(1)), backgroundColor: C.accent }],
      },
      options: baseOpts({ indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: C.tick }, grid: { color: C.grid }, beginAtZero: true, max: 100 },
                  y: { ticks: { color: C.tick }, grid: { color: C.grid } } } }),
    });

    draw("chart-shifts", {
      type: "bar",
      data: {
        labels: shifts.shifts.map((s) => s.label),
        datasets: [
          { label: "Created", data: shifts.shifts.map((s) => s.created), backgroundColor: C.blue },
          { label: "Expected", data: shifts.shifts.map((s) => s.expected), backgroundColor: C.grey },
        ],
      },
      options: baseOpts(),
    });
  } catch (e) {
    console.error("charts failed", e);
  }
}

// --------------------------------------------------------------------------- //
// Wiring
// --------------------------------------------------------------------------- //
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#input").value;
  $("#input").value = "";
  $("#input").style.height = "auto";
  askQuestion(q);
});

$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); }
});
$("#input").addEventListener("input", (e) => {
  e.target.style.height = "auto";
  e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px";
});

$("#quick").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  if (btn.dataset.report) generateReport(btn.dataset.report);
  else if (btn.dataset.q) askQuestion(btn.dataset.q);
});

$("#charts-toggle").addEventListener("change", (e) => {
  const on = e.target.checked;
  $("#charts-pane").hidden = !on;
  $("#layout").classList.toggle("with-charts", on);
  if (on) loadCharts();
});
$("#refresh-charts").addEventListener("click", loadCharts);

refreshHealth();
setInterval(refreshHealth, 30000);
