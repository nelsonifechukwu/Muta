# Qwen3 1.7B Q4_0: Mac STEM audit

All 100 returned Mac raw-completion texts were reviewed in full. This AI-assisted semantic audit is separate from GCP results and is not an official ADTC grade or a chat-template test.

| Category | Strict pass | Core answer correct | Questions |
|---|---:|---:|---:|
| Mathematics multiple choice | 15 | 20 | 25 |
| Written mathematics | 21 | 24 | 25 |
| Science multiple choice | 16 | 24 | 25 |
| Written science | 7 | 13 | 25 |
| **Total** | **59** | **81** | **100** |

The original option parser recorded 37/50 (14 mathematics, 23 science). That extraction count is not a grade of the explanation. 100 responses reached their output limit.

## Policy

Strict pass requires the correct answer, requested working or explanation, all substantive requested components and no unresolved material error. A requested check may use inverse arithmetic, substitution or a distinct correct numerical method. Repeating the same calculation or asserting correctness is insufficient; checking every intermediate step is unnecessary.

Core-answer correctness separately records the main value or conclusion despite incomplete instructions or faulty support. Correct option values can pass without a letter; wrong explicit labels fail unless genuinely corrected. Length, repetition and token-limit stops are not independent failures once a complete correct answer exists. False continued explanations still count, including in visible reasoning text. Unsafe advice fails a requested safety component even alongside a safe alternative.

## Decisions

### Mathematics multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M01 | Yes | Yes | Selects C and calculates 6 × 500 = ₦3,000; later repeated prompt text adds no contrary answer. |
| M02 | Yes | Yes | Selects C and calculates 8 × 250 = ₦2,000 before an unfinished repeated explanation. |
| M03 | Yes | Yes | Selects D and repeatedly calculates 36 ÷ 6 = 6 correctly. |
| M04 | Yes | Yes | Corrects the initial 240 km to 60 × 3 = 180 km and explicitly rejects 240; 180 uniquely identifies B despite confused commentary about the options. |
| M05 | Yes | Yes | Selects D and calculates 8 × 5 = 40 m². |
| M06 | Yes | Yes | Recognizes that 80 ÷ 4 = 20 contradicts its initial B; then explicitly corrects the answer to A, 20. |
| M07 | No | No | Finds the ₦1,800 cost but stops during subtraction before giving the requested change. |
| M08 | No | Yes | Calculates 40 correctly but repeatedly retains C, 44 as a conflicting answer and ends without resolving its claimed contradiction. |
| M09 | No | Yes | Calculates 15 − 3 = 12 but repeatedly declares A, 13 correct without resolving the conflict. |
| M10 | No | No | Gives C, 12 litres instead of 8 litres and no calculation. |
| M11 | Yes | Yes | Calculates 2,000 × 0.15 = 300 and selects B. |
| M12 | No | Yes | Correctly derives 15 blue beads but retains B, 12 and ends in unresolved uncertainty. |
| M13 | Yes | Yes | Correctly calculates 10,000 × 0.05 × 2 = ₦1,000 and selects B. |
| M14 | No | No | Sums the values to 45 but stops before completing division or giving the mean. |
| M15 | Yes | Yes | Selects B and correctly computes 2 × (9 + 4) = 26 m. |
| M16 | Yes | Yes | Solves 3x = 15 to x = 5 and selects C. |
| M17 | No | Yes | Calculates 90 but retains B, 60 as a conflicting answer and stops before completing its correction. |
| M18 | Yes | Yes | Calculates 2.5 × 1,000 = 2,500 m and selects B. |
| M19 | No | No | Only repeats a modified option list; gives neither a selected answer nor the requested profit calculation. |
| M20 | Yes | Yes | Selects C and calculates 150 ÷ 3 = 50 km/h. |
| M21 | No | No | Produces repeated homework-site navigation text without answering. |
| M22 | Yes | Yes | Selects B and calculates 180 − 50 − 60 = 70°. |
| M23 | Yes | Yes | Selects A and obtains side length √144 = 12 cm. |
| M24 | No | Yes | Finds common factors correctly and identifies 6, but retains D, 12 and claims the correct working must be wrong. |
| M25 | Yes | Yes | Selects C and computes 14 + 3 = 17 from the common difference. |

