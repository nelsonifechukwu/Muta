"use strict";

const state = {
  data: null,
  quick: false,
  expanded: new Set(),      // model files with history open
  runsCache: {},            // model file -> runs[]
  pollAt: 0,                // Date.now() of last successful poll
  timer: null,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmt = {
  score: (x, d = 1) => (x == null ? "—" : x.toFixed(d)),
  num: (x, d = 1) => (x == null ? "—" : Number(x).toFixed(d)),
  int: (x) => (x == null ? "—" : String(Math.round(x))),
  gb: (b) => (b == null ? "—" : (b / 2 ** 30).toFixed(2) + " GB"),
  mb: (x) => (x == null ? "—" : Math.round(x).toLocaleString() + " MB"),
  when: (iso) => iso == null ? "—" :
    new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
  elapsed: (s) => {
    s = Math.max(0, Math.floor(s));
    const m = Math.floor(s / 60), h = Math.floor(m / 60);
    return h ? `${h}:${String(m % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
             : `${m}:${String(s % 60).padStart(2, "0")}`;
  },
};

// ---------------------------------------------------------------- polling

async function poll() {
  clearTimeout(state.timer);
  try {
    const res = await fetch("/api/state");
    state.data = await res.json();
    state.pollAt = Date.now();
    await refreshExpandedRuns();
    render();
  } catch (e) { /* server briefly away; keep previous render */ }
  const busy = !!(state.data && state.data.current);
  state.timer = setTimeout(poll, busy ? 2500 : 8000);
}

async function refreshExpandedRuns() {
  for (const file of state.expanded) {
    try {
      const res = await fetch("/api/runs?model=" + encodeURIComponent(file));
      state.runsCache[file] = (await res.json()).runs;
    } catch (e) { /* keep cache */ }
  }
}

// ---------------------------------------------------------------- render

function render() {
  const d = state.data;
  if (!d) return;
  renderHeader(d);
  renderCampaign(d.campaign, "campaign");
  renderCampaign(d.campaign_parity, "campaign-parity");
  renderCampaign(d.campaign_alternative, "campaign-alternative");
  renderTpsRef(d);
  renderRunCard(d);
  renderChart(d);
  renderTable(d);
}

function renderCampaign(campaign, prefix) {
  const sub = $(`${prefix}-sub`);
  const table = $(`${prefix}-table`);
  const formula = $(`${prefix}-formula`);
  if (!campaign) {
    sub.textContent = "No campaign summary has been generated yet.";
    table.innerHTML = "";
    formula.textContent = "";
    return;
  }
  const denominators = campaign.tps_max_sensitivity || [];
  const isWebsiteAlternative = String(campaign.performance_formula || "").includes("public challenge");
  const isOfficialFullRun = campaign.evidence_tier === "official_profiler_full_run";
  const lookupDenominator = (mapping, denominator) => {
    if (!mapping) return null;
    return mapping[String(denominator)] || mapping[Number(denominator).toFixed(1)] || null;
  };
  const models = [...(campaign.models || [])].sort((a, b) => {
    const aResult = lookupDenominator(a.scores, denominators[0]);
    const bResult = lookupDenominator(b.scores, denominators[0]);
    const aScore = aResult ? aResult.s_total : null;
    const bScore = bResult ? bResult.s_total : null;
    if (aScore != null && bScore != null) return bScore - aScore;
    return (b.tg_tps_mean || 0) - (a.tg_tps_mean || 0);
  });
  const throughputLabel = isOfficialFullRun ? "Profiler generation tok/s" : "tok/s mean ± SD";
  const rssLabel = isOfficialFullRun
    ? "Profiler peak RSS"
    : isWebsiteAlternative
    ? "Measured process-tree RSS mean ± SD"
    : models.some((model) => model.rss_estimated)
      ? "Est. profiler RSS mean ± SD"
      : "Profiler peak RSS mean ± SD";
  sub.textContent = `${campaign.hardware_context || "unknown host"} · ` +
    `${models.length} exact GGUF artifacts · binary ${String(campaign.benchmark_binary_sha256 || "unknown").slice(0, 12)}…`;
  const scoreHeads = denominators.map((d) =>
    `<th>S @ ${isWebsiteAlternative ? "TPS_max floor" : "profiler ref"} ${esc(d)}</th>`
  ).join("");
  const head = `<thead><tr><th>Exact model</th><th>Size</th><th>${throughputLabel}</th>` +
    `<th>${rssLabel}</th><th>Accuracy proxies</th>` +
    `${scoreHeads}</tr></thead>`;
  const rows = models.map((m) => {
    const scoreCells = denominators.map((d) => {
      const score = lookupDenominator(m.scores, d);
      return `<td class="total">${score ? fmt.score(score.s_total, 2) : "—"}</td>`;
    }).join("");
    const accuracyEntries = Object.entries(m.accuracy_tasks || {}).map(([task, result]) => {
      const ci = result.ci95_percent || [];
      const interval = ci.length === 2
        ? ` · 95% CI ${fmt.num(ci[0], 1)}–${fmt.num(ci[1], 1)}`
        : "";
      return `${esc(task)} ${fmt.num(result.score_percent, 1)}% (n=${esc(result.samples)})${interval}`;
    }).join("<br>");
    const sampleLabel = m.measurement_tier === "official_profiler_full_run"
      ? `${esc(m.throughput_rounds)} full profiler run / ${esc(m.throughput_repetitions)} internal benchmark samples`
      : `${esc(m.throughput_rounds)} interleaved rounds / ${esc(m.throughput_repetitions)} timed samples`;
    const throughputCell = isOfficialFullRun
      ? fmt.num(m.tg_tps_mean, 2)
      : `${fmt.num(m.tg_tps_mean, 2)} ± ${fmt.num(m.tg_tps_sd, 2)}`;
    const rssCell = isOfficialFullRun
      ? fmt.mb(m.peak_rss_mib_mean)
      : `${fmt.mb(m.peak_rss_mib_mean)} ± ${fmt.mb(m.peak_rss_mib_sd)}`;
    return `<tr><td><div class="model-name">${esc(shortName(m.model))}</div>` +
      `<div class="model-sub mono">sha256:${esc(String(m.model_sha256 || "unknown").slice(0, 16))}… · ${esc(m.measurement_tier || "unlabelled")} · ${sampleLabel}</div></td>` +
      `<td>${fmt.gb(m.model_bytes)}</td>` +
      `<td>${throughputCell}</td>` +
      `<td>${rssCell}</td>` +
      `<td>${accuracyEntries || "pending"}</td>` +
      scoreCells + `</tr>`;
  }).join("");
  table.innerHTML = head + `<tbody>${rows}</tbody>`;
  const winnerText = denominators.map((d) => {
    const winner = lookupDenominator(campaign.winners, d);
    return winner ? `${d}→${shortName(winner.model)} (${fmt.num(winner.s_total, 2)})` : null;
  }).filter(Boolean).join(" · ");
  formula.textContent = `${campaign.performance_formula}. ${campaign.accuracy_notice}. ` +
    `${campaign.rss_notice || ""}. ${campaign.thermal_notice}. ${campaign.tps_max_scenario_notice || ""}.` + (winnerText
      ? ` Winner by ${isWebsiteAlternative ? "TPS_max floor scenario" : "profiler reference"}: ${winnerText}.`
      : "");
}

function renderTpsRef(d) {
  const sc = d.scoring || {};
  const el = $("tps-ref");
  if (!el) return;
  if (sc.tps_reference == null) {
    el.textContent = "TPS_max = fastest stored run (none measured yet)";
    return;
  }
  const run = sc.tps_reference_run || {};
  el.textContent = `TPS_max = ${fmt.num(sc.tps_reference)} tok/s` +
    (run.model_file
      ? ` (${shortName(run.model_file)} · run #${run.id}${run.quick ? " · quick" : ""})`
      : "");
}

function renderHeader(d) {
  const m = d.metadata || {};
  const claims = [];
  if (m.african_alpha_claim) claims.push("African-language claim");
  if (m.budget_laptop_claim) claims.push("budget-laptop claim");
  $("meta-line").textContent =
    `${m.team_id || "?"} · ${m.domain || "?"}` +
    (claims.length ? ` · ${claims.join(" · ")}` : "") +
    (m.current_model_path ? ` · metadata → ${m.current_model_path}` : "");
  const pill = $("status-pill");
  if (d.current) {
    pill.classList.add("busy");
    pill.textContent = `profiling ${shortName(d.current.model_file)}`;
  } else {
    pill.classList.remove("busy");
    pill.textContent = "idle";
  }
}

function renderRunCard(d) {
  const card = $("run-card");
  if (!d.current) { card.hidden = true; return; }
  card.hidden = false;
  $("run-title").textContent = `Profiling ${d.current.model_file}`;
  $("run-sub").textContent = d.current.skip_accuracy
    ? "quick run · --skip-accuracy · no S_acc for this run"
    : "full run · arc_easy 50 samples · this can take a while";
  const log = $("run-log");
  const pinned = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
  log.textContent = (d.current.log || []).join("\n");
  if (pinned) log.scrollTop = log.scrollHeight;
  tickElapsed();
}

function tickElapsed() {
  const d = state.data;
  if (!d || !d.current) return;
  const drift = (Date.now() - state.pollAt) / 1000;
  $("run-elapsed").textContent = fmt.elapsed(d.current.elapsed_s + drift);
}
setInterval(tickElapsed, 1000);

function renderChart(d) {
  const el = $("chart");
  const scored = d.models.filter((m) => m.best && m.best.scores && m.best.scores.s_total != null);
  if (!scored.length) {
    el.innerHTML = `<p class="chart-empty">No fully-scored runs yet — run a full profile (quick runs skip accuracy, so they have no S_total).</p>`;
    return;
  }
  scored.sort((a, b) => b.best.scores.s_total - a.best.scores.s_total);
  const rows = scored.map((m) => {
    const t = m.best.scores.s_total;
    return `<div class="chart-row" data-chart-model="${esc(m.file)}">
      <div class="chart-label">${esc(shortName(m.file))}</div>
      <div class="bar-track"><div class="bar" style="width:${Math.min(100, t)}%"></div></div>
      <div class="chart-value">${t.toFixed(1)}</div>
    </div>`;
  }).join("");
  const axis = `<div class="chart-axis"><div></div><div class="ticks">
      <span style="left:0">0</span><span style="left:25%">25</span><span style="left:50%">50</span>
      <span style="left:75%">75</span><span style="left:100%">100</span></div><div></div></div>`;
  el.innerHTML = rows + axis;
}

function statusChips(run) {
  if (!run) return `<span class="dim">—</span>`;
  const s = run.scores || {};
  const chips = [];
  if (run.status === "failed") {
    chips.push(chip("critical", run.oom ? "OOM" : "crash"));
    chips.push(chip("critical", "DQ"));
  } else {
    if (run.throttled) chips.push(chip("serious", "throttled"));
    if (s.thermal_penalty > 0) chips.push(chip("warning", "−10 thermal"));
    if (!run.throttled && !(s.thermal_penalty > 0)) chips.push(chip("good", "clean"));
  }
  return chips.join("");
}

function chip(kind, label) {
  return `<span class="chip ${kind}"><span class="dot"></span>${esc(label)}</span>`;
}

function claimChips(run, meta) {
  const african = run ? run.african_claim : meta.african_alpha_claim;
  const budget = run ? run.budget_claim : meta.budget_laptop_claim;
  const out = [];
  if (african) out.push(chip("neutral", "African"));
  if (budget) out.push(chip("neutral", "budget"));
  return out.length ? out.join("") : `<span class="dim">—</span>`;
}

function shortName(file) { return file.replace(/\.gguf$/i, ""); }

function renderTable(d) {
  const busy = !!d.current;
  const present = d.models.filter((m) => m.present).length;
  const gone = d.models.length - present;
  $("models-sub").textContent =
    `${present} GGUF file${present === 1 ? "" : "s"} in model/` +
    (gone ? ` · ${gone} deleted model${gone === 1 ? "" : "s"} with saved runs` : "") +
    ` · latest run shown per model · click History for all runs`;
  const head = `<thead><tr>
    <th>Model</th><th>S_total</th><th>S_acc</th><th>S_perf</th><th>S_eff</th>
    <th>arc_easy</th><th>tok/s</th><th>TTFT ms</th><th>Peak RAM</th><th>CPU temp</th>
    <th class="center">Status</th><th class="center">Claims</th>
  </tr></thead>`;
  const rows = d.models.map((m) => {
    const r = m.latest, s = r ? r.scores : null;
    const running = d.current && d.current.model_file === m.file;
    const info = m.present
      ? [fmt.gb(m.size_bytes), m.quant, m.params]
      : ["file deleted — runs kept", m.quant, m.params];
    const sub = info.filter(Boolean).join(" · ") +
      (m.runs_count
        ? ` · ${m.runs_count} run${m.runs_count === 1 ? "" : "s"} · last ${fmt.when(r && (r.finished_at || r.started_at))}`
        : " · never profiled");
    const arc = r && r.arc_score != null ? `${r.arc_score.toFixed(3)}` : "—";
    const main = `<tr class="model-row" data-model="${esc(m.file)}">
      <td>
        <div class="model-name${m.present ? "" : " dim"}">${esc(shortName(m.file))}</div>
        <div class="model-sub">${esc(sub)}</div>
        <div class="model-actions">
          <button class="btn primary small" data-action="profile" data-model="${esc(m.file)}"
            ${busy || !m.present ? "disabled" : ""}>${running ? "Running…" : "Profile"}</button>
          <button class="btn small" data-action="history" data-model="${esc(m.file)}"
            ${m.runs_count ? "" : "disabled"}>History ${state.expanded.has(m.file) ? "▴" : "▾"}</button>
        </div>
      </td>
      <td class="total">${s ? fmt.score(s.s_total) : "—"}</td>
      <td>${s ? fmt.score(s.s_acc) : "—"}</td>
      <td>${s ? fmt.score(s.s_perf) : "—"}</td>
      <td>${s ? fmt.score(s.s_eff) : "—"}</td>
      <td>${arc}</td>
      <td>${r ? fmt.num(r.tps) : "—"}</td>
      <td>${r ? fmt.int(r.ttft_ms) : "—"}</td>
      <td>${r ? fmt.mb(r.peak_rss_mb) : "—"}</td>
      <td>${r && r.temp_c != null ? fmt.num(r.temp_c) + " °C" : "—"}</td>
      <td class="center">${statusChips(r)}</td>
      <td class="center">${claimChips(r, d.metadata || {})}</td>
    </tr>`;
    const hist = state.expanded.has(m.file) ? historyRow(m.file) : "";
    return main + hist;
  }).join("");
  $("models-table").innerHTML = head + `<tbody>${rows}</tbody>`;
}

function historyRow(file) {
  const runs = state.runsCache[file] || [];
  const model = (state.data ? state.data.models : []).find((m) => m.file === file);
  const gone = !!model && !model.present;
  const rows = runs.filter((r) => r.status !== "running").map((r) => {
    const s = r.scores || {};
    return `<tr>
      <td>#${r.id} · ${fmt.when(r.finished_at || r.started_at)}</td>
      <td>${r.skip_accuracy ? "quick" : "full"}</td>
      <td>${r.status === "ok" ? "ok" : (r.oom ? "OOM" : "crash")}</td>
      <td>${fmt.score(s.s_total)}</td>
      <td>${fmt.score(s.s_acc)}</td>
      <td>${fmt.score(s.s_perf)}</td>
      <td>${fmt.score(s.s_eff)}</td>
      <td>${fmt.num(r.tps)}</td>
      <td>${fmt.mb(r.peak_rss_mb)}</td>
      <td>
        <button class="btn small" data-action="json" data-id="${r.id}">Report</button>
        <button class="btn small" data-action="promote" data-id="${r.id}"
          ${r.status === "ok" && !gone ? "" : "disabled"}
          ${gone ? 'title="model file deleted — cannot promote"' : ""}>→ submission.json</button>
        <button class="btn small danger" data-action="delete" data-id="${r.id}">Delete</button>
      </td>
    </tr>`;
  }).join("");
  return `<tr class="history-row"><td colspan="12">
    <table class="history">
      <thead><tr><th>Run</th><th>Mode</th><th>Status</th><th>S_total</th><th>S_acc</th><th>S_perf</th>
      <th>S_eff</th><th>tok/s</th><th>Peak RAM</th><th>Actions</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="10" class="dim">no finished runs</td></tr>`}</tbody>
    </table>
  </td></tr>`;
}

// ---------------------------------------------------------------- actions

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;

  if (action === "profile") {
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: btn.dataset.model, skip_accuracy: state.quick }),
    });
    if (!res.ok) alert((await res.json()).error || "failed to start");
    poll();
  } else if (action === "cancel") {
    if (confirm("Cancel the current profiling run?")) {
      await fetch("/api/cancel", { method: "POST" });
      poll();
    }
  } else if (action === "history") {
    const file = btn.dataset.model;
    if (state.expanded.has(file)) state.expanded.delete(file);
    else {
      state.expanded.add(file);
      await refreshExpandedRuns();
    }
    render();
  } else if (action === "json") {
    const res = await fetch("/api/runs/" + btn.dataset.id);
    const d = await res.json();
    $("modal-title").textContent = `Run #${d.id} · ${d.model_file} · ${d.status}`;
    $("modal-body").textContent = d.report
      ? JSON.stringify(d.report, null, 2)
      : `error: ${d.error || "unknown"}\nexit code: ${d.exit_code}\n\n--- log ---\n${d.log_tail || "(empty)"}`;
    $("modal").hidden = false;
  } else if (action === "promote") {
    if (confirm("Overwrite metadata.json and submission.json at the repo root with this run?")) {
      const res = await fetch(`/api/runs/${btn.dataset.id}/promote`, { method: "POST" });
      if (!res.ok) alert((await res.json()).error || "promote failed");
      poll();
    }
  } else if (action === "delete") {
    if (confirm("Delete this run from the database?")) {
      await fetch("/api/runs/" + btn.dataset.id, { method: "DELETE" });
      poll();
    }
  } else if (action === "modal-close") {
    $("modal").hidden = true;
  }
});

