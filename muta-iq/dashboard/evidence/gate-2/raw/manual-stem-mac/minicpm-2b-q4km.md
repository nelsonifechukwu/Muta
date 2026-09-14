# MiniCPM5 2B Q4_K_M: Mac STEM audit

All 100 returned Mac raw-completion texts were reviewed in full. This AI-assisted semantic audit is separate from GCP results and is not an official ADTC grade or a chat-template test.

| Category | Strict pass | Core answer correct | Questions |
|---|---:|---:|---:|
| Mathematics multiple choice | 9 | 13 | 25 |
| Written mathematics | 4 | 9 | 25 |
| Science multiple choice | 1 | 3 | 25 |
| Written science | 3 | 10 | 25 |
| **Total** | **17** | **35** | **100** |

The original option parser recorded 10/50 (8 mathematics, 2 science). That extraction count is not a grade of the explanation. 78 responses reached their output limit; 2 were empty.

## Policy

Strict pass requires the correct answer, requested working or explanation, all substantive requested components and no unresolved material error. A requested check may use inverse arithmetic, substitution or a distinct correct numerical method. Repeating the same calculation or asserting correctness is insufficient; checking every intermediate step is unnecessary.

Core-answer correctness separately records the main value or conclusion despite incomplete instructions or faulty support. Correct option values can pass without a letter; wrong explicit labels fail unless genuinely corrected. Length, repetition and token-limit stops are not independent failures once a complete correct answer exists. False continued explanations still count, including in visible reasoning text. Unsafe advice fails a requested safety component even alongside a safe alternative.

## Decisions

### Mathematics multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M01 | No | No | Generates other shopping questions without answering the chalk-cost question. |
| M02 | No | No | Generates other arithmetic questions without answering the exercise-book cost. |
| M03 | Yes | Yes | Selects D and calculates 36 ÷ 6 = 6. |
| M04 | Yes | Yes | Selects B and calculates 60 × 3 = 180 km. |
| M05 | No | Yes | Calculates area 40 m² correctly but repeatedly selects C, 26 m². |
| M06 | No | No | Selects B, 10 after incorrectly dividing the correct quarter by two again. |
| M07 | No | No | Generates other price questions without calculating Chidi's change. |
| M08 | No | No | Generates other class-count questions without answering 18 + 22. |
| M09 | No | No | Generates other spoilage questions without answering the mango question. |
| M10 | No | Yes | Names A, 8 litres but changes four containers to three and gives contradictory working 3 × 2 = 6. |
| M11 | Yes | Yes | Selects B and computes 2,000 × 15% = ₦300. |
| M12 | No | No | Reverses the red:blue ratio and gives 10 blue beads instead of 15. |
| M13 | Yes | Yes | Selects B and correctly computes ₦10,000 × 5% × 2 = ₦1,000. |
| M14 | No | No | Generates unrelated arithmetic questions without giving the requested mean. |
| M15 | Yes | Yes | Selects B and computes 2 × (9 + 4) = 26 m. |
| M16 | No | No | Repeats empty final-answer headings without solving x. |
| M17 | No | Yes | Gives the correct 90 without an option letter, but no requested calculation. |
| M18 | No | No | Only enumerates integers; gives no conversion answer. |
| M19 | No | Yes | Correctly gives 25% without its option letter but supplies no calculation. |
| M20 | Yes | Yes | Calculates 150 ÷ 3 = 50 km/h, uniquely identifying C without its letter. |
| M21 | Yes | Yes | Selects B and correctly computes 3/(3 + 7) = 3/10. |
| M22 | Yes | Yes | Selects B and calculates 180 − (50 + 60) = 70°; subsequent separate examples have correct numerical answers. |
| M23 | No | No | Generates other shape questions without answering the square's side length. |
| M24 | Yes | Yes | Selects C, lists factors correctly and identifies the greatest shared value 6. |
| M25 | No | No | Repeats the question and generates further sequences without selecting or calculating a next term. |

