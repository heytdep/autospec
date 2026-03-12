const API = "";
let state = {
  runId: null,
  journals: [],
  compartments: null,
  registry: null,
  status: null,
  intersections: [],
  evoStep: 0,
  live: null,
  feedEvents: [],
  prevPhases: {},
};

// ── fetch helpers ──

async function api(path) {
  const r = await fetch(API + path);
  if (!r.ok) return null;
  return r.json();
}

async function loadRuns() {
  const runs = await api("/api/runs");
  const sel = document.getElementById("run-select");
  sel.innerHTML = '<option value="">select run...</option>';
  (runs || []).forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = `${r.id} [${r.status}]`;
    sel.appendChild(opt);
  });

  if (!state.runId && runs && runs.length > 0) {
    const running = runs.find((r) => r.status === "running");
    const pick = running || runs[runs.length - 1];
    sel.value = pick.id;
    loadRun(pick.id);
  }
}

async function loadRun(runId) {
  state.runId = runId;
  state.feedEvents = [];
  state.prevPhases = {};
  const [compartments, registry, journals, status, intersections, live] =
    await Promise.all([
      api(`/api/runs/${runId}/compartments`),
      api(`/api/runs/${runId}/registry`),
      api(`/api/runs/${runId}/journals`),
      api(`/api/runs/${runId}/status`),
      api(`/api/runs/${runId}/intersections`),
      api(`/api/runs/${runId}/live`),
    ]);

  state.compartments = compartments;
  state.registry = registry;
  state.journals = journals || [];
  state.status = status;
  state.intersections = intersections || [];
  state.live = live;

  if (live) {
    for (const c of live.compartments) {
      state.prevPhases[c.id] = c.phase;
    }
  }

  updateStatusBadge();
  populateFilters();
  renderOverview();
  renderProgress();
  renderJournals();
  renderEvolution();
  renderTechniques();
  renderAgents();

  if (state.status?.state === "running") {
    switchTab("agents");
  }
}

// ── status badge ──

function updateStatusBadge() {
  const badge = document.getElementById("run-status");
  const s = state.status?.state || "unknown";
  badge.textContent = s;
  badge.className = "status-badge " + s;
}

// ── tabs ──

function switchTab(tabName) {
  document.querySelectorAll("nav .tab").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((t) => t.classList.remove("active"));
  const btn = document.querySelector(`nav .tab[data-tab="${tabName}"]`);
  if (btn) btn.classList.add("active");
  const section = document.getElementById("tab-" + tabName);
  if (section) section.classList.add("active");
}

