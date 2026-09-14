# Fine-tuned Qwen2.5 control: Mac STEM audit

All 100 Mac Metal raw-completion responses were read in full. This is an AI-assisted semantic audit, not an official ADTC grade, chat-template test or CPU performance result. It is separate from the GCP scalar audit.

| Category | Strict pass | Core answer correct | Questions |
|---|---:|---:|---:|
| Mathematics multiple choice | 22 | 23 | 25 |
| Written mathematics | 11 | 21 | 25 |
| Science multiple choice | 20 | 23 | 25 |
| Written science | 4 | 13 | 25 |
| **Total** | **57** | **80** | **100** |

The original option parser recorded 44/50: 21 mathematics and 23 science. This counts extracted option letters, not complete correct explanations. M08, M12 and M14 uniquely identify the correct numerical option without its letter and pass semantic grading. Seventeen responses reached their output-token limit.

## Grading policy

Strict pass requires a correct answer, correct requested working or explanation, all substantive requested components, and no unresolved material contradiction. Explicitly requested checks require inverse arithmetic, substitution or a distinct correct numerical method; repeating a derivation or saying it checks out is insufficient. A genuine check of a substantive intermediate constraint is sufficient without rechecking every substep.

Core-answer correctness records whether the main value or scientific conclusion is right despite missing checks or faulty support. It is a diagnostic, not a tutoring-quality or competition score. Correct values uniquely selecting an option can pass without a letter; explicitly wrong labels cannot. Self-correction is accepted when the error is resolved. Token-limit stops, repetition and length-format excess are not automatic failures, but incorrect continued text still counts. Unsafe advice fails a requested safety component even if a safe alternative also appears.

## Response decisions

`Pass` is the strict instruction-complete judgment; `Core` records the main answer separately. Exact response hashes and source lines are in [the JSON ledger](qwen25-control.json).

### Mathematics multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M01 | Yes | Yes | Selects C and calculates 6 × 500 = ₦3,000. |
| M02 | Yes | Yes | Selects C and calculates 8 × 250 = ₦2,000. |
| M03 | Yes | Yes | Selects D and divides 36 pupils by 6 groups to obtain 6. |
| M04 | Yes | Yes | Selects B and calculates 60 × 3 = 180 km. |
| M05 | Yes | Yes | Selects D and calculates 8 × 5 = 40 m². |
| M06 | Yes | Yes | Selects A and calculates 80 ÷ 4 = 20 mangoes. |
| M07 | No | No | Reverses the change subtraction to 1,800 − 5,000 = −3,200, claims payment was insufficient, and rejects the correct positive ₦3,200 despite mentioning option C. |
| M08 | Yes | Yes | Calculates 18 + 22 = 40 pupils, uniquely identifying B; the letter is omitted. |
| M09 | Yes | Yes | Selects D and calculates 15 − 3 = 12 good mangoes. |
| M10 | Yes | Yes | Selects A and calculates 4 × 2 = 8 litres. |
| M11 | Yes | Yes | Selects B and correctly calculates 15/100 × ₦2,000 = ₦300 before repeating it. |
| M12 | Yes | Yes | Calculates 3/5 × 25 = 15 blue beads, uniquely identifying C without its letter. |
| M13 | No | No | Selects C, ₦1,500, and also miscalculates the simple interest as ₦2,000; neither gives the correct ₦1,000. |
| M14 | Yes | Yes | Adds 12 + 15 + 18 = 45 and divides by 3 to obtain 15, uniquely identifying B without its letter. |
| M15 | Yes | Yes | Selects B and correctly calculates perimeter 2 × (9 + 4) = 26 m before repetition. |
| M16 | Yes | Yes | Selects C and correctly solves 3x + 5 = 20 to obtain x = 5. |
| M17 | Yes | Yes | Selects C and calculates three-quarters of 120 as 90. |
| M18 | Yes | Yes | Selects B and gives the correct conversion equation 2.5 km = 2,500 m. |
| M19 | No | Yes | States the correct ₦200 profit and 25% profit percentage with option B, but omits the requested calculation. |
| M20 | Yes | Yes | Selects C and calculates average speed as 150 ÷ 3 = 50 km/h. |
| M21 | Yes | Yes | Selects B; explicitly totals 3 + 7 = 10 counters and obtains 3/10. |
| M22 | Yes | Yes | Selects B and subtracts 50° + 60° from 180° to obtain 70°. |
| M23 | Yes | Yes | Selects A and takes √144 = 12 cm. |
| M24 | Yes | Yes | Selects C and uses prime factors to obtain highest common factor 6. |
| M25 | Yes | Yes | Selects C and adds the common difference 3 to 14, obtaining 17. |

