"use strict";

const state = {
  data: null,
  quick: false,
  expanded: new Set(),      // model files with history open
  runsCache: {},            // model file -> runs[]
  pollAt: 0,                // Date.now() of last successful poll
  timer: null,
  modalReturnFocus: null,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sentenceCase = (s) => s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : "";

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

// ---------------------------------------------------------------- report evidence

const REPORT_OFFICIAL = [
  { name: "Qwen3 1.7B Q4_0", file: "muta-tutor-qwen3-1.7b-q4_0.gguf", sha: "a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e", bytes: 974198528, ttft: 35372.22, tps: 9.79, rss: 1116.31, acc: 72, ci: [58.33, 82.53], sAcc: 72, sPerf: 65.2667, sEff: 84.4265, total: 72.4653 },
  { name: "Qwen3.5 0.8B Q4_K_M", file: "qwen3.5-0.8b-q4_k_m.gguf", sha: "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517", bytes: 532517120, ttft: 28261.79, tps: 9.74, rss: 694.73, acc: 68, ci: [54.19, 79.24], sAcc: 68, sPerf: 64.9333, sEff: 90.3079, total: 71.5416 },
  { name: "BitCPM4 8B TQ2_0", file: "bitcpm4-8b-tq2_0-envocab.gguf", sha: "069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d", bytes: 2208746208, ttft: 584154.13, tps: 0.81, rss: 2306.56, acc: 88, ci: [76.20, 94.38], sAcc: 88, sPerf: 5.4, sEff: 67.8214, total: 59.1843 },
  { name: "Qwen3.5 4B IQ4_XS", file: "qwen3.5-4b-iq4_xs.gguf", sha: "658a9e7e406deb06d0179755e3c14f6a82915a4be4962a2f92a64d948d2e572f", bytes: 2477053088, ttft: 395187.97, tps: 1.13, rss: 2627.34, acc: 76, ci: [62.59, 85.70], sAcc: 76, sPerf: 7.5333, sEff: 63.3463, total: 52.9293 },
];

const REPORT_RUNTIME = [
  { name: "Docker baseline", tps: 5.3, memory: "4.77 GB, still rising", date: "30 Jul" },
  { name: "Resource caps", tps: 6.72, memory: "4.44 GB", date: "31 Jul" },
  { name: "Native default", tps: 29.78, memory: "3,519 MiB footprint", date: "1 Aug" },
  { name: "6 threads + unified KV", tps: 31.09, memory: "3,137 MiB footprint", date: "1 Aug" },
  { name: "Draft speculation", tps: 24.72, memory: "host RAM not reliable", date: "31 Jul" },
];

const REPORT_FUNNEL = [
  { name: "Qwen3.5 4B", gb: 2.55, acc: 73.3, lane: "reasoning" },
  { name: "Qwen3.5 2B", gb: 1.19, acc: 64.8, lane: "reasoning" },
  { name: "Qwen3.5 0.8B", gb: 0.50, acc: 51.3, lane: "reasoning" },
  { name: "Qwen3 1.7B Q4_0", gb: 0.91, acc: 72, lane: "audit" },
  { name: "Qwen3 1.7B Q4_K_M", gb: 0.96, acc: 72, lane: "audit", selected: true },
  { name: "Qwen3.5 0.8B Q4_K_M", gb: 0.50, acc: 68, lane: "audit" },
  { name: "BitCPM4 8B TQ2_0", gb: 2.06, acc: 88, lane: "audit" },
  { name: "Qwen3.5 4B IQ4_XS", gb: 2.31, acc: 76, lane: "audit" },
  { name: "LFM2.5 1.2B", gb: 0.65, acc: 56, lane: "audit", muted: true },
  { name: "Qwen2.5 Math 1.5B", gb: 0.87, acc: 24, lane: "audit", muted: true },
];

const REPORT_STREAMING = [
  { name: "Stream all", rss: 279, tps: 10.47 },
  { name: "Pin 1,000 MB", rss: 1136, tps: 13.04 },
  { name: "Pin 1,300 MB", rss: 1408, tps: 14.04 },
  { name: "Pin 1,500 MB", rss: 1636, tps: 15.35 },
  { name: "Resident", rss: 2129, tps: 18.70 },
];

const EXPERIMENTS = [
  { status: "adopted", name: "Concurrency and cache caps", finding: "Two parallel slots, four checkpoints, and a 256 MiB cache stopped memory growth. The early Docker baseline rose from about 5.3 to 6.72 tok/s.", source: "RESULTS.md · 31 Jul" },
  { status: "adopted", name: "Six-thread runtime", finding: "Six batch and decode threads reached 31.09 tok/s, 83% of the estimated weight-bandwidth limit. Ten threads reduced decode throughput to approximately 4.4 tok/s.", source: "RESULTS.md · 1 Aug" },
  { status: "adopted", name: "Unified KV, two checkpoints", finding: "Unified KV and two checkpoints reduced retained state and improved prefill while holding decode near 31 tok/s on the development host.", source: "RESULTS.md · 1 Aug" },
  { status: "rejected", name: "0.8B draft speculation", finding: "98.4% proposal acceptance still slowed native decode from 30.84 to 24.72 tok/s. Host RAM readings were flagged as unreliable, so no native memory delta is claimed.", source: "RESULTS.md · 31 Jul" },
  { status: "neutral", name: "N-gram speculation", finding: "A 12–22% acceptance rate did not offset lookup and verification overhead. The feature is disabled by default and uses no additional model memory.", source: "RESULTS.md · 1 Aug" },
  { status: "rejected", name: "More threads", finding: "Throughput did not increase after memory bandwidth saturated. Ten threads reduced decode throughput to approximately 4.4 tok/s; temperature was not measured in this sweep.", source: "RESULTS.md · 1 Aug" },
  { status: "rejected", name: "Disable mmap", finding: "Decode fell by about 28% and memory rose by about 1 GiB. The stock audit’s eager mmap policy cannot be changed by the submitted GGUF.", source: "RESULTS.md · GGUF campaign" },
  { status: "neutral", name: "mlock", finding: "Pinning pages produced no repeatable throughput gain in the tested resident configuration.", source: "RESULTS.md · 1 Aug" },
  { status: "adopted", name: "No-repack product path", finding: "Avoiding runtime tensor conversion cut a tested 4B footprint from about 3,236 to 602 MiB. The campaign cannot use this engine-only change.", source: "RESULTS.md · 1 Aug" },
  { status: "adopted", name: "Fixed context budget", finding: "Explicit context and KV limits replaced runtime defaults, fixing a memory variable for subsequent comparisons.", source: "runtime configuration" },
  { status: "adopted", name: "4B reasoning baseline", finding: "The 4B model exceeded the 2B model by 15.7 points across three STEM tasks. The later audit used a different kernel configuration and a separate accuracy proxy.", source: "RESULTS.md · 5 Aug" },
  { status: "neutral", name: "IQ4_XS importance matrix", finding: "Task scores moved in both directions by roughly one or two items, with no reliable accuracy gain.", source: "RESULTS.md · 6 Aug" },
  { status: "adopted", name: "Uniform Qwen quant ladder", finding: "Under AVX2, Q4_K_M recorded the highest total. Q5_K_M gained four ARC-Easy points, but the gain did not repeat on ARC-Challenge or SciQ and throughput was lower.", source: "GGUF campaign · 19 Aug" },
  { status: "rejected", name: "Mixed embedding and head precision", finding: "Q3_K_M with a Q6_K head fell to 66% ARC-Easy; IQ4_XS with a Q6_K head was slower and larger than uniform IQ4_XS.", source: "GGUF campaign · 19 Aug" },
  { status: "neutral", name: "Vendor importance matrix", finding: "The Qwen K-quant ladder used the vendor matrix consistently, but its calibration corpus is unpublished. Dataset disjointness cannot be independently verified.", source: "GGUF campaign · 19 Aug" },
  { status: "neutral", name: "Metal offload", finding: "Hybrid 4B decode was neutral to slightly slower than CPU-only on the development Mac. GPU support remains optional.", source: "RESULTS.md · 6 Aug" },
  { status: "deferred", name: "TinyStories TTFT preamble", finding: "A tiny warm-up model produced a 1.65 ms first chunk with a small resident cost, but licensing was unresolved and the feature is off by default.", source: "RESULTS.md · 6 Aug" },
  { status: "adopted", name: "BitCPM vocabulary pruning", finding: "Pruning 73,448 tokens to 44,416 saved 164 MiB. English tokenisation matched across 20,464 checked tokens and perplexity changed from 10.558 to 10.473.", source: "muta-iq/opt/docs/REPORT.md" },
  { status: "rejected", name: "BitCPM TQ1_0 body", finding: "The file lost 340 MiB, but generic-kernel throughput fell 22%. The evaluator lacked the kernel needed to turn fewer bits into less work.", source: "muta-iq/opt/docs/REPORT.md" },
  { status: "rejected", name: "Head and embedding requants", finding: "At most 48 MiB was saved and the largest estimated total-score increase was approximately 0.14. Behavioural effects were not measured.", source: "muta-iq/opt/docs/REPORT.md" },
  { status: "rejected", name: "Low-rank factorisation", finding: "Ternary matrices remained full-rank. Rank-2048 factorisation error was about 0.80 before quantisation and exceeded 1 after it.", source: "muta-iq/opt/docs/REPORT.md" },
  { status: "rejected", name: "Unstructured sparsity", finding: "Dense GGUF stores the zeros and the stock kernels still multiply them. There was no file or compute saving to score.", source: "muta-iq/opt/docs/REPORT.md" },
  { status: "rejected", name: "Single-layer pruning", finding: "One Qwen layer gained about 3.7% speed but lost two ARC-Easy points. The accuracy cost exceeded the performance return.", source: "GGUF campaign · 19 Aug" },
  { status: "deferred", name: "Qwen vocabulary pruning", finding: "Not attempted: the current tools cannot rewrite the GPT-2 BPE merges coherently. BitCPM’s verified vocabulary prune does not transfer automatically.", source: "GGUF campaign · 19 Aug" },
  { status: "rejected", name: "Context metadata change", finding: "The profiler fixes prompt length at 512 tokens and generation length at 128 tokens. Context metadata does not change this workload.", source: "GGUF campaign · 19 Aug" },
  { status: "rejected", name: "Custom tensor layout", finding: "The stock quantiser layout was retained. An unsupported alignment or packing scheme could fail to load and disqualify the run.", source: "GGUF campaign · 19 Aug" },
  { status: "adopted", name: "Embedded chat template", finding: "The GGUF contains the chat template and tutoring persona, both verified on a live server. They affect evaluator responses but do not affect raw ARC or throughput measurements.", source: "muta-iq/REPORT.md" },
  { status: "rejected", name: "Weight streaming for submission", finding: "Streaming could cut residency to hundreds of MiB, but SSD bandwidth missed the 15 tok/s target and a custom engine cannot accompany a GGUF-only entry.", source: "muta-iq/opt/docs/STREAMING_ENGINE.md" },
  { status: "adopted", name: "Runtime-conditional quant choice", finding: "Pure Q4_0 wins the scalar participant regime. With AVX2/FMA/F16C enabled, Q4_K_M reaches the cap with 59.7 MiB less estimated RSS and leads by 0.1666 points.", source: "avx2-score-of-record · 19 Aug" },
  { status: "adopted", name: "Tied output head", finding: "The final tied-versus-untied control saved about 175 MB of file bytes with the same 72% ARC-Easy proxy.", source: "GGUF campaign · 19 Aug" },
  { status: "adopted", name: "Exact-hash rebuild", finding: "The candidate was rebuilt from pinned source and matched the promoted SHA-256 after correcting a 32-byte metadata-name difference.", source: "Set up Muta on GCP VM" },
  { status: "adopted", name: "Direct official-profiler campaign", finding: "Four exact artifacts completed full participant runs. The 1.7B Q4_0 total exceeds the 0.8B total by 0.92 points.", source: "campaign-20260819/official-profiler" },
  { status: "adopted", name: "Portable AVX2 score of record", finding: "Five exact hashes were rerun with AVX2, FMA, and F16C enabled and AVX-512 disabled. Q4_K_M records 80.4484 and Q4_0 records 80.2818. BitCPM throughput increases by 9.235× and its total remains below the Qwen results.", source: "campaign-20260819/avx2-score-of-record" },
  { status: "deferred", name: "QAT or distillation", finding: "QAT and distillation may recover capability in a smaller artifact. Neither has completed a controlled campaign.", source: "muta-iq/opt/docs/REPORT.md" },
];

const CHALLENGE_FAQ = [
  { q: "Will evaluation run without internet access?", rule: "Yes. The judging environment is offline.", progress: "The runtime resolves local files first, the promoted GGUF is hash-pinned, and the tutor has an offline launch path. A clean physical-target rehearsal remains." },
  { q: "How is the final score calculated?", rule: "Accuracy carries 50%, performance 30%, and efficiency 20%, with a thermal penalty and hard-failure rules.", progress: "The executable formula is implemented and tested. This report keeps the public cohort-relative formula in a separate sensitivity lane." },
  { q: "Can teams develop on stronger hardware?", rule: "Yes, but the final artifact is evaluated on the standard laptop profile.", progress: "Development used an M2 Mac and a GCP x86 proxy. Mac results are classified as development evidence." },
  { q: "Does adding an African language qualify for the use-case bonus?", rule: "Language support alone does not establish the African use case.", progress: "" },
  { q: "What does cross-disciplinary integration require?", rule: "The model must depend substantively on another deep-tech discipline.", progress: "Muta plans to combine scientific tutoring with verified mathematics and local retrieval. Several relevant routes remain incomplete or return 501, so this requirement is not yet satisfied." },
  { q: "Are fine-tuned open models allowed?", rule: "Yes, subject to the competition’s open-model and artifact rules.", progress: "The current AVX2 choice and scalar fallback are reproducible Qwen3-derived GGUFs. QAT and distillation remain deferred because neither completed a controlled training run." },
  { q: "Which countries are eligible?", rule: "Eligibility follows the organiser’s published country rules.", progress: "" },
  { q: "Can Africans studying abroad enter?", rule: "The FAQ describes the applicable eligibility route.", progress: "" },
  { q: "Is there an age restriction?", rule: "The organiser’s FAQ gives the eligibility condition.", progress: "" },
  { q: "How is the team identified in the artifact?", rule: "Submission metadata must identify the registered team.", progress: "The current metadata uses team ID `team-muta`. Registration details still need a final submission check." },
  { q: "Must the base model be open source?", rule: "The submission must follow the challenge’s open-model requirements.", progress: "The current Qwen3 base uses an open licence. The exact source, conversion path, binary, artifact size, and SHA-256 are recorded." },
  { q: "Which inference formats and tools are allowed?", rule: "The model-only track evaluates GGUF with llama.cpp.", progress: "The campaign submits exact GGUF artifacts and pins llama.cpp b10175. Custom streaming and lazy-mmap engines are excluded from the scoring claim." },
  { q: "What is the maximum model size?", rule: "The practical limit is the 7 GB memory ceiling on the standard machine.", progress: "The direct campaign spans about 0.50–2.31 GiB peak model footprints, all below the ceiling. Whole-tree RSS remains the unit of record." },
  { q: "Where should the final benchmark be run?", rule: "The organiser evaluates the artifact on its standard hardware; local results are preparatory.", progress: "Full participant runs exist on a four-vCPU GCP x86 proxy with the pinned audit binary. Package temperature and physical-laptop bandwidth remain unmeasured." },
  { q: "What must the Gate 1 submission contain?", rule: "Gate 1 requires the open-source repository and structured report, a working model download path, two test prompts, screenshots or clips, and a 2-minute demo video.", progress: "The repository records exact model metadata, the reproducible campaign, the runtime, and this report. Final packaging, the two submission prompts, and the video remain incomplete." },
  { q: "What should teams enter as self-reported scores?", rule: "DevPost asks for separate S_perf and S_eff values computed from local profiler telemetry. Teams do not submit S_acc.", progress: "Q4_K_M under the portable AVX2 policy records S_perf 100.00 and estimated S_eff 72.24. The direct scalar participant run for Q4_0 records S_perf 65.27 and S_eff 84.43. Its 72% ARC-Easy result remains an internal accuracy proxy, not a submitted S_acc value." },
  { q: "Is the whole application evaluated, or only the model?", rule: "The model-only evaluation uses the submitted GGUF in the organiser’s runtime.", progress: "Product improvements are recorded separately from model-only evidence. Retrieval, the custom streamer, and UI changes are excluded from the GGUF campaign score." },
  { q: "How many prompts are visible before submission?", rule: "The FAQ describes two visible prompts plus hidden tests.", progress: "The local profiler path covers the visible task shape and accuracy proxies. Hidden-prompt performance remains unknown by design." },
  { q: "How is temperature handled?", rule: "Temperature is checked around evaluation and can trigger a 10-point penalty above the threshold or when throttling is detected.", progress: "The GCP host exposed no usable package sensor and reported no throttling. Temperature is recorded as unavailable." },
  { q: "Can the system have an optional online mode?", rule: "The judged path must work offline; optional network features cannot be required.", progress: "Muta’s core runtime, model, retrieval plan, and UI are designed for offline use. Deployment uses local artifacts; network provisioning is a development fallback." },
  { q: "How should the African use case be demonstrated?", rule: "The use case should solve a concrete African problem; language support is not mandatory.", progress: "The current case is an offline tutor for bandwidth-constrained classrooms and budget laptops. Benchmark evidence alone is insufficient; the product claim still needs classroom evidence." },
  { q: "What should the demo video show?", rule: "The video should demonstrate the working entry under the stated constraints.", progress: "A final video has not been recorded." },
];

const svgText = (x, y, value, attrs = "") => `<text x="${x}" y="${y}" ${attrs}>${esc(value)}</text>`;

function initReport() {
  renderScoreLab();
  renderRuntimeChart();
  renderModelFunnelChart();
  renderStreamingChart();
  renderOfficialCharts();
  renderLedger("adopted");
  renderFaq();
  updateStreamingBudget();
  updateReadingProgress();
  updateActiveChapter();
}

function renderScoreLab() {
  const accuracy = Number($("score-accuracy").value);
  const tps = Number($("score-tps").value);
  const ram = Number($("score-ram").value);
  const penalty = $("score-thermal").checked ? 10 : 0;
  const sPerf = Math.min(tps / 15, 1) * 100;
  const sEff = Math.max(0, (7 - ram) / 7) * 100;
  const parts = [
    { label: "Accuracy × 0.50", value: accuracy * .5, color: "#1b6ca8" },
    { label: "Performance × 0.30", value: sPerf * .3, color: "#427b58" },
    { label: "Efficiency × 0.20", value: sEff * .2, color: "#b57614" },
    { label: "Thermal penalty", value: -penalty, color: "#ad2111" },
  ];
  $("score-accuracy-value").value = accuracy.toFixed(0);
  $("score-tps-value").value = tps.toFixed(2);
  $("score-ram-value").value = ram.toFixed(2);
  $("score-total").value = (parts.reduce((sum, part) => sum + part.value, 0)).toFixed(2);
  $("score-breakdown").innerHTML = parts.map((part) => `<div class="score-part" style="--fill:${Math.abs(part.value) * 2}%;--part-color:${part.color}"><span>${esc(part.label)}</span><strong>${part.value >= 0 ? "+" : ""}${part.value.toFixed(2)}</strong></div>`).join("");
}

function renderRuntimeChart() {
  const el = $("runtime-chart");
  const width = 700, height = 290, left = 165, right = 52, top = 22, rowH = 49;
  const plotW = width - left - right;
  const bars = REPORT_RUNTIME.map((item, i) => {
    const y = top + i * rowH;
    const tpsW = item.tps / 35 * plotW;
    return `${svgText(left - 10, y + 15, item.name, 'text-anchor="end" class="svg-label"')}
      <rect x="${left}" y="${y}" width="${tpsW}" height="13" rx="2" class="svg-throughput" />
      ${svgText(left + tpsW + 6, y + 11, `${item.tps.toFixed(2)} tok/s`, 'class="svg-value"')}
      ${svgText(left, y + 29, `Memory: ${item.memory}`, 'class="svg-value muted"')}`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>
    .svg-label{font-size:11px;fill:#3c3836}.svg-value{font-size:9px;fill:#427b58;font-weight:700}.svg-value.muted{fill:#8a8580;font-weight:400}.svg-throughput{fill:#427b58}
  </style>${bars}${svgText(left, height - 8, "Generation bars share one scale; memory text preserves each source's recorded unit and caveat.", 'class="svg-foot"')}</svg>`;
}

function renderModelFunnelChart() {
  const el = $("model-funnel-chart");
  const width = 720, height = 500, left = 190, right = 65;
  const x = (gb) => left + gb / 2.8 * (width - left - right);
  let grid = "";
  [0, .5, 1, 1.5, 2, 2.5].forEach((tick) => {
    const px = x(tick);
    grid += `<line x1="${px}" y1="42" x2="${px}" y2="454" class="svg-grid"/>${svgText(px, 476, `${tick.toFixed(1)} GiB`, 'text-anchor="middle" class="svg-tick"')}`;
  });
  const reasoning = REPORT_FUNNEL.filter((item) => item.lane === "reasoning");
  const audit = REPORT_FUNNEL.filter((item) => item.lane === "audit");
  const renderRows = (items, startY, gap, lane) => items.map((item, i) => {
    const py = startY + i * gap, px = x(item.gb);
    const cls = item.selected ? "selected" : item.muted ? "muted" : lane;
    const scoreLabel = lane === "reasoning" ? `${item.acc.toFixed(1)} four-task mean` : `${item.acc.toFixed(0)}% ARC proxy`;
    return `${svgText(left - 12, py + 3, item.name, 'text-anchor="end" class="svg-row-label"')}
      <line x1="${left}" y1="${py}" x2="${px}" y2="${py}" class="lollipop-line ${cls}"/>
      <circle cx="${px}" cy="${py}" r="${item.selected ? 7 : 5}" class="svg-point ${cls}"/><title>${esc(item.name)}: ${item.gb} GiB; ${scoreLabel}</title>
      ${svgText(Math.min(px + 10, width - right + 5), py + 3, scoreLabel, `class="svg-score-label ${cls}"`)}`;
  }).join("");
  const points = renderRows(reasoning, 82, 40, "reasoning") + renderRows(audit, 245, 29, "audit");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>
    .svg-grid{stroke:#e6e2db;stroke-width:1}.svg-tick{font-size:9px;fill:#8a8580}.panel-title{font-size:9px;fill:#504945;font-weight:800;letter-spacing:1px}.panel-note{font-size:8px;fill:#8a8580}.svg-row-label{font-size:8.5px;fill:#3c3836}.lollipop-line{stroke:#9dbcac;stroke-width:2}.lollipop-line.audit{stroke:#9dbcd5}.lollipop-line.muted{stroke:#cec8be}.lollipop-line.selected{stroke:#af3a03}.svg-point{fill:#427b58;stroke:#ffffff;stroke-width:2}.svg-point.audit{fill:#1b6ca8}.svg-point.selected{fill:#af3a03;stroke:#ffffff}.svg-point.muted{fill:#aaa49d}.svg-score-label{font-size:8px;fill:#427b58}.svg-score-label.audit{fill:#1b6ca8}.svg-score-label.selected{fill:#af3a03;font-weight:800}.svg-score-label.muted{fill:#aaa49d}
  </style>${grid}${svgText(0, 20, "REASONING STUDY", 'class="panel-title"')}${svgText(0, 34, "Four-task mean; development host", 'class="panel-note"')}${svgText(0, 196, "AUDIT CANDIDATES", 'class="panel-title"')}${svgText(0, 210, "ARC-Easy proxy; separate task and engine regime", 'class="panel-note"')}<line x1="0" y1="180" x2="${width}" y2="180" class="svg-grid"/>${points}</svg>`;
}

function renderStreamingChart() {
  const el = $("streaming-chart");
  const width = 430, height = 280, left = 48, right = 20, top = 20, bottom = 42;
  const x = (rss) => left + rss / 2300 * (width - left - right);
  const y = (tps) => top + (20 - tps) / 12 * (height - top - bottom);
  let grid = "";
  [0, 500, 1000, 1500, 2000].forEach((tick) => { const px=x(tick); grid += `<line x1="${px}" y1="${top}" x2="${px}" y2="${height-bottom}" class="svg-grid"/>${svgText(px,height-18,tick,'text-anchor="middle" class="svg-tick"')}`; });
  [10, 15, 20].forEach((tick) => { const py=y(tick); grid += `<line x1="${left}" y1="${py}" x2="${width-right}" y2="${py}" class="svg-grid ${tick===15?'target':''}"/>${svgText(left-7,py+3,tick,'text-anchor="end" class="svg-tick"')}`; });
  const path = REPORT_STREAMING.map((d,i)=>`${i?'L':'M'} ${x(d.rss)} ${y(d.tps)}`).join(" ");
  const points = REPORT_STREAMING.map((d,i)=>`<circle cx="${x(d.rss)}" cy="${y(d.tps)}" r="5" class="svg-stream-point"/><title>${esc(d.name)}: ${d.tps} tok/s at ${d.rss} MiB</title>${svgText(x(d.rss)+(i===4?-4:6),y(d.tps)+(i===4?16:-8),d.name,`text-anchor="${i===4?'end':'start'}" class="svg-point-label"`)}`).join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>
    .svg-grid{stroke:#e6e2db}.svg-grid.target{stroke:#b57614;stroke-dasharray:4 4}.svg-tick{font-size:8px;fill:#8a8580}.svg-path{fill:none;stroke:#427b58;stroke-width:2}.svg-stream-point{fill:#427b58;stroke:#ffffff;stroke-width:2}.svg-point-label{font-size:7.5px;fill:#504945}
  </style>${grid}<path d="${path}" class="svg-path"/>${points}${svgText(width/2,height-2,"Peak RSS (MiB)",'text-anchor="middle" class="svg-axis"')}</svg>`;
}

function renderOfficialCharts() {
  const scoreEl = $("official-score-chart");
  const width = 360, height = 330, left = 116, right = 28, top = 25, rowH = 67;
  const plotW = width - left - right;
  const rows = REPORT_OFFICIAL.map((item, i) => {
    const y = top + i * rowH;
    const a = item.sAcc * .5 / 80 * plotW, p = item.sPerf * .3 / 80 * plotW, e = item.sEff * .2 / 80 * plotW;
    return `${svgText(left-7,y+15,item.name,'text-anchor="end" class="svg-label"')}<rect x="${left}" y="${y}" width="${a}" height="20" class="seg acc"/><rect x="${left+a}" y="${y}" width="${p}" height="20" class="seg perf"/><rect x="${left+a+p}" y="${y}" width="${e}" height="20" class="seg eff"/>${svgText(left+(item.total/80*plotW)+5,y+15,item.total.toFixed(2),'class="svg-total"')}`;
  }).join("");
  scoreEl.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>.svg-label{font-size:8px;fill:#504945}.seg.acc{fill:#1b6ca8}.seg.perf{fill:#427b58}.seg.eff{fill:#b57614}.svg-total{font-size:9px;fill:#282828;font-weight:800}.legend{font-size:8px;fill:#6b6866}</style>${rows}<rect x="${left}" y="${height-35}" width="8" height="8" class="seg acc"/>${svgText(left+12,height-28,"Accuracy",'class="legend"')}<rect x="${left+65}" y="${height-35}" width="8" height="8" class="seg perf"/>${svgText(left+77,height-28,"Performance",'class="legend"')}<rect x="${left+145}" y="${height-35}" width="8" height="8" class="seg eff"/>${svgText(left+157,height-28,"Efficiency",'class="legend"')}</svg>`;

  const scatterEl = $("official-scatter-chart");
  const sw=360, sh=330, sl=46, sr=20, st=25, sb=48;
  const sx=(rss)=>sl+(rss-500)/2400*(sw-sl-sr), sy=(tps)=>st+(11-tps)/11*(sh-st-sb);
  let grid="";
  [500,1000,1500,2000,2500].forEach(t=>{const px=sx(t);grid+=`<line x1="${px}" y1="${st}" x2="${px}" y2="${sh-sb}" class="svg-grid"/>${svgText(px,sh-25,t,'text-anchor="middle" class="svg-tick"')}`});
  [0,5,10].forEach(t=>{const py=sy(t);grid+=`<line x1="${sl}" y1="${py}" x2="${sw-sr}" y2="${py}" class="svg-grid"/>${svgText(sl-6,py+3,t,'text-anchor="end" class="svg-tick"')}`});
  const labelOffsets = [
    { dx: 7, dy: 18, anchor: "start" },
    { dx: 7, dy: -9, anchor: "start" },
    { dx: -7, dy: -9, anchor: "end" },
    { dx: -7, dy: 17, anchor: "end" },
  ];
  const pts=REPORT_OFFICIAL.map((d,i)=>{const label=labelOffsets[i];return `<circle cx="${sx(d.rss)}" cy="${sy(d.tps)}" r="${4+d.acc/25}" class="scatter-point ${i===0?'selected':''}"/><title>${esc(d.name)}: ${d.tps} tok/s, ${d.rss.toFixed(0)} MiB, ${d.acc}% ARC-Easy</title>${svgText(sx(d.rss)+label.dx,sy(d.tps)+label.dy,d.name,`text-anchor="${label.anchor}" class="scatter-label ${i===0?'selected':''}"`)}`}).join("");
  scatterEl.innerHTML=`<svg viewBox="0 0 ${sw} ${sh}" aria-hidden="true"><style>.svg-grid{stroke:#e6e2db}.svg-tick{font-size:8px;fill:#8a8580}.scatter-point{fill:#9dbcd5;fill-opacity:.9;stroke:#fff;stroke-width:2}.scatter-point.selected{fill:#af3a03}.scatter-label{font-size:7.5px;fill:#6b6866}.scatter-label.selected{fill:#af3a03;font-weight:800}</style>${grid}${pts}${svgText(sw/2,sh-3,"Peak RSS (MiB)",'text-anchor="middle" class="svg-axis"')}</svg>`;
}

function updateStreamingBudget() {
  const tps = Number($("streaming-tps").value);
  const bandwidth = Number($("streaming-bandwidth").value);
  const interval = 1000 / tps;
  const slack = Math.max(0, interval - 48);
  const mb = slack / 1000 * bandwidth * 1000;
  $("streaming-tps-value").value = tps.toFixed(1).replace(".0", "");
  $("streaming-bandwidth-value").value = bandwidth.toFixed(2);
  $("streaming-interval").textContent = `${interval.toFixed(1)} ms`;
  $("streaming-slack").textContent = `${slack.toFixed(1)} ms`;
  $("streaming-budget").textContent = `${mb.toFixed(0)} MB/token`;
  $("streaming-share").textContent = `${(mb / 2200 * 100).toFixed(1)}%`;
}

function renderLedger(filter) {
  const rows = EXPERIMENTS.filter((item) => filter === "all" || item.status === filter);
  $("experiment-ledger").innerHTML = rows.map((item) => `<article class="ledger-entry"><span class="ledger-status ${item.status}">${item.status === "neutral" ? "No clear gain" : esc(item.status)}</span><h3>${esc(item.name)}</h3><p>${esc(item.finding)}</p><span class="ledger-source">${esc(item.source)}</span></article>`).join("");
}

function renderFaq() {
  $("faq-list").innerHTML = CHALLENGE_FAQ.map((item, i) => `<details class="faq-item"><summary><span class="faq-number">${String(i + 1).padStart(2, "0")}</span><span class="faq-question">${esc(item.q)}</span></summary><div class="faq-body"><div><h4>Challenge rule</h4><p>${esc(item.rule)}</p></div><div><h4>Muta progress</h4>${item.progress ? `<p>${esc(item.progress)}</p>` : '<div class="empty-progress" aria-label="No Muta progress recorded"></div>'}</div></div></details>`).join("");
}

function renderSensitivity(campaign) {
  if (!campaign || !$("sensitivity-floor")) return;
  const allowed = campaign.tps_max_sensitivity || [];
  const index = Math.max(0, Math.min(allowed.length - 1, Math.round(Number($("sensitivity-floor").value))));
  const floor = allowed[index] || 15;
  $("sensitivity-floor").value = index;
  $("sensitivity-floor-value").value = floor;
  const lookup = (mapping) => mapping && (mapping[String(floor)] || mapping[Number(floor).toFixed(1)]);
  const models = (campaign.models || []).map((model) => ({ model, score: lookup(model.scores) })).filter((entry) => entry.score).sort((a,b)=>b.score.s_total-a.score.s_total);
  const winner = lookup(campaign.winners);
  $("sensitivity-winner").textContent = winner ? shortName(winner.model) : "No result at this floor";
  $("sensitivity-winner-score").textContent = winner ? `S = ${Number(winner.s_total).toFixed(2)}` : "";
  const el = $("sensitivity-chart");
  const width=700, left=190, right=42, rowH=30, height=Math.max(130,models.length*rowH+35), plotW=width-left-right;
  const rows=models.map((entry,i)=>{const y=8+i*rowH, w=Math.min(100,entry.score.s_total)/100*plotW;return `${svgText(left-8,y+13,shortName(entry.model.model),'text-anchor="end" class="sens-label"')}<rect x="${left}" y="${y}" width="${w}" height="17" rx="2" class="sens-bar ${i===0?'winner':''}"/>${svgText(left+w+6,y+13,Number(entry.score.s_total).toFixed(2),'class="sens-value"')}`}).join("");
  el.innerHTML=`<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>.sens-label{font-size:8px;fill:#6b6866}.sens-bar{fill:#d3bdca}.sens-bar.winner{fill:#8f3f71}.sens-value{font-size:8px;fill:#504945;font-weight:700}</style>${rows}</svg>`;
  $("sensitivity-chart-summary").textContent = models.length
    ? `At a ${floor} token-per-second cohort floor: ` + models.map((entry) =>
      `${shortName(entry.model.model)} scores ${Number(entry.score.s_total).toFixed(2)}`).join("; ") + "."
    : `No website-relative model scores are available at a ${floor} token-per-second cohort floor.`;
}

function updateReadingProgress() {
  const root = document.documentElement;
  const max = root.scrollHeight - root.clientHeight;
  $("reading-progress").style.width = `${max > 0 ? Math.min(100, scrollY / max * 100) : 0}%`;
}

function updateActiveChapter() {
  const links = [...document.querySelectorAll(".contents a")];
  const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
  let active = sections[0];
  for (const section of sections) if (section.getBoundingClientRect().top <= 140) active = section;
  links.forEach((link) => link.classList.toggle("active", active && link.getAttribute("href") === `#${active.id}`));
}

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
  renderIsaComparison(d.campaign_avx2_score);
  renderCampaignSnapshotWarning(d.campaign);
  renderTpsRef(d);
  renderRunCard(d);
  renderChart(d);
  renderTable(d);
  renderSensitivity(d.campaign_alternative);
}

function renderCampaign(campaign, prefix) {
  const sub = $(`${prefix}-sub`);
  const table = $(`${prefix}-table`);
  const formula = $(`${prefix}-formula`);
  if (!campaign) {
    sub.textContent = "No campaign summary is available at the configured path.";
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
  const hasFirstToken = models.some((model) => model.first_token_latency_ms != null);
  const rssLabel = isOfficialFullRun
    ? "Profiler peak RSS"
    : models.some((model) => model.rss_estimated)
      ? "Est. profiler RSS mean ± SD"
      : "Profiler peak RSS mean ± SD";
  sub.textContent = `${campaign.hardware_context || "unknown host"} · ` +
    `${models.length} exact GGUF artifact${models.length === 1 ? "" : "s"} · binary SHA-256 ${String(campaign.benchmark_binary_sha256 || "unknown").slice(0, 12)}…`;
  const scoreHeads = denominators.map((d) =>
    `<th>Total @ ${isWebsiteAlternative ? "cohort floor" : "profiler ref"} ${esc(d)}</th>`
  ).join("");
  const head = `<thead><tr><th>Exact model</th><th>Size</th><th>${throughputLabel}</th>` +
    `${hasFirstToken ? "<th>First token</th>" : ""}<th>${rssLabel}</th><th>Accuracy proxies</th>` +
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
      return `${esc(task)} proxy: ${fmt.num(result.score_percent, 1)}% (n=${esc(result.samples)})${interval}`;
    }).join("<br>");
    const sampleLabel = m.measurement_tier === "official_profiler_full_run"
      ? `${esc(m.throughput_rounds)} full profiler run · ${esc(m.throughput_repetitions)} internal benchmark samples`
      : `${esc(m.throughput_rounds)} interleaved round${m.throughput_rounds === 1 ? "" : "s"} · ${esc(m.throughput_repetitions)} timed sample${m.throughput_repetitions === 1 ? "" : "s"}`;
    const throughputCell = isOfficialFullRun
      ? fmt.num(m.tg_tps_mean, 2)
      : `${fmt.num(m.tg_tps_mean, 2)} ± ${fmt.num(m.tg_tps_sd, 2)}`;
    const rssCell = isOfficialFullRun
      ? fmt.mb(m.peak_rss_mib_mean)
      : `${fmt.mb(m.peak_rss_mib_mean)} ± ${fmt.mb(m.peak_rss_mib_sd)}`;
    return `<tr><td><div class="model-name">${esc(shortName(m.model))}</div>` +
      `<div class="model-sub mono">SHA-256 ${esc(String(m.model_sha256 || "unknown").slice(0, 16))}… · ${esc(m.measurement_tier || "unlabelled")} · ${sampleLabel}</div></td>` +
      `<td>${fmt.gb(m.model_bytes)}</td>` +
      `<td>${throughputCell}</td>` +
      `${hasFirstToken ? `<td>${m.first_token_latency_ms == null ? "—" : `${fmt.num(m.first_token_latency_ms / 1000, 2)} s`}</td>` : ""}` +
      `<td>${rssCell}</td>` +
      `<td>${accuracyEntries || "Not measured"}</td>` +
      scoreCells + `</tr>`;
  }).join("");
  table.innerHTML = head + `<tbody>${rows}</tbody>`;
  const winnerText = denominators.map((d) => {
    const winner = lookupDenominator(campaign.winners, d);
    return winner ? `${d}→${shortName(winner.model)} (${fmt.num(winner.s_total, 2)})` : null;
  }).filter(Boolean).join(" · ");
  const evidenceSummary = isOfficialFullRun
    ? "Direct official-profiler evidence. The executable fixes the performance reference at 15 tok/s"
    : isWebsiteAlternative
      ? "Website-relative sensitivity only. AVX2 deployment measurements are rescored with the public cohort formula; each candidate is included in its effective denominator"
      : "Profiler-parity estimate under the no-AVX audit kernel";
  formula.textContent = `${evidenceSummary}. ${sentenceCase(campaign.accuracy_notice)}. ` +
    `${sentenceCase(campaign.rss_notice)}. ${sentenceCase(campaign.thermal_notice)}.` + (winnerText
      ? ` Highest score by ${isWebsiteAlternative ? "website-relative floor" : "profiler reference"}: ${winnerText}.`
      : "");
}

function renderIsaComparison(comparison) {
  const chart = $("isa-score-chart");
  const summary = $("isa-score-summary");
  const sub = $("campaign-avx2-score-sub");
  const table = $("campaign-avx2-score-table");
  const formula = $("campaign-avx2-score-formula");
  if (!comparison || !Array.isArray(comparison.models)) {
    if (chart) chart.innerHTML = '<p class="chart-empty">The paired ISA comparison is unavailable.</p>';
    if (summary) summary.textContent = "The paired ISA comparison is unavailable.";
    if (sub) sub.textContent = "No AVX2 score-of-record artifact is available at the configured path.";
    if (table) table.innerHTML = "";
    if (formula) formula.textContent = "";
    return;
  }

  const label = (file) => ({
    "muta-tutor-qwen3-1.7b-q4_0.gguf": "Q4_0 tied",
    "Q4_K_M-tied.gguf": "Q4_K_M tied",
    "Q5_K_M-tied.gguf": "Q5_K_M tied",
    "IQ4_XS-tied.gguf": "IQ4_XS tied",
    "bitcpm4-8b-tq2_0-envocab.gguf": "BitCPM TQ2_0",
  }[file] || shortName(file));
  const models = [...comparison.models];
  const scalarWinner = comparison.winners && comparison.winners.scalar || {};
  const avx2Winner = comparison.winners && comparison.winners.avx2 || {};

  if (chart) {
    const width = 820, left = 174, right = 54, top = 40, groupH = 64, barH = 17;
    const height = top + models.length * groupH + 38;
    const plotW = width - left - right;
    const x = (score) => left + Number(score) / 85 * plotW;
    let grid = "";
    [0, 20, 40, 60, 80].forEach((tick) => {
      const px = x(tick);
      grid += `<line x1="${px}" y1="${top - 12}" x2="${px}" y2="${height - 34}" class="isa-grid"/>` +
        svgText(px, height - 14, tick, 'text-anchor="middle" class="isa-tick"');
    });
    const rows = models.map((item, index) => {
      const y = top + index * groupH;
      const scalar = Number(item.scalar.score.s_total);
      const avx2 = Number(item.avx2.score.s_total);
      const scalarIsWinner = item.model === scalarWinner.model;
      const avx2IsWinner = item.model === avx2Winner.model;
      return `${svgText(left - 12, y + 25, label(item.model), 'text-anchor="end" class="isa-model"')}
        <rect x="${left}" y="${y}" width="${x(scalar) - left}" height="${barH}" rx="2" class="isa-bar scalar ${scalarIsWinner ? "winner" : ""}"/>
        ${svgText(x(scalar) - 6, y + 12, scalar.toFixed(4), 'text-anchor="end" class="isa-total"')}
        <rect x="${left}" y="${y + 22}" width="${x(avx2) - left}" height="${barH}" rx="2" class="isa-bar avx2 ${avx2IsWinner ? "winner" : ""}"/>
        ${svgText(x(avx2) - 6, y + 34, avx2.toFixed(4), 'text-anchor="end" class="isa-total"')}
        ${scalarIsWinner ? svgText(x(scalar) + 7, y + 12, "highest scalar total", 'class="isa-winner-label"') : ""}
        ${avx2IsWinner ? svgText(x(avx2) + 7, y + 34, "highest AVX2 total", 'class="isa-winner-label"') : ""}`;
    }).join("");
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>
      .isa-grid{stroke:#e6e2db;stroke-width:1}.isa-tick{font-size:9px;fill:#8a8580}.isa-model{font-size:10px;fill:#3c3836}.isa-bar.scalar{fill:#b57614}.isa-bar.avx2{fill:#31714f}.isa-bar.winner{stroke:#282828;stroke-width:2}.isa-total{font-size:8.5px;fill:#fff;font-weight:700}.isa-winner-label{font-size:8px;fill:#282828;font-weight:700}
    </style>${grid}${rows}${svgText(left + plotW / 2, height - 1, "Capped-15 total score", 'text-anchor="middle" class="svg-axis"')}</svg>`;
  }
  if (summary) {
    summary.textContent = models.map((item) =>
      `${label(item.model)}: scalar ${item.scalar.score.s_total.toFixed(4)}, portable AVX2 ${item.avx2.score.s_total.toFixed(4)}`
    ).join("; ") + `. Highest scalar total: ${label(scalarWinner.model)}. Highest AVX2 total: ${label(avx2Winner.model)}.`;
  }

  if (sub && table && formula) {
    const ranked = [...models].sort((a, b) => b.avx2.score.s_total - a.avx2.score.s_total);
    sub.textContent = `${comparison.hardware_contexts.avx2} · ${ranked.length} exact GGUF artifacts · AVX2 binary SHA-256 ${String(comparison.avx2_binary_sha256).slice(0, 12)}…`;
    table.innerHTML = `<thead><tr><th>Exact model</th><th>Scalar total</th><th>AVX2 total</th><th>Scalar → AVX2 tg128</th><th>Scalar → AVX2 est. RSS</th><th>Accuracy proxy</th></tr></thead><tbody>` +
      ranked.map((item) => `<tr class="${item.model === avx2Winner.model ? "avx2-winner-row" : ""}"><td><div class="model-name">${esc(label(item.model))}</div><div class="model-sub mono">SHA-256 ${esc(item.model_sha256.slice(0, 16))}…</div></td><td>${fmt.num(item.scalar.score.s_total, 4)}</td><td class="total">${fmt.num(item.avx2.score.s_total, 4)}</td><td>${fmt.num(item.scalar.tg128_tps, 4)} → ${fmt.num(item.avx2.tg128_tps, 4)}</td><td>${fmt.num(item.scalar.estimated_profiler_rss_mib, 1)} → ${fmt.num(item.avx2.estimated_profiler_rss_mib, 1)} MiB</td><td>${fmt.num(item.accuracy_proxy, 0)}% ARC-Easy</td></tr>`).join("") +
      `</tbody>`;
    formula.textContent = `Controlled paired evidence · S_perf = 100 × min(TPS / 15, 1) · estimated profiler RSS = measured child tree + 45 MiB root allowance · thermal unknown. Highest scalar total: ${label(scalarWinner.model)} (${fmt.num(scalarWinner.s_total, 4)}). Highest portable AVX2 total: ${label(avx2Winner.model)} (${fmt.num(avx2Winner.s_total, 4)}).`;
  }
}

function renderCampaignSnapshotWarning(campaign) {
  const warning = $("campaign-override-warning");
  if (!warning) return;
  const close = (left, right) => Math.abs(Number(left) - Number(right)) < 0.0001;
  const loadedModels = campaign && campaign.models || [];
  const modelsMatch = loadedModels.length === REPORT_OFFICIAL.length && REPORT_OFFICIAL.every((expected) => {
    const loaded = loadedModels.find((model) => model.model === expected.file);
    const total = loaded && loaded.scores && (loaded.scores["15.0"] || loaded.scores["15"]);
    const accuracy = loaded && loaded.accuracy_tasks && loaded.accuracy_tasks.arc_easy;
    const ci = accuracy && accuracy.ci95_percent || [];
    return !!loaded && loaded.model_sha256 === expected.sha && loaded.model_bytes === expected.bytes &&
      close(loaded.first_token_latency_ms, expected.ttft) && close(loaded.tg_tps_mean, expected.tps) &&
      close(loaded.peak_rss_mib_mean, expected.rss) && close(loaded.accuracy_proxy, expected.acc) &&
      loaded.accuracy_samples === 50 && loaded.measurement_tier === "official_profiler_full_run" &&
      loaded.throughput_rounds === 1 && loaded.throughput_repetitions === 5 &&
      ci.length === 2 && close(ci[0], expected.ci[0]) && close(ci[1], expected.ci[1]) &&
      !!total && close(total.s_acc, expected.sAcc) && close(total.s_perf, expected.sPerf) &&
      close(total.s_eff, expected.sEff) && close(total.s_total, expected.total) &&
      close(total.thermal_penalty, 0) && total.disqualified === false;
  });
  warning.hidden = !!(campaign &&
    campaign.benchmark_binary_sha256 === "7f01dc0465d64f726b2b66139859a8ff1ca204f4901e18b71ddfa678dea19370" &&
    campaign.hardware_context === "official_profiler_participant_gcp_n2_custom_4_8192_2c4t" &&
    campaign.evidence_tier === "official_profiler_full_run" &&
    campaign.performance_formula === "S_perf = min(TPS / 15, 1) * 100 (official profiler)" &&
    Array.isArray(campaign.tps_max_sensitivity) && campaign.tps_max_sensitivity.length === 1 &&
    close(campaign.tps_max_sensitivity[0], 15) &&
    modelsMatch);
}

function renderTpsRef(d) {
  const sc = d.scoring || {};
  const el = $("tps-ref");
  if (!el) return;
  if (sc.tps_reference == null) {
    el.textContent = "TPS_max = fastest stored run; the archive has no measured run yet";
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
  if (m.african_alpha_claim) claims.push("African-use-case metadata claim");
  if (m.budget_laptop_claim) claims.push("budget-laptop metadata claim");
  $("meta-line").textContent =
    `${m.team_id || "?"} · ${m.domain || "?"}` +
    (claims.length ? ` · ${claims.join(" · ")}` : "") +
    (m.current_model_path ? ` · selected path: ${m.current_model_path}` : "");
  const pill = $("status-pill");
  if (d.current) {
    pill.classList.add("busy");
    pill.textContent = `Profiling ${shortName(d.current.model_file)}`;
  } else {
    pill.classList.remove("busy");
    pill.textContent = "Profiler idle";
  }
}

function renderRunCard(d) {
  const card = $("run-card");
  if (!d.current) { card.hidden = true; return; }
  card.hidden = false;
  $("run-title").textContent = `Profiling ${d.current.model_file}`;
  $("run-sub").textContent = d.current.skip_accuracy
    ? "Diagnostic run · --skip-accuracy · no accuracy or total score will be produced"
    : "Full run · 50 ARC-Easy proxy items · leave this page open for live logs";
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
    el.innerHTML = `<p class="chart-empty">The archive has no fully scored runs. A diagnostic run skips accuracy and therefore cannot produce a total score.</p>`;
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
    if (!run.throttled && !(s.thermal_penalty > 0)) {
      chips.push(run.temp_c == null
        ? chip("neutral", "temperature unknown")
        : chip("good", "no penalty"));
    }
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
  if (african) out.push(chip("neutral", "use-case claim"));
  if (budget) out.push(chip("neutral", "budget target"));
  return out.length ? out.join("") : `<span class="dim">—</span>`;
}

function shortName(file) { return file.replace(/\.gguf$/i, ""); }

function renderTable(d) {
  const busy = !!d.current;
  const present = d.models.filter((m) => m.present).length;
  const gone = d.models.length - present;
  $("models-sub").textContent =
    `${present} GGUF file${present === 1 ? "" : "s"} in model/` +
    (gone ? ` · ${gone} removed artifact${gone === 1 ? "" : "s"} with retained run records` : "") +
    ` · the latest run appears below; open History for the complete record`;
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
      : ["artifact removed; run records retained", m.quant, m.params];
    const sub = info.filter(Boolean).join(" · ") +
      (m.runs_count
        ? ` · ${m.runs_count} run${m.runs_count === 1 ? "" : "s"} · last ${fmt.when(r && (r.finished_at || r.started_at))}`
        : " · no stored run");
    const arc = r && r.arc_score != null ? `${r.arc_score.toFixed(3)}` : "—";
    const main = `<tr class="model-row" data-model="${esc(m.file)}">
      <td>
        <div class="model-name${m.present ? "" : " dim"}">${esc(shortName(m.file))}</div>
        <div class="model-sub">${esc(sub)}</div>
        <div class="model-actions">
          <button class="btn primary small" data-action="profile" data-model="${esc(m.file)}"
            ${busy || !m.present ? "disabled" : ""}>${running ? "Running…" : "Start profile"}</button>
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
        <button class="btn small" data-action="json" data-id="${r.id}">Raw report</button>
        <button class="btn small" data-action="promote" data-id="${r.id}"
          ${r.status === "ok" && !gone ? "" : "disabled"}
          ${gone ? 'title="The model artifact is no longer present and cannot be promoted"' : ""}>Set as submission</button>
        <button class="btn small danger" data-action="delete" data-id="${r.id}">Delete record</button>
      </td>
    </tr>`;
  }).join("");
  return `<tr class="history-row"><td colspan="12">
    <table class="history">
      <thead><tr><th>Run</th><th>Mode</th><th>Status</th><th>S_total</th><th>S_acc</th><th>S_perf</th>
      <th>S_eff</th><th>tok/s</th><th>Peak RAM</th><th>Actions</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="10" class="dim">No completed run records</td></tr>`}</tbody>
    </table>
  </td></tr>`;
}

function openModal(returnFocus) {
  state.modalReturnFocus = returnFocus || document.activeElement;
  $("modal").hidden = false;
  $("modal").querySelector('[data-action="modal-close"]').focus();
}

function closeModal() {
  if ($("modal").hidden) return;
  $("modal").hidden = true;
  if (state.modalReturnFocus && document.contains(state.modalReturnFocus)) {
    state.modalReturnFocus.focus();
  }
  state.modalReturnFocus = null;
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
    if (!res.ok) alert((await res.json()).error || "The profiler could not start this run.");
    poll();
  } else if (action === "cancel") {
    if (confirm("Cancel the active profiling run? Its partial output will not become a scored result.")) {
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
      : `Error: ${d.error || "Unknown error"}\nExit code: ${d.exit_code}\n\n--- Profiler log ---\n${d.log_tail || "No log output"}`;
    openModal(btn);
  } else if (action === "promote") {
    if (confirm("Set this completed run as the submission candidate? This replaces metadata.json and submission.json at the repository root.")) {
      const res = await fetch(`/api/runs/${btn.dataset.id}/promote`, { method: "POST" });
      if (!res.ok) alert((await res.json()).error || "The run could not be set as the submission candidate.");
      poll();
    }
  } else if (action === "delete") {
    if (confirm("Delete this run record from the local dashboard database? This cannot be undone.")) {
      await fetch("/api/runs/" + btn.dataset.id, { method: "DELETE" });
      poll();
    }
  } else if (action === "modal-close") {
    closeModal();
  }
});

$("modal").addEventListener("click", (ev) => {
  if (ev.target === $("modal")) closeModal();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !$("modal").hidden) {
    closeModal();
    return;
  }
  if (ev.key === "Tab" && !$("modal").hidden) {
    const focusable = [...$("modal").querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
      .filter((element) => !element.disabled && element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  }
});

$("quick-toggle").addEventListener("change", (ev) => { state.quick = ev.target.checked; });

for (const id of ["score-accuracy", "score-tps", "score-ram", "score-thermal"]) {
  $(id).addEventListener("input", renderScoreLab);
}
for (const id of ["streaming-tps", "streaming-bandwidth"]) {
  $(id).addEventListener("input", updateStreamingBudget);
}
$("sensitivity-floor").addEventListener("input", () => renderSensitivity(state.data && state.data.campaign_alternative));
document.addEventListener("click", (ev) => {
  const filter = ev.target.closest && ev.target.closest("[data-ledger-filter]");
  if (!filter) return;
  document.querySelectorAll("[data-ledger-filter]").forEach((button) => {
    const active = button === filter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderLedger(filter.dataset.ledgerFilter);
});
addEventListener("scroll", () => { updateReadingProgress(); updateActiveChapter(); }, { passive: true });
addEventListener("resize", updateReadingProgress);

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
      <span>archive run</span><b>#${r.id} · ${fmt.when(r.finished_at)}</b>
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

initReport();
poll();
