# Proposed winner-test science family blueprint

Date: 18 September 2026. Status: **local design only; zero questions authored,
zero families admitted, no answer keys or reference sources acquired, no model
outputs inspected**. This is the science half of the proposed 2,000-item test,
not a new training dataset or a claim of a validated benchmark.

Read together with:

- `docs/plans/2026-09-18-full-data-winner-test-design.md`
- `docs/plans/2026-09-18-full-data-winner-test-inventory.md`
- `docs/plans/2026-09-18-round2-holdout-audit-implementation.md`
- `model-development/finetune/muta_dataset_v2/generators.py`
- ROADMAP's WAEC-Bench design, separate method/answer marks, and science slice.

The current winner-test design governs where older roadmap language is stronger
than the evidence: matched generated performance does not prove reasoning or
absence of contamination. This blueprint does not change frozen training,
checkpoint selection, existing scores, or the winner decision rule.

## Conditional allocation

| Primary stratum | Physics | Chemistry | Biology | Total |
|---|---:|---:|---:|---:|
| Science MC | 170 | 165 | 165 | 500 |
| Science written/tutoring | 170 | 165 | 165 | 500 |
| Both | 340 | 330 | 330 | 1,000 |

There are **24 proposed families**, eight per subject. P01 and P02 provisionally
receive 25 MC and 25 written each; C01 and B01 also receive 25 + 25. Each other
family receives 20 + 20. These are capacity targets, not permission to fill
rejected families with renamed variants. Losing a family can leave a quota
unfilled; stop and revise the pre-inference design openly rather than relaxing
exclusions or padding after seeing scores.

Each 500-item stratum provisionally targets 150 foundation, 250 standard and
100 advanced items, assigned by independent curriculum review of reasoning
burden rather than operand size. Proposed subject rows are physics 50/85/35,
chemistry 50/80/35, biology 50/85/30. They are not yet calibrated difficulty
labels or a claim of full WASSCE syllabus coverage.

Written modes: 125 worked solutions, 125 Socratic hints, 125 misconception
corrections, and 125 exam marking schemes. Each family contributes five of each;
the additional five in P01 go to worked solutions, P02 to hints, C01 to
misconception correction, and B01 to marking schemes. A mode wrapper is **not**
a new family. Single-turn hints can measure a useful next step, not successful
multi-turn learning. MC uses four options with an overall balanced answer-key
position allocation fixed independently before inference; score correctness
separately from requested explanation/format.

Scientific reasoning is embedded in the same physics/chemistry/biology items,
not an extra double-counted stratum. Tags distinguish model assumptions,
controls/confounding, conservation, uncertainty, and evidence versus claims.
Predesign tag counts after the family audit, before item authoring/inference.

## What constitutes one family

A family is a typed reasoning graph: the roles of supplied observations and
unknowns, physical/biological assumptions, intervening constraints or causal
steps, required decision branches, and the requested conclusion. Numbers,
names, organism labels, units, wording, option order, requested unknown, or
tutoring mode alone do not create another family. Algebraic rearrangements
and invertible presentations of the same graph stay together. Apparent new
compositions must contain a necessary substantive reasoning step, not a
decorative extra calculation grafted onto a seen template.

For each proposed family, preserve a graph description, assumptions, admissible
variant bounds, excluded reductions, and a crosswalk to all observed training,
development, and known-suite families. Independent reviewers may merge proposal
IDs, reject them, or mark their relationship unresolved. An unresolved family
is not admitted to the strict primary fresh-family test. Shared arithmetic is
not by itself proof of an identical science graph, but a changed science story
is not proof of a new graph either. Resolve this boundary before outputs.

MC and written items use different original instances rather than duplicate
stems; shared graph IDs remain the same across both strata. If two families
are merged by review, retain the merged cluster for all comparisons. Do not
create one cluster per item, format, subject label, or question seed.

## Reference and verification contracts

The references below are **prospective source targets**, not checked citations.
No website or book was fetched for this task, no source licence was verified,
and no claim rests on a fabricated page/section number. Before admitting a
family, bind an actual edition/revision, relevant section/page, retrieval or
local-artifact identity, source licence/status, and a content hash. Author new
scenarios and wording; do not copy textbook exercises or exam questions.

