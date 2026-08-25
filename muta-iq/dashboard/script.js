"use strict";

// Published-snapshot mode. build_static.py stamps <html data-snapshot="api/state.json"> when it
// renders the report for static hosting (GitHub Pages). With no app.py behind the page, it
// fetches that pre-rendered /api/state payload once — relatively, so a /<repo>/ project-page
// prefix works — keeps every read-only view, and disables the profiler's mutating controls.
const SNAPSHOT_URL = document.documentElement.dataset.snapshot || "";
const STATIC = SNAPSHOT_URL !== "";

const state = {
  data: null,
  quick: false,
  expanded: new Set(),      // model files with history open
  runsCache: {},            // model file -> runs[]
  pollAt: 0,                // Date.now() of last successful poll
  timer: null,
  modalReturnFocus: null,
  hashRestored: false,
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

const REPORT_CURRENT_OFFICIAL = [
  { name: "Math-Expert 0.6B Q4_K_M", file: "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf", sha: "7f64c2e3bbd5c6fa570f49631cad5527ebd4acd7fcaf014963152027b2dae9a1", bytes: 396706176, ttft: 23613.51, tps: 12.72, rss: 540.32, acc: 68, ci: [54.19, 79.24], sAcc: 68, sPerf: 84.8, sEff: 92.4621, total: 77.9324 },
  { name: "Qwen3.5 0.8B Q4_0 final", file: "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf", sha: "c96df4ef6d9416bea6a35866751cb6cf02e20ec6ce28b20980d66c90604d5d7b", bytes: 507156160, ttft: 16622.38, tps: 12.63, rss: 670.39, acc: 64, ci: [50.14, 75.86], sAcc: 64, sPerf: 84.2, sEff: 90.6475, total: 75.3895 },
  ...REPORT_OFFICIAL,
];

const REPORT_RUNTIME = [
  { name: "Docker baseline", tps: 5.3, memory: "4.77 GB, still rising" },
  { name: "Resource caps", tps: 6.72, memory: "4.44 GB" },
  { name: "Native default", tps: 29.78, memory: "3,519 MiB footprint" },
  { name: "6 threads + unified KV", tps: 31.09, memory: "3,137 MiB footprint" },
  { name: "Draft speculation", tps: 24.72, memory: "host RAM not reliable" },
];

const REPORT_FUNNEL = [
  { name: "Qwen3.5 4B", gb: 2.55, acc: 73.3, lane: "reasoning" },
  { name: "Qwen3.5 2B", gb: 1.19, acc: 64.8, lane: "reasoning" },
  { name: "Qwen3.5 0.8B", gb: 0.50, acc: 51.3, lane: "reasoning" },
  { name: "Qwen3.5 0.8B Q4_0 final", gb: 0.47, acc: 64, lane: "audit" },
  { name: "Fine-tuned Qwen3.5 0.8B", gb: 0.48, acc: 70.2, lane: "audit", selected: true },
  { name: "Fine-tuned Qwen2.5 1.5B", gb: 0.92, acc: 77.8, lane: "audit", leader: true },
  { name: "Math-Expert 0.6B Q4_K_M", gb: 0.37, acc: 68, lane: "audit", leader: true },
  { name: "Qwen3 1.7B Q4_0", gb: 0.91, acc: 72, lane: "audit" },
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
  { status: "adopted", name: "Concurrency and cache caps", finding: "Two parallel slots, four checkpoints, and a 256 MiB cache stopped memory growth. The early Docker baseline rose from about 5.3 to 6.72 tok/s.", source: "runtime memory study" },
  { status: "adopted", name: "Six-thread runtime", finding: "Six batch and decode threads reached 31.09 tok/s, 83% of the estimated weight-bandwidth limit. Ten threads reduced decode throughput to approximately 4.4 tok/s.", source: "runtime thread sweep" },
  { status: "adopted", name: "Unified KV, two checkpoints", finding: "Unified KV and two checkpoints reduced retained state and improved prefill while holding decode near 31 tok/s on the development host.", source: "runtime memory study" },
  { status: "rejected", name: "0.8B draft speculation", finding: "98.4% proposal acceptance still slowed native decode from 30.84 to 24.72 tok/s. We flagged host RAM readings as unreliable, so we do not claim a native memory delta.", source: "speculation study" },
  { status: "neutral", name: "N-gram speculation", finding: "A 12–22% acceptance rate did not offset lookup and verification overhead. The feature is disabled by default and uses no additional model memory.", source: "speculation study" },
  { status: "rejected", name: "More threads", finding: "Throughput stopped increasing once memory bandwidth saturated. Ten threads cut decode throughput to about 4.4 tok/s; we did not measure temperature in this sweep.", source: "runtime thread sweep" },
  { status: "rejected", name: "Disable mmap", finding: "Decode fell by about 28% and memory rose by about 1 GiB. The submitted GGUF cannot change the stock audit’s eager mmap policy.", source: "runtime memory study" },
  { status: "neutral", name: "mlock", finding: "Pinning pages produced no repeatable throughput gain in the tested resident configuration.", source: "runtime memory study" },
  { status: "adopted", name: "No-repack product path", finding: "Avoiding runtime tensor conversion cut a tested 4B footprint from about 3,236 to 602 MiB. The campaign cannot use this engine-only change.", source: "runtime memory study" },
  { status: "adopted", name: "Fixed context budget", finding: "We replaced runtime defaults with explicit context and KV limits, fixing a memory variable for later comparisons.", source: "runtime configuration" },
  { status: "adopted", name: "4B reasoning baseline", finding: "The 4B model exceeded the 2B model by 15.7 points across three STEM tasks. The later audit used a different kernel configuration and a separate accuracy proxy.", source: "model-scale study" },
  { status: "neutral", name: "IQ4_XS importance matrix", finding: "Task scores moved in both directions by roughly one or two items, with no reliable accuracy gain.", source: "quantization study" },
  { status: "adopted", name: "Uniform Qwen quant ladder", finding: "Under vector execution, Q4_K_M recorded the highest total. Q5_K_M gained four ARC-Easy points, but the gain did not repeat on ARC-Challenge or SciQ and throughput was lower.", source: "quantization sweep" },
  { status: "rejected", name: "Mixed embedding and head precision", finding: "Q3_K_M with a Q6_K head fell to 66% ARC-Easy; IQ4_XS with a Q6_K head was slower and larger than uniform IQ4_XS.", source: "quantization sweep" },
  { status: "neutral", name: "Vendor importance matrix", finding: "The Qwen K-quant ladder used the vendor matrix consistently, but its calibration corpus is unpublished. We cannot independently verify dataset disjointness.", source: "quantization sweep" },
  { status: "neutral", name: "Metal offload", finding: "Hybrid 4B decode was neutral to slightly slower than CPU-only on the development Mac. GPU support remains optional.", source: "runtime optimisation study" },
  { status: "deferred", name: "TinyStories TTFT preamble", finding: "A tiny warm-up model produced a 1.65 ms first chunk with a small resident cost, but we had not resolved licensing, so the feature stays off by default.", source: "first-token latency study" },
  { status: "adopted", name: "BitCPM vocabulary pruning", finding: "Pruning 73,448 tokens to 44,416 saved 164 MiB. English tokenisation matched across 20,464 checked tokens and perplexity changed from 10.558 to 10.473.", source: "vocabulary study" },
  { status: "rejected", name: "BitCPM TQ1_0 body", finding: "The file lost 340 MiB, but generic-kernel throughput fell 22%. The evaluator lacked the kernel needed to turn fewer bits into less work.", source: "ternary quantization study" },
  { status: "rejected", name: "Head and embedding requants", finding: "We saved at most 48 MiB, and the largest estimated total-score gain was about 0.14. We did not measure behavioural effects.", source: "mixed-precision study" },
  { status: "rejected", name: "Low-rank factorisation", finding: "Ternary matrices remained full-rank. Rank-2048 factorisation error was about 0.80 before quantisation and exceeded 1 after it.", source: "factorisation study" },
  { status: "rejected", name: "Unstructured sparsity", finding: "Dense GGUF stores the zeros and the stock kernels still multiply them. There was no file or compute saving to score.", source: "sparsity study" },
  { status: "rejected", name: "Single-layer pruning", finding: "One Qwen layer gained about 3.7% speed but lost two ARC-Easy points. The accuracy cost exceeded the performance return.", source: "pruning study" },
  { status: "deferred", name: "Qwen vocabulary pruning", finding: "We have not attempted this: our current tools cannot rewrite the GPT-2 BPE merges coherently. BitCPM’s verified vocabulary prune does not transfer automatically.", source: "vocabulary study" },
  { status: "rejected", name: "Context metadata change", finding: "The profiler fixes prompt length at 512 tokens and generation length at 128 tokens. Context metadata does not change this workload.", source: "context study" },
  { status: "rejected", name: "Custom tensor layout", finding: "We kept the stock quantiser layout. An unsupported alignment or packing scheme could fail to load and disqualify the run.", source: "tensor-layout study" },
  { status: "adopted", name: "Embedded chat template", finding: "The GGUF contains the chat template and tutoring persona, both verified on a live server. They affect evaluator responses but do not affect raw ARC or throughput measurements.", source: "prompt-format study" },
  { status: "rejected", name: "Weight streaming for submission", finding: "Streaming could cut residency to hundreds of MiB, but SSD bandwidth missed the 15 tok/s target and a custom engine cannot accompany a GGUF-only entry.", source: "weight-streaming study" },
  { status: "adopted", name: "Runtime-conditional model choice", finding: "After fine-tuning and matched 500-item evaluation, Qwen3.5 0.8B leads the scalar comparison at 80.3664 and Qwen2.5 1.5B leads the vector comparison at 84.1387. The submission choice still depends on the audit CPU configuration.", source: "fine-tuning campaign" },
  { status: "adopted", name: "Second widening: Qwen2/2.5, Llama 3.2, Gemma 2, Phi-4 Mini, Orca Mini", finding: "Eight matched GGUFs under scalar and vector execution put Qwen2.5 1.5B Q4_K_M first on the vector total at 82.8697 (ARC-Easy-50). A 500-item rerun lowered that to 80.7697 at 71.8% accuracy, still the leading vector candidate.", source: "second model-architecture widening" },
  { status: "adopted", name: "Tied output head", finding: "The final tied-versus-untied control saved about 175 MB of file bytes with the same 72% ARC-Easy proxy.", source: "quantization sweep" },
  { status: "adopted", name: "Reproducible artifact build", finding: "We rebuilt the promoted candidate from its documented source. It matched byte-for-byte once we corrected a 32-byte metadata-name difference.", source: "artifact construction study" },
  { status: "adopted", name: "Direct participant-profiler campaign", finding: "Four models completed full participant runs. The 1.7B Q4_0 total exceeded the initially tested 0.8B Q4_K_M total by 0.92 points.", source: "direct profiler measurements" },
  { status: "adopted", name: "Metric-aligned Qwen3.5 fine-tune", finding: "BF16 LoRA rank 16 on corrected multiple-choice continuations raised ARC-Easy-500 from 55.2% to 70.2%. Matched throughput and RSS were unchanged; total rose by about 7.5 points in both CPU configurations.", source: "fine-tuning campaign" },
  { status: "adopted", name: "Licence-clean Qwen2.5 fine-tune", finding: "BF16 LoRA rank 16 on licence-clean ARC and QASC training rows raised ARC-Easy-500 from 74.4% to 77.8%. The vector total rose from 82.4386 to 84.1387.", source: "fine-tuning campaign" },
  { status: "rejected", name: "Initial LoRA and QLoRA mixtures", finding: "Eight balanced and reasoning-heavy runs improved validation loss but did not improve the exact 500-item profiler task. The mixtures overrepresented long solutions and used the wrong prompt/completion token boundary.", source: "fine-tuning campaign" },
  { status: "adopted", name: "Vector score of record", finding: "The fine-tuned Qwen2.5 1.5B Q4_K_M has the highest measured vector total at matched n=500, 84.1387. The fine-tuned Qwen3.5 0.8B leads the matched scalar total at 80.3664.", source: "fine-tuning campaign" },
  { status: "deferred", name: "QAT or distillation", finding: "QAT and distillation may recover capability in a smaller artifact. Neither has completed a controlled campaign.", source: "future model-development study" },
];

const CHALLENGE_FAQ = [
  { q: "Will evaluation run without internet access?", rule: "Yes. The judging environment is offline.", progress: "The runtime resolves local files first, the promoted GGUF is stored locally, and the tutor has an offline launch path. A clean physical-target rehearsal remains." },
  { q: "How is the final score calculated?", rule: "Accuracy carries 50%, performance 30%, and efficiency 20%, with a thermal penalty and hard-failure rules.", progress: "We implemented and tested the executable formula. This report keeps the public cohort-relative formula in a separate sensitivity lane." },
  { q: "Can teams develop on stronger hardware?", rule: "Yes, but the final artifact is evaluated on the standard laptop profile.", progress: "We developed on an M2 Mac and a GCP x86 proxy. We classify Mac results as development evidence." },
  { q: "Does adding an African language qualify for the use-case bonus?", rule: "Language support alone does not establish the African use case.", progress: "" },
  { q: "What does cross-disciplinary integration require?", rule: "The model must depend substantively on another deep-tech discipline.", progress: "Muta plans to combine scientific tutoring with verified mathematics and local retrieval. Several relevant routes remain incomplete or return 501, so this requirement is not yet satisfied." },
  { q: "Are fine-tuned open models allowed?", rule: "Yes, subject to the competition’s open-model and artifact rules.", progress: "Both current finalists are BF16 LoRA fine-tunes of official Qwen checkpoints. The training code pins source revisions, records dataset manifests, excludes evaluation splits, filters held-out overlap, and exports the merged weights to GGUF." },
  { q: "Which countries are eligible?", rule: "Eligibility follows the organiser’s published country rules.", progress: "" },
  { q: "Can Africans studying abroad enter?", rule: "The FAQ describes the applicable eligibility route.", progress: "" },
  { q: "Is there an age restriction?", rule: "The organiser’s FAQ gives the eligibility condition.", progress: "" },
  { q: "How is the team identified in the artifact?", rule: "Submission metadata must identify the registered team.", progress: "The current metadata uses team ID `team-muta`. Registration details still need a final submission check." },
  { q: "Must the base model be open source?", rule: "The submission must follow the challenge’s open-model requirements.", progress: "Both tuned candidates derive from official Qwen checkpoints with documented source, training data, conversion method, licence, and artifact size." },
  { q: "Which inference formats and tools are allowed?", rule: "The model-only track evaluates GGUF with llama.cpp.", progress: "We measured the submitted GGUFs under matched scalar and vector configurations. Custom streaming and lazy-mmap engines stay out of the scoring claim." },
  { q: "What is the maximum model size?", rule: "The practical limit is the 7 GB memory ceiling on the standard machine.", progress: "The direct campaign spans about 0.50–2.31 GiB peak model footprints, all below the ceiling. Whole-tree RSS remains the unit of record." },
  { q: "Where should the final benchmark be run?", rule: "The organiser evaluates the artifact on its standard hardware; local results are preparatory.", progress: "We have full participant runs on a four-vCPU GCP x86 proxy under the competition procedure. Package temperature and physical-laptop bandwidth remain unmeasured." },
  { q: "What must the Gate 1 submission contain?", rule: "Gate 1 requires the open-source repository and structured report, a working model download path, two test prompts, screenshots or clips, and a 2-minute demo video.", progress: "The repository contains the model metadata, reproducible experiments, runtime, and this report. Final packaging, the two submission prompts, and the video remain incomplete." },
  { q: "What should teams enter as self-reported scores?", rule: "DevPost asks for separate S_perf and S_eff values computed from local profiler telemetry. Teams do not submit S_acc.", progress: "The tuned vector candidates both reach the capped performance score on the GCP proxy. Estimated vector efficiency is 86.48 for Qwen3.5 and 76.19 for Qwen2.5. These are controlled proxy values; the physical-target profiler run remains required." },
  { q: "Is the whole application evaluated, or only the model?", rule: "The model-only evaluation uses the submitted GGUF in the organiser’s runtime.", progress: "We record product improvements separately from model-only evidence. Retrieval, the custom streamer, and UI changes stay out of the GGUF campaign score." },
  { q: "How many prompts are visible before submission?", rule: "The FAQ describes two visible prompts plus hidden tests.", progress: "The local profiler path covers the visible task shape and accuracy proxies. Hidden-prompt performance remains unknown by design." },
  { q: "How is temperature handled?", rule: "Temperature is checked around evaluation and can trigger a 10-point penalty above the threshold or when throttling is detected.", progress: "The GCP host exposed no usable package sensor and reported no throttling. Temperature is recorded as unavailable." },
  { q: "Can the system have an optional online mode?", rule: "The judged path must work offline; optional network features cannot be required.", progress: "We designed Muta’s core runtime, model, retrieval plan, and UI for offline use. Deployment uses local artifacts; network provisioning is only a development fallback." },
  { q: "How should the African use case be demonstrated?", rule: "The use case should solve a concrete African problem; language support is not mandatory.", progress: "The current case is an offline tutor for bandwidth-constrained classrooms and budget laptops. Benchmark evidence alone is insufficient; the product claim still needs classroom evidence." },
  { q: "What should the demo video show?", rule: "The video should demonstrate the working entry under the stated constraints.", progress: "We have not recorded a final video yet." },
];

const svgText = (x, y, value, attrs = "") => `<text x="${x}" y="${y}" ${attrs}>${esc(value)}</text>`;

// Vertical grouped bar chart: one group of compact bars per item, values above each bar,
// rotated item labels along the bottom. Used for every scalar/vector total comparison.
function verticalGroupedChart(items, series, options = {}) {
  const width = options.width || Math.max(620, items.length * 82 + 90);
  const height = options.height || 320;
  const left = options.left || 44, right = options.right || 18;
  const top = options.top || 22, bottom = options.bottom || 90;
  const max = options.max || 100;
  const ticks = options.ticks || [0, 20, 40, 60, 80, 100];
  const plotW = width - left - right, plotH = height - top - bottom;
  const groupW = plotW / items.length;
  const gap = Math.max(2, Math.min(6, groupW * .06));
  const barW = Math.max(7, Math.min(26, (groupW - gap * (series.length + 1)) / series.length));
  const y = (value) => top + (max - Number(value)) / max * plotH;
  const grid = ticks.map((tick) => {
    const py = y(tick);
    return `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}" class="vgc-grid"/>` +
      svgText(left - 7, py + 3, tick, 'text-anchor="end" class="vgc-tick"');
  }).join("");
  const bars = items.map((item, index) => {
    const groupX = left + index * groupW;
    const usedW = series.length * barW + (series.length - 1) * gap;
    const startX = groupX + (groupW - usedW) / 2;
    const mark = series.map((lane, laneIndex) => {
      const value = Number(lane.value(item));
      const px = startX + laneIndex * (barW + gap);
      const py = y(value);
      const winner = lane.winner && lane.winner(item);
      return `<rect x="${px}" y="${py}" width="${barW}" height="${top + plotH - py}" rx="1.5" class="vgc-bar ${lane.className}${winner ? " winner" : ""}"/>` +
        svgText(px + barW / 2, py - 5, options.valueFormat ? options.valueFormat(value) : value.toFixed(1), 'text-anchor="middle" class="vgc-value"');
    }).join("");
    const center = groupX + groupW / 2;
    const labelY = height - bottom + 17;
    return mark + svgText(center, labelY, options.label(item), `text-anchor="end" transform="rotate(-38 ${center} ${labelY})" class="vgc-label"`);
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" data-orientation="vertical" aria-hidden="true"><style>
    .vgc-grid{stroke:#e6e2db;stroke-width:1}.vgc-tick{font-size:9px;fill:#8a8580}.vgc-label{font-size:9px;fill:#3c3836}.vgc-bar.scalar{fill:#b57614}.vgc-bar.avx2{fill:#31714f}.vgc-bar.official,.vgc-bar.tuned{fill:#1b6ca8}.vgc-bar.diagnostic,.vgc-bar.control{fill:#b8afa3}.vgc-bar.throughput{fill:#427b58}.vgc-bar.winner{stroke:#282828;stroke-width:2}.vgc-value{font-size:8px;fill:#504945;font-weight:700}
  </style>${grid}${bars}</svg>`;
}

function initReport() {
  renderRuntimeChart();
  renderModelFunnelChart();
  renderStreamingChart();
  renderOfficialCharts();
  renderLedger("adopted");
  renderFaq();
  updateReadingProgress();
  updateActiveChapter();
}

function renderRuntimeChart() {
  const el = $("runtime-chart");
  const width = 560, height = 340, left = 44, right = 18, top = 22, bottom = 108;
  const plotW = width - left - right, plotH = height - top - bottom;
  const max = 35, ticks = [0, 10, 20, 30];
  const groupW = plotW / REPORT_RUNTIME.length;
  const barW = Math.max(16, Math.min(38, groupW * .5));
  const y = (tps) => top + (max - tps) / max * plotH;
  const grid = ticks.map((tick) => {
    const py = y(tick);
    return `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}" class="vgc-grid"/>` +
      svgText(left - 7, py + 3, tick, 'text-anchor="end" class="vgc-tick"');
  }).join("");
  const bars = REPORT_RUNTIME.map((item, index) => {
    const groupX = left + index * groupW, cx = groupX + groupW / 2;
    const px = cx - barW / 2, py = y(item.tps);
    const labelY = height - bottom + 17;
    return `<rect x="${px}" y="${py}" width="${barW}" height="${top + plotH - py}" rx="1.5" class="vgc-bar throughput"/>
      ${svgText(cx, py - 6, `${item.tps.toFixed(2)} tok/s`, 'text-anchor="middle" class="vgc-value"')}
      ${svgText(cx, labelY, item.name, `text-anchor="end" transform="rotate(-38 ${cx} ${labelY})" class="vgc-label"`)}
      ${svgText(cx, labelY + 30, `Memory: ${item.memory}`, `text-anchor="end" transform="rotate(-38 ${cx} ${labelY + 30})" class="vgc-label muted"`)}`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" data-orientation="vertical" aria-hidden="true"><style>
    .vgc-grid{stroke:#e6e2db;stroke-width:1}.vgc-tick{font-size:9px;fill:#8a8580}.vgc-label{font-size:9px;fill:#3c3836}.vgc-label.muted{fill:#8a8580}.vgc-bar.throughput{fill:#427b58}.vgc-value{font-size:8px;fill:#504945;font-weight:700}
  </style>${grid}${bars}</svg>`;
}

function renderModelFunnelChart() {
  const el = $("model-funnel-chart");
  const reasoning = REPORT_FUNNEL.filter((item) => item.lane === "reasoning");
  const audit = REPORT_FUNNEL.filter((item) => item.lane === "audit");
  const width = 720, height = 265 + audit.length * 31, left = 190, right = 65;
  const x = (gb) => left + gb / 2.8 * (width - left - right);
  let grid = "";
  [0, .5, 1, 1.5, 2, 2.5].forEach((tick) => {
    const px = x(tick);
    grid += `<line x1="${px}" y1="42" x2="${px}" y2="${height - 46}" class="svg-grid"/>${svgText(px, height - 20, `${tick.toFixed(1)} GiB`, 'text-anchor="middle" class="svg-tick"')}`;
  });
  const renderRows = (items, startY, gap, lane) => items.map((item, i) => {
    const py = startY + i * gap, px = x(item.gb);
    const cls = item.selected ? "selected" : item.leader ? "leader" : item.muted ? "muted" : lane;
    const status = item.selected ? " · risk-adjusted" : item.leader ? " · raw leader" : "";
    const scoreLabel = lane === "reasoning" ? `${item.acc.toFixed(1)} four-task mean` : `${item.acc.toFixed(0)}% ARC proxy${status}`;
    return `${svgText(left - 12, py + 3, item.name, 'text-anchor="end" class="svg-row-label"')}
      <line x1="${left}" y1="${py}" x2="${px}" y2="${py}" class="lollipop-line ${cls}"/>
      <circle cx="${px}" cy="${py}" r="${item.selected || item.leader ? 7 : 5}" class="svg-point ${cls}"/><title>${esc(item.name)}: ${item.gb} GiB; ${scoreLabel}</title>
      ${svgText(Math.min(px + 10, width - right + 5), py + 3, scoreLabel, `class="svg-score-label ${cls}"`)}`;
  }).join("");
  const points = renderRows(reasoning, 82, 40, "reasoning") + renderRows(audit, 245, 29, "audit");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>
    .svg-grid{stroke:#e6e2db;stroke-width:1}.svg-tick{font-size:9px;fill:#8a8580}.panel-title{font-size:9px;fill:#504945;font-weight:800;letter-spacing:1px}.panel-note{font-size:8px;fill:#8a8580}.svg-row-label{font-size:8.5px;fill:#3c3836}.lollipop-line{stroke:#9dbcac;stroke-width:2}.lollipop-line.audit{stroke:#9dbcd5}.lollipop-line.muted{stroke:#cec8be}.lollipop-line.selected{stroke:#af3a03}.lollipop-line.leader{stroke:#427b58}.svg-point{fill:#427b58;stroke:#ffffff;stroke-width:2}.svg-point.audit{fill:#1b6ca8}.svg-point.selected{fill:#af3a03;stroke:#ffffff}.svg-point.leader{fill:#427b58;stroke:#282828}.svg-point.muted{fill:#aaa49d}.svg-score-label{font-size:8px;fill:#427b58}.svg-score-label.audit{fill:#1b6ca8}.svg-score-label.selected{fill:#af3a03;font-weight:800}.svg-score-label.leader{fill:#427b58;font-weight:800}.svg-score-label.muted{fill:#aaa49d}
  </style>${grid}${svgText(0, 20, "REASONING STUDY", 'class="panel-title"')}${svgText(0, 34, "Four-task mean; development host", 'class="panel-note"')}${svgText(0, 196, "AUDIT CANDIDATES", 'class="panel-title"')}${svgText(0, 210, "ARC-Easy-50 proxy; separate task and engine regime", 'class="panel-note"')}<line x1="0" y1="180" x2="${width}" y2="180" class="svg-grid"/>${points}</svg>`;
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
  const width = Math.max(420, REPORT_CURRENT_OFFICIAL.length * 78 + 90), height = 360;
  const left = 44, right = 18, top = 26, bottom = 118, legendY = 16;
  const plotW = width - left - right, plotH = height - top - bottom;
  const max = 85, groupW = plotW / REPORT_CURRENT_OFFICIAL.length;
  const barW = Math.max(20, Math.min(46, groupW * .55));
  const bars = REPORT_CURRENT_OFFICIAL.map((item, index) => {
    const groupX = left + index * groupW, cx = groupX + groupW / 2, px = cx - barW / 2;
    const bottomY = top + plotH;
    const accH = item.sAcc * .5 / max * plotH, perfH = item.sPerf * .3 / max * plotH, effH = item.sEff * .2 / max * plotH;
    const accTop = bottomY - accH, perfTop = accTop - perfH, effTop = perfTop - effH;
    const labelY = height - bottom + 17;
    return `<rect x="${px}" y="${accTop}" width="${barW}" height="${accH}" class="seg acc"/>
      <rect x="${px}" y="${perfTop}" width="${barW}" height="${perfH}" class="seg perf"/>
      <rect x="${px}" y="${effTop}" width="${barW}" height="${effH}" class="seg eff"/>
      ${svgText(cx, effTop - 6, item.total.toFixed(2), 'text-anchor="middle" class="svg-total"')}
      ${svgText(cx, labelY, item.name, `text-anchor="end" transform="rotate(-38 ${cx} ${labelY})" class="svg-label"`)}`;
  }).join("");
  scoreEl.innerHTML = `<svg viewBox="0 0 ${width} ${height}" data-orientation="vertical" aria-hidden="true"><style>.svg-label{font-size:9px;fill:#3c3836}.seg.acc{fill:#1b6ca8}.seg.perf{fill:#427b58}.seg.eff{fill:#b57614}.svg-total{font-size:9px;fill:#282828;font-weight:800}.legend{font-size:8px;fill:#6b6866}</style>${bars}<rect x="${left}" y="${legendY}" width="8" height="8" class="seg acc"/>${svgText(left+12,legendY+7,"Accuracy",'class="legend"')}<rect x="${left+65}" y="${legendY}" width="8" height="8" class="seg perf"/>${svgText(left+77,legendY+7,"Performance",'class="legend"')}<rect x="${left+150}" y="${legendY}" width="8" height="8" class="seg eff"/>${svgText(left+162,legendY+7,"Efficiency",'class="legend"')}</svg>`;

  const scatterEl = $("official-scatter-chart");
  const sw=360, sh=330, sl=46, sr=20, st=25, sb=48;
  const sx=(rss)=>sl+(rss-500)/2400*(sw-sl-sr), sy=(tps)=>st+(14-tps)/14*(sh-st-sb);
  let grid="";
  [500,1000,1500,2000,2500].forEach(t=>{const px=sx(t);grid+=`<line x1="${px}" y1="${st}" x2="${px}" y2="${sh-sb}" class="svg-grid"/>${svgText(px,sh-25,t,'text-anchor="middle" class="svg-tick"')}`});
  [0,5,10,14].forEach(t=>{const py=sy(t);grid+=`<line x1="${sl}" y1="${py}" x2="${sw-sr}" y2="${py}" class="svg-grid"/>${svgText(sl-6,py+3,t,'text-anchor="end" class="svg-tick"')}`});
  const labelOffsets = [
    { dx: 7, dy: 18, anchor: "start" },
    { dx: 7, dy: -9, anchor: "start" },
    { dx: 7, dy: 18, anchor: "start" },
    { dx: 7, dy: -9, anchor: "start" },
    { dx: -7, dy: -9, anchor: "end" },
    { dx: -7, dy: 17, anchor: "end" },
  ];
  const pts=REPORT_CURRENT_OFFICIAL.map((d,i)=>{const label=labelOffsets[i];return `<circle cx="${sx(d.rss)}" cy="${sy(d.tps)}" r="${4+d.acc/25}" class="scatter-point ${i===0?'selected':''}"/><title>${esc(d.name)}: ${d.tps} tok/s, ${d.rss.toFixed(0)} MiB, ${d.acc}% ARC-Easy</title>${svgText(sx(d.rss)+label.dx,sy(d.tps)+label.dy,d.name,`text-anchor="${label.anchor}" class="scatter-label ${i===0?'selected':''}"`)}`}).join("");
  scatterEl.innerHTML=`<svg viewBox="0 0 ${sw} ${sh}" aria-hidden="true"><style>.svg-grid{stroke:#e6e2db}.svg-tick{font-size:8px;fill:#8a8580}.scatter-point{fill:#9dbcd5;fill-opacity:.9;stroke:#fff;stroke-width:2}.scatter-point.selected{fill:#af3a03}.scatter-label{font-size:7.5px;fill:#6b6866}.scatter-label.selected{fill:#af3a03;font-weight:800}</style>${grid}${pts}${svgText(sw/2,sh-3,"Peak RSS (MiB)",'text-anchor="middle" class="svg-axis"')}</svg>`;
}

function renderLedger(filter) {
  const rows = EXPERIMENTS.filter((item) => filter === "all" || item.status === filter);
  $("experiment-ledger").innerHTML = rows.map((item) => `<article class="ledger-entry"><span class="ledger-status ${item.status}">${item.status === "neutral" ? "No clear gain" : esc(item.status)}</span><h3>${esc(item.name)}</h3><p>${esc(item.finding)}</p><span class="ledger-source">${esc(item.source)}</span></article>`).join("");
}

function renderFaq() {
  $("faq-list").innerHTML = CHALLENGE_FAQ.map((item, i) => `<details class="faq-item"><summary><span class="faq-number">${String(i + 1).padStart(2, "0")}</span><span class="faq-question">${esc(item.q)}</span></summary><div class="faq-body"><div><h4>Challenge rule</h4><p>${esc(item.rule)}</p></div><div><h4>Muta progress</h4>${item.progress ? `<p>${esc(item.progress)}</p>` : '<div class="empty-progress" aria-label="No Muta progress recorded"></div>'}</div></div></details>`).join("");
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
    const res = await fetch(STATIC ? SNAPSHOT_URL : "/api/state");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
    state.pollAt = Date.now();
    await refreshExpandedRuns();
    render();
  } catch (e) {
    if (STATIC) renderSnapshotFailure();
    /* otherwise the server is briefly away; keep the previous render */
  }
  if (STATIC) return; // a published snapshot never changes, so there is nothing to poll
  const busy = !!(state.data && state.data.current);
  state.timer = setTimeout(poll, busy ? 2500 : 8000);
}

function renderSnapshotFailure() {
  const pill = $("status-pill");
  pill.classList.remove("busy");
  pill.textContent = "Snapshot unavailable";
  pill.title = `The pre-rendered evidence file (${SNAPSHOT_URL}) could not be loaded.`;
}

function snapshotRuns(file) {
  const byModel = (state.data && state.data.runs_by_model) || {};
  return byModel[file] || [];
}

function snapshotRun(id) {
  const byModel = (state.data && state.data.runs_by_model) || {};
  return Object.values(byModel).flat().find((run) => String(run.id) === String(id)) || null;
}

async function refreshExpandedRuns() {
  for (const file of state.expanded) {
    if (STATIC) { state.runsCache[file] = snapshotRuns(file); continue; }
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
  const ladderModels = renderIsaComparison(d.campaign_avx2_score, d.overnight);
  renderOvernight(d.overnight);
  const extensionModels = renderModelExtension(d.model_extension);
  const finetuneModels = renderFinetune(d.finetune);
  renderCombinedComparison(ladderModels, extensionModels, finetuneModels);
  renderCampaignSnapshotWarning(d.campaign);
  renderTpsRef(d);
  renderRunCard(d);
  renderChart(d);
  renderTable(d);
  restoreInitialHash();
}

function restoreInitialHash() {
  if (state.hashRestored || !location.hash) return;
  const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (!target) return;
  state.hashRestored = true;
  requestAnimationFrame(() => requestAnimationFrame(() => target.scrollIntoView()));
}

function renderOvernight(campaign) {
  const scoreChart = $("overnight-score-chart");
  const scoreSummary = $("overnight-score-summary");
  const quantChart = $("overnight-quant-chart");
  const quantSummary = $("overnight-quant-summary");
  const avx2Chart = $("overnight-avx2-score-chart");
  const avx2Summary = $("overnight-avx2-score-summary");
  const avx2Table = $("overnight-avx2-table");
  const finalistTable = $("overnight-finalist-table");
  const screenTable = $("overnight-screen-table");
  if (!scoreChart || !quantChart || !avx2Chart || !avx2Table || !finalistTable || !screenTable) return;
  if (!campaign || !campaign.finalists) {
    scoreChart.innerHTML = '<p class="chart-empty">The expanded campaign summary is unavailable.</p>';
    quantChart.innerHTML = '<p class="chart-empty">The quantization summary is unavailable.</p>';
    avx2Chart.innerHTML = '<p class="chart-empty">The latest vector finalist summary is unavailable.</p>';
    avx2Table.innerHTML = "";
    finalistTable.innerHTML = "";
    screenTable.innerHTML = "";
    return;
  }

  const finalists = Object.values(campaign.finalists).sort((a, b) =>
    b.official.s_total - a.official.s_total);
  const finalistLabel = (model) => model.startsWith("Qwen3-0.6B")
    ? "Math-Expert 0.6B Q4_K_M" : "Qwen3.5 0.8B Q4_0";

  {
    const officialWinnerModel = campaign.official_profiler_winner;
    avx2Chart.innerHTML = verticalGroupedChart(finalists, [
      {className: "scalar", value: (entry) => entry.official.s_total, winner: () => false},
      {className: "avx2", value: (entry) => entry.avx2_fixed_15.arc_easy_50.s_total,
        winner: (entry) => entry.official.model === officialWinnerModel},
    ], {width: 420, height: 300, max: 85, ticks: [0, 20, 40, 60, 80],
      label: (entry) => finalistLabel(entry.official.model), valueFormat: (value) => value.toFixed(1)});
    avx2Summary.textContent = finalists.map((entry) =>
      `${finalistLabel(entry.official.model)}: direct scalar ${entry.official.s_total.toFixed(4)}, ` +
      `vector ${entry.avx2_fixed_15.arc_easy_50.s_total.toFixed(4)}`
    ).join("; ") + ".";

    avx2Table.innerHTML = `<thead><tr><th>Model</th><th>Direct scalar total</th><th>Vector pp512</th><th>Vector tg128</th><th>Est. vector profiler RSS</th><th>ARC-Easy-50 vector total</th><th>ARC-Easy-500 vector diagnostic</th></tr></thead><tbody>` +
      finalists.map((entry) => {
        const avx = entry.avx2_fixed_15;
        const transfer = avx.transferred_from_tensor_identical_source
          ? `<small>Vector measured on a tensor-identical parent quant</small>`
          : `<small>Vector measured on the submitted model</small>`;
        return `<tr class="${entry.official.model === campaign.official_profiler_winner ? "avx2-selected-row" : ""}"><td><div class="model-name">${esc(finalistLabel(entry.official.model))}</div>${transfer}</td><td>${fmt.num(entry.official.s_total, 4)}</td><td>${fmt.num(avx.pp512_tps, 4)}</td><td>${fmt.num(avx.tg128_tps, 4)}</td><td>${fmt.num(avx.estimated_profiler_rss_mib, 1)} MiB<small>${fmt.num(avx.child_tree_rss_mib, 1)} measured + ${fmt.num(avx.profiler_root_rss_estimate_mib, 0)} estimated</small></td><td class="total">${fmt.num(avx.arc_easy_50.s_total, 4)}<small>${fmt.num(avx.arc_easy_50.accuracy_percent, 1)}% accuracy</small></td><td>${fmt.num(avx.arc_easy_500.s_total, 4)}<small>${fmt.num(avx.arc_easy_500.accuracy_percent, 1)}% accuracy</small></td></tr>`;
      }).join("") + "</tbody>";
  }

  {
    const recommendedModel = campaign.risk_adjusted_recommendation;
    scoreChart.innerHTML = verticalGroupedChart(finalists, [
      {className: "official", value: (entry) => entry.official.s_total, winner: () => false},
      {className: "diagnostic", value: (entry) => entry.diagnostic_total_with_arc_easy_500,
        winner: (entry) => entry.official.model === recommendedModel},
    ], {width: 420, height: 300, max: 85, ticks: [0, 20, 40, 60, 80],
      label: (entry) => finalistLabel(entry.official.model), valueFormat: (value) => value.toFixed(1)});
    scoreSummary.textContent = finalists.map((entry) =>
      `${finalistLabel(entry.official.model)}: profiler slice ${entry.official.s_total.toFixed(2)}, ` +
      `larger-sample diagnostic ${entry.diagnostic_total_with_arc_easy_500.toFixed(2)}`
    ).join("; ") + ".";
  }

  {
    const rows = (campaign.quantization_sweep || []).filter((entry) =>
      entry.scalar && entry.accuracy && entry.accuracy.arc_easy != null);
    const width = 620, height = 360, left = 58, right = 32, top = 28, bottom = 50;
    const x = (tps) => left + Number(tps) / 24 * (width - left - right);
    const y = (acc) => top + (72 - Number(acc)) / 24 * (height - top - bottom);
    let grid = "";
    [0, 5, 10, 15, 20].forEach((tick) => {
      const px = x(tick);
      grid += `<line x1="${px}" y1="${top}" x2="${px}" y2="${height - bottom}" class="overnight-grid"/>` +
        svgText(px, height - 24, tick, 'text-anchor="middle" class="overnight-tick"');
    });
    [50, 60, 70].forEach((tick) => {
      const py = y(tick);
      grid += `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}" class="overnight-grid"/>` +
        svgText(left - 8, py + 3, `${tick}%`, 'text-anchor="end" class="overnight-tick"');
    });
    const shortQuant = (name) => name
      .replace("Qwen3-0.6B-Math-Expert.", "")
      .replace(".gguf", "")
      .replace("Q4_0-body-", "body+")
      .replace("Q4_0-Q5_0-last4-Q8_0-embd", "Q4_0 + last4 Q5_0");
    const points = rows.map((entry, index) => {
      const px = x(entry.scalar.tg128_tps), py = y(entry.accuracy.arc_easy);
      const selected = entry.model.includes("Q4_K_M");
      const anchor = px > width - 185 ? "end" : "start";
      const dx = anchor === "end" ? -8 : 8;
      const dy = index % 2 ? 14 : -8;
      return `<circle cx="${px}" cy="${py}" r="${selected ? 7 : 5}" class="overnight-point ${selected ? "selected" : ""}"/><title>${esc(entry.model)}: ${entry.scalar.tg128_tps.toFixed(2)} tok/s, ${entry.accuracy.arc_easy.toFixed(0)}% ARC-Easy</title>` +
        svgText(px + dx, py + dy, shortQuant(entry.model), `text-anchor="${anchor}" class="overnight-point-label ${selected ? "selected" : ""}"`);
    }).join("");
    quantChart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><style>
      .overnight-grid{stroke:#e6e2db}.overnight-tick{font-size:11px;fill:#8a8580}.overnight-point{fill:#b57614;stroke:#fff;stroke-width:2}.overnight-point.selected{fill:#1b6ca8;stroke:#282828}.overnight-point-label{font-size:9.5px;fill:#6b6866}.overnight-point-label.selected{fill:#1b6ca8;font-weight:800}
    </style>${grid}${points}${svgText(width / 2, height - 2, "Scalar profiler-compatible generation tok/s", 'text-anchor="middle" class="svg-axis"')}${svgText(12, height / 2, "ARC-Easy", 'text-anchor="middle" transform="rotate(-90 12 180)" class="svg-axis"')}</svg>`;
    quantSummary.textContent = rows.map((entry) =>
      `${shortQuant(entry.model)}: ${entry.scalar.tg128_tps.toFixed(2)} tok/s and ${entry.accuracy.arc_easy.toFixed(0)}% ARC-Easy`
    ).join("; ") + ".";
  }

  {
    const taskOrder = ["arc_easy_50", "arc_easy_200", "arc_easy_500", "arc_challenge_50", "sciq_50", "gsm8k_10"];
    const taskLabel = {arc_easy_50:"ARC-Easy", arc_easy_200:"ARC-Easy", arc_easy_500:"ARC-Easy", arc_challenge_50:"ARC-Challenge", sciq_50:"SciQ", gsm8k_10:"GSM8K strict"};
    const taskResult = (entry, key) => key === "arc_easy_50"
      ? {score_percent: entry.official.arc_easy_50, samples: 50, ci95_percent: entry.official.arc_easy_50_ci95}
      : entry.accuracy[key];
    finalistTable.innerHTML = `<thead><tr><th>Task</th><th>Samples</th>${finalists.map((entry) => `<th>${esc(finalistLabel(entry.official.model))}</th>`).join("")}</tr></thead><tbody>` +
      taskOrder.map((key) => {
        const first = taskResult(finalists[0], key);
        return `<tr><td>${esc(taskLabel[key])}</td><td>${esc(first && first.samples || "—")}</td>` + finalists.map((entry) => {
          const result = taskResult(entry, key);
          if (!result) return "<td>—</td>";
          const ci = result.ci95_percent || [];
          return `<td><strong>${fmt.num(result.score_percent, 1)}%</strong>${ci.length === 2 ? `<small>95% CI ${fmt.num(ci[0], 1)}–${fmt.num(ci[1], 1)}</small>` : ""}</td>`;
        }).join("") + "</tr>";
      }).join("") + "</tbody>";
  }

  {
    const disposition = {
      "OpenMath-Nemotron-1.5B-q4_0.gguf": "Reject: 44% ARC-Easy",
      "Noema-2B-Q4_K_M.gguf": "Reject: 4.45 scalar tok/s",
      "Noema-2B-pure-Q4_0.gguf": "Reject: 8.89 scalar tok/s",
      "Qwen3.5-0.8B-Opus-Q4_K_M.gguf": "Reject: slower than Q4_0; teacher-data provenance",
      "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf": "Profiler-slice alternative",
      "qwen2-0.5b-numina-math.Q4_K_M.gguf": "Reject: 54% ARC-Easy",
      "Qwen3.5-2B-Q4_0.gguf": "Reject: 6.23 scalar tok/s",
      "gemma-3-1b-it-Q4_0.gguf": "Reject: 58% ARC-Easy",
      "VibeThinker-1.5B.Q4_K_M.gguf": "Reject: 36% ARC-Easy",
      "Qwen3.5-0.8B-Q4_0.gguf": "Tensor-identical source of final recommendation",
      "Qwen3.5-0.8B-Q4_K_M.gguf": "Reject: Q4_0 is faster and smaller",
    };
    const rows = [...(campaign.screened_candidates || [])].sort((a, b) =>
      (b.scalar && b.scalar.tg128_tps || 0) - (a.scalar && a.scalar.tg128_tps || 0));
    screenTable.innerHTML = `<thead><tr><th>Model</th><th>Scalar tg128</th><th>Vector tg128</th><th>Accuracy screen</th><th>Decision</th></tr></thead><tbody>` + rows.map((entry) => {
      const accuracy = Object.entries(entry.accuracy || {}).map(([task, value]) => `${task}: ${fmt.num(value, 0)}%`).join(" · ");
      return `<tr><td><div class="model-name">${esc(shortName(entry.model))}</div></td><td>${fmt.num(entry.scalar && entry.scalar.tg128_tps, 2)}</td><td>${fmt.num(entry.avx2 && entry.avx2.tg128_tps, 2)}</td><td>${esc(accuracy || "screened separately")}</td><td>${esc(disposition[entry.model] || "Rejected in staged screen")}</td></tr>`;
    }).join("") + "</tbody>";
  }
}

function renderCampaign(campaign, prefix) {
  const sub = $(`${prefix}-sub`);
  const table = $(`${prefix}-table`);
  const formula = $(`${prefix}-formula`);
  if (!campaign) {
    sub.textContent = "No campaign summary is available.";
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
  sub.textContent = `${hardwareLabel(campaign.hardware_context)} · ` +
    `${models.length} model${models.length === 1 ? "" : "s"} · standardized benchmark protocol`;
  const scoreHeads = denominators.map((d) =>
    `<th>Total @ ${isWebsiteAlternative ? "cohort floor" : "profiler ref"} ${esc(d)}</th>`
  ).join("");
  const head = `<thead><tr><th>Model</th><th>Size</th><th>${throughputLabel}</th>` +
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
      `<div class="model-sub">${sampleLabel}</div></td>` +
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
    ? "Direct participant-profiler evidence. The performance reference is fixed at 15 tok/s"
    : isWebsiteAlternative
      ? "Website-relative sensitivity only. Vector deployment measurements are rescored with the public cohort formula; each candidate is included in its effective denominator"
      : "Profiler-parity estimate under the no-AVX audit kernel";
  formula.textContent = `${evidenceSummary}. ${sentenceCase(campaign.accuracy_notice)}. ` +
    `${sentenceCase(campaign.rss_notice)}. ${sentenceCase(campaign.thermal_notice)}.` + (winnerText
      ? ` Highest score by ${isWebsiteAlternative ? "website-relative floor" : "profiler reference"}: ${winnerText}.`
      : "");
}

function renderIsaComparison(comparison, overnight) {
  const chart = $("isa-score-chart");
  const summary = $("isa-score-summary");
  const sub = $("campaign-avx2-score-sub");
  const table = $("campaign-avx2-score-table");
  const formula = $("campaign-avx2-score-formula");
  if (!comparison || !Array.isArray(comparison.models)) {
    if (chart) chart.innerHTML = '<p class="chart-empty">The paired ISA comparison is unavailable.</p>';
    if (summary) summary.textContent = "The paired ISA comparison is unavailable.";
    if (sub) sub.textContent = "No vector score-of-record artifact is available at the configured path.";
    if (table) table.innerHTML = "";
    if (formula) formula.textContent = "";
    return;
  }

  const label = (file) => ({
    "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf": "Qwen3.5 0.8B Q4_0 final",
    "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf": "Math-Expert 0.6B Q4_K_M",
    "muta-tutor-qwen3-1.7b-q4_0.gguf": "Qwen3 1.7B Q4_0 tied",
    "Q4_K_M-tied.gguf": "Qwen3 1.7B Q4_K_M tied",
    "Q5_K_M-tied.gguf": "Qwen3 1.7B Q5_K_M tied",
    "IQ4_XS-tied.gguf": "Qwen3 1.7B IQ4_XS tied",
    "bitcpm4-8b-tq2_0-envocab.gguf": "BitCPM4 8B TQ2_0",
  }[file] || shortName(file));
  const latest = overnight && overnight.finalists ? Object.values(overnight.finalists).map((entry) => ({
    model: entry.official.model,
    latest: true,
    scalar: {
      tg128_tps: entry.official.tps,
      estimated_profiler_rss_mib: entry.official.peak_rss_mib,
      score: {s_total: entry.official.s_total},
    },
    avx2: {
      tg128_tps: entry.avx2_fixed_15.tg128_tps,
      estimated_profiler_rss_mib: entry.avx2_fixed_15.estimated_profiler_rss_mib,
      score: {s_total: entry.avx2_fixed_15.arc_easy_50.s_total},
    },
    accuracy_proxy: entry.official.arc_easy_50,
  })) : [];
  const models = [...latest, ...comparison.models];
  const scalarWinnerItem = [...models].sort((a, b) => b.scalar.score.s_total - a.scalar.score.s_total)[0];
  const avx2WinnerItem = [...models].sort((a, b) => b.avx2.score.s_total - a.avx2.score.s_total)[0];
  const scalarWinner = {model: scalarWinnerItem.model, s_total: scalarWinnerItem.scalar.score.s_total};
  const avx2Winner = {model: avx2WinnerItem.model, s_total: avx2WinnerItem.avx2.score.s_total};

  if (chart) {
    chart.innerHTML = verticalGroupedChart(models, [
      {className: "scalar", value: (item) => item.scalar.score.s_total,
        winner: (item) => item.model === scalarWinner.model},
      {className: "avx2", value: (item) => item.avx2.score.s_total,
        winner: (item) => item.model === avx2Winner.model},
    ], {width: 900, height: 320, max: 85, ticks: [0, 20, 40, 60, 80],
      label: (item) => label(item.model), valueFormat: (value) => value.toFixed(1)});
  }
  if (summary) {
    summary.textContent = models.map((item) =>
      `${label(item.model)}: scalar ${item.scalar.score.s_total.toFixed(4)}, vector ${item.avx2.score.s_total.toFixed(4)}`
    ).join("; ") + `. Highest scalar total: ${label(scalarWinner.model)}. Highest vector total: ${label(avx2Winner.model)}.`;
  }

  if (sub && table && formula) {
    const ranked = [...models].sort((a, b) => b.avx2.score.s_total - a.avx2.score.s_total);
    sub.textContent = `${hardwareLabel(comparison.hardware_contexts.avx2)} · ${ranked.length} models · matched scalar and vector measurements`;
    table.innerHTML = `<thead><tr><th>Model</th><th>Scalar total</th><th>Vector total</th><th>Scalar → vector tg128</th><th>Scalar → vector est. RSS</th><th>Accuracy proxy</th></tr></thead><tbody>` +
      ranked.map((item) => `<tr class="${item.model === avx2Winner.model ? "avx2-winner-row" : ""}"><td><div class="model-name">${esc(label(item.model))}</div></td><td>${fmt.num(item.scalar.score.s_total, 4)}</td><td class="total">${fmt.num(item.avx2.score.s_total, 4)}</td><td>${fmt.num(item.scalar.tg128_tps, 4)} → ${fmt.num(item.avx2.tg128_tps, 4)}</td><td>${fmt.num(item.scalar.estimated_profiler_rss_mib, 1)} → ${fmt.num(item.avx2.estimated_profiler_rss_mib, 1)} MiB</td><td>${fmt.num(item.accuracy_proxy, 0)}% ARC-Easy</td></tr>`).join("") +
      `</tbody>`;
    formula.textContent = `Matched scalar and vector measurements on one GCP 2C/4T proxy · S_perf = 100 × min(TPS / 15, 1) · scalar finalist rows use direct profiler RSS; vector rows use measured child-tree RSS + 45 MiB root estimate · thermal unknown. Highest scalar total: ${label(scalarWinner.model)} (${fmt.num(scalarWinner.s_total, 4)}). Highest vector total: ${label(avx2Winner.model)} (${fmt.num(avx2Winner.s_total, 4)}).`;
  }
  return models.map((item) => ({
    key: `ladder:${item.model}`, label: label(item.model), group: "First exploration",
    scalar_total: item.scalar.score.s_total, avx2_total: item.avx2.score.s_total,
  }));
}

function renderModelExtension(modelExtension) {
  const chart = $("model-extension-score-chart");
  const summary = $("model-extension-score-summary");
  const sub = $("model-extension-sub");
  const table = $("model-extension-table");
  const formula = $("model-extension-formula");
  if (!modelExtension || !Array.isArray(modelExtension.models)) {
    if (chart) chart.innerHTML = '<p class="chart-empty">The eight-model architecture screen is unavailable.</p>';
    if (summary) summary.textContent = "The eight-model architecture screen is unavailable.";
    if (sub) sub.textContent = "No model-extension summary is available at the configured path.";
    if (table) table.innerHTML = "";
    if (formula) formula.textContent = "";
    return null;
  }
  const models = modelExtension.models;
  const scalarWinnerItem = [...models].sort((a, b) => b.scalar.s_total - a.scalar.s_total)[0];
  const avx2WinnerItem = [...models].sort((a, b) => b.avx2.s_total - a.avx2.s_total)[0];

  if (chart) {
    const ranked = [...models].sort((a, b) => b.avx2.s_total - a.avx2.s_total);
    chart.innerHTML = verticalGroupedChart(ranked, [
      {className: "scalar", value: (item) => item.scalar.s_total,
        winner: (item) => item.model === scalarWinnerItem.model},
      {className: "avx2", value: (item) => item.avx2.s_total,
        winner: (item) => item.model === avx2WinnerItem.model},
    ], {width: 900, height: 320, max: 85, ticks: [0, 20, 40, 60, 80],
      label: (item) => `${item.rank} · ${item.label}`, valueFormat: (value) => value.toFixed(1)});
  }
  if (summary) {
    summary.textContent = models.map((item) =>
      `${item.rank} ${item.label}: scalar ${item.scalar.s_total.toFixed(4)}, vector ${item.avx2.s_total.toFixed(4)}, ${item.accuracy_percent}% ARC-Easy n=50`
    ).join("; ") + `. Highest scalar total: ${scalarWinnerItem.label}. Highest vector total: ${avx2WinnerItem.label}.`;
  }
  if (sub && table && formula) {
    const ranked = [...models].sort((a, b) => b.avx2.s_total - a.avx2.s_total);
    sub.textContent = `${hardwareLabel(modelExtension.hardware_context)} · ${ranked.length} current models · matched scalar and vector measurements`;
    table.innerHTML = `<thead><tr><th>Model</th><th>Scalar → vector pp512</th><th>Scalar → vector tg128</th><th>Decode gain</th><th>Vector RSS</th><th>ARC-Easy, n=50</th><th>Scalar → vector total</th></tr></thead><tbody>` +
      ranked.map((item) => `<tr class="${item.model === avx2WinnerItem.model ? "avx2-winner-row" : ""}"><td><div class="model-name">${esc(`${item.rank} · ${item.label}`)}</div></td><td>${fmt.num(item.scalar.pp512_tps, 4)} → ${fmt.num(item.avx2.pp512_tps, 4)}</td><td>${fmt.num(item.scalar.tg128_tps, 4)} → ${fmt.num(item.avx2.tg128_tps, 4)}</td><td>${fmt.num(item.decode_speedup, 3)}×</td><td>${fmt.num(item.avx2.estimated_profiler_rss_mib, 1)} MiB</td><td>${fmt.num(item.accuracy_percent, 0)}%</td><td class="total">${fmt.num(item.scalar.s_total, 4)} → <strong>${fmt.num(item.avx2.s_total, 4)}</strong></td></tr>`).join("") +
      `</tbody>`;
    formula.textContent = `Eight-model architecture screen on one GCP 2C/4T proxy · S_perf = 100 × min(TPS / 15, 1) · vector RSS adds the 45 MiB profiler-root estimate to measured child-tree RSS · thermal unknown · one ARC-Easy n=50 result per GGUF is reused for both CPU configurations. Highest scalar total: ${scalarWinnerItem.label} (${fmt.num(scalarWinnerItem.scalar.s_total, 4)}). Highest vector total: ${avx2WinnerItem.label} (${fmt.num(avx2WinnerItem.avx2.s_total, 4)}).`;
  }
  return models.map((item) => ({
    key: `extension:${item.model}`,
    label: item.label.includes("Q8_0") ? item.label : `${item.label} Q4_K_M`,
    group: "Second exploration",
    scalar_total: item.scalar.s_total, avx2_total: item.avx2.s_total,
  }));
}

function renderFinetune(finetune) {
  const accuracyChart = $("finetune-accuracy-chart");
  const accuracySummary = $("finetune-accuracy-summary");
  const scoreChart = $("finetune-score-chart");
  const scoreSummary = $("finetune-score-summary");
  const resultsTable = $("finetune-results-table");
  const heldoutTable = $("finetune-heldout-table");
  const heldoutNote = $("finetune-heldout-note");
  if (!accuracyChart || !scoreChart || !resultsTable || !heldoutTable) return null;
  if (!finetune || !Array.isArray(finetune.models)) {
    accuracyChart.innerHTML = '<p class="chart-empty">The fine-tuning summary is unavailable.</p>';
    scoreChart.innerHTML = '<p class="chart-empty">The fine-tuning summary is unavailable.</p>';
    resultsTable.innerHTML = "";
    heldoutTable.innerHTML = "";
    if (accuracySummary) accuracySummary.textContent = "The fine-tuning summary is unavailable.";
    if (scoreSummary) scoreSummary.textContent = "The fine-tuning summary is unavailable.";
    return null;
  }

  const models = finetune.models;
  const scalarWinner = [...models].sort((a, b) => b.scalar.candidate_total - a.scalar.candidate_total)[0];
  const vectorWinner = [...models].sort((a, b) => b.vector.candidate_total - a.vector.candidate_total)[0];

  accuracyChart.innerHTML = verticalGroupedChart(models, [
    {className: "control", value: (item) => item.accuracy.control_percent},
    {className: "tuned", value: (item) => item.accuracy.candidate_percent,
      winner: (item) => item.id === vectorWinner.id},
  ], {width: 470, height: 270, bottom: 74, max: 85, ticks: [0, 20, 40, 60, 80],
    label: (item) => item.label.replace(/ Q4_.+$/, ""), valueFormat: (value) => `${value.toFixed(1)}%`});

  scoreChart.innerHTML = verticalGroupedChart(models, [
    {className: "scalar", value: (item) => item.scalar.candidate_total,
      winner: (item) => item.id === scalarWinner.id},
    {className: "avx2", value: (item) => item.vector.candidate_total,
      winner: (item) => item.id === vectorWinner.id},
  ], {width: 470, height: 270, bottom: 74, max: 90, ticks: [0, 20, 40, 60, 80],
    label: (item) => item.label.replace(/ Q4_.+$/, ""), valueFormat: (value) => value.toFixed(1)});

  if (accuracySummary) {
    accuracySummary.textContent = models.map((item) =>
      `${item.label}: ${item.accuracy.control_percent.toFixed(1)}% control, ${item.accuracy.candidate_percent.toFixed(1)}% fine-tuned, ${item.accuracy.delta_points.toFixed(1)} points gained`
    ).join("; ") + ".";
  }
  if (scoreSummary) {
    scoreSummary.textContent = models.map((item) =>
      `${item.label}: scalar ${item.scalar.candidate_total.toFixed(4)}, vector ${item.vector.candidate_total.toFixed(4)}`
    ).join("; ") + `. Scalar leader: ${scalarWinner.label}. Vector leader: ${vectorWinner.label}.`;
  }

  resultsTable.innerHTML = `<thead><tr><th>Model</th><th>ARC-Easy control → tuned</th><th>Scalar tok/s · est. RSS</th><th>Scalar total control → tuned</th><th>Vector tok/s · est. RSS</th><th>Vector total control → tuned</th></tr></thead><tbody>` +
    models.map((item) => `<tr class="${item.id === scalarWinner.id || item.id === vectorWinner.id ? "selected-row" : ""}"><td><strong>${esc(item.label)}</strong><small>${esc(item.candidate)}</small></td><td>${fmt.num(item.accuracy.control_percent, 1)}% → <strong>${fmt.num(item.accuracy.candidate_percent, 1)}%</strong><small>+${fmt.num(item.accuracy.delta_points, 1)} points</small></td><td>${fmt.num(item.scalar.candidate_tps, 2)} · ${fmt.num(item.scalar.candidate_peak_rss_mib, 0)} MiB</td><td>${fmt.num(item.scalar.control_total, 4)} → <strong>${fmt.num(item.scalar.candidate_total, 4)}</strong><small>+${fmt.num(item.scalar.delta_total, 4)}</small></td><td>${fmt.num(item.vector.candidate_tps, 2)} · ${fmt.num(item.vector.candidate_peak_rss_mib, 0)} MiB</td><td>${fmt.num(item.vector.control_total, 4)} → <strong>${fmt.num(item.vector.candidate_total, 4)}</strong><small>+${fmt.num(item.vector.delta_total, 4)}</small></td></tr>`).join("") + `</tbody>`;

  const heldoutRows = models.flatMap((item) => (item.held_out || []).map((result) => ({item, result})));
  heldoutTable.innerHTML = heldoutRows.length
    ? `<thead><tr><th>Model</th><th>Benchmark</th><th>Samples</th><th>Control → tuned</th></tr></thead><tbody>` + heldoutRows.map(({item, result}) => `<tr><td>${esc(item.label)}</td><td>${esc(result.benchmark)}</td><td>${fmt.int(result.samples)}</td><td>${fmt.num(result.control_percent, 1)}% → <strong>${fmt.num(result.candidate_percent, 1)}%</strong></td></tr>`).join("") + `</tbody>`
    : "";
  const pending = models.filter((item) => item.held_out_status).map((item) => `${item.label}: ${item.held_out_status}`);
  if (heldoutNote) heldoutNote.textContent = pending.join(" ");

  return models.map((item) => ({
    key: `finetune:${item.id}`, label: `Tuned ${item.label}`, group: "Fine-tuned finalists",
    scalar_total: item.scalar.candidate_total, avx2_total: item.vector.candidate_total,
  }));
}

function renderCombinedComparison(ladderModels, extensionModels, finetuneModels) {
  const chart = $("all-models-score-chart");
  const summary = $("all-models-score-summary");
  if (!chart) return;
  const combined = [...(ladderModels || []), ...(extensionModels || []), ...(finetuneModels || [])];
  if (!combined.length) {
    chart.innerHTML = '<p class="chart-empty">The combined model comparison is unavailable.</p>';
    if (summary) summary.textContent = "The combined model comparison is unavailable.";
    return;
  }
  const ranked = [...combined].sort((a, b) => b.avx2_total - a.avx2_total);
  const scalarWinner = [...combined].sort((a, b) => b.scalar_total - a.scalar_total)[0];
  const avx2Winner = ranked[0];
  chart.innerHTML = verticalGroupedChart(ranked, [
    {className: "scalar", value: (item) => item.scalar_total, winner: (item) => item.key === scalarWinner.key},
    {className: "avx2", value: (item) => item.avx2_total, winner: (item) => item.key === avx2Winner.key},
  ], {width: Math.max(1200, ranked.length * 62 + 90), height: 340, max: 85, ticks: [0, 20, 40, 60, 80],
    label: (item) => item.label, valueFormat: (value) => value.toFixed(1)});
  if (summary) {
    summary.textContent = ranked.map((item) =>
      `${item.label} (${item.group}): scalar ${item.scalar_total.toFixed(4)}, vector ${item.avx2_total.toFixed(4)}`
    ).join("; ") + `. Highest scalar total across both explorations: ${scalarWinner.label}. Highest vector total across both explorations: ${avx2Winner.label}.`;
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
    `${m.domain || "Math and scientific reasoning"}` +
    (claims.length ? ` · ${claims.join(" · ")}` : "") +
    (m.current_model_path ? ` · selected model: ${shortName(m.current_model_path.split("/").pop())}` : "");
  const pill = $("status-pill");
  if (STATIC) {
    pill.classList.remove("busy");
    pill.textContent = "Published snapshot";
    pill.title = "Read-only copy rendered from the repository's stored evidence; profiling needs the local dashboard server.";
  } else if (d.current) {
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

function hardwareLabel(context) {
  const value = String(context || "");
  if (value.includes("n2_custom_4_8192_2c4t") || value.includes("2c4t")) {
    return value.includes("no_avx")
      ? "2-core, 4-thread scalar CPU proxy"
      : "2-core, 4-thread x86 CPU proxy";
  }
  return value ? value.replaceAll("_", " ") : "CPU benchmark environment";
}

function renderTable(d) {
  const busy = !!d.current;
  const present = d.models.filter((m) => m.present).length;
  const gone = d.models.length - present;
  $("models-sub").textContent = STATIC
    ? `${d.models.length} artifact${d.models.length === 1 ? "" : "s"} with stored run records` +
      ` · published snapshot; the latest run appears below and History opens the complete record`
    : `${present} GGUF file${present === 1 ? "" : "s"} in model/` +
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
    // A published snapshot is built without the model/ directory, so disk presence is simply
    // unknown there, not "removed".
    const info = STATIC
      ? [m.quant, m.params]
      : m.present
        ? [fmt.gb(m.size_bytes), m.quant, m.params]
        : ["artifact removed; run records retained", m.quant, m.params];
    const sub = info.filter(Boolean).join(" · ") +
      (m.runs_count
        ? ` · ${m.runs_count} run${m.runs_count === 1 ? "" : "s"}`
        : " · no stored run");
    const arc = r && r.arc_score != null ? `${r.arc_score.toFixed(3)}` : "—";
    const main = `<tr class="model-row" data-model="${esc(m.file)}">
      <td>
        <div class="model-name${m.present || STATIC ? "" : " dim"}">${esc(shortName(m.file))}</div>
        <div class="model-sub">${esc(sub)}</div>
        <div class="model-actions">
          <button class="btn primary small" data-action="profile" data-model="${esc(m.file)}"
            ${busy || !m.present || STATIC ? "disabled" : ""}
            ${STATIC ? 'title="Profiling needs the local dashboard server"' : ""}>${running ? "Running…" : "Start profile"}</button>
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
      <td>#${r.id}</td>
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
          ${r.status === "ok" && !gone && !STATIC ? "" : "disabled"}
          ${STATIC ? 'title="Promotion needs the local dashboard server"'
            : gone ? 'title="The model artifact is no longer present and cannot be promoted"' : ""}>Set as submission</button>
        <button class="btn small danger" data-action="delete" data-id="${r.id}"
          ${STATIC ? 'disabled title="Deleting a record needs the local dashboard server"' : ""}>Delete record</button>
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
  // The published snapshot has no server to mutate. Its buttons are disabled in render; this
  // guard keeps a stray click from reaching an /api route that does not exist there.
  if (STATIC && ["profile", "cancel", "promote", "delete"].includes(action)) return;

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
    let d;
    if (STATIC) {
      d = snapshotRun(btn.dataset.id);
      if (!d) return;
    } else {
      const res = await fetch("/api/runs/" + btn.dataset.id);
      d = await res.json();
    }
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
      <span>archive run</span><b>#${r.id}</b>
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

if (STATIC) {
  $("static-notice").hidden = false;
  $("quick-toggle").closest("label").hidden = true; // the toggle only configures a live run
}
initReport();
poll();
