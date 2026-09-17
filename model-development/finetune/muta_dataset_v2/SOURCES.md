# Source and rights audit

Snapshot date: **15 September 2026**. This is an engineering risk register, not legal advice.

## Decision rule

A source is not enabled merely because it is public, downloadable, searchable, or easy to OCR.
The default is exclusion unless the dataset/content licence, exact revision, allowed split, and
verification path are explicit. Rights in code do not automatically prove rights in bundled data,
and a dataset-level licence does not automatically clear every upstream question or diagram.

## Protected exam sources: taxonomy only unless permissioned

| Source | Finding | Dataset decision |
|---|---|---|
| [WAEC Nigeria e-Learning](https://www.waeconline.org.ng/e-learning/) | Public subject archives and examiner commentary; reviewed pages carry a WAEC copyright/all-rights-reserved footer. | Without permission: independently phrased topic/rubric/error taxonomy only. No source item enters warehouse, SFT, or evaluation. With a WAEC evaluation grant: quarantine actual items as evaluation-only; training requires a separate explicit grant. |
| [WAEC Mathematics archive](https://www.waeconline.org.ng/e-learning/Mathematics/mathsmain.html) | Paper 2 material spans many years and is useful for observing assessed skills. | Independently normalized taxonomy only until permission; a permissioned evaluation set remains temporally held out and cannot enter SFT. |
| [WAEC Ghana Chief Examiner reports](https://waecgh.org/chief-examiners-report/) | Official reports identify strengths and weaknesses but provide no open training licence. | Independently summarize error categories; do not copy report wording or questions. |
| [CheetahWAEC](https://cheetahwaec.com/past-papers) | Its [terms](https://cheetahwaec.com/terms) reserve original explanations, acknowledge third-party rights, disclaim guaranteed accuracy, and prohibit scraping/harvesting/mass download when it harms the site or other users. They do not grant model-training or redistribution rights. | Without permission: independently phrased taxonomy only. Evaluation requires Cheetah permission for its explanations/access and WAEC/other underlying rightsholder clearance. Permissioned rows default to evaluation-only; training requires an additional explicit grant. |
| [MySchoolGist free JAMB downloads](https://myschoolgist.com/nigeria/free-jamb-past-questions-available/) | Free study downloads across 12 subjects, but the page has a copyright footer and no model-training/republication licence. Its [app policy](https://myschoolgist.com/privacy-policy-app/) separately says it owns the software and that education consultants create the app content; it does not establish chain-of-title for every JAMB PDF. | Without permission: independently phrased JAMB subject/topic/item-format taxonomy only. Evaluation requires MySchoolGist and JAMB/underlying rightsholder clearance. Permissioned rows default to evaluation-only; training requires an additional explicit grant. |
| [Official JAMB brochure notice](https://ibass.jamb.gov.ng/assets/uploads/brochure-notice.pdf) | This publication requires written permission for reproduction, transmission, or storage in a retrieval system. It is evidence of JAMB's publication practice, not a claim that this one notice governs every past paper. No official open question-data or ML-training grant was located in the 2026-09-16 review. | Keep JAMB material outside acquisition under this dataset policy unless the relevant rights are documented. |
| [ALOC Station Questions API](https://aloc.com.ng/docs/questions) | The API exposes normalized WAEC, JAMB, NECO, Post-UTME, and state-board questions, but its [Developer Terms v2.3.0](https://www.aloc.com.ng/terms) limit standard-plan caching to 48 hours, prohibit permanent wholesale mirroring and systematic cursor crawling, and expressly prohibit using API responses or questions to train, fine-tune, evaluate, or benchmark an LLM or neural network. The mentioned enterprise bulk-data licence does not by itself override the separate AI-training ban. | Standard/free API keys contribute zero rows and are not exercised for this project. Obtain a signed bespoke bulk-export and AI-training amendment plus documented upstream exam-content authority before acquisition. See `ALOC_PERMISSION_REQUEST.md`. |
| [SdashAPI](https://sdashapi.com/) | Its [terms](https://sdashapi.com/Terms-of-Service) prohibit systematic harvesting for training/fine-tuning without written permission. | Standard plans excluded; negotiate a dataset licence if desired. |
| [TestUstad](https://testustad.com/copyright) | Express restriction on harvesting for a machine-learning training set. | Excluded. |

Older materials must not be assumed public domain merely because of age; no item-level
public-domain determination was made. The
taxonomy boundary excludes question/answer wording, explanations, marking schemes, report prose,
figures, screenshots, OCR, close paraphrases, and source-derived rows from both training and
evaluation. Taxonomy labels must be independently worded.

The permission route is source-specific: WAEC licenses WAEC material; CheetahWAEC can license only
the explanations/access rights it owns and requires separate exam-rightsholder clearance;
MySchoolGist can license only the content/access rights it owns and requires separate JAMB or other
underlying-rightsholder clearance. ALOC requires a bespoke agreement that expressly overrides its
standard caching, bulk-mirroring, automated-cursor, and AI-training restrictions and documents its
authority to license each included exam corpus. An evaluation permission does not imply training permission.
The first permissioned ingest must be quarantined and evaluation-only. A licence receipt must
identify countries, years, subjects, papers, solutions, figures, automated retrieval/OCR,
permanent storage, evaluation, training, derived datasets, adapter/model-weight distribution,
territory, duration, and attribution. Store the executed grant and artifact hashes before changing
the source registry.

## Candidate warehouse is not the SFT view

The warehouse is a candidate and audit pool. Registry entries marked prohibited or evaluation-only
are documentation records and contribute no content rows. Inclusion of a source or allocation in a
recipe or manifest is not a licence decision, quality approval, or training authorization.

A training-eligible SFT view is a separately materialized, hashed artifact. It may contain only
rows from enabled sources with `split: train` and allowed original source splits that match the
registry licence/revision, pass schema,
verification, deduplication, and holdout checks. A row is authorized either natively by immutable
`verification.training_eligible: true` metadata or by a separate exact-row audit receipt whose
decision is `approved` and that binds the warehouse fingerprint, row ID, content hash, reviewer
attestation, review method, and rubric artifact hash. Current audit-gated sources are row-only: a template/cluster attestation never
blanket-authorizes its instantiations. Auditing never
edits the warehouse row or approves an entire source by assertion. The SFT manifest must retain the
review-decision hashes and report the rows selected and authorized, not the 2.5M warehouse target.
The training config and logs must separately report the examples, tokens, epochs, and steps actually
consumed; a 300K selected SFT artifact is not evidence that all 300K rows were trained on.

The candidate warehouse is intentionally mathematics-heavy because its largest open bulk sources
are symbolic and word-problem generators. Its 1,085,000-row original component is science-heavy
(25% mathematics; 75% physics/chemistry/biology/integrated science), but those are warehouse
generation weights—not the final SFT mix. The later 300K selector must solve the declared overall
subject × pedagogy constraints from actual audited rows and must not sample sources proportionally.

Five original prototypes—profit after a price reduction, equal-distance average speed,
coloured-counter ratio, coloured-counter probability, and simple interest—are retained only as
quarantined audit code. Their semantic story templates were guided by sealed judge/STEM prompts;
low lexical five-gram overlap cannot prove that they are uncontaminated, so they contribute zero
rows.

The 30 active generator families are broad curriculum operators independently supported by the
NaCCA/NERDC topic map: linear and simultaneous equations, sequences, measurement, mechanics,
electricity, waves, mole/solution calculations, stoichiometry, cell magnification, inheritance,
statistics, geometry, energy, pressure, practical-science variables, efficiency, volume, and
temperature conversion. Sealed benchmark prompts did **not** determine their stories,
misconception labels, scaffolds, or response wording. In addition to normalized exact/five-gram
screening, structured guards reject the known benchmark numerical cores for linear equations,
sequences, Pythagoras, Ohm's law, and the quarantined simple-interest case.

## Curriculum/version warning

“WASSCE-aligned” is not a single timeless or pan-West-African label. Ghana's current SHS materials
are indexed by [NaCCA](https://nacca.gov.gh/secondary-education-curriculum/), while Nigeria's
[revised senior-secondary curriculum](https://www.nerdc.gov.ng/content_manager/new_senior_curriculum_home.html)
began a new implementation era. Each record therefore distinguishes country, authority, version,
and exam era. A general synthetic problem is tagged as general rather than falsely attributed to
WAEC, NaCCA, or NERDC.

The independently normalized coverage map includes:

- mathematics: number, commercial arithmetic, algebra, functions, geometry, mensuration,
  trigonometry, data/statistics, probability, vectors, mechanics, and introductory calculus;
- physics: measurement, matter, kinematics/dynamics, energy, heat, waves/light/sound, electricity,
  magnetism/electronics, atomic/nuclear physics, and practical investigation;
- chemistry: particles/moles/stoichiometry, solutions, energetics, rates/equilibrium, periodicity,
  bonding, redox/electrochemistry, carbon compounds, qualitative analysis, and practical safety;
- biology: cells, transport, diversity/ecology, plant/mammalian systems, disease, reproduction,
  inheritance/evolution, health/conservation, and practical investigation;
- cross-cutting: units, significant figures, graphs/tables/diagrams, experimental variables,
  evidence-based inference, coherent working, misconception diagnosis, and rubric compliance.

These are topic labels, not copied curricular prose.

## Enabled bulk and anchor sources

| Source | Pin | Licence | Use and caveat |
|---|---|---|---|
| [DeepMind Mathematics Dataset](https://github.com/google-deepmind/mathematics_dataset/tree/427f45075f84b8b9774950196ad63867ca20ffb3) | `427f45075f84b8b9774950196ad63867ca20ffb3` | Apache-2.0 | Fresh train-regime generation is the main volume source. Record source regime, module cluster, difficulty, and per-row seed. The archived Muta overlay removes upstream identity-set ordering, sorts symbol choices, and seeds SymPy's private RNG; each build must pass a fresh cross-hash-seed process probe and also starts with `PYTHONHASHSEED=3407`. Exact answers are useful, but short-answer style must be down-weighted in SFT. |
| [TemplateGSM](https://huggingface.co/datasets/math-ai/TemplateGSM/tree/0c8ed6b60fea0a84f25ddb1b8b761db695df2e19) | `0c8ed6b60fea0a84f25ddb1b8b761db695df2e19` | CC-BY-4.0 | Use only `templategsm-2000-1k`. Release builds require the authenticated local 2,000-file, 2,403,438,064-byte snapshot (inventory SHA-256 `9100d9daa8214a5018124e2e44dc1ee0378ecd0a992f4c450430d76f95801132`; README SHA-256 `20b70e0f0d41021e54e4a73b1972fde7f6355f405bd67eef00472e4ce711ba7a`) and do not use the network for row materialization. A hash-bound full scan rejects 226,263/2,000,000 rows and quarantines all 362 templates with any observed failure; 1,638 templates remain, with 655,200-row capacity at cap 400. The same static filter runs again per row. Nested configurations are not independent data, publisher code is never executed, and survivors remain audit-gated. |
| [QASC](https://huggingface.co/datasets/allenai/qasc/tree/a34ba204eb9a33b919c10cc08f4f1c8dae5ec070) | `a34ba204eb9a33b919c10cc08f4f1c8dae5ec070` | CC-BY-4.0 | Train split only; validation/test are holdouts. Answer-key rows remain audit-gated because some wording is unnatural. |
| [GSM8K](https://huggingface.co/datasets/openai/gsm8k/tree/740312add88f781978c0658806c59bc2815b9866) | `740312add88f781978c0658806c59bc2815b9866` | MIT | Train split only; test is sealed. Calculator annotations are independently recomputed, but semantic defects can survive arithmetic verification, so rows remain audit-gated. |
| [Muta original generators](https://github.com/nelsonifechukwu/Muta) | Composite SHA-256 over archived executable code, schema/recipe/registry, dependency lock, repository licence, and sealed-holdout definitions | MIT | Original wording, exact arithmetic, unit/self-checks, misconception and tutor variants. Programmatic regeneration must reproduce the entire problem, prompt, completion, metadata, identity, and canonical source-task hash; only independently normalized exam/curriculum taxonomy labels are used. |

Verification semantics are source-specific and must not be collapsed into a single “verified” claim:

| Source | What is checked | What is not certified |
|---|---|---|
| Muta original | Full deterministic regeneration plus independent exact-arithmetic/unit checks and response-policy checks. | Human pedagogical quality for every generated row. |
| DeepMind Mathematics | Deterministic replay of the pinned symbolic generator and its self-emitted exact answer. | A separately implemented derivation or human correctness review. |
| TemplateGSM | Binds the pinned full-source audit; quarantines every failing template; and rechecks finite canonical result, terminal target support, float artifacts, and exact numeric-only equalities. | Publisher code parsing/execution, an independent solution of the prompt, complete coverage of equations containing variables/words/units, wording quality, or semantic correctness. The lexical approximation escape uses a ±120-character context and may suppress an unrelated contradiction when words such as `about` occur nearby. |
| QASC | Publisher answer key and supporting-fact fields, with official validation/test prompts held out. | Independent truth or naturalness review. |
| GSM8K | Restricted-AST recomputation of calculator annotations and publisher final-answer consistency, with test held out. | Independent validation of the story semantics or reasoning prose. |

`verification.training_eligible` is a source/split/policy gate, not a universal human correctness
certificate. The combined warehouse and any SFT view are per-source licensed, not blanket MIT.
Every final SFT provenance bundle needs a hashed attribution inventory containing creator/title,
source ID and immutable revision/config/split, selected count, licence text hash and URL,
transformation/change notice, synthetic flag, verification/audit result, and evidence receipt.

## Candidate-only sources

- [Nemotron-Science-v1](https://huggingface.co/datasets/nvidia/Nemotron-Science-v1): disabled
  after a fresh sample showed graduate gene-therapy/medical material passing the keyword-based
  secondary-level filter. It contributes zero default rows unless a stronger syllabus classifier
  and cluster-level human audit are added.

- [Siyavula Nigeria](https://ng.siyavula.com/read): promising NERDC-aligned African material.
  Only clearly CC-BY HTML/unbranded assets should be considered, with page hashes and exclusion of
  separately attributed media; branded CC-BY-ND PDFs are not transformable.
- [OpenMathInstruct-2](https://huggingface.co/datasets/nvidia/OpenMathInstruct-2): 13,972,791
  training rows, but overlapping convenience subsets must not be double-counted. Multiple solution
  traces share a much smaller problem pool, and public samples expose malformed/awkward material.
- [Orca-Math 200K](https://huggingface.co/datasets/microsoft/orca-math-word-problems-200k):
  potentially useful, but both questions and solutions are synthetic and need independent semantic
  and numerical verification.
- [OpenR1-Math-220k](https://huggingface.co/datasets/open-r1/OpenR1-Math-220k): verified
  flags help, but long olympiad traces and source lineage are a poor default fit for a 1.5B
  secondary tutor.
- [QuaRTz](https://huggingface.co/datasets/allenai/quartz) and
  [ROPES](https://huggingface.co/datasets/allenai/ropes): useful causal reasoning candidates;
  preserve their validation/test sets and audit embedded passage lineage.
- [AI2 ARC](https://huggingface.co/datasets/allenai/ai2_arc): not used in v2. It already appeared in
  the prior fine-tune, Gate 2 uses ARC-Easy, and CC-BY-SA model-weight treatment requires an
  explicit project decision.

## Explicit exclusions and holdouts

- SciQ: CC-BY-NC-3.0; excluded from the permissive/future-commercial path.
- OpenBookQA: dataset licence recorded as unknown; excluded.
- OpenStax current content/exercises: content- and edition-specific AI/licensing restrictions;
  excluded without permission.
- ScienceQA and large scraped “science Q&A” mirrors: inadequate item-level rights/lineage.
- WAEC, JAMB, NECO, Cambridge, AQA, Edexcel, commercial revision banks, and contest/forum material:
  no ingestion based merely on public visibility.
- Muta exact judge prompts, STEM-100, ARC-Easy-500, upstream validation/test splits, and
  [AfriMGSM](https://huggingface.co/datasets/yuntian-deng/afrimgsm) remain evaluation-only.