### Written mathematics

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M26 | Yes | Yes | Derives price ₦400 and verifies 45 × 400 = 18,000, then the ₦3,000 profit and 20% profit rate. |
| M27 | No | Yes | Correctly obtains 4 GB but only repeats the forward multiplication and subtraction as its check. |
| M28 | Yes | Yes | Finds Bisi 12 and Ada 24 and checks 12 + 24 = 36. |
| M29 | Yes | Yes | Finds ₦600 discount and ₦4,400 price, then independently recomputes the discount with the equivalent fraction 3/25. |
| M30 | No | Yes | Finds 96 litres correctly but its repeated check is identical to the original forward calculation. |
| M31 | Yes | Yes | Corrects distribution to 2x + 6 and substitutes x = 4 to show the original gives 14 rather than the incorrect expansion's 11. |
| M32 | Yes | Yes | Calculates beans as 1/12 of the field and unused land as 1/4. |
| M33 | Yes | Yes | Derives pen price ₦300 and checks 2 × 400 + 300 = 1,100. |
| M34 | No | No | Uses 20 instead of 12 for the third term and derives an incorrect quadratic rule and next term 44. |
| M35 | Yes | Yes | Finds 10 cups by proportion, then checks through the separate unit-rate method. |
| M36 | Yes | Yes | Correctly converts 18 months to 1.5 years and obtains ₦6,000 interest and ₦56,000 total. |
| M37 | Yes | Yes | Finds ₦30,000 original pay and checks its 20% increase gives ₦36,000. |
| M38 | Yes | Yes | Correctly obtains circumference 44 m and area 154 m² using π = 22/7. |
| M39 | No | Yes | Correctly derives 10 m but only repeats the Pythagorean calculation rather than back-substituting the length. |
| M40 | Yes | Yes | Totals 10 counters, counts 7 non-blue counters and gives probability 7/10. |
| M41 | Yes | Yes | Finds the fourth score 90 and verifies all four scores average 75. |
| M42 | Yes | Yes | Subtracts transport, takes four whole ₦800 meals and correctly obtains ₦600 remaining. |
| M43 | Yes | Yes | Computes ₦86,000 total and checks 86,000 − 78,000 = 8,000 delivery cost. |
| M44 | Yes | Yes | Correctly gives median 7 as the middle value and mode 7 as the most frequent. |
| M45 | Yes | Yes | Confirms the student is correct and explains 25% = 1/4, so 80 ÷ 4 = 20. |
| M46 | Yes | Yes | Correctly multiplies 7.2 × 5 = 36 km. |
| M47 | Yes | Yes | Correctly computes 4 × 15 × 12 = 720 litres. |
| M48 | Yes | Yes | Solves x = 8 and checks both original sides equal 30. |
| M49 | Yes | Yes | Correctly subtracts the 6 m² platform from the 80 m² floor to obtain 74 m². |
| M50 | Yes | Yes | Correctly distinguishes the true implication from its false converse and gives a valid 2 × 3 rectangle counterexample. |