document.querySelectorAll("nav .tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// ── overview: compartment diagram + live agent activity ──

function renderOverview() {
  renderOverviewGraph();
  renderOverviewAgents();
}

function renderOverviewGraph() {
  const svg = document.getElementById("overview-graph");
  svg.innerHTML = "";

  if (!state.compartments?.compartments) {
    svg.innerHTML = '<text x="400" y="175" text-anchor="middle" fill="#666">no compartments loaded</text>';
    return;
  }

  const comps = state.compartments.compartments;
  const ints = state.compartments.intersections || [];
  const liveComps = state.live?.compartments || [];
  const liveMap = {};
  liveComps.forEach((lc) => { liveMap[lc.id] = lc; });
  const escalation = state.live?.escalation || state.status?.escalation || {};

  const cx = 400, cy = 160;
  const positions = {};

  if (comps.length <= 4) {
    const totalW = (comps.length - 1) * 220;
    const startX = cx - totalW / 2;
    comps.forEach((c, i) => {
      positions[c.id] = { x: startX + i * 220, y: cy };
    });
  } else {
    const radius = 140;
    comps.forEach((c, i) => {
      const angle = (i / comps.length) * Math.PI * 2 - Math.PI / 2;
      positions[c.id] = { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
    });
  }

  ints.forEach((inter) => {
    const [a, b] = inter.compartments;
    if (!positions[a] || !positions[b]) return;
    const pa = positions[a], pb = positions[b];
    const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;

    const hasActive = inter.compartments.some((id) => liveMap[id]?.phase && liveMap[id].phase !== "idle");

    svg.innerHTML += `<line class="intersection-edge${hasActive ? " active" : ""}"
      x1="${pa.x}" y1="${pa.y}" x2="${pb.x}" y2="${pb.y}"/>`;

    const dy = pa.y === pb.y ? -20 : 0;
    const dx = pa.y !== pb.y ? 15 : 0;
    svg.innerHTML += `<text class="intersection-label" x="${mx + dx}" y="${my + dy - 4}">${inter.id}: ${(inter.shared_vars || []).join(", ")}</text>`;
    svg.innerHTML += `<text class="intersection-label" x="${mx + dx}" y="${my + dy + 8}">${inter.coupling_strength || ""}</text>`;
  });

  const boxW = 160, boxH = 80;
  comps.forEach((c) => {
    const p = positions[c.id];
    const lc = liveMap[c.id];
    const isActive = lc && lc.phase !== "idle";
    const compJournals = state.journals.filter((j) => j.compartment === c.id);
    const okCount = compJournals.filter((j) => j.status === "OK").length;
    const failCount = compJournals.filter((j) => j.status === "FAIL").length;
    const esc = escalation[c.id];

    const cls = isActive ? "comp-node active" : "comp-node";

    svg.innerHTML += `<rect class="${cls}" x="${p.x - boxW/2}" y="${p.y - boxH/2}" width="${boxW}" height="${boxH}" rx="0"/>`;

    svg.innerHTML += `<text class="comp-label" x="${p.x}" y="${p.y - 22}">${c.id}</text>`;
    svg.innerHTML += `<text class="intersection-label" x="${p.x}" y="${p.y - 10}">${c.name}</text>`;

    if (isActive) {
      const phaseLabel = PHASE_LABELS[lc.phase] || lc.phase;
      const phaseColor = PHASE_COLORS[lc.phase] || "var(--text-dim)";
      svg.innerHTML += `<circle class="agent-indicator" cx="${p.x + boxW/2 - 8}" cy="${p.y - boxH/2 + 8}" r="4">
        <title>${phaseLabel}</title></circle>`;
      svg.innerHTML += `<text x="${p.x}" y="${p.y + 6}" text-anchor="middle" font-size="10" fill="${phaseColor}" font-weight="700">${phaseLabel}</text>`;
      svg.innerHTML += `<text x="${p.x}" y="${p.y + 20}" text-anchor="middle" font-size="9" fill="var(--text-dim)">step ${lc.step || "?"} | ${fmtElapsed(lc.elapsed_s)}</text>`;
    } else {
      svg.innerHTML += `<text x="${p.x}" y="${p.y + 6}" text-anchor="middle" font-size="10">
        <tspan fill="${cssVar("--ok")}">${okCount} ok</tspan>  <tspan fill="${cssVar("--fail")}">${failCount} fail</tspan></text>`;
    }

    if (esc && esc.tier > 0) {
      svg.innerHTML += `<text x="${p.x}" y="${p.y + 32}" text-anchor="middle" font-size="9" fill="${cssVar("--fail")}">escalation tier ${esc.tier}</text>`;
    }
  });
}

function renderOverviewAgents() {
  const container = document.getElementById("overview-agents");
  if (!state.compartments?.compartments) {
    container.innerHTML = "";
    return;
  }

  const comps = state.compartments.compartments;
  const liveComps = state.live?.compartments || [];
  const liveMap = {};
  liveComps.forEach((lc) => { liveMap[lc.id] = lc; });
  const escalation = state.live?.escalation || state.status?.escalation || {};

  let html = "";
  comps.forEach((c) => {
    const lc = liveMap[c.id];
    const isActive = lc && lc.phase !== "idle";
    const compJournals = state.journals.filter((j) => j.compartment === c.id);
    const lastJournal = compJournals[compJournals.length - 1];
    const esc = escalation[c.id];

    html += `<div class="comp-agent-section">`;
    html += `<div class="comp-agent-header">
      <span>${c.id} / ${c.name}</span>
      <span class="comp-stats">
        ${lc ? lc.completed_steps + " completed" : compJournals.length + " steps"} |
        ${esc ? esc.consecutive_no_progress + " idle" : "0 idle"}
      </span>
    </div>`;
    html += `<div class="comp-agent-body">`;

    if (isActive) {
      const phaseLabel = PHASE_LABELS[lc.phase] || lc.phase;
      const phaseColor = PHASE_COLORS[lc.phase] || "var(--text-dim)";
      html += `<div class="agent-line">
        <span class="pulse-dot" style="background:${phaseColor}"></span>
        <strong style="color:${phaseColor}">${phaseLabel}</strong>
        <span style="color:var(--text-dim)">step ${lc.step || "?"}</span>
        <span style="flex:1;font-size:10px">${
          lc.phase === "reviewing" ? escHtml(lc.phase_data?.technique || "") :
          lc.phase === "judging" ? "verdict: " + (lc.phase_data?.verdict || "") :
          lc.phase === "hard-gate" ? "ruling: " + (lc.phase_data?.ruling || "") : ""
        }</span>
        <span style="color:var(--text-dim);font-variant-numeric:tabular-nums">${fmtElapsed(lc.elapsed_s)}</span>
      </div>`;
    } else {
      html += `<div class="idle">idle</div>`;
    }

    if (lastJournal) {
      html += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--bg3);font-size:10px;color:var(--text-dim)">
        last: step ${lastJournal.step}
        <span style="color:var(--${lastJournal.status === "OK" ? "ok" : "fail"})">${lastJournal.status}</span>
        ${lastJournal.proposal?.technique_name || ""} -
        ${lastJournal.proposal?.claim ? lastJournal.proposal.claim.slice(0, 80) + (lastJournal.proposal.claim.length > 80 ? ".." : "") : ""}
      </div>`;
    }

    html += `</div></div>`;
  });

  container.innerHTML = html;
}

// ── progress ──

function renderProgress() {
  const j = state.journals;
  const ok = j.filter((x) => x.status === "OK");
  const fail = j.filter((x) => x.status === "FAIL");
  const liveComps = state.live?.compartments || [];
  const inProgress = liveComps.filter((c) => c.phase !== "idle").length;

  document.getElementById("m-total-steps").textContent = j.length;
  document.getElementById("m-in-progress").textContent = inProgress;
  document.getElementById("m-ok-steps").textContent = ok.length;
  document.getElementById("m-fail-steps").textContent = fail.length;

  const reg = Array.isArray(state.registry) ? state.registry : state.registry?.techniques || [];
  document.getElementById("m-techniques").textContent = reg.length;
  document.getElementById("m-novel").textContent = reg.filter(
    (t) => t.class === "novel" || t.class === "candidate-novel"
  ).length;

  const summary = document.getElementById("progress-live-summary");
  if (liveComps.length > 0 && inProgress > 0) {
    summary.innerHTML = `<div class="live-progress-bar">${liveComps.map((c) => {
      const isActive = c.phase !== "idle";
      const phaseColor = PHASE_COLORS[c.phase] || "var(--text-dim)";
      const phaseLabel = PHASE_LABELS[c.phase] || c.phase;
      return `<div class="live-progress-item ${isActive ? "active" : ""}">
        <span class="live-progress-id">${c.id}</span>
        ${isActive ? '<span class="pulse-dot" style="background:' + phaseColor + '"></span>' : ""}
        <span style="color:${phaseColor};font-weight:700">${phaseLabel}</span>
        <span style="color:var(--text-dim)">${c.step ? "step " + c.step : ""}</span>
        <span style="color:var(--text-dim);font-variant-numeric:tabular-nums">${isActive ? fmtElapsed(c.elapsed_s) : ""}</span>
      </div>`;
    }).join("")}</div>`;
  } else {
    summary.innerHTML = "";
  }

  renderStateSpaceChart(j);
  renderOutcomesChart(j);
  renderTimeline(ok);
}

function renderStateSpaceChart(journals) {
  const svg = document.getElementById("chart-state-space");
  svg.innerHTML = "";
  const points = journals
    .filter((j) => j.hard_gate?.state_space_after != null)
    .map((j) => ({ step: j.step, val: j.hard_gate.state_space_after, comp: j.compartment }));

  if (points.length === 0) {
    svg.innerHTML = '<text x="300" y="130" text-anchor="middle">no state space data</text>';
    return;
  }

  const pad = { t: 20, r: 20, b: 30, l: 60 };
  const w = 600 - pad.l - pad.r;
  const h = 250 - pad.t - pad.b;
  const maxV = Math.max(...points.map((p) => p.val));
  const minV = Math.min(...points.map((p) => p.val));
  const range = maxV - minV || 1;

  const sx = (i) => pad.l + (i / Math.max(points.length - 1, 1)) * w;
  const sy = (v) => pad.t + (1 - (v - minV) / range) * h;

  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (i / 4) * h;
    const val = maxV - (i / 4) * range;
    svg.innerHTML += `<line class="grid-line" x1="${pad.l}" y1="${y}" x2="${pad.l + w}" y2="${y}"/>`;
    svg.innerHTML += `<text x="${pad.l - 5}" y="${y + 3}" text-anchor="end">${fmtNum(val)}</text>`;
  }

  let areaD = `M ${sx(0)} ${sy(points[0].val)}`;
  points.forEach((p, i) => { areaD += ` L ${sx(i)} ${sy(p.val)}`; });
  areaD += ` L ${sx(points.length - 1)} ${pad.t + h} L ${sx(0)} ${pad.t + h} Z`;
  svg.innerHTML += `<path class="area-state" d="${areaD}"/>`;

  let lineD = `M ${sx(0)} ${sy(points[0].val)}`;
  points.forEach((p, i) => { lineD += ` L ${sx(i)} ${sy(p.val)}`; });
  svg.innerHTML += `<path class="line-state" d="${lineD}"/>`;

  points.forEach((p, i) => {
    svg.innerHTML += `<circle cx="${sx(i)}" cy="${sy(p.val)}" r="2.5" fill="var(--text)">
      <title>step ${p.step} (${p.comp}): ${fmtNum(p.val)}</title></circle>`;
  });

  svg.innerHTML += `<text x="${pad.l + w / 2}" y="${250 - 5}" text-anchor="middle">step</text>`;
}

function renderOutcomesChart(journals) {
  const svg = document.getElementById("chart-outcomes");
  svg.innerHTML = "";

  if (journals.length === 0) {
    svg.innerHTML = '<text x="300" y="130" text-anchor="middle">no data</text>';
    return;
  }

  const pad = { t: 20, r: 20, b: 30, l: 40 };
  const w = 600 - pad.l - pad.r;
  const h = 250 - pad.t - pad.b;
  const barW = Math.min(24, w / journals.length - 2);

  journals.forEach((j, i) => {
    const x = pad.l + (i / journals.length) * w + 1;
    const isOk = j.status === "OK";
    const color = isOk ? "var(--ok)" : "var(--fail)";
    const barH = isOk ? h * 0.8 : h * 0.4;
    const y = pad.t + h - barH;

    svg.innerHTML += `<rect x="${x}" y="${y}" width="${barW}" height="${barH}"
      fill="${color}" opacity="0.7">
      <title>step ${j.step} (${j.compartment}): ${j.status}</title></rect>`;
  });

  svg.innerHTML += `<line class="axis" x1="${pad.l}" y1="${pad.t + h}" x2="${pad.l + w}" y2="${pad.t + h}"/>`;
  svg.innerHTML += `<text x="${pad.l + w / 2}" y="${250 - 5}" text-anchor="middle">step</text>`;
}

function renderTimeline(okJournals) {
  const container = document.getElementById("timeline-improvements");
  container.innerHTML = "";

  if (okJournals.length === 0) {
    container.innerHTML = '<div class="placeholder">no improvements yet</div>';
    return;
  }

  okJournals.forEach((j) => {
    const div = document.createElement("div");
    div.className = "timeline-item";
    div.innerHTML = `
      <span class="timeline-step">step ${j.step}</span>
      <span class="timeline-comp">${j.compartment}</span>
      <span class="timeline-delta">${j.proposal?.structural_delta || "-"}</span>
      <span class="timeline-technique">${j.proposal?.technique_name || j.proposal?.technique || "-"}</span>
    `;
    container.appendChild(div);
  });
}

// ── journals ──

function populateFilters() {
  const compFilter = document.getElementById("journal-compartment-filter");
  compFilter.innerHTML = '<option value="">all compartments</option>';
  if (state.compartments?.compartments) {
    state.compartments.compartments.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.id} (${c.name})`;
      compFilter.appendChild(opt);
    });
  }

  const techFilter = document.getElementById("journal-technique-filter");
  techFilter.innerHTML = '<option value="">all techniques</option>';
  const techniques = new Set(state.journals.map((j) => jTech(j)).filter((t) => t && t !== "-"));
  techniques.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    techFilter.appendChild(opt);
  });
}

