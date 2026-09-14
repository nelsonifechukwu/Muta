# Fine-tuned Qwen2.5 control: manual STEM audit

All 100 original GCP scalar raw-completion responses were reviewed, including their full explanations and continuation text. This is an AI-assisted semantic audit, not an official ADTC grade or a chat-template test.

| Category | Strict pass | Core answer correct | Questions |
|---|---:|---:|---:|
| Mathematics multiple choice | 25 | 25 | 25 |
| Written mathematics | 11 | 20 | 25 |
| Science multiple choice | 16 | 23 | 25 |
| Written science | 5 | 14 | 25 |
| **Total** | **57** | **82** | **100** |

The original option parser recorded **44/50**: 21 mathematics and 23 science. That is a letter-extraction count, not the strict semantic result. Four mathematics responses gave the correct option value without its letter; they pass this semantic audit. Several science answers selected the correct option but added false explanations.

## Grading policy

Strict pass requires a correct answer, correct requested working or explanation, all substantive requested components, and no unresolved material contradiction. An explicit check can use substitution, inverse arithmetic or a distinct correct numerical method; merely repeating the derivation or claiming it checks out is insufficient. Self-correction is accepted when the error is resolved. A correct final sentence does not excuse unretracted conflicting reasoning.

Core-answer correctness is recorded separately. It can be true when the main value or scientific conclusion is correct but the response omits a check or gives incorrect supporting claims. It is not a tutoring-quality score.

Correct option values uniquely identifying an answer are accepted without their letter. Wrong explicit labels fail strict grading. Token-limit stops, repetition, and word/sentence-format excess are not automatic failures if the substantive answer is already complete. All returned text still counts: incorrect additions can turn an otherwise correct answer into a failure.

## Response decisions

`Pass` is the strict instruction-complete judgment; `Core` records the main answer separately. Source line numbers and exact response hashes are in the accompanying JSON.

### Mathematics multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M01 | Yes | Yes | Selects C and calculates 6 × 500 = ₦3,000. |
| M02 | Yes | Yes | Selects C and calculates 8 × 250 = ₦2,000. |
| M03 | Yes | Yes | Selects D and calculates 36 ÷ 6 = 6 pupils. |
| M04 | Yes | Yes | Calculates 60 × 3 = 180 km, uniquely identifying B; the option letter is omitted. |
| M05 | Yes | Yes | Selects D and calculates 8 × 5 = 40 m². |
| M06 | Yes | Yes | Selects A and calculates 80 ÷ 4 = 20 mangoes. |
| M07 | Yes | Yes | Selects C; correctly subtracts 3 × ₦600 from ₦5,000 to obtain ₦3,200. |
| M08 | Yes | Yes | Calculates 18 + 22 = 40 pupils, uniquely identifying B; the letter is omitted. |
| M09 | Yes | Yes | Selects D and calculates 15 − 3 = 12 good mangoes. |
| M10 | Yes | Yes | Selects A and calculates 2 litres × 4 = 8 litres. |
| M11 | Yes | Yes | Selects B and correctly calculates 15/100 × ₦2,000 = ₦300 before repeating it. |
| M12 | Yes | Yes | Calculates 3/5 × 25 = 15 blue beads, uniquely identifying C; the letter is omitted. |
| M13 | Yes | Yes | Selects B and correctly calculates ₦10,000 × 0.05 × 2 = ₦1,000 before repetition. |
| M14 | Yes | Yes | Selects B; adds the three values to 45 and divides by 3 to obtain 15. |
| M15 | Yes | Yes | Selects B and calculates 2 × (9 + 4) = 26 m; subsequent repetition introduces no error. |
| M16 | Yes | Yes | Selects C and correctly solves 3x + 5 = 20 to obtain x = 5. |
| M17 | Yes | Yes | Selects C and calculates 120 × 3/4 = 90. |
| M18 | Yes | Yes | Selects B and converts 2.5 km × 1,000 m/km = 2,500 m. |
| M19 | Yes | Yes | Correctly calculates (1,000 − 800)/800 × 100 = 25%, uniquely identifying B without its letter. |
| M20 | Yes | Yes | Selects C and calculates 150 km ÷ 3 h = 50 km/h. |
| M21 | Yes | Yes | Selects B; explicitly totals 3 + 7 = 10 counters and obtains 3/10. |
| M22 | Yes | Yes | Selects B and calculates 180° − (50° + 60°) = 70°. |
| M23 | Yes | Yes | Selects A and takes √144 = 12 cm before repeating the result. |
| M24 | Yes | Yes | Selects C; correct prime factorizations give shared factor 2 × 3 = 6. |
| M25 | Yes | Yes | Selects C; identifies the common difference 3 and calculates 14 + 3 = 17. |