### Written mathematics

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M26 | No | Yes | Correctly derives ₦400 per remaining tuber from ₦18,000/45, but omits the requested numerical check of the revenue or profit. |
| M27 | No | Yes | Correctly obtains 25 − 3 × 7 = 4 GB, but performs no independent check. |
| M28 | Yes | Yes | Finds Bisi = 12 and Ada = 24, then explicitly verifies their sum is 36. |
| M29 | No | Yes | Finds discount ₦600 and new price ₦4,400. The stated check merely repeats that ₦4,400 is ₦600 less than ₦5,000; it performs no reverse arithmetic or rate verification. |
| M30 | No | Yes | Correctly calculates 120 − 3 × 8 = 96 litres, but omits the requested check. |
| M31 | Yes | Yes | Corrects the distribution to 2x + 6 and verifies equivalence by substituting a value of x. |
| M32 | Yes | Yes | Correctly identifies 1/12 used for beans and 1/4 of the farm left unused. |
| M33 | No | Yes | Finds the correct ₦300 pen price, but checks one notebook plus pen as 400 + 300 = 700 while claiming this equals the ₦1,100 total. |
| M34 | No | No | Recognizes increasing differences but gives the next term as 16 using 12 + 4 instead of 30. |
| M35 | No | Yes | Correctly scales the flour ratio to 10 cups for 25 loaves, but does not perform the requested check. |
| M36 | Yes | Yes | Converts 18 months to 1.5 years and correctly obtains ₦6,000 simple interest and ₦56,000 total. |
| M37 | Yes | Yes | Finds original rent ₦30,000 and checks that its ₦6,000 increase produces ₦36,000. |
| M38 | Yes | Yes | Uses π = 22/7 correctly to obtain circumference 44 m and area 154 m². |
| M39 | No | Yes | Correctly derives length 10 m using Pythagoras, but does not independently substitute the result to perform the requested check. |
| M40 | Yes | Yes | Correctly counts 7 non-blue counters among 10 and obtains probability 7/10. |
| M41 | No | No | Gives 75 instead of 90 and falsely claims that the resulting four-score mean is 75. |
| M42 | No | No | Gives six meals rather than four and contradicts the ₦5,000 budget and remaining amount after transport. |
| M43 | No | Yes | Correctly computes ₦78,000 + ₦8,000 = ₦86,000 but supplies no separate requested check. |
| M44 | No | Yes | Correctly gives median 7 and mode 7, but repeatedly makes the false general claim that the median is less affected by outliers than the mode. |
| M45 | No | No | Rejects the student's correct 20, confuses the requested percentage with 25/80, and concludes 31.25%. |
| M46 | Yes | Yes | Correctly applies 7.2 cm × 5 km/cm = 36 km. |
| M47 | Yes | Yes | Correctly computes four pumps × 15 litres/minute × 12 minutes = 720 litres. |
| M48 | Yes | Yes | Solves x = 8 and verifies that both sides of the original equation equal 30. |
| M49 | Yes | Yes | Correctly subtracts the 2 × 3 platform from the 10 × 8 floor to obtain 74 m². |
| M50 | No | Yes | Correctly rejects the converse and gives a valid 3 × 4 rectangle, but also calls a 2 × 2 square a rectangle that is not a square and misstates the logical classification. |

