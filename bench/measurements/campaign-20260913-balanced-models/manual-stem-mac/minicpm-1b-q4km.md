# MiniCPM5 1B Q4_K_M: Mac STEM audit

All 100 returned Mac raw-completion texts were reviewed in full. This AI-assisted semantic audit is separate from GCP results and is not an official ADTC grade or a chat-template test.

| Category | Strict pass | Core answer correct | Questions |
|---|---:|---:|---:|
| Mathematics multiple choice | 10 | 15 | 25 |
| Written mathematics | 0 | 4 | 25 |
| Science multiple choice | 1 | 8 | 25 |
| Written science | 0 | 4 | 25 |
| **Total** | **11** | **31** | **100** |

The original option parser recorded 14/50 (8 mathematics, 6 science). That extraction count is not a grade of the explanation. 43 responses reached their output limit; 4 were empty.

## Policy

Strict pass requires the correct answer, requested working or explanation, all substantive requested components and no unresolved material error. A requested check may use inverse arithmetic, substitution or a distinct correct numerical method. Repeating the same calculation or asserting correctness is insufficient; checking every intermediate step is unnecessary.

Core-answer correctness separately records the main value or conclusion despite incomplete instructions or faulty support. Correct option values can pass without a letter; wrong explicit labels fail unless genuinely corrected. Length, repetition and token-limit stops are not independent failures once a complete correct answer exists. False continued explanations still count, including in visible reasoning text. Unsafe advice fails a requested safety component even alongside a safe alternative. Supporting statements are judged for material errors, not every introductory simplification.

## Decisions

### Mathematics multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M01 | Yes | Yes | Selects C and calculates 6 × 500 = ₦3,000. |
| M02 | Yes | Yes | Calculates 8 × 250 = 2,000, uniquely identifying C without its letter. |
| M03 | No | Yes | Calculates 36 ÷ 6 = 6 but labels it B rather than D. |
| M04 | Yes | Yes | Selects B and correctly calculates 60 × 3 = 180 km. |
| M05 | No | Yes | Calculates 8 × 5 = 40 m² but labels it A rather than D. |
| M06 | No | Yes | Eventually gives the correct quarter as 20 but begins with an unrelated 20% answer of 16 and never resolves the answer shift. |
| M07 | No | No | Selects D instead of the correct change and switches to unrelated pen/pencil questions. |
| M08 | No | No | Only selects D, which is incorrect, and gives no calculation. |
| M09 | No | Yes | Calculates 15 − 3 = 12 but labels it B rather than D. |
| M10 | No | No | Changes four containers to three and concludes B, 6 litres rather than 8. |
| M11 | Yes | Yes | Selects B and repeatedly calculates 0.15 × 2,000 = ₦300 correctly. |
| M12 | No | No | Reverses red and blue shares and gives 10 blue beads instead of 15. |
| M13 | Yes | Yes | Selects B and correctly calculates 10,000 × 0.05 × 2 = ₦1,000 before unrelated continuation. |
| M14 | Yes | Yes | Selects B and calculates (12 + 15 + 18)/3 = 15. |
| M15 | Yes | Yes | Selects B and calculates 2 × (9 + 4) = 26 m. |
| M16 | No | No | Only lists altered equations without solving for x or selecting an answer. |
| M17 | No | No | Starts with 30 and repeats malformed numbers instead of the correct 90. |
| M18 | No | No | Only repeats all four options without selecting or calculating a conversion. |
| M19 | No | No | Selects 20% with invalid arithmetic rather than the correct 25%. |
| M20 | Yes | Yes | Calculates 150 ÷ 3 = 50 km/h and finally selects C, clearly superseding the opening D, 75 km/h. |
| M21 | Yes | Yes | Totals 3 + 7 = 10 and correctly gives B, 3/10. |
| M22 | No | No | Gives 110° and an incorrect subtraction instead of 70°. |
| M23 | No | No | Repeatedly selects B, 24 cm, without a valid calculation. |
| M24 | No | Yes | Correctly derives HCF 6 but explicitly assigns option D rather than C. |
| M25 | Yes | Yes | Selects C and computes 14 + 3 = 17 before unrelated continuation. |