function renderJournals() {
  const list = document.getElementById("journal-list");
  const detail = document.getElementById("journal-detail");
  detail.classList.add("hidden");
  list.innerHTML = "";

  const compF = document.getElementById("journal-compartment-filter").value;
  const statusF = document.getElementById("journal-status-filter").value;
  const techF = document.getElementById("journal-technique-filter").value;

  let filtered = state.journals;
  if (compF) filtered = filtered.filter((j) => j.compartment === compF);
  if (statusF) filtered = filtered.filter((j) => j.status === statusF);
  if (techF) filtered = filtered.filter((j) => jTech(j) === techF);

  filtered.forEach((j) => {
    const div = document.createElement("div");
    div.className = "journal-entry";
    div.innerHTML = `
      <span class="journal-step">step ${j.step}</span>
      <span class="journal-compartment">${j.compartment}</span>
      <span class="journal-status ${j.status.toLowerCase()}">${j.status}</span>
      <span class="journal-technique">${jTech(j)}</span>
      <span class="journal-claim">${escHtml(jClaim(j))}</span>
    `;
    div.addEventListener("click", () => showJournalDetail(j, div));
    list.appendChild(div);
  });
}

function jTech(j) {
  return j.technique_name || j.proposal?.technique_name || j.technique || j.proposal?.technique || "-";
}
function jClaim(j) {
  return j.proposal_summary || j.proposal?.claim || "-";
}