### Written mathematics

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M26 | No | Yes | Correctly derives ₦400 per tuber but gives no requested check before switching to share-trading examples. |
| M27 | No | No | Generates other data-use questions without answering this one. |
| M28 | Yes | Yes | Finds Ada 24 and Bisi 12 and explicitly checks their sum is 36. |
| M29 | No | Yes | Correctly derives discount ₦600 and new price ₦4,400; the check only asserts correctness and restates the original percentage. |
| M30 | No | No | Generates other arithmetic questions without calculating the remaining water. |
| M31 | No | No | Generates lesson/website recommendations and other exercises without correcting the expansion. |
| M32 | No | No | Generates other problems without finding the unused farm fraction. |
| M33 | No | No | Changes two notebooks to five, derives negative ₦900 and falsely declares the problem inconsistent. |
| M34 | No | No | Produces a lesson plan and other sequence exercises without giving the rule or next term. |
| M35 | No | No | Generates other ratio questions without answering flour needed for 25 loaves. |
| M36 | No | No | Repeats the interest question in numbered steps without calculating interest or total. |
| M37 | No | No | Generates pay questions without finding the original amount. |
| M38 | No | No | Generates other garden questions without calculating the requested circumference and area. |
| M39 | No | No | Lists instructions to calculate and verify, but performs neither and gives no ladder length. |
| M40 | Yes | Yes | Counts 7 non-blue among 10 counters, gives 7/10 and confirms by the complementary probability. |
| M41 | No | No | Generates other missing-score questions without solving the supplied mean problem. |
| M42 | No | No | Only repeats the budget question without giving meals or money remaining. |
| M43 | No | No | Generates other questions without computing the cement and delivery cost. |
| M44 | No | Yes | Correctly gives median and mode 7, but adds an incorrect coefficient of variation of 0.5 and repeats unsupported statistics. |
| M45 | No | Yes | States the student's 20 is correct but supplies no calculation or explanation of what 25% means. |
| M46 | Yes | Yes | Correctly computes 7.2 cm × 5 km/cm = 36 km. |
| M47 | No | No | Generates other pump/garden questions without the requested total volume. |
| M48 | No | No | Returns an empty response. |
| M49 | Yes | Yes | Calculates floor 80 m² minus platform 6 m² to obtain 74 m². |
| M50 | No | Yes | Identifies the true implication and false converse but never supplies a counterexample, and explicitly reverses valid and invalid modus-ponens patterns. |

### Science multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S01 | No | No | Generates other plant questions without answering how sunlight makes food. |
| S02 | No | No | Generates other health questions without identifying the blood-pumping organ. |
| S03 | No | No | Selects condensation while correctly describing it as the reverse of the requested change; never identifies evaporation. |
| S04 | No | No | Generates other respiration questions without naming oxygen for the supplied question. |
| S05 | No | No | Generates battery questions without answering the gravity question. |
| S06 | No | No | Generates photosynthesis questions without identifying roots. |
| S07 | No | Yes | Gives sea-level 100°C but repeatedly adds the false claim that mountain water boils at 212°C. |
| S08 | No | Yes | Selects the Sun but only restates that Earth orbits it rather than the other options; no substantive explanation is supplied. |
| S09 | No | No | Generates other simple-machine questions without identifying the inclined plane. |
| S10 | No | No | Generates health questions without naming red blood cells. |
| S11 | No | No | Only repeats the question and all options without selecting or explaining a unit. |
| S12 | No | No | Selects stays blue while its explanation also says acid turns blue litmus red; the contradiction is unresolved. |
| S13 | No | No | Generates other electricity questions without identifying Newton's second law. |
| S14 | No | No | Generates other cell questions without naming the mitochondrion. |
| S15 | No | No | Generates health questions without answering the photosynthesis gas question. |
| S16 | No | No | Generates sound-speed questions without identifying vacuum as the medium in which sound cannot travel. |
| S17 | No | No | Generates spring/thermodynamics questions without defining density. |
| S18 | No | No | Generates chemical-property questions without identifying carbon. |
| S19 | No | No | Asks about a nonexistent S in H₂O instead of supplying a correct formula and explanation for water. |
| S20 | No | No | Generates sustainability questions without selecting solar energy. |
| S21 | Yes | Yes | Selects ovum and explains its release during ovulation. |
| S22 | No | No | Generates atmosphere questions without identifying the troposphere. |
| S23 | No | No | Generates fire-safety questions without identifying oxygen and water for rusting. |
| S24 | No | No | Generates temperature/energy questions without identifying strongest conduction in solids. |
| S25 | No | No | Generates unrelated pH questions without naming neutral pH 7. |