| Reference code | Target material to acquire or locate and pin | Required evidence |
|---|---|---|
| PHY | OpenStax College Physics, relevant edition/section | Exact laws, conventions, assumptions and applicability bounds used in the family |
| CHE | OpenStax Chemistry 2e, relevant section | Chemical rules, reaction/particle assumptions, conditions and factual exclusions |
| BIO | OpenStax Biology 2e, relevant section | Biological mechanism, model limits and terminology; check secondary-school suitability |
| SI | BIPM SI Brochure, relevant edition/section | Unit definitions and conversions actually used; constants stated in prompts when needed |
| GIVEN | Original, fully stated tables, rules or finite models | Authored premise/rule manifest plus independently recomputed solutions; this checks consequences, not whether the model describes nature |

Verification labels used below:

- **A:** exact arithmetic/rational computation and rounding checks, independently
  implemented from the published problem, not merely rerunning its generator.
- **S:** symbolic or constraint verification, including domains, uniqueness and
  boundary cases; equivalence of an expression alone is insufficient.
- **U:** dimensions and conversion checks, including units on intermediate steps.
- **D:** finite enumeration, graph traversal, or truth-table checks with a
  separately reviewed rule set.
- **F:** source-backed factual and scientific-validity review. Arithmetic cannot
  establish that a law, organism claim, experimental conclusion or distractor
  premise is true. Every family needs F approval even when its key is executable.
- **R:** independent, mode-aware answer/rubric review. All written responses need
  R; a correct final number does not validate a hint or explanatory causal link.

No family is fully approved by an agent's unsupported confidence. Record whether
reviewers are agents or humans. A solver, its author and its own self-check are
not independent verification. A factual answer remains unverified until the
specific supporting source and independent reviewer are recorded.

## Physics: eight proposed reasoning graphs

Counts in the table are **MC / written**. All require F and R in addition to
the listed executable checks. The overlap column identifies review risks, not
clearance; all 24 proposals also require QASC/ARC/private-source/suite screening.