function showJournalDetail(j, el) {
  document.querySelectorAll(".journal-entry.selected").forEach((e) => e.classList.remove("selected"));
  el.classList.add("selected");

  const detail = document.getElementById("journal-detail");
  detail.classList.remove("hidden");
  const counterex = j.counterexample || j.review?.counterexample || null;
  const targets = j.target_actions || j.proposal?.target_actions || [];
  const diff = j.proposal?.diff || null;
  const reviewVerdict = j.review_verdict || j.review?.verdict || "-";
  const reviewFinding = j.review_core_finding || j.review?.argument || "";
  const judgmentRuling = j.judgment_ruling || j.judgment?.ruling || "-";
  const judgmentFinding = j.judgment_key_finding || j.judgment?.reasoning || "";

  detail.innerHTML = `
    <h4>Step ${j.step} - ${j.compartment} - ${j.status}</h4>

    <div class="field-label">technique</div>
    <div class="field-value">${escHtml(jTech(j))}</div>

    <div class="field-label">claim</div>
    <div class="field-value">${escHtml(jClaim(j))}</div>

    <div class="field-label">target actions</div>
    <div class="field-value">${targets.join(", ") || "-"}</div>

    <div class="field-label">structural delta</div>
    <div class="field-value">${escHtml(j.proposal?.structural_delta || "-")}</div>

    ${diff ? `<div class="field-label">diff</div><pre>${escHtml(diff)}</pre>` : ""}

    <div class="field-label">review verdict</div>
    <div class="field-value" style="color:${reviewVerdict === "ACCEPT" ? "var(--ok)" : "var(--fail)"}">${reviewVerdict}</div>

    ${reviewFinding ? `<div class="field-label">reviewer finding</div><div class="field-value">${escHtml(reviewFinding)}</div>` : ""}

    ${counterex ? `<div class="field-label">counterexample</div><pre>${escHtml(counterex)}</pre>` : ""}

    <div class="field-label">judgment</div>
    <div class="field-value" style="color:${judgmentRuling === "ACCEPT" ? "var(--ok)" : "var(--fail)"}">${judgmentRuling}${judgmentFinding ? ": " + escHtml(judgmentFinding) : ""}</div>

    ${j.reviewer_objections?.length ? `
      <div class="field-label">objections (${j.reviewer_objections.length})</div>
      ${j.reviewer_objections.map((o) => `<div style="margin:4px 0;padding:4px 6px;background:var(--bg2);border:1px solid var(--bg3);font-size:10px">
        <span style="color:${o.ruling === "sustained" ? "var(--fail)" : "var(--ok)"};font-weight:700">${o.ruling}</span> ${escHtml(o.objection)}
      </div>`).join("")}` : ""}

    <div class="field-label">hard gate</div>
    <div class="field-value">
      ${j.hard_gate?.ran ? `passed: ${j.hard_gate.passed}, state space: ${fmtNum(j.hard_gate.state_space_before)} -> ${fmtNum(j.hard_gate.state_space_after)}` : "not run"}
    </div>

    ${j.hard_gate?.counterexample ? `<div class="field-label">model checker counterexample</div><pre>${escHtml(j.hard_gate.counterexample)}</pre>` : ""}

    <div class="field-label">structural verification</div>
    <div class="field-value">${j.structural_verification?.ran ? `claim substantiated: ${j.structural_verification.claim_substantiated}` : "not run"}
      ${j.structural_verification?.evidence ? `<br>${j.structural_verification.evidence}` : ""}</div>

    ${j.failure_reason ? `<div class="field-label">failure reason</div><div class="field-value" style="color:var(--fail)">${escHtml(j.failure_reason)}</div>` : ""}
  `;
}