### Written mathematics

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M26 | No | No | Invents decimal options and falsely says the stated cost, quantity and profit information is missing. |
| M27 | No | No | Gives 3,000,000 instead of 4 GB, without working. |
| M28 | No | No | Only repeats the given sum 36 without finding either age. |
| M29 | No | No | Gives a discount of $0.12 and new price $4,980 instead of ₦600 and ₦4,400. |
| M30 | No | No | Only repeats the tank question without calculating remaining water. |
| M31 | No | Yes | Corrects the expansion to 2x + 6 but does not identify the missing multiplication of 3 by 2; its x = 4 check evaluates only the expanded expression, not the original. |
| M32 | No | No | Invents choices and selects 1/6 rather than the correct unused fraction 1/4. |
| M33 | No | No | Repeatedly gives pen price ₦200 instead of ₦300. |
| M34 | No | No | Gives 24 and switches to multiples of three, not the required sequence rule and next term 30. |
| M35 | No | No | Only computes 0.4 cups per loaf without answering cups for 25 loaves or checking it. |
| M36 | No | No | Makes a factor-of-ten error, gives ₦60,000 interest and ₦110,000 total. |
| M37 | No | No | Adds another 20% to the increased pay and gives ₦43,200 instead of reversing the increase to ₦30,000. |
| M38 | No | No | Gets circumference 44 m but incorrectly gives area 462 m² rather than 154 m². |
| M39 | No | Yes | Repeats the correct 10 m without Pythagorean working or the requested check. |
| M40 | No | No | Invents choices and selects 1/5 instead of 7/10. |
| M41 | No | No | Invents a five-score total and answers 72 instead of finding the fourth score 90. |
| M42 | No | No | Gives four meals but forgets transport, incorrectly leaving ₦1,800 rather than ₦600. |
| M43 | No | No | Gives ₦24,000 instead of ₦86,000 and repeats contradictory cost claims. |
| M44 | No | No | Defines median and mode but never gives their values for the supplied data. |
| M45 | No | Yes | Correctly calculates 0.25 × 80 = 20 but does not explain the requested meaning of 25% as 25 per 100 or one quarter. |
| M46 | No | No | Uses the wrong scale and converts centimetres directly to kilometres, giving 36,000,000 km. |
| M47 | No | No | Only repeats a partial pump question without a volume calculation. |
| M48 | No | Yes | Correctly solves x = 8 but supplies no requested check of the original sides. |
| M49 | No | No | Only enumerates integers without calculating tiled area. |
| M50 | No | No | Repeatedly asserts every rectangle is a square and supplies neither correction nor counterexample. |

### Science multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S01 | No | Yes | Selects photosynthesis but gives no requested explanation. |
| S02 | No | No | Answers lungs rather than heart. |
| S03 | No | No | Answers freezing and gives reversed phase changes and an incorrect room-temperature state. |
| S04 | No | No | Selects carbon dioxide even while its supporting definition says respiration uses oxygen. |
| S05 | Yes | Yes | Identifies gravity as attraction between Earth and objects and contrasts the other forces. |
| S06 | No | No | Answers leaf and falsely claims a leaf contains a network of roots. |
| S07 | No | No | Gives 212°C instead of 100°C. |
| S08 | No | Yes | Correctly names the Sun without a letter but adds no requested explanation. |
| S09 | No | No | Selects D instead of an inclined plane and moves to other machine questions. |
| S10 | No | No | Selects plasma and falsely says red blood cells do not carry oxygen in blood. |
| S11 | No | No | Selects ohm and explicitly rejects ampere as the unit of current. |
| S12 | No | Yes | States the correct red colour but selects B instead of A and adds a false claim about red litmus turning blue in acid. |
| S13 | No | Yes | Selects B correctly but provides no explanation. |
| S14 | No | No | Only lists all four options without selecting or explaining an organelle. |
| S15 | No | No | Uses letter B but explicitly identifies carbon dioxide as the photosynthesis byproduct instead of oxygen. |
| S16 | No | No | Selects water and gives malformed statements about media themselves travelling, not sound. |
| S17 | No | No | Outputs unrelated numerical options rather than a density definition. |
| S18 | No | Yes | Identifies carbon correctly but labels it D and incorrectly gives oxygen atomic number 16. |
| S19 | No | Yes | Initially selects the original correct C, but then repeatedly changes the options so C denotes O₂ and keeps selecting it; no valid explanation is given. |
| S20 | No | No | Only lists all four energy sources without selecting one or explaining renewability. |
| S21 | No | No | Answers sperm rather than ovum. |
| S22 | No | No | Answers stratosphere rather than troposphere. |
| S23 | No | Yes | Selects oxygen and water but gives no explanation. |
| S24 | No | No | Answers liquids rather than solids. |
| S25 | No | No | Answers acidic instead of neutral. |