| ID; count | Concrete family graph and admissible variation | Independent reference/check contract | Overlap and exclusion boundary |
|---|---|---|---|
| P01; 25 / 25 | One-dimensional perfectly inelastic two-body collision: signed initial momenta plus a closed-system assumption → common final velocity → direction and energy-loss consistency. Vary positive masses and signed velocities; no ambiguous external impulse. | PHY momentum/collisions + GIVEN; A/S/U verify momentum conservation, unique velocity, nonnegative kinetic-energy loss. F checks model assumptions. | `force`, `kinetic_energy`, linear/simultaneous-equation families are components. Reject reductions to one known energy substitution or cosmetic rewrites of an existing collision template. |
| P02; 25 / 25 | A rigid horizontal beam with two vertical supports and off-centre loads: take signed moments and vertical-force balance → support reactions → contact-admissibility consistency check. Vary load locations within an explicitly stable support span; this check is not a new branch. | PHY static equilibrium + GIVEN; A/S/U independently solve both balances and substitute back; F verifies point-load/beam assumptions. | `force`, `work_done`, `simultaneous_equations` and generic lever items may overlap. Rotation balance must be a necessary step; changing the unknown reaction is not a new family. |
| P03; 20 / 20 | Explicit ideal circuit node/edge list with a switch and parallel branches: remove an open edge → determine connected current paths → compare branch operation before/after. State positive finite resistances; exclude source shorts, missing diagrams and implicit connections. | PHY DC circuits + GIVEN; D connectivity plus S/U where current comparisons are asked. F checks ideal-source/component assumptions. | `ohm_voltage` and `electrical_power` are not new when wrapped in a switch story. Hold if the graph collapses to a single resistor substitution or a known circuit template. |
| P04; 20 / 20 | Known mass initially fully solid at its melting point, with supplied latent heat and liquid specific heat: compare supplied heat with the melting budget → residual phase fraction or post-melt temperature. Inputs stay below boiling; no unmodelled heat loss. | PHY phase change/calorimetry + GIVEN; A/S/U check the piecewise boundary, conservation and units. F checks initial phase as well as temperature; melting-point temperature alone does not fix liquid fraction. | `energy_efficiency` and generic arithmetic branches can overlap. Latent/sensible branch selection must be necessary; new material names are not new families. |
| P05; 20 / 20 | A converging thin lens with a declared sign convention and object distance: lens constraint → signed image position → real/virtual classification and orientation/scale. Exclude exact focal singularity unless the intended key explicitly handles it. | PHY geometric optics + GIVEN; S/U solve with domain checks, A magnification, F verifies sign interpretation. | `magnification` is a component; simple image-size/actual-size division is excluded. Existing lens templates or reversed unknowns belong to the same family. |
| P06; 20 / 20 | A string fixed at both ends with two observed resonance modes labelled by mode number: infer the common fundamental → test whether a third stated resonance is consistent. Modes and idealized boundary conditions explicit. | PHY standing waves + GIVEN; A/S/U verify the integer-mode constraint and independent observations. | `wave_speed`, `arithmetic_sequence` and generic proportionality are high-risk neighbours. Hold unless review finds a genuinely different necessary boundary-condition/model-check graph. |
| P07; 20 / 20 | Repeated detector counts with a known constant background: subtract background → compare source count ratios over equal intervals → infer an integer number of half-lives and test a prediction. Use noiseless idealized expected counts, not false exact claims about random measurements. | PHY radioactive decay + GIVEN; A/S/U verify exponential relation and nonnegative source counts. F checks count/activity distinction and stated idealization. | Generic exponential/sequence tasks and known radiation questions need crosswalk review. Merely changing isotope names or count scales is not new. |
| P08; 20 / 20 | A closed conducting loop with positive finite resistance, an explicitly oriented normal and signed external flux table: identify increasing/decreasing/constant flux → induced field opposes the change → current sense under a given orientation convention. | PHY induction + GIVEN; D sign/rule table, S finite differences if requested; F/R check Lenz-law explanation and orientation consistency. | Avoid direct wave/electrical-power wrappers and previously used induction prompts. Direction labels cannot rely on an unseen drawing; a zero-change interval is not a new family. |

## Chemistry: eight proposed reasoning graphs