// ── checkpoints ──

function renderCheckpoints(compartmentId) {
  if (!document.getElementById("journal-show-checkpoints").checked) {
    document.getElementById("checkpoint-list").classList.add("hidden");
    return;
  }
  if (!compartmentId) {
    document.getElementById("checkpoint-list").innerHTML =
      '<div class="placeholder">select a compartment to see checkpoints</div>';
    document.getElementById("checkpoint-list").classList.remove("hidden");
    return;
  }

  api(`/api/runs/${state.runId}/checkpoints/${compartmentId}`).then((cps) => {
    const container = document.getElementById("checkpoint-list");
    container.classList.remove("hidden");
    container.innerHTML = "";
    (cps || []).forEach((cp) => {
      const div = document.createElement("div");
      div.className = "checkpoint-entry";
      div.innerHTML = `
        <span class="checkpoint-name">${cp.name}</span>
        <span class="checkpoint-type">${cp.ok_only ? "OK only" : "full"}</span>
      `;
      div.addEventListener("click", () => {
        const detail = document.getElementById("journal-detail");
        detail.classList.remove("hidden");
        detail.innerHTML = `<h4>${cp.name}</h4><pre>${escHtml(cp.content || "empty")}</pre>`;
      });
      container.appendChild(div);
    });
  });
}

// ── spec evolution ──

function renderEvolution() {
  const max = state.journals.length;
  const slider = document.getElementById("evo-slider");
  slider.max = max;
  slider.value = 0;
  state.evoStep = 0;

  document.getElementById("evo-prev").disabled = true;
  document.getElementById("evo-next").disabled = max === 0;
  document.getElementById("evo-step-label").textContent = "step 0";

  drawCompartmentGraph(-1);
}

function drawCompartmentGraph(stepIdx) {
  const svg = document.getElementById("compartment-graph");
  svg.innerHTML = "";

  if (!state.compartments?.compartments) {
    svg.innerHTML = '<text x="350" y="200" text-anchor="middle">no compartments</text>';
    return;
  }

  const comps = state.compartments.compartments;
  const ints = state.compartments.intersections || [];

  const currentJournal = stepIdx >= 0 ? state.journals[stepIdx] : null;
  const changedComp = currentJournal?.compartment;

  const cx = 350, cy = 180, radius = 130;
  const positions = {};
  comps.forEach((c, i) => {
    const angle = (i / comps.length) * Math.PI * 2 - Math.PI / 2;
    positions[c.id] = {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    };
  });

  ints.forEach((inter) => {
    const [a, b] = inter.compartments;
    if (!positions[a] || !positions[b]) return;
    const pa = positions[a], pb = positions[b];
    const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;

    const isActive = currentJournal &&
      inter.compartments.includes(changedComp) &&
      inter.shared_vars?.some((v) =>
        currentJournal.proposal?.target_actions?.length > 0
      );

    svg.innerHTML += `<line class="intersection-edge${isActive ? " active" : ""}"
      x1="${pa.x}" y1="${pa.y}" x2="${pb.x}" y2="${pb.y}"/>`;
    svg.innerHTML += `<text class="intersection-label" x="${mx}" y="${my - 8}">${inter.id}</text>`;
    svg.innerHTML += `<text class="intersection-label" x="${mx}" y="${my + 5}">${(inter.shared_vars || []).join(", ")}</text>`;
  });

  comps.forEach((c) => {
    const p = positions[c.id];
    const isChanged = c.id === changedComp;
    const cls = isChanged ? "comp-node changed" : "comp-node";

    svg.innerHTML += `<rect class="${cls}" x="${p.x - 55}" y="${p.y - 25}" width="110" height="50" rx="0"/>`;
    svg.innerHTML += `<text class="comp-label" x="${p.x}" y="${p.y - 5}">${c.id}</text>`;
    svg.innerHTML += `<text class="intersection-label" x="${p.x}" y="${p.y + 10}">${c.name}</text>`;

    if (isChanged && currentJournal) {
      svg.innerHTML += `<rect class="change-marker" x="${p.x + 40}" y="${p.y - 20}" width="8" height="8">
        <title>${currentJournal.status}: ${currentJournal.proposal?.technique_name || ""}</title></rect>`;
    }
  });
}

