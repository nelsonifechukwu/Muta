# ADTC Mathematics and Scientific Reasoning: 100-Prompt Accuracy Report

## Executive summary

This benchmark used 100 total prompts, with the same 100 prompts presented to both models:

- 50 mathematics prompts
- 50 scientific-reasoning prompts
- Each subject contained 25 multiple-choice and 25 written-reasoning prompts
- The four prompts tested earlier were included
- Written questions were allowed 512 output tokens rather than 256

| Model | Mathematics | Science | Overall simulated accuracy | Accuracy contribution* |
|---|---:|---:|---:|---:|
| Qwen3.5-0.8B Q4_0 | 35/50 | 35/50 | **70/100 — 70%** | **35/50** |
| Qwen2.5-1.5B Q4_K_M | 39/50 | 37/50 | **76/100 — 76%** | **38/50** |

\*If this synthetic percentage mapped directly onto the competition's 50-point accuracy component.

**Current accuracy winner: Qwen2.5-1.5B, by 6 percentage points.**

The [official rules](https://adtc-2026.devpost.com/rules) assign 50% to model accuracy and quality using multiple-choice benchmarks and qualitative evaluation. However, the [official submission template](https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template) indicates that competitors submit two prompts and organizers add two hidden prompts. Therefore, this 100-prompt run is a stress test, not a prediction of the exact four-prompt judging result.

## Test configuration

- Profiler-faithful raw `llama-cpp-python` completion
- Context: 2,048 tokens
- Temperature: 0
- Multiple-choice maximum: 256 generated tokens
- Written-reasoning maximum: 512 generated tokens
- No `llama-server` chat template or explicit reasoning switch
- Strict binary grading: unresolved contradictions, wrong explanations, or missing required answer components were marked wrong
- A response that corrected itself and finished with the right conclusion was accepted

Wrong-output cells below contain the decisive error, shortened from the full response.

## Mathematics multiple choice

| ID | Prompt summary; expected answer | Qwen3.5-0.8B | Qwen2.5-1.5B |
|---|---|---|---|
| M01 | 6 chalk boxes × ₦500; C, ₦3,000 | 🟢 | 🟢 |
| M02 | 8 books × ₦250; C, ₦2,000 | 🟢 | 🟢 |
| M03 | 36 pupils ÷ 6; D, 6 | 🟢 | 🟢 |
| M04 | 60 km/h × 3 h; B, 180 km | 🟢 | 🟢 |
| M05 | Area of 8 m × 5 m; D, 40 m² | 🟢 | 🟢 |
| M06 | One-quarter of 80; A, 20 | 🟢 | 🟢 |
| M07 | ₦5,000 less 3 pens at ₦600; C, ₦3,200 | 🟢 | 🔴 Chose C but gave reversed working: “1,800 − 5,000 = −3,200” and called it a refund |
| M08 | 18 boys + 22 girls; B, 40 | 🟢 | 🟢 |
| M09 | 15 mangoes − 3 spoiled; D, 12 | 🟢 | 🟢 |
| M10 | 4 containers × 2 L; A, 8 L | 🟢 | 🟢 |
| M11 | 15% discount on ₦2,000; B, ₦300 | 🟢 | 🟢 |
| M12 | Ratio 2:3, total 25; C, 15 blue | 🔴 Stopped around “2x + 3x = 25” without producing the requested answer | 🟢 |
| M13 | Simple interest: ₦10,000 at 5% for 2 years; B, ₦1,000 | 🟢 | 🔴 “C. ₦1,500”; its working also incorrectly reached ₦2,000 |
| M14 | Mean of 12, 15, 18; B, 15 | 🟢 | 🟢 |
| M15 | Perimeter of 9 m × 4 m; B, 26 m | 🟢 | 🟢 |
| M16 | Solve 3x + 5 = 20; C, x = 5 | 🟢 | 🟢 |
| M17 | Three-quarters of 120; C, 90 | 🟢 | 🟢 |
| M18 | 2.5 km in metres; B, 2,500 m | 🟢 | 🟢 |
| M19 | Profit on ₦800→₦1,000; B, 25% | 🟢 | 🟢 |
| M20 | 150 km ÷ 3 h; C, 50 km/h | 🟢 | 🟢 |
| M21 | 3 red among 10 counters; B, 3/10 | 🔴 Repeated “3/7” | 🔴 Calculated 3/10 correctly but labelled it option C instead of B |
| M22 | Third triangle angle: 50°, 60°; B, 70° | 🟢 | 🟢 |
| M23 | Side of square with area 144 cm²; A, 12 cm | 🟢 | 🟢 |
| M24 | HCF of 18 and 24; C, 6 | 🟢 | 🔴 Truncated after prime factorization, before giving 6 or the requested option |
| M25 | Next in 5, 8, 11, 14; C, 17 | 🟢 | 🟢 |

## Written mathematics reasoning

| ID | Prompt summary; expected result | Qwen3.5-0.8B | Qwen2.5-1.5B |
|---|---|---|---|
| M26 | Yam spoilage and 20% overall profit; ₦400 each | 🔴 Wandered through ₦333.33, ₦360 and finally ₦180 | 🟢 |
| M27 | 25 GB − 3 GB/day for 7 days; 4 GB | 🔴 “21 GB daily…140 GB…115 GB remaining/no data” | 🟢 |
| M28 | Ada twice Bisi, total 36; 24 and 12 | 🟢 | 🟢 |
| M29 | 12% discount on ₦5,000; ₦600 and ₦4,400 | 🟢 | 🟢 |
| M30 | 120 L leaking 3 L/h for 8 h; 96 L | 🟢 | 🟢 |
| M31 | Correct 2(x + 3); distribute to both terms, 2x + 6 | 🔴 Correct result, but identified the mistake as “treating coefficient 2 as a variable” | 🟢 |
| M32 | ⅔ maize, then ¼ of remainder beans; ¼ unused | 🔴 Contradictory 1/12, 11/12, 8% and 92% answers | 🟢 |
| M33 | Two ₦400 notebooks, total ₦1,100; pen ₦300 | 🟢 | 🟢 |
| M34 | Sequence 2, 6, 12, 20; rule n(n+1), next 30 | 🔴 “n² + 2n + 2; next 38” | 🔴 “20 × 3 = 60” |
| M35 | 4 cups for 10 loaves; 10 cups for 25 | 🟢 | 🟢 |
| M36 | ₦50,000 at 8% for 18 months; ₦6,000, total ₦56,000 | 🟢 | 🔴 “Interest ₦9,000; total ₦59,000” |
| M37 | ₦36,000 after 20% increase; original ₦30,000 | 🟢 | 🟢 |
| M38 | Circle r = 7, π = 22/7; 44 m and 154 m² | 🔴 “25.1 m and 98.6 m²” | 🟢 |
| M39 | Right triangle 6 m, 8 m; ladder 10 m | 🟢 | 🟢 |
| M40 | Not-blue probability from 5 red, 3 blue, 2 green; 7/10 | 🟢 | 🟢 |
| M41 | Four-score mean 75; fourth score 90 | 🔴 “Fourth score is 50” | 🔴 “Fourth score is 75” |
| M42 | ₦5,000 less transport, ₦800 meals; 4 meals, ₦600 | 🟢 | 🔴 “6 meals and ₦1,000 remains” |
| M43 | 12 cement bags × ₦6,500 + ₦8,000; ₦86,000 | 🔴 “₦18,500” | 🔴 “₦83,000” despite writing ₦78,000 + ₦8,000 |
| M44 | Data 4, 7, 7, 9, 12; median 7, mode 7 | 🔴 “Median 8” | 🔴 “Median 8” |
| M45 | Is 25% of 80 equal to 20? Yes | 🔴 Calculated 20, then declared the student incorrect | 🟢 |
| M46 | Map scale 1 cm:5 km, distance 7.2 cm; 36 km | 🟢 | 🟢 |
| M47 | Four pumps × 15 L/min × 12 min; 720 L | 🔴 “7,200 L” | 🔴 “180 L” |
| M48 | Solve 5(x−2) = 3x+6; x = 8, both sides 30 | 🔴 Found x = 8 but checked “40 versus 42” and rejected it | 🟢 |
| M49 | 10×8 floor less 2×3 platform; 74 m² | 🟢 | 🟢 |
| M50 | Square⇒rectangle, converse false; nonsquare rectangle | 🔴 Counterexample was “a square that is not a rectangle” | 🟢 |

## Science multiple choice

| ID | Prompt summary; expected answer | Qwen3.5-0.8B | Qwen2.5-1.5B |
|---|---|---|---|
| S01 | Plants use sunlight to make food; B, photosynthesis | 🟢 | 🟢 |
| S02 | Organ that pumps blood; B, heart | 🟢 | 🟢 |
| S03 | Liquid water→vapour; D, evaporation | 🔴 “B. Condensation”; also defined condensation as liquid→gas | 🟢 |
| S04 | Gas required for aerobic respiration; C, oxygen | 🟢 | 🟢 |
| S05 | Force pulling objects toward Earth; A, gravity | 🟢 | 🟢 |
| S06 | Plant part absorbing water/minerals; B, root | 🟢 | 🟢 |
| S07 | Pure-water boiling point at sea level; C, 100°C | 🟢 | 🟢 |
| S08 | Earth revolves around; D, Sun | 🟢 | 🟢 |
| S09 | Sloping simple machine; A, inclined plane | 🟢 | 🟢 |
| S10 | Blood cells carrying oxygen; C, red cells | 🟢 | 🟢 |
| S11 | SI current unit; C, ampere | 🟢 | 🟢 |
| S12 | Blue litmus in acid; A, red | 🟢 | 🔴 “D. It stays blue,” while simultaneously saying it turns red |
| S13 | F = ma; B, Newton's second law | 🟢 | 🟢 |
| S14 | Organelle releasing usable energy; C, mitochondrion | 🟢 | 🟢 |
| S15 | Gas released during photosynthesis; B, oxygen | 🟢 | 🟢 |
| S16 | Medium through which sound cannot travel; D, vacuum | 🟢 | 🟢 |
| S17 | Density formula; B, mass ÷ volume | 🟢 | 🟢 |
| S18 | Atomic number 6; C, carbon | 🟢 | 🟢 |
| S19 | Formula for water; C, H₂O | 🟢 | 🟢 |
| S20 | Renewable source; D, solar energy | 🟢 | 🟢 |
| S21 | Female human reproductive cell; B, ovum | 🟢 | 🟢 |
| S22 | Atmospheric layer containing most weather; C, troposphere | 🟢 | 🟢 |
| S23 | Rust requires; A, oxygen and water | 🟢 | 🟢 |
| S24 | Strongest ordinary heat conduction; C, solids | 🟢 | 🟢 |
| S25 | pH 7; C, neutral | 🟢 | 🟢 |

## Written scientific reasoning

| ID | Prompt summary; expected reasoning | Qwen3.5-0.8B | Qwen2.5-1.5B |
|---|---|---|---|
| S26 | Heavy/light falling balls; F = mg but a = g without drag | 🔴 Claimed the heavier ball accelerates faster because it is closer to Earth's centre | 🔴 Correct equal acceleration, but falsely said gravitational force is identical and contradicted whether the student was correct |
| S27 | Sweat cooling; energetic molecules evaporate and remove energy | 🟢 | 🟢 |
| S28 | Remove bulb: series goes off, parallel remains on | 🔴 Said the other bulb remains lit in both circuits | 🔴 Said the other bulb is unaffected in both circuits |
| S29 | Destarched leaf, covered region, iodine starch test | 🔴 Proposed food colouring/paper and omitted the iodine starch test | 🔴 Removed the leaves before exposure and omitted destarching |
| S30 | Floating depends on average density and buoyancy, not weight alone | 🔴 Gave a nail/wood comparison that confirms the misconception and misstated upthrust | 🔴 Claimed heavy objects inherently have higher density and supplied no sound counterexample |
| S31 | Antibiotics treat bacteria, not viral colds | 🔴 Core conclusion correct, but central explanation falsely called a virus “a type of protein” | 🟢 |
| S32 | High altitude: lower pressure/oxygen partial pressure; faster breathing | 🟢 | 🟢 |
| S33 | Same room temperature; metal conducts heat from the hand faster | 🔴 Said the metal must actually be colder | 🔴 Said the metal must actually be colder |
| S34 | Seasons caused by axial tilt; hemispheres have opposite seasons | 🔴 Attributed seasons to orbital speed/moving toward or away from the Sun | 🔴 Repeated a wrong hemisphere-tilt statement and did not establish opposite seasons |
| S35 | 6 V ÷ 3 Ω = 2 A; doubled resistance gives 1 A | 🟢 | 🟢 |
| S36 | Dissolving sugar physical; burning chemical | 🟢 | 🟢 |
| S37 | Mass conservation in a closed flask; gas escape misleads when open | 🟢 | 🟢 |
| S38 | HCl + NaOH neutralization; salt/water; pH falls toward 7 | 🔴 Said H⁺ decreases, OH⁻ increases and pH rises as acid is added | 🔴 Produced an arbitrary repeating list of pH values without answering |
| S39 | Midday transpiration exceeds uptake; stomata close; evening recovery | 🔴 Attributed wilting mainly to cooling/metabolism and reversed the recovery mechanism | 🟢 |
| S40 | Dominance affects phenotype, not inheritance probability/frequency | 🟢 | 🟢 |
| S41 | Fewer grasshoppers→fewer frogs→possibly fewer snakes | 🟢 | 🟢 |
| S42 | Fertilizer experiment: IV, DV, controls and repeats | 🟢 | 🟢 |
| S43 | 0→20 m/s in 5 s; acceleration 4 m/s² | 🟢 | 🟢 |
| S44 | Sharp knife: same force over smaller area gives higher pressure | 🟢 | 🔴 Explained high pressure correctly, then concluded the blunt knife cuts more easily |
| S45 | Wet hands lower resistance and allow greater current | 🔴 Claimed wet hands increase resistance and reduce current | 🟢 |
| S46 | Moon phases from viewing illuminated portion; shadow only in lunar eclipse | 🔴 Correctly named eclipse but gave the wrong Sun–Earth–Moon alignment | 🔴 Repeated that ordinary phases are caused by Earth's shadow |
| S47 | Boiling when vapour pressure equals lower atmospheric pressure | 🔴 Claimed vapour pressure is inherently higher at altitude and gave the wrong boiling criterion | 🔴 Abandoned the explanation and generated questions about boiling points at many altitudes |
| S48 | Photosynthesis stores light energy; respiration releases usable energy | 🔴 Said photosynthesis “releases chemical energy” | 🔴 Said respiration converts chemical energy into light |
| S49 | Vaccines prime adaptive immunity and memory; not an immediate cure | 🟢 | 🟢 |
| S50 | Plasmodium via infected female Anopheles; mosquito-control prevention | 🔴 Claimed respiratory spores/fecal–oral transmission and recommended masks | 🔴 Mentioned mosquito bites, then generated unrelated quizzes and omitted Plasmodium and prevention |

## Conclusions

The **Qwen2.5-1.5B model is currently the safer competition choice for accuracy**. Its advantage comes almost entirely from written mathematics: **18/25 versus 12/25**.

The biggest weakness in both models is not basic factual recall. It is explanation stability:

- producing a correct calculation but attaching the wrong option;
- giving a correct principle and then reversing it in the conclusion;
- entering repetitive loops;
- inventing a new question after answering the original;
- consuming the output allowance with internal reasoning.

The 0.8B Qwen3.5 model is particularly fragile on multi-step word problems and misconception correction. The 1.5B model is better overall, but its failures on series circuits, Moon phases, boiling, energy conversion, and contradictory multiple-choice labels would be highly visible to a qualitative judge.

The public [ADTC profiler repository](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler) does not publish the organizers' hidden prompts or exact qualitative rubric, so the defensible interpretation is:

- **Internal stress-test accuracy:** 70% versus 76%
- **Likely ranking:** Qwen2.5-1.5B ahead
- **Official score prediction:** uncertain because the real hidden set is only a few prompts and judge discretion can create high variance