| ID; count | Concrete family graph and admissible variation | Independent reference/check contract | Overlap and exclusion boundary |
|---|---|---|---|
| C01; 25 / 25 | Given valid reactant/product species with coefficients missing: element counts → conservation constraints → unique smallest positive integer coefficient vector. Restrict to reactions whose chemistry and coefficient solution are independently verified. | CHE chemical equations + GIVEN; S integer/nullspace check, D atom-count substitution and normalization; F verifies actual reaction/conditions. | `stoichiometric_mole_ratio` assumes a balanced equation, but coefficient inference and DeepMind algebra may still overlap. Reject if the full graph is already represented; coefficients are not independent families. |
| C02; 20 / 20 | A specified redox transformation with the applicable oxidation-state rules: assign changed states → count electron loss/gain → identify oxidized/reduced species and the oxidizing agent. Avoid exceptions unless explicitly supplied. | CHE oxidation/reduction + GIVEN; D charge/electron bookkeeping with independently specified rules; F confirms chemistry and terminology. | Supplied-equation stoichiometry is related; a new element does not establish a new family. Elementary definition recall alone is excluded. |
| C03; 20 / 20 | Mix named dilute ionic solutions with a supplied finite solubility table: enumerate ion pairings → identify the unique insoluble product → cancel spectators and balance net ionic charge/atoms. | CHE precipitation/net ionic equations + GIVEN; D table lookup and S atom/charge checks; F verifies table scope and reaction assumptions. | Full QASC/ARC and private exam review essential. Do not treat different precipitates as independent families or add concentration arithmetic merely to disguise a known item. |
| C04; 20 / 20 | A sample chromatogram described by spot positions plus co-run reference lanes: compare matched migration ratios under the same conditions → infer compatible components → distinguish identification from proof of purity. | CHE separation/analytical principles + GIVEN; A/D position-ratio and match checks; F reviews the limits of identification. | Ratios and microscopy-style scale calculations are components. Unknown mixtures must be identifiable under the stated finite reference set; equal migration is not asserted to prove chemical identity generally. |
| C05; 20 / 20 | Paired reaction trials with one controlled factor varied and explicit gas-volume/time observations: identify a valid controlled comparison → derive the observed rate ordering → reject a confounded causal claim. | CHE reaction rates + GIVEN; A/U rate calculations, D factor-difference checks; F/R adjudicate the experimental inference. | `pulse_rate`/rate arithmetic alone is not fresh. Candidate keys cannot infer a universal mechanism from one invented table; graph may merge with B02 or B03 on independent review. |
| C06; 20 / 20 | Matched open/closed vessel mass records for a stated gas-forming reaction: track the defined system boundary → account for escaping material → evaluate an apparent violation of mass conservation. | CHE conservation/gas reactions + GIVEN; A mass balance, D system-boundary bookkeeping; F verifies reaction and what each scale measures. | `moles`, `molar_gas_volume`, `mass_percentage` may be nearby. A subtraction-only loss problem or a reworded known conservation example is excluded. |
| C07; 20 / 20 | Fixed amount of an ideal gas in two equilibrium states: convert absolute temperatures → combine pressure/volume/temperature constraints → accept or reject a proposed final state. State ideal-gas approximation and units. | CHE gas laws + SI + GIVEN; A/S/U cross-multiply the two-state invariant and check Kelvin values. | `molar_gas_volume`, `celsius_to_fahrenheit`, dilution/proportion and public algebra templates create substantial risk. Different gas labels or a rearranged unknown do not count as new. |
| C08; 20 / 20 | A finite table of solid, molten and aqueous conductivity plus melting behaviour: apply stated structural-model hypotheses → eliminate inconsistent hypotheses → identify what additional observation is needed when evidence remains ambiguous. | CHE bonding/structure/properties + GIVEN; D hypothesis-table consistency; F/R essential for exceptions and the warranted conclusion. | General QASC/ARC fact chains are likely neighbours. Do not assert properties uniquely identify all real substances; one fixed structural discrimination graph covers its material variants. |

## Biology: eight proposed reasoning graphs