### Science multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S01 | Yes | Yes | Selects photosynthesis and correctly describes sunlight enabling conversion of carbon dioxide and water to glucose and oxygen. |
| S02 | Yes | Yes | Selects the heart and explains blood pumping by contraction and relaxation. |
| S03 | No | Yes | Selects evaporation and describes escaping water molecules correctly, but incorrectly groups freezing with condensation as opposite processes to evaporation. |
| S04 | Yes | Yes | Selects oxygen and explains its role in aerobic glucose breakdown; repetition introduces no material contradiction. |
| S05 | Yes | Yes | Selects gravity and explains Earth's mass attracting objects. |
| S06 | Yes | Yes | Selects roots and links their extensive surface area to uptake of soil water and minerals. |
| S07 | Yes | Yes | Selects 100°C and explains equality of water vapour pressure and standard sea-level atmospheric pressure. |
| S08 | No | Yes | Selects the Sun and describes Earth's orbit correctly, then says stars such as the Sun are not the primary object Earth revolves around. |
| S09 | Yes | Yes | Selects an inclined plane and explains that a sloping surface raises a load with less effort. |
| S10 | Yes | Yes | Selects red blood cells and explains oxygen carriage. The diffusion statement can describe gas loading/unloading across their membrane; plasma is correctly identified as liquid. |
| S11 | No | Yes | Selects the ampere and distinguishes other units, but invents an incorrect force-based and volt-per-metre definition of an ampere. |
| S12 | No | No | Selects D, stays blue, while its explanation says acid turns blue litmus red; the contradiction is unresolved. |
| S13 | Yes | Yes | Selects Newton's second law and correctly relates acceleration to net force and mass. |
| S14 | Yes | Yes | Selects mitochondria and explains usable energy release through cellular respiration. |
| S15 | Yes | Yes | Selects oxygen and correctly explains its production during photosynthesis; other-gas exclusions are scoped to that process. |
| S16 | Yes | Yes | Selects vacuum and explains that sound requires a material medium. |
| S17 | Yes | Yes | Selects mass divided by volume and correctly explains mass per unit volume. |
| S18 | No | No | Chooses oxygen while listing carbon as atomic number 6, and never resolves the contradiction. |
| S19 | Yes | Yes | Selects H₂O and explains the two-to-one ratio of hydrogen to oxygen atoms. |
| S20 | Yes | Yes | Selects solar energy and contrasts natural replenishment with finite fossil fuels. |
| S21 | Yes | Yes | Selects ovum and identifies it as the female gamete; the later explicit male/female distinction resolves the earlier awkward plural wording. |
| S22 | Yes | Yes | Selects the troposphere and identifies it as the lowest atmospheric layer in which most weather occurs. |
| S23 | Yes | Yes | Selects oxygen and water and explains their reaction with iron to form rust. |
| S24 | Yes | Yes | Selects solids and explains conduction through closely packed interacting particles. |
| S25 | Yes | Yes | Selects neutral and explains equal hydrogen and hydroxide ion concentrations at the school-level reference conditions. Generic concentration labels do not uniquely classify acidity. |

### Written science

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S26 | No | No | Falsely says both balls experience the same gravitational force and repeatedly alternates between calling the student's reasoning correct and mistaken. |
| S27 | No | Yes | Correctly identifies cooling by evaporation, but says evaporation releases required heat, calls escaping molecules highest in potential energy, and reverses whether taking heat from skin cools it. |
| S28 | No | No | Fails to identify an open series circuit and gives contradictory current/resistance and parallel-brightness predictions. |
| S29 | No | No | Provides neither destarching nor an iodine starch test and places the purported light condition in darkness; leaf appearance is not a valid starch assay. |
| S30 | No | No | Alternates density and buoyancy criteria with reversed upthrust inequalities and supplies no valid counterexample to the heavy-object claim. |
| S31 | Yes | Yes | Correctly identifies a cold as viral and explains that antibiotics treat bacterial rather than viral infections. |
| S32 | No | Yes | Correctly links altitude to reduced oxygen availability, but falsely says reduced air pressure pushing on the body makes moving air harder. |
| S33 | No | No | Explains the sensation through metal losing heat to wood or a hotter object rather than faster heat transfer from the hand at equal room temperature. |
| S34 | No | Yes | Identifies opposing hemispheric tilts and Earth's January proximity, but gives no heating/day-length mechanism or explicit opposing-seasons observation. |
| S35 | Yes | Yes | Correctly uses Ohm's law to obtain 2 A then 1 A when resistance doubles at fixed voltage. |
| S36 | Yes | Yes | Correctly classifies dissolving sugar as physical and burning it as chemical, explaining unchanged sugar identity versus formation of new substances. |
| S37 | No | Yes | States closed-system mass is constant, but gives a contradictory before/after mass-difference account and denies or omits escaping-gas loss in an open container. |
| S38 | No | No | Repeats the question and lists unrelated pH values without identifying the reaction, its products or the required alkaline-to-neutral trend. |
| S39 | No | Yes | Correctly identifies midday water loss exceeding uptake and evening recovery, but twice reverses the direction of water movement down a water-potential gradient. |
| S40 | No | Yes | Recognizes drift and mutation as reasons dominance need not control frequency, but wrongly makes A dominant over B, misdefines allele frequency, denies selection changes it, and never completes the inheritance distinction. |
| S41 | No | No | Predicts more frogs and snakes after grasshoppers decline, incorrectly claiming fewer grasshoppers provide more food and energy. |
| S42 | No | Yes | Identifies fertilizer amount, plant height, controls and repeats correctly, but assigns three groups of five pots after specifying ten pots. |
| S43 | No | Yes | Calculates 4 m/s² correctly, but describes speed increasing by 4 m/s² instead of 4 m/s each second. |
| S44 | No | No | Ends by claiming a blunt larger-area blade has lower pressure and therefore cuts more easily, contradicting the correct pressure-based explanation. |
| S45 | No | Yes | Correctly links wet hands to lower resistance and greater current, but provides no requested safety action and repeats an invented universal water-resistance value. |
| S46 | No | No | Says Earth's shadow causes phases and gives contradictory eclipse geometry instead of distinguishing the two phenomena. |
| S47 | No | No | Generates further questions about altitude rather than explaining boiling through equality of vapour and atmospheric pressure. |
| S48 | No | No | Lists reactants and products but incorrectly says respiration converts chemical energy into light, failing the requested energy comparison. |
| S49 | Yes | Yes | Rejects immediate cure and explains antigen recognition, antibodies and a faster response on later exposure. The weakened/dead-agent example is accepted as a level-appropriate mechanism, not an exhaustive vaccine taxonomy. |
| S50 | No | No | Leaves the cause, transmission and prevention as blanks and repeats them without answering. |