function updateEvolution(stepIdx) {
  state.evoStep = stepIdx;
  const slider = document.getElementById("evo-slider");
  slider.value = stepIdx;
  document.getElementById("evo-step-label").textContent =
    stepIdx === 0 ? "step 0" : `step ${state.journals[stepIdx - 1]?.step || stepIdx}`;
  document.getElementById("evo-prev").disabled = stepIdx <= 0;
  document.getElementById("evo-next").disabled = stepIdx >= state.journals.length;

  drawCompartmentGraph(stepIdx - 1);

  const detail = document.getElementById("evo-detail");
  if (stepIdx === 0 || !state.journals[stepIdx - 1]) {
    detail.innerHTML = '<p class="placeholder">select a step to see changes</p>';
    return;
  }

  const j = state.journals[stepIdx - 1];
  const techName = j.technique_name || j.proposal?.technique_name || j.technique || j.proposal?.technique || "-";
  const claim = j.proposal_summary || j.proposal?.claim || "-";
  const targets = j.target_actions || j.proposal?.target_actions || [];
  const delta = j.proposal?.structural_delta || "-";
  const diff = j.proposal?.diff || null;
  const counterex = j.counterexample || j.review?.counterexample || null;

  detail.innerHTML = `
    <h4>Step ${j.step} - ${j.compartment}</h4>
    <div class="field-label">status</div>
    <div class="field-value" style="color:var(--${j.status === "OK" ? "ok" : "fail"})">${j.status}</div>
    <div class="field-label">technique</div>
    <div class="field-value">${escHtml(techName)}</div>
    <div class="field-label">claim</div>
    <div class="field-value">${escHtml(claim)}</div>
    ${targets.length ? `<div class="field-label">target actions</div><div class="field-value">${targets.join(", ")}</div>` : ""}
    <div class="field-label">structural delta</div>
    <div class="field-value">${escHtml(delta)}</div>
    ${diff ? `<div class="field-label">diff</div><pre>${escHtml(diff)}</pre>` : ""}
    ${j.review_verdict ? `<div class="field-label">review verdict</div><div class="field-value" style="color:${j.review_verdict === "ACCEPT" ? "var(--ok)" : "var(--fail)"}">${j.review_verdict}</div>` : ""}
    ${j.review_core_finding ? `<div class="field-label">reviewer finding</div><div class="field-value">${escHtml(j.review_core_finding)}</div>` : ""}
    ${counterex ? `<div class="field-label">counterexample</div><pre>${escHtml(counterex)}</pre>` : ""}
    ${j.judgment_ruling ? `<div class="field-label">judgment</div><div class="field-value" style="color:${j.judgment_ruling === "ACCEPT" ? "var(--ok)" : "var(--fail)"}">${j.judgment_ruling}: ${escHtml(j.judgment_key_finding || "")}</div>` : ""}
    ${j.reviewer_objections?.length ? `<div class="field-label">objections (${j.reviewer_objections.length})</div>${j.reviewer_objections.map((o) => `<div style="margin:4px 0;padding:4px 6px;background:var(--bg2);border:1px solid var(--bg3);font-size:10px"><span style="color:${o.ruling === "sustained" ? "var(--fail)" : "var(--ok))"};font-weight:700">${o.ruling}</span> ${escHtml(o.objection)}</div>`).join("")}` : ""}
    ${j.failure_reason ? `<div class="field-label">failure reason</div><div class="field-value" style="color:var(--fail)">${escHtml(j.failure_reason)}</div>` : ""}
  `;
}

// ── techniques ──