| ID; count | Concrete family graph and admissible variation | Independent reference/check contract | Overlap and exclusion boundary |
|---|---|---|---|
| B01; 25 / 25 | Two compartments with explicitly water-permeable but solute-impermeable membrane and stated relative water potentials under controlled conditions: infer initial net water movement → compatible mass change → correct a reversed-direction explanation. | BIO membrane transport + GIVEN; D direction/constraint table, A only when a fully specified mass budget exists; F verifies osmosis assumptions. | No hidden inference from concentration alone when pressure or other solutes differ. `germination_percentage`/`mass_percentage` wrappers are excluded; likely QASC/ARC family exposure requires review. |
| B02; 20 / 20 | Controlled enzyme trials with a common endpoint and measured time: invert time to compare operational rates → separate substrate/pH/temperature changes → select the supported conclusion and an adequate control. | BIO enzymes + GIVEN; A/U endpoint-rate comparison, D controlled-factor check; F/R check mechanism versus evidence. | May merge with C05 as the same rate/control graph; enzyme vocabulary is not enough to keep a separate cluster. Do not claim a universal optimum from supplied observations. |
| B03; 20 / 20 | An explicitly controlled two-factor light/CO₂ table with a stated photosynthesis-rate measure: compare within-factor contrasts → identify context-dependent response/limitation → reject an unsupported single-factor explanation. | BIO photosynthesis + GIVEN; A contrast checks, D factor table; F/R adjudicate limitation and measurement assumptions. | May overlap C05/B02 or public experimental-design families. A different plant or rescaled rate table is not a new family; an uncontrolled factorial story is invalid. |
| B04; 20 / 20 | A small directed feeding network with declared short-term causal rules and unchanged other conditions: trace a specified intervention → distinguish a direct supported effect from an indirect, unresolved effect. | BIO ecology/food webs + GIVEN; D signed-path/rule enumeration; F/R verify biological plausibility and limits. | `population_density`, generic graph problems and QASC chains require crosswalk. Do not infer deterministic long-term population changes from feeding arrows alone. |
| B05; 20 / 20 | A diploid cell with chromosome-count convention stated: DNA replication then a specified division stage → track chromosomes versus chromatids per cell → detect a category/counting error. | BIO cell cycle/meiosis + GIVEN; D state-transition ledger, A integer counts; F checks stage and counting conventions. | `recessive_cross` is different in surface format, not automatic evidence of independence. Inheritance and public cell-division templates must be reviewed; ploidy rescaling is not a new family. |
| B06; 20 / 20 | A fully supplied dichotomous key with observed and unknown specimen features: traverse all compatible paths → obtain the remaining candidate set → select the next discriminating observation. | BIO classification/key use + GIVEN; D exhaustive key traversal and unique-query checks; F verifies descriptions and terminology. | DeepMind logic/lookup or known classification families may be equivalent. Taxon-name changes are not new; if multiple next observations are equally valid, rubric must allow all or reject the item. |
| B07; 20 / 20 | A habitat with specified strata and a proposed preferential sampling route: identify inclusion bias → choose a sampling allocation that can represent every stratum → delimit the inference justified by observed counts. | BIO ecological methods + GIVEN; D coverage/allocation checks, A only for explicitly specified weights; F/R verify representativeness assumptions. | `population_density`, probability/mean and generic sampling families are risk neighbours. Mere count/area computation is excluded; convenience versus random selection must be explicit. |
| B08; 20 / 20 | An explicit temperature-control feedback diagram represented as a signed rule list: disturbance → sensor/control response → effector action → tendency toward or away from the stated set point. Identify a broken link in a student's explanation. | BIO homeostasis + GIVEN; D rule composition and sign consistency; F/R verify physiology and terminology. | Public feedback/control questions may share the graph even across disciplines. This is classroom model reasoning, not diagnosis or treatment; relabelled feedback variables are not new families. |

## Known local-family overlap baseline

The active local generator has 30 families. Inspected generator file SHA-256:
`5e6a4ebe19a8de8c85dba45327cbc743ce7b19048b224eb9198b8dcbc9384631`.
Its science formula IDs inspected for this proposal are:

| Subject | Existing formula IDs: variants are not fresh-family evidence |
|---|---|
| Physics | `force`, `density`, `ohm_voltage`, `wave_speed`, `kinetic_energy`, `electrical_power`, `pressure`, `work_done` |
| Chemistry | `moles`, `concentration`, `dilution`, `molar_gas_volume`, `stoichiometric_mole_ratio`, `mass_percentage`, `neutralization_volume` |
| Biology | `magnification`, `population_density`, `recessive_cross`, `germination_percentage`, `pulse_rate` |
| Integrated science | `energy_efficiency`, `rectangular_tank_litres`, `celsius_to_fahrenheit` |

The seven active mathematics graphs are also exclusion neighbours: linear and
simultaneous equations, arithmetic sequences, means, triangle area, Pythagoras,
and percentage increase. The source's five quarantined generators (profit,
average speed, ratio, probability, interest) were designed after exposure to
known evaluation structure; quarantine does not make their associated known
test prompts fresh. The proposed families are not exempt merely because their
IDs are absent from `GENERATORS`.

The inventory additionally records 56 DeepMind module clusters, 878 TemplateGSM
clusters, GSM8K/QASC rows, private exam additions, and existing judges/STEM and
other known suites. These names/cluster counts are an inventory, not a semantic
crosswalk. No full-corpus or incumbent-data scan was performed for this design.
The exact old incumbent train/development files were absent from the initially
inspected local locations, but were subsequently located and hash/schema-checked
in place on Oracle; see the incumbent-coverage plan. Their availability does not
mean candidate overlap has been checked. Unknown pretraining remains unknown.

## Authoring and admission gates