### Written mathematics

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| M26 | No | Yes | Correctly derives ₦400 per tuber from ₦18,000/45, but omits the requested check of revenue and profit at that price. |
| M27 | No | Yes | Correctly obtains 25 − 3 × 7 = 4 GB; saying the calculation is easy to verify does not perform the requested check. |
| M28 | Yes | Yes | Finds Bisi = 12 and Ada = 24, then explicitly checks 12 + 24 = 36. The final 36 refers to that sum. |
| M29 | No | Yes | Correctly finds the ₦600 discount and ₦4,400 new price, but performs no requested back-check. |
| M30 | No | Yes | Correctly derives 120 − 3 × 8 = 96 litres but does not perform the requested check. |
| M31 | Yes | Yes | Identifies faulty distribution, gives 2x + 6, and substitutes x = 4 into both expressions to obtain 14. |
| M32 | Yes | Yes | Correctly subtracts the beans' 1/12 share from the remaining 1/3 to obtain 1/4 unused. |
| M33 | No | Yes | Gives the correct ₦300 pen price, but checks one notebook plus pen instead of two and asserts ₦700 is ₦1,100. |
| M34 | No | No | The stated recurrence does not fit the sequence and gives 60 instead of 30. |
| M35 | No | Yes | Correctly solves 4/10 = x/25 to obtain 10 cups, but does not verify the resulting proportion as requested. |
| M36 | Yes | Yes | Correctly converts 18 months to 1.5 years, obtains ₦6,000 interest and ₦56,000 total; repetition does not change the result. |
| M37 | Yes | Yes | Finds ₦30,000 and verifies that adding its ₦6,000 increase gives ₦36,000. |
| M38 | Yes | Yes | Uses the stipulated π to calculate circumference 44 m and area 154 m² correctly. |
| M39 | No | Yes | Correctly derives length 10 m using Pythagoras, but does not independently substitute the result to perform the requested check. |
| M40 | Yes | Yes | Correctly totals 10 counters, identifies 7 non-blue counters, and gives probability 7/10. |
| M41 | No | No | Gives 75 instead of 90 and falsely claims that the resulting four-score mean is 75. |
| M42 | No | No | Ignores the transport deduction, gives six meals instead of four, and contradicts itself about the remaining money. |
| M43 | No | Yes | Correctly calculates ₦78,000 + ₦8,000 = ₦86,000 but supplies no separate requested check. |
| M44 | No | Yes | Median and mode are both correctly 7, but the added explanation falsely says the mode is only useful when several values tie for highest frequency. |
| M45 | No | No | Computes 20 but then rejects the student's correct answer, confuses 20/80 with 25/80, and concludes 31.25%. |
| M46 | Yes | Yes | Correctly applies 7.2 cm × 5 km/cm = 36 km. |
| M47 | Yes | Yes | Correctly computes four pumps × 15 litres/minute × 12 minutes = 720 litres. |
| M48 | Yes | Yes | Solves x = 8 and explicitly verifies both original sides equal 30. |
| M49 | Yes | Yes | Correctly calculates 10 × 8 − 2 × 3 = 74 m². |
| M50 | No | No | Its counterexample is a unit square that it incorrectly says is not a square; the explanation of the logical error is also wrong. |