### Written science

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S26 | No | Yes | Correctly explains mass-independent acceleration using F/m, but twice claims the student confuses weight with gravitational force although these are the same quantity in its explanation. |
| S27 | No | Yes | Describes faster molecules escaping with energy, but never connects the cooling to energy taken from the pupil's skin. |
| S28 | No | No | Gives wrong resistance/current changes after removal and claims unequal voltage drops in parallel; never gives correct on/off behavior. |
| S29 | No | Yes | States the correct light requirement for starch production but provides no experiment, control or starch-test observations. |
| S30 | No | No | Generates other buoyancy questions with false premises rather than explaining density/upthrust and a counterexample. |
| S31 | No | No | Returns an empty response. |
| S32 | No | Yes | Recognizes increased breathing compensates for reduced oxygen, but omits the requested pressure mechanism and attributes the response to increased oxygen demand. |
| S33 | No | No | Generates other heat-transfer questions without explaining why equal-temperature metal feels colder. |
| S34 | Yes | Yes | Rejects distance as the cause, identifies axial tilt and gives the hemispheres' opposite summer timing. Awkward direct-rays wording is not a material error. |
| S35 | Yes | Yes | Calculates 2 A then 1 A at fixed voltage and gives correct supporting power and resistance relations. |
| S36 | No | No | Repeats classifications to be performed but never classifies sugar dissolving or burning. |
| S37 | No | No | Generates other chemistry questions with false numerical premises rather than explaining conservation of mass. |
| S38 | No | No | Reverses the acid-into-base pH trend, says excess acid increases pH and omits the required products. |
| S39 | No | No | Generates other plant questions without explaining the stated midday wilt and evening recovery. |
| S40 | No | Yes | Rejects dominance determining frequency but treats Hardy–Weinberg as its determining cause and never clearly distinguishes phenotype expression from transmission probability. |
| S41 | No | No | Invents a different grasshopper scenario, claims frog numbers are unaffected and gives no correct downstream energy explanation. |
| S42 | No | No | Gives instructions to analyze results and extend a future experiment, not the requested variables, controls and repeats. |
| S43 | No | Yes | Calculates 4 m/s², then inconsistently says speed increases by 8 m/s in the second second and 12 m/s in the third. |
| S44 | No | No | Generates other physics questions without explaining sharp-blade pressure. |
| S45 | No | No | Generates electrical-safety questions without explaining wet-skin resistance/current or giving the requested action. |
| S46 | No | No | Provides only a new-Moon hint before unrelated exercises; omits the phase mechanism and lunar-eclipse explanation. |
| S47 | Yes | Yes | Explains lower atmospheric pressure and vapour-pressure equality at a lower boiling temperature; later measurement examples add no definite contradictory result. |
| S48 | No | No | Discusses ATP and respiration but omits the required photosynthesis comparison, complete reactants/products and their linkage. |
| S49 | No | Yes | Explains adaptive memory and future responses but corrects a different claim about vaccines causing disease, never addressing the requested immediate-cure claim. |
| S50 | No | No | Generates unrelated sunlight questions without answering malaria cause, transmission or prevention. |

## Review boundaries

- S08: second-review decision — fail. Selects the Sun but only restates that Earth orbits it rather than the other options; no substantive explanation is supplied.
- S26: second-review decision — fail. Correctly explains mass-independent acceleration using F/m, but twice claims the student confuses weight with gravitational force although these are the same quantity in its explanation.
- S27: second-review decision — fail. Describes faster molecules escaping with energy, but never connects the cooling to energy taken from the pupil's skin.
- S34: second-review decision — pass. Rejects distance as the cause, identifies axial tilt and gives the hemispheres' opposite summer timing. Awkward direct-rays wording is not a material error.
- S40: second-review decision — fail. Rejects dominance determining frequency but treats Hardy–Weinberg as its determining cause and never clearly distinguishes phenotype expression from transmission probability.

## Provenance

- Exact model: `MiniCPM5-2B-Q4_K_M.gguf`, SHA-256 `ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd`.
- [Responses](../mac-accuracy/MiniCPM5-2B-Q4_K_M.gguf/stem/responses.jsonl): SHA-256 `afeabf3cdb05a8eb7fb774f4e4eaa9461dba5458372cd17e23b058f52b585a09`.
- [Configuration](../mac-accuracy/MiniCPM5-2B-Q4_K_M.gguf/stem/config.json): SHA-256 `12dc41283250ca18c6c700a87cbec5060652d81252babac80e5c487f93b2b0ca`.
- [Lifecycle](../mac-accuracy/MiniCPM5-2B-Q4_K_M.gguf/stem/events.jsonl): SHA-256 `47419b79d7dfdcd0400326a81b1e5bfbf967d4334d75bec031e0d17f85e7aa9d`.
- Hardware: `apple_m4_pro_24gib_macos_metal_b10175`; two CPU threads, 99 requested GPU layers, 256 MiB host-cache cap, 2,048-token context.
- Raw `/completion`: temperature 0, seed 42, 256/512 output tokens for multiple-choice/written prompts, no chat template or external system prompt, prompt caching disabled.
- Server SHA-256 `f497d6b948174173f8159b6fa46c7b4816e2ecfd306ae9c0f7f11e6a7a79af88`; archive source declaration `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`. The executable reports version 0 (unknown); the source declaration is not independently identified by its version string.
- Actual layer placement and continuous host isolation are not proven by response rows. These results do not measure laptop throughput or RAM.
- All 100 unique IDs, exact prompts, expected fields and model hashes match the fixed suite. The [JSON ledger](minicpm-2b-q4km.json) retains every source line and response hash. No raw response was changed or pooled with another hardware context.