1. Review the 24 graph definitions and all likely cross-family merges first.
   Pin sources and conventions; reject graphs too close to accessible prior
   examples before spending effort on many variants. Do not ask a candidate
   model to supply its own benchmark answers.
2. Author only self-contained original text/table items. Every required datum,
   unit, sign convention and idealization must be visible. No missing diagrams,
   copied question stems, fabricated experimental observations presented as
   real research, or hazardous hands-on laboratory instructions. Simulated
   observations must be explicitly labelled idealized or hypothetical.
3. Independently solve the visible problem and check every distractor against
   the same assumptions. Require exactly one MC key, plausible but demonstrably
   wrong distractors, and no answer-position or length shortcuts. Include edge
   and ambiguity checks without multiplying the independence count.
4. Produce executable A/S/U/D receipts where applicable, plus sourced F review
   and independent R review for the reference answer and every tutoring rubric.
   Record accepted alternatives and answer precision before outputs. Do not
   treat a generated reference as a publisher answer.
5. Run the reviewed audit tool against exact manifest-bound warehouse, selected
   training, development, incumbent, and known-suite inputs. Preserve compact
   hash-only match receipts; do not duplicate private corpus text. Lexical
   `no_flag_from_implemented_checks` is not family clearance. Resolve semantic
   and cross-namespace matches independently; reject unresolved items/families.
6. Freeze admitted family membership, item/source/verification hashes, quotas,
   mode-aware rubrics, grading/adjudication procedure, and statistical protocol
   before any finalist outputs. Existing audit schema carries review references
   but is not itself a scoring rubric or a proof of independent review.

Suggested written rubric dimensions are valid scientific premises, correct
necessary reasoning, correct units/conventions, and fulfillment of the requested
teaching mode. Freeze credits and central-error ceilings before scoring. A
Socratic hint can earn full mode credit without revealing the answer; a polished
hint based on a false premise cannot. Calibration requires independently graded
responses other than the locked finalist outputs. Do not infer human agreement
from agreement between related agents.

## Power and scope limits

- The proposed 1,000 rows contain at most **24 family clusters**, not 1,000
  independent science problems. Each subject has at most eight; merges or
  exclusions can lower this. Because the same graph appears in both MC and
  written strata, resample its paired item bundle across both together.
- More variants improve within-family measurement but cannot manufacture
  independent coverage. As an illustration only, with average cluster size
  about 41.7, the exchangeable-correlation design-effect approximation
  `1 + (41.7 - 1) * rho` gives an effective item count around 109 at rho=0.2,
  and about 24 at rho=1. This is not a power calculation for the paired,
  unequal-size, multi-stratum comparison or a substitute for cluster counts.
- Assess paired cluster-level variability and plausible discordance/rubric
  scenarios using nonfinalist calibration or prespecified simulations before
  unblinding. Include all planned contender comparisons and predeclared
  regression checks. The proposed +2-point primary gain and 3-point stratum
  margin are not proven detectable by these quotas. Eight subject clusters
  cannot justify precise broad subject-level superiority claims by default.
- If adequate family coverage/power cannot be established under strict
  exclusion, record the test as a limited or exploratory comparison, or revise
  the design before inference with explicit authorization. Do not silently
  relabel same-family variants as novel, weaken the outcome rule, inflate the
  family count, or extend the test after seeing which candidate leads.
- This deliberately small graph inventory omits substantial secondary science
  breadth (for example much organic chemistry, taxonomy, human systems and
  practical/visual work). A conditional win here is not mastery of every WAEC
  paper, proof of actual learning gains, or target-CPU deployment qualification.

Next bounded action: independent blueprint review, then a family/source
feasibility gate. No question materialization or reference acquisition is part
of this document-only task.

## Blueprint review record

Independent agent reviewer `winner_protocol_review` checked the complete
proposal and its allocations. Their concrete P04 finding was corrected by
stating the initially fully solid phase; temperature at melting point alone
does not determine the latent-heat budget. P02's contact check was clarified
as a consistency check, not another branch. Review approves this conditional
design only, not the proposed families' independence, source claims, answer
keys, curriculum calibration, statistical power, or readiness for inference.