### Science multiple choice

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S01 | No | Yes | Selects photosynthesis correctly, but falsely states that evaporation releases energy; evaporation absorbs energy. |
| S02 | Yes | Yes | Selects the heart and correctly explains pumping blood through contraction and relaxation. |
| S03 | Yes | Yes | Selects evaporation and explains energetic molecules escaping from a liquid surface into vapour. |
| S04 | No | Yes | Selects oxygen correctly but incorrectly dismisses hydrogen by claiming it is not a gas. |
| S05 | Yes | Yes | Selects gravity and attributes attraction toward Earth to mass; the central explanation is correct. |
| S06 | Yes | Yes | Selects roots and explains their absorption of water and minerals from soil. |
| S07 | No | Yes | Selects 100°C but also falsely calls 212°C the standard-pressure boiling point and distinguishes that pressure from sea-level pressure. |
| S08 | No | Yes | Selects the Sun and describes Earth's orbit correctly, then explicitly states that the Sun is not a celestial body. |
| S09 | Yes | Yes | Selects an inclined plane and explains that its sloping surface reduces the force needed to raise a load. |
| S10 | No | Yes | Correctly selects red blood cells, but calls plasma a blood cell and categorically denies its dissolved-oxygen transport. |
| S11 | Yes | Yes | Selects the ampere, explains charge flow per second, and correctly distinguishes volt, watt and ohm. |
| S12 | No | No | Repeatedly chooses D, stays blue, while its own explanation says acid turns blue litmus red; the contradiction is unresolved. |
| S13 | Yes | Yes | Selects Newton's second law and correctly relates net force, mass and acceleration. |
| S14 | Yes | Yes | Selects the mitochondrion and explains energy release through cellular respiration. |
| S15 | Yes | Yes | Selects oxygen and explains its production alongside glucose during photosynthesis and light-to-chemical energy conversion. |
| S16 | Yes | Yes | Selects vacuum and explains that sound requires a material medium. |
| S17 | Yes | Yes | Selects mass divided by volume and correctly explains mass per unit volume. |
| S18 | No | No | Chooses oxygen even while listing carbon as atomic number 6; its final conclusion remains oxygen. |
| S19 | Yes | Yes | Selects H₂O and explains the two-to-one ratio of hydrogen to oxygen atoms. |
| S20 | Yes | Yes | Selects solar energy and correctly contrasts a naturally replenished source with finite fossil fuels. |
| S21 | Yes | Yes | Identifies the ovum as the female gamete, explicitly identifies sperm as male, and describes fertilization. |
| S22 | No | Yes | Selects the troposphere correctly but incorrectly characterizes the other atmospheric layers as primarily concerned with weather patterns. |
| S23 | Yes | Yes | Selects oxygen and water and explains oxidation of iron in their presence. |
| S24 | No | Yes | Selects solids correctly but reverses the comparison of molecular freedom by saying particles move more freely in liquids than gases. |
| S25 | Yes | Yes | Selects neutral and explains equal hydrogen- and hydroxide-ion concentrations in the question's standard aqueous context. |

### Written science