function renderTechniques() {
  const tbody = document.querySelector("#techniques-table tbody");
  tbody.innerHTML = "";
  const classF = document.getElementById("tech-class-filter").value;

  let techs = Array.isArray(state.registry) ? state.registry : state.registry?.techniques || [];
  if (classF) techs = techs.filter((t) => t.class === classF);

  techs.forEach((t) => {
    const apps = t.applications || [];
    const okApps = apps.filter((a) => a.outcome === "OK").length;
    const total = apps.length;
    const rate = total > 0 ? Math.round((okApps / total) * 100) : 0;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${t.id}</td>
      <td>${t.name}</td>
      <td><span class="class-badge ${t.class}">${t.class}</span></td>
      <td>${Array.isArray(t.optimizes) ? t.optimizes.join(", ") : t.optimizes || "-"}</td>
      <td>${total}</td>
      <td>
        <span class="success-bar"><span class="success-bar-fill" style="width:${rate}%"></span></span>
        ${rate}%
      </td>
      <td>${t.source?.type || "-"}</td>
    `;
    tr.addEventListener("click", () => showTechniqueDetail(t));
    tbody.appendChild(tr);
  });
}

function showTechniqueDetail(t) {
  const detail = document.getElementById("technique-detail");
  detail.classList.remove("hidden");

  const vt = t.verification_trail;
  detail.innerHTML = `
    <h4>${t.name} (${t.id})</h4>

    <div class="field-label">class</div>
    <div class="field-value"><span class="class-badge ${t.class}">${t.class}</span></div>

    <div class="field-label">description</div>
    <div class="field-value">${t.description || "-"}</div>

    <div class="field-label">optimizes</div>
    <div class="field-value">${Array.isArray(t.optimizes) ? t.optimizes.join(", ") : t.optimizes || "-"}</div>

    <div class="field-label">preconditions</div>
    <div class="field-value">${Array.isArray(t.preconditions) ? t.preconditions.join("; ") : t.preconditions || "-"}</div>

    <div class="field-label">generalized form</div>
    <div class="field-value">${t.generalized_form || "-"}</div>

    <div class="field-label">source</div>
    <div class="field-value">${t.source?.type || "-"}: ${t.source?.ref || "-"}</div>

    ${vt ? `
      <div class="field-label">verification trail</div>
      <div class="field-value">
        novelty: ${vt.novelty_check || "-"}<br>
        generality: ${vt.generality_check || "-"}<br>
        triad review: ${vt.triad_review || "-"}
        ${vt.prior_work_ref ? `<br>prior work: ${vt.prior_work_ref}` : ""}
      </div>
    ` : ""}

    <div class="field-label">applications (${(t.applications || []).length})</div>
    ${(t.applications || []).map((a) => `
      <div style="margin:4px 0;padding:4px 6px;background:var(--bg2);border:1px solid var(--bg3);font-size:10px">
        step ${a.step} (${a.compartment}): <span style="color:var(--${a.outcome === "OK" ? "ok" : "fail"})">${a.outcome}</span>
        ${a.notes ? ` - ${a.notes}` : ""}
      </div>
    `).join("")}

    ${(t.known_failures || []).length > 0 ? `
      <div class="field-label">known failures</div>
      ${t.known_failures.map((f) => `
        <div style="margin:4px 0;padding:4px 6px;background:var(--bg2);border:1px solid var(--bg3);font-size:10px;color:var(--fail)">
          step ${f.step} (${f.compartment}): ${f.reason}
        </div>
      `).join("")}
    ` : ""}
  `;
}

// ── live agents ──

const PHASE_ORDER = ["idle", "proposing", "reviewing", "judging", "hard-gate"];
const PHASE_LABELS = {
  "idle": "IDLE",
  "proposing": "PROPOSING",
  "reviewing": "REVIEWING",
  "judging": "JUDGING",
  "hard-gate": "HARD GATE",
};
const PHASE_COLORS = {
  "idle": "var(--text-dim)",
  "proposing": "var(--accent)",
  "reviewing": "var(--candidate)",
  "judging": "var(--novel)",
  "hard-gate": "var(--ok)",
};

function renderAgents() {
  renderLive();
}

function renderLive() {
  const live = state.live;
  if (!live) {
    document.getElementById("live-header").innerHTML =
      '<div class="placeholder">no live data</div>';
    document.getElementById("live-compartments").innerHTML = "";
    return;
  }

  const anyActive = live.compartments.some((c) => c.phase !== "idle");
  const runState = live.state || "unknown";

  document.getElementById("live-header").innerHTML = `
    <div class="live-status-bar">
      <span class="live-indicator ${anyActive ? "active" : ""}"></span>
      <span class="live-state ${runState}">${runState.toUpperCase()}</span>
      <span class="live-started">${live.started ? "started " + live.started : ""}</span>
      <span class="live-config">${live.config ? "P=" + live.config.P + " S=" + live.config.S + " F=" + live.config.F + " M=" + live.config.M : ""}</span>
    </div>`;

  const container = document.getElementById("live-compartments");
  container.innerHTML = live.compartments.map((c) => {
    const esc = live.escalation?.[c.id] || {};
    const phaseColor = PHASE_COLORS[c.phase] || "var(--text-dim)";
    const phaseLabel = PHASE_LABELS[c.phase] || c.phase;
    const isActive = c.phase !== "idle";

    const pipelineHtml = PHASE_ORDER.map((p, i) => {
      const idx = PHASE_ORDER.indexOf(c.phase);
      let cls = "pipe-stage";
      if (p === c.phase && isActive) cls += " current";
      else if (i < idx) cls += " done";
      return `<div class="${cls}" title="${PHASE_LABELS[p]}">${PHASE_LABELS[p]}</div>`;
    }).join('<div class="pipe-arrow"></div>');

    let bodyHtml = "";
    if (c.phase === "reviewing" && c.phase_data) {
      bodyHtml = `
        <div class="live-detail-row"><span class="live-label">technique</span> ${escHtml(c.phase_data.technique || "")}</div>
        <div class="live-detail-row"><span class="live-label">claim</span> ${escHtml(c.phase_data.claim || "")}</div>
        <div class="live-detail-row"><span class="live-label">targets</span> ${(c.phase_data.target_actions || []).join(", ")}</div>
        <div class="live-phase-note">reviewer is evaluating this proposal</div>`;
    } else if (c.phase === "judging" && c.phase_data) {
      bodyHtml = `
        <div class="live-detail-row"><span class="live-label">verdict</span> <span style="color:${c.phase_data.verdict === "ACCEPT" ? "var(--ok)" : "var(--fail)"}">${escHtml(c.phase_data.verdict || "")}</span></div>
        <div class="live-detail-row"><span class="live-label">reviewer</span> ${escHtml(c.phase_data.summary || "")}</div>
        <div class="live-phase-note">judge is ruling on reviewer's verdict</div>`;
    } else if (c.phase === "hard-gate" && c.phase_data) {
      bodyHtml = `
        <div class="live-detail-row"><span class="live-label">ruling</span> <span style="color:${c.phase_data.ruling === "ACCEPT" ? "var(--ok)" : "var(--fail)"}">${escHtml(c.phase_data.ruling || "")}</span></div>
        <div class="live-detail-row"><span class="live-label">reasoning</span> ${escHtml(c.phase_data.reasoning || "")}</div>
        <div class="live-phase-note">running TLC model checker</div>`;
    } else if (c.phase === "proposing") {
      bodyHtml = `<div class="live-phase-note">proposer agent is generating a spec improvement</div>`;
    } else {
      bodyHtml = `<div class="live-phase-note idle">waiting for next step</div>`;
    }

    return `
      <div class="live-comp ${isActive ? "active" : ""}">
        <div class="live-comp-header">
          <span class="live-comp-id">${c.id}</span>
          <span class="live-comp-phase" style="color:${phaseColor}">${isActive ? '<span class="pulse-dot" style="background:' + phaseColor + '"></span>' : ""}${phaseLabel}</span>
          <span class="live-comp-step">${c.step ? "step " + c.step : ""}</span>
          <span class="live-comp-elapsed">${isActive ? fmtElapsed(c.elapsed_s) : ""}</span>
          <span class="live-comp-completed">${c.completed_steps} completed</span>
          ${esc.tier > 0 ? '<span class="live-esc">esc tier ' + esc.tier + "</span>" : ""}
        </div>
        <div class="live-pipeline">${pipelineHtml}</div>
        <div class="live-comp-body">${bodyHtml}</div>
      </div>`;
  }).join("");
}