### Science multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S01 | No | Yes | Selects photosynthesis correctly but falsely says respiration uses carbon dioxide and releases oxygen. |
| S02 | Yes | Yes | Selects the heart and explains contraction/relaxation producing circulatory pressure. |
| S03 | No | Yes | Correctly selects evaporation but groups freezing with condensation as reverse processes to evaporation. |
| S04 | Yes | Yes | Selects oxygen and correctly identifies its role as final electron acceptor during aerobic respiration. |
| S05 | Yes | Yes | Selects gravity and explains mass producing gravitational attraction. |
| S06 | No | Yes | Selects roots but only repeats the asked absorption function without any substantive explanation. |
| S07 | No | Yes | Gives 100°C correctly, then falsely gives 212°C at standard pressure and stops during an incomplete attempted correction. |
| S08 | No | Yes | Correctly identifies the Sun without its option letter, but attributes seasons to orbit alone without the essential axial tilt. |
| S09 | No | Yes | Correctly explains the inclined plane's force-distance trade-off, but later incorrectly defines pulleys as ropes or chains rather than grooved wheels carrying them. |
| S10 | Yes | Yes | Selects red blood cells, notes their abundance, and correctly contrasts plasma, immune white cells and clotting platelets. |
| S11 | Yes | Yes | Selects ampere, defines one coulomb per second and correctly contrasts volt, watt and ohm. |
| S12 | Yes | Yes | Selects red and explains the acidic pH range; the later generated pH question adds no material error. |
| S13 | Yes | Yes | Selects Newton's second law and correctly contrasts the first law's inertia statement. |
| S14 | Yes | Yes | Selects mitochondria and explains ATP production through cellular respiration. |
| S15 | Yes | Yes | Selects oxygen and explains its production alongside glucose during photosynthesis. |
| S16 | Yes | Yes | Selects vacuum and explains sound needs a material medium. |
| S17 | Yes | Yes | Selects mass divided by volume and explains density as mass per unit volume. |
| S18 | No | No | Answers nitrogen despite stating carbon has atomic number 6, then switches to a different seven-proton question. |
| S19 | Yes | Yes | Selects H₂O and explains its two hydrogen atoms and one oxygen atom. |
| S20 | Yes | Yes | Selects solar energy and explains replenishment from the Sun in contrast with finite fossil sources. |
| S21 | Yes | Yes | Selects ovum and explains ovarian origin and fertilization by sperm to form a zygote. |
| S22 | Yes | Yes | Selects the troposphere and explains its water vapour and weather activity. The overly absolute 'only' is accepted as an introductory simplification, not a material error. |
| S23 | No | Yes | Selects oxygen and water but repeatedly presents an unbalanced rust equation with five waters rather than six. |
| S24 | No | Yes | Correctly explains heat conduction in solids, but adds a false conductivity ordering that places ice below wood and water. |
| S25 | Yes | Yes | Selects neutral and explains equal hydrogen and hydroxide ion concentrations with suitable pH examples. |

### Written science

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S26 | No | No | Repeats a classroom-demonstration setup without explaining equal free-fall acceleration. |
| S27 | No | No | Generates other questions instead of explaining evaporative cooling. |
| S28 | No | Yes | Correctly predicts series off and parallel on, but wrongly gives finite R for the open circuit and retains R/2 after a parallel branch is removed. |
| S29 | No | No | Only generates questions about experimental apparatus and tests; gives no experiment or observations. |
| S30 | No | Yes | Correctly distinguishes density from heaviness and mentions floating ships, but the proposed metal/wood comparison supports rather than disproves the claim and the upthrust-weight criterion is omitted. |
| S31 | No | No | Asks unrelated questions instead of explaining viral colds and bacterial antibiotic targets. |
| S32 | No | Yes | Correctly relates lower pressure to less oxygen per breath and faster breathing, but repeatedly invents confused car/room-versus-outdoor air-density comparisons. |
| S33 | No | No | Generates repeated heat-transfer questions without explaining the hand-to-metal heat flow. |
| S34 | No | No | Repeatedly gives elliptical orbit as the explanation for seasons without axial tilt or a meaningful hemispheric observation. |
| S35 | Yes | Yes | Correctly calculates 2 A then 1 A and explains inverse proportionality at fixed voltage. |
| S36 | Yes | Yes | Classifies dissolving as physical because sugar retains identity and burning as chemical because new substances form; physical-state wording is accepted as physical-form language. |
| S37 | No | No | Generates questions about mass and weight without explaining conservation or escaping gas. |
| S38 | No | No | Generates a different titration question with invalid pH data instead of naming neutralization, products and the requested trend. |
| S39 | No | No | Generates repeated plant-transport questions without explaining midday loss and evening recovery. |
| S40 | No | Yes | Correctly separates dominance from allele frequency and names evolutionary factors, but omits the requested distinction from probability of inheritance. |
| S41 | No | No | Repeats energy-efficiency questions without predicting or explaining frog and snake changes. |
| S42 | No | No | Repeats questions about greenhouse experiments without specifying variables, controls or repetition. |
| S43 | Yes | Yes | Calculates 4 m/s² and correctly explains a 4 m/s increase in speed each second. |
| S44 | Yes | Yes | Correctly uses pressure = force/area to explain the sharp blade's higher pressure at equal force. |
| S45 | No | Yes | Explains lower wet-skin resistance and advises avoiding wet-hand contact, but adds contradictory and unsafe car-grounding speculation about current through the body. |
| S46 | No | Yes | Initially distinguishes lunar phases and lunar eclipses correctly, but adds contradictory claims about solar phases and equates Moon phases with eclipses. |
| S47 | Yes | Yes | Explains boiling when vapour pressure equals atmospheric pressure and why lower mountain pressure lowers boiling temperature. |
| S48 | Yes | Yes | Correctly describes both energy conversions, reactants/products and their complementary roles. |
| S49 | No | No | Generates immune-system questions without correcting the vaccine claim or explaining memory. |
| S50 | Yes | Yes | Correctly names Plasmodium, infected female Anopheles bites and repellent/protective clothing as prevention. |