## Reviewed boundaries

Second review retained the following decisions:

- M29 fails: its stated check restates the original subtraction without inverse arithmetic or rate verification.
- S03 fails: freezing is incorrectly described as the reverse of evaporation.
- S10 passes: diffusion can describe gas exchange across blood-cell membranes; the response does not say diffusion replaces circulation.
- S34 fails: opposite hemispheric tilts are stated, but their heating effect and opposing seasons are not explained.
- S43 fails: 4 m/s² is calculated, but its numerical meaning is not expressed as 4 m/s gained each second.
- S49 passes: its common vaccine mechanism is an acceptable explanation at the requested level, not an exhaustive taxonomy.
- S40 has a correct core answer only in the limited sense that drift and mutation can change frequencies independently of dominance. Incorrect genetic definitions, the false selection claim and the incomplete inheritance distinction make the full answer fail.

## Provenance and limits

The check-policy clarification was applied to all seven missing-check responses (M26, M27, M29, M30, M35, M39, M43). None supplies an alternative numerical method; no grade changed.

- Model: `Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf`, SHA-256 `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`.
- Source: [Mac responses](../mac-accuracy/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf/stem/responses.jsonl), SHA-256 `76da3b4134bafa42074f91a3e7b090ec2cb4e6581f50777971cf6dbeadae1c6f`.
- Settings: [stage configuration](../mac-accuracy/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf/stem/config.json), SHA-256 `2078bdd3803074749362d5e068389984c6366269a7332b157962e14c2ab89010`.
- Lifecycle: [stage events](../mac-accuracy/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf/stem/events.jsonl), SHA-256 `94fff83ab4ba470fb3124872e561a6480d850e93fb817bbf0bb3b0208eede393`.
- Hardware context: `apple_m4_pro_24gib_macos_metal_b10175`; two CPU threads, 99 requested GPU layers, explicit 256 MiB host-cache cap and 2,048 context tokens.
- Raw `/completion`: temperature 0, seed 42, 256-token multiple-choice limit, 512-token written limit, no embedded chat template or external system prompt, prompt caching disabled.
- Server SHA-256: `f497d6b948174173f8159b6fa46c7b4816e2ecfd306ae9c0f7f11e6a7a79af88`. The archive-built executable reports version 0 (unknown); source revision `60bccc3763395e01b039aa1ddeacc8cc0ea69f70` is an operator-supplied declaration paired with that verified binary hash.
- Actual offloaded-layer placement and continuous host isolation are not established by the response rows. These are accuracy-screen outputs, not laptop throughput or memory evidence.
- All 100 unique IDs, exact prompts, expected fields and model hashes match the fixed suite; each category contains 25 questions. Raw files were not changed.
- Thirteen responses exactly match the same model's GCP response hashes: M02, M05, M06, M08, M09, M11, M21, M39, M41, M47, S16, S17 and S26. Only these judgments were reused. The other 87 returned texts were reviewed independently; hardware contexts were not pooled.