| ID | Pass | Core | Reason |
|---|:---:|:---:|---|
| S26 | No | No | Falsely says both balls experience the same gravitational force and repeatedly alternates between calling the student's reasoning correct and mistaken. |
| S27 | Yes | Yes | Correctly explains evaporation, higher-energy molecules escaping and energy loss from skin. Review resolved the convection reference as subsequent heat transport in air, not a definite contradiction of evaporative cooling. |
| S28 | No | No | Does not identify the opened series circuit; gives inconsistent bright/dim predictions for both series and parallel arrangements. |
| S29 | No | Yes | Correctly proposes light/dark comparison and an iodine test, but never destarches the plant, so pre-existing starch invalidates the claimed dark-control observation. |
| S30 | No | No | Incorrectly equates greater weight with greater density, claims upthrust always equals weight, and never provides the requested counterexample. |
| S31 | Yes | Yes | Correctly identifies a cold as viral and explains that antibiotics treat bacterial rather than viral infections. |
| S32 | Yes | Yes | Correctly links lower pressure and oxygen availability to increased ventilation; later repetition adds no conflicting claim. |
| S33 | No | No | Claims metal must be colder after losing heat to the room instead of explaining faster heat transfer from the hand at equal room temperature. |
| S34 | No | Yes | Identifies opposing hemispheric tilts rather than orbital distance, but gives 23.5° relative to the orbital plane instead of its normal and never explains the sunlight/day-length mechanism. |
| S35 | Yes | Yes | Correctly calculates 6/3 = 2 A, then 6/6 = 1 A, and explains inverse proportionality at fixed voltage. |
| S36 | No | No | Labels dissolving sugar a chemical change and falsely says sugar molecules rearrange into water; its classifications and evidence contradict one another. |
| S37 | No | Yes | States the correct closed-system mass conclusion, but says the before/after mass difference is the product mass and never explains escaping gas in an open container. |
| S38 | No | No | Names neutralization and its products correctly but repeatedly reverses the requested pH trajectory, saying acidic-to-neutral instead of alkaline-to-neutral. |
| S39 | No | No | Contradicts the stated wet soil, attributes recovery to evening stomatal opening, and never explains midday loss exceeding root uptake. |
| S40 | No | Yes | Correctly rejects inevitable growth of dominant-allele frequency, but misdefines allele frequency and dominance and suggests dominance can influence inheritance probability. |
| S41 | No | Yes | Implies fewer frogs and snakes, but substitutes fewer animals being eaten for the requested explanation that reduced grasshopper food/energy lowers frog survival and then snake food supply. |
| S42 | No | Yes | Correctly identifies variables, controls and repeats, but allocates three groups of five pots after specifying ten pots; the design has an unresolved counting contradiction. |
| S43 | No | Yes | Calculates 4 m/s² correctly, but describes a speed increase of 4 m/s² rather than explaining 4 m/s gained each second. |
| S44 | No | Yes | Ends with the correct smaller-area/higher-pressure conclusion, but never retracts its earlier equal-pressure claim and reversed area/pressure reasoning. |
| S45 | No | Yes | Explains increased conductivity/current and gives a valid towel-drying action, but also suggests using a hairdryer to dry wet hands. That hazardous electrical-appliance advice fails the requested safety component. |
| S46 | No | No | Repeatedly says Earth's shadow causes phases and then denies that it falls on the Moon during a lunar eclipse. |
| S47 | No | No | Generates new altitude questions instead of explaining equality of vapour and atmospheric pressures at boiling. |
| S48 | No | No | Lists reactants and products correctly but incorrectly describes aerobic respiration's main energy change as chemical energy to heat and light. |
| S49 | Yes | Yes | Corrects the immediate-cure claim and explains adaptive recognition, antibodies and a faster memory response on later exposure. |
| S50 | No | No | Mentions mosquito bites but omits Plasmodium and prevention, then generates unrelated questions rather than completing the requested explanation. |

## Review boundaries

Second review resolved S27 as a pass: its evaporation account is complete, and the subsequent air-transport reference is not a definite contradiction. S41 remains a failure because fewer animals being eaten and a static energy-chain example do not explain reduced food supply causing population decline. S43 remains a failure because the numerical meaning of acceleration is wrong. S45 is a failure because the hairdryer suggestion introduces unsafe advice despite the valid towel option. Guidance from [Electrical Safety First](https://www.electricalsafetyfirst.org.uk/news-and-insights/how-to-prevent-an-electrical-burn/) explicitly warns against using electrical appliances with wet hands. The two changed judgments cancel: 57 strict passes and 82 correct core answers remain. No raw response was edited.

## Provenance and limitations

The check-policy clarification was applied to all seven missing-check responses (M26, M27, M29, M30, M35, M39, M43). None supplies an alternative numerical method; no grade changed.

- Model: `Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf`
- Model SHA-256: `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`
- Source: [stem-responses.jsonl](../raw/stem-responses.jsonl), SHA-256 `5996240435fb63674cf60173756bdb2926b54654d5d752871fa8ab1daa158294`
- Lifecycle: [stem-events.jsonl](../raw/stem-events.jsonl), SHA-256 `a6598af5646914ffa17534c1426a733b657ca62d33357da4386b2f6d5d7555c0`
- Server SHA-256: `379d824db41143559e5524bb8a84d543666fa8ccc1541bfbc0310fb698347d43`
- The lifecycle command records scalar-server path, 2,048 context tokens, four CPU threads and zero GPU layers. There is no explicit host-cache limit in that original command; the later 256 MiB cap does not apply retroactively.
- Temperature zero, seed 42, 256/512 output-token limits and raw `/completion` use are reconstructed from the campaign protocol and runner design. They were not saved as complete settings objects in each original response.
- Original rows omit hardware-context fields, build flags and continuous isolation evidence. The GCP scalar identification uses the recorded command and campaign provenance.
- All 100 IDs, exact prompts, expected-answer fields and model hashes match the fixed suite. Every category contains 25 unique prompts. Twenty-one responses reached their output-token limit. Raw response files were not changed.