### Written science

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S26 | No | No | Discusses mass and gravitational force but never states or explains equal acceleration in free fall or the requested observation. |
| S27 | No | No | Only asks what happens to faster molecules; gives no answer. |
| S28 | No | No | Explains initial circuit formulas but stops before saying what happens when a bulb is removed. |
| S29 | No | No | Only outputs B without an experiment or explanation. |
| S30 | No | No | Returns an empty response. |
| S31 | No | Yes | Correctly identifies bacterial infections as antibiotic targets but never explains that a cold is viral and is not cured by them. |
| S32 | No | No | Only enumerates letters without answering the altitude question. |
| S33 | No | No | Discusses cooking utensils and incorrectly says metal does not absorb heat easily, without explaining hand-to-spoon heat transfer. |
| S34 | No | No | Only repeats the 23.5° tilt fact and the instruction; gives no causal explanation or hemispheric observation. |
| S35 | No | No | Only repeats voltages and resistances without calculating either current. |
| S36 | No | No | Returns an empty response. |
| S37 | No | No | Lists thermal labels and letters instead of explaining conservation of mass. |
| S38 | No | No | Starts from neutral rather than alkaline solution, omits the neutralization products and invents an incorrect Henderson–Hasselbalch equation. |
| S39 | No | No | Only repeats option letters without explaining wilting or recovery. |
| S40 | No | Yes | States dominance does not determine frequency but gives false haemoglobin/sickle-cell genetics and counts allele frequency by individuals rather than allele copies. |
| S41 | No | No | Returns an empty response. |
| S42 | No | No | Only enumerates letters instead of describing the experiment. |
| S43 | No | Yes | Calculates 4 m/s² but repeatedly says speed increases by 4 m/s² each second rather than 4 m/s each second. |
| S44 | No | No | Only repeats option letters without a pressure explanation. |
| S45 | No | No | Repeats instructions to identify an answer, with no resistance/current explanation or safety action. |
| S46 | No | No | Repeats instructions to correct misconceptions but never explains phases or lunar eclipses. |
| S47 | No | Yes | Correctly associates mountain boiling temperature with atmospheric pressure but never explains lower pressure or equality with vapour pressure. |
| S48 | No | No | Reverses photosynthesis reactants/products by saying glucose becomes carbon dioxide and water, despite later correct energy-conversion statements. |
| S49 | No | No | Returns an empty response. |
| S50 | No | No | Only repeats generic parasite/vector labels without naming the cause, mosquito transmission or prevention. |

## Review boundaries

A second AI reviewer resolved three boundaries. M20 passes because its final correct option and calculation supersede the opening error. M31 fails because the distributive error is not identified and only the expanded expression is checked. M45 fails because decimal conversion supplies a calculation but not the requested meaning of the percentage. These are internal audit decisions, not official grades.

## Provenance

Source responses: [responses.jsonl](../mac-accuracy/MiniCPM5-1B-Q4_K_M.gguf/stem/responses.jsonl). The adjacent [JSON ledger](minicpm-1b-q4km.json) binds every decision to its response hash and source line.

- Model SHA-256: `81b64d05a23b17b34c475f42b3e72fbde62d4b92cc34541f7a8031d0752deafa`.
- Responses SHA-256: `963f3b094f359a888870432d9dc64276959389d6385eaabcf17cce507d29c1a6`.
- Runtime: Mac M4 Pro, Metal; 2 threads, 99 requested GPU layers, 2,048-token context and 256 MiB host-cache cap.
- Generation: temperature 0, seed 42; 256 output tokens for multiple choice and 512 for written questions; raw completion without embedded chat template or external system prompt.
- Server SHA-256: `f497d6b948174173f8159b6fa46c7b4816e2ecfd306ae9c0f7f11e6a7a79af88`. Its version string is `0 (unknown)`; the declared source revision is `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`, paired with the verified executable hash.

Actual layer placement and continuous host isolation are not established by the response rows. No Mac throughput, RSS or ADTC composite score is inferred from these accuracy-only responses.