## Review boundaries

- M04: second-review decision — pass. Corrects the initial 240 km to 60 × 3 = 180 km and explicitly rejects 240; 180 uniquely identifies B despite confused commentary about the options.
- M08: second-review decision — fail. Calculates 40 correctly but repeatedly retains C, 44 as a conflicting answer and ends without resolving its claimed contradiction.
- M29: second-review decision — pass. Finds ₦600 discount and ₦4,400 price, then independently recomputes the discount with the equivalent fraction 3/25.
- M35: second-review decision — pass. Finds 10 cups by proportion, then checks through the separate unit-rate method.
- S06: second-review decision — fail. Selects roots but only repeats the asked absorption function without any substantive explanation.
- S07: second-review decision — fail. Gives 100°C correctly, then falsely gives 212°C at standard pressure and stops during an incomplete attempted correction.
- S08: second-review decision — fail. Correctly identifies the Sun without its option letter, but attributes seasons to orbit alone without the essential axial tilt.
- S09: second-review decision — fail. Correctly explains the inclined plane's force-distance trade-off, but later incorrectly defines pulleys as ropes or chains rather than grooved wheels carrying them.
- S22: second-review decision — pass. Selects the troposphere and explains its water vapour and weather activity. The overly absolute 'only' is accepted as an introductory simplification, not a material error.
- S32: second-review decision — fail. Correctly relates lower pressure to less oxygen per breath and faster breathing, but repeatedly invents confused car/room-versus-outdoor air-density comparisons.
- S36: second-review decision — pass. Classifies dissolving as physical because sugar retains identity and burning as chemical because new substances form; physical-state wording is accepted as physical-form language.
- S45: second-review decision — fail. Explains lower wet-skin resistance and advises avoiding wet-hand contact, but adds contradictory and unsafe car-grounding speculation about current through the body.

## Provenance

- Exact model: `Qwen3-1.7B-Q4_0.gguf`, SHA-256 `c876f159707a4e4f70e045106c69db15bfc935a4981706fd4f65c6e7ea1e81c5`.
- [Responses](../mac-accuracy/Qwen3-1.7B-Q4_0.gguf/stem/responses.jsonl): SHA-256 `b51f9d71335d9751f972fad9a0a125636ec23c38671626413139a8cccb6c323b`.
- [Configuration](../mac-accuracy/Qwen3-1.7B-Q4_0.gguf/stem/config.json): SHA-256 `d02d36720a75cf8dffb58d038f40e6042796f2850723f8f8835cff90fa9abbe8`.
- [Lifecycle](../mac-accuracy/Qwen3-1.7B-Q4_0.gguf/stem/events.jsonl): SHA-256 `100230af1267c9413fe760fabd8ef4f869681a697daa8a7946ef00590fe71e42`.
- Hardware: `apple_m4_pro_24gib_macos_metal_b10175`; two CPU threads, 99 requested GPU layers, 256 MiB host-cache cap, 2,048-token context.
- Raw `/completion`: temperature 0, seed 42, 256/512 output tokens for multiple-choice/written prompts, no chat template or external system prompt, prompt caching disabled.
- Server SHA-256 `f497d6b948174173f8159b6fa46c7b4816e2ecfd306ae9c0f7f11e6a7a79af88`; archive source declaration `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`. The executable reports version 0 (unknown); the source declaration is not independently identified by its version string.
- Actual layer placement and continuous host isolation are not proven by response rows. These results do not measure laptop throughput or RAM.
- All 100 unique IDs, exact prompts, expected fields and model hashes match the fixed suite. The [JSON ledger](qwen3-1b-q40.json) retains every source line and response hash. No raw response was changed or pooled with another hardware context.