function updateFeed(live) {
  if (!live) return;
  const now = new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  for (const c of live.compartments) {
    const key = c.id;
    const prev = state.prevPhases[key];
    if (prev && prev !== c.phase) {
      state.feedEvents.unshift({
        time: now,
        comp: c.id,
        event: `${prev} -> ${c.phase}`,
        detail: c.phase === "reviewing" ? c.phase_data?.technique || "" :
                c.phase === "judging" ? "reviewer verdict: " + (c.phase_data?.verdict || "") :
                c.phase === "hard-gate" ? "judge ruling: " + (c.phase_data?.ruling || "") : "",
      });
    }
    state.prevPhases[key] = c.phase;
  }
  if (state.feedEvents.length > 50) state.feedEvents.length = 50;

  const feed = document.getElementById("live-feed");
  if (!feed) return;
  feed.innerHTML = state.feedEvents.map((e) => `
    <div class="feed-entry">
      <span class="feed-time">${e.time}</span>
      <span class="feed-comp">${e.comp}</span>
      <span class="feed-event">${e.event}</span>
      <span class="feed-detail">${escHtml(e.detail)}</span>
    </div>`).join("");
}

function fmtElapsed(s) {
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m " + (s % 60) + "s";
  return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
}

// ── event wiring ──

document.getElementById("run-select").addEventListener("change", (e) => {
  if (e.target.value) loadRun(e.target.value);
});

document.getElementById("refresh-btn").addEventListener("click", () => {
  if (state.runId) loadRun(state.runId);
  else loadRuns();
});

["journal-compartment-filter", "journal-status-filter", "journal-technique-filter"].forEach((id) => {
  document.getElementById(id).addEventListener("change", renderJournals);
});

document.getElementById("journal-show-checkpoints").addEventListener("change", () => {
  renderCheckpoints(document.getElementById("journal-compartment-filter").value);
});

document.getElementById("journal-compartment-filter").addEventListener("change", (e) => {
  renderCheckpoints(e.target.value);
});

document.getElementById("tech-class-filter").addEventListener("change", renderTechniques);

document.getElementById("evo-slider").addEventListener("input", (e) => {
  updateEvolution(parseInt(e.target.value));
});
document.getElementById("evo-prev").addEventListener("click", () => {
  if (state.evoStep > 0) updateEvolution(state.evoStep - 1);
});
document.getElementById("evo-next").addEventListener("click", () => {
  if (state.evoStep < state.journals.length) updateEvolution(state.evoStep + 1);
});

// ── auto-refresh for live view ──

let refreshInterval = null;

function startAutoRefresh() {
  if (refreshInterval) return;
  refreshInterval = setInterval(async () => {
    if (!state.runId) return;
    const [status, journals, live] = await Promise.all([
      api(`/api/runs/${state.runId}/status`),
      api(`/api/runs/${state.runId}/journals`),
      api(`/api/runs/${state.runId}/live`),
    ]);
    state.status = status;
    state.journals = journals || state.journals;
    state.live = live;
    updateStatusBadge();
    renderOverview();
    renderProgress();
    updateFeed(live);
    renderAgents();
  }, 2000);
}

// ── helpers ──

function fmtNum(n) {
  if (n == null) return "-";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return n.toString();
}

function escHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function escSvg(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ── init ──

loadRuns();
startAutoRefresh();