$("modal").addEventListener("click", (ev) => {
  if (ev.target === $("modal")) $("modal").hidden = true;
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") $("modal").hidden = true;
});

$("quick-toggle").addEventListener("change", (ev) => { state.quick = ev.target.checked; });

// chart tooltip
document.addEventListener("mousemove", (ev) => {
  const row = ev.target.closest && ev.target.closest("[data-chart-model]");
  const tip = $("tooltip");
  if (!row || !state.data) { tip.hidden = true; return; }
  const m = state.data.models.find((x) => x.file === row.dataset.chartModel);
  if (!m || !m.best) { tip.hidden = true; return; }
  const r = m.best, s = r.scores;
  tip.innerHTML = `<div class="tt-title">${esc(shortName(m.file))}</div>
    <div class="tt-grid">
      <span>S_total</span><b>${fmt.score(s.s_total)}</b>
      <span>S_acc</span><b>${fmt.score(s.s_acc)}</b>
      <span>S_perf</span><b>${fmt.score(s.s_perf)}</b>
      <span>S_eff</span><b>${fmt.score(s.s_eff)}</b>
      <span>tok/s</span><b>${fmt.num(r.tps)}</b>
      <span>peak RAM</span><b>${fmt.mb(r.peak_rss_mb)}</b>
      <span>run</span><b>#${r.id} · ${fmt.when(r.finished_at)}</b>
    </div>`;
  tip.hidden = false;
  const pad = 14;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > innerHeight - 8) y = ev.clientY - h - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
});

poll();
