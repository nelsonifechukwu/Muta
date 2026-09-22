"""Original evaluation-only science tutoring cases and evidence-backed score reducer.

No model calls. Semantic judgments must be supplied by a qualified reviewer or a
separately validated judge. The reducer is deliberately not a keyword grader.
Run with --build to create the review packet, never a training artifact.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/muta-science-tutor-20260919/sources/muta_authored_science_heldout"
PROVENANCE = ROOT / "provenance/science-tutor-20260919/sources"
SUBJECTS = ("physics", "chemistry", "biology", "earth_science")
GROUPS = ("concept_causal", "quantitative", "experimental_misconception", "adaptive_judgment")
REQUEST = (
    " Please correct my reasoning and explain the science briefly, using words I can follow. "
    "For a calculation, include the corrected result and units. Then ask one short check "
    "question that I can answer next; do not answer that check question for me."
)

# Original factual notes from primary institutional pages read on 2026-09-19.
# These are citations, not copied exercises, source text, or third-party grants.
REFERENCES = {
    "field": (
        "NASA: Millennium of Geomagnetism",
        "https://pwg.gsfc.nasa.gov/earthmag/mill_4.htm",
        "Magnetic field lines are a visualization of a field, not physical strings.",
        "web indexed page text",
    ),
    "power": (
        "EIA: Measuring Electricity",
        "https://www.eia.gov/energyexplained/electricity/measuring-electricity.php",
        "Watts express power; watt-hours express power accumulated over time.",
        "web open and indexed text",
    ),
    "pendulum": (
        "NASA: Anatomy of Black Holes, pendulum activity",
        "https://imagine.gsfc.nasa.gov/educators/blackholes/imagine/page19.html",
        "Pendulum measurements specify length and small swings; timing several cycles reduces relative timing error. We use no published exercise quantities.",
        "web open and indexed text",
    ),
    "design": (
        "NIST: Completely Randomized Designs",
        "https://www.itl.nist.gov/div898/handbook/pri/section3/pri331.htm",
        "Random allocation and replicated units support comparisons of a treatment.",
        "web open text",
    ),
    "wetbulb": (
        "NWS: Dry Bulb, Wet Bulb and Dew Point",
        "https://www.weather.gov/source/zhu/ZHU_Training_Page/definitions/dry_wet_bulb_definition/dry_wet_bulb.html",
        "Evaporation cools the wet sensor; at saturation ideal wet and dry readings coincide. We do not adopt the page's loose heat-content wording.",
        "web indexed page text",
    ),
    "soda": (
        "USGS: Bottled Soda and Volcanic Eruptions",
        "https://www.usgs.gov/observatories/hvo/news/volcano-watch-bottled-soda-helps-us-understand-volcanic-eruptions",
        "Carbonated drinks hold dissolved carbon dioxide under pressure, not liquid carbon dioxide droplets.",
        "web indexed page text",
    ),
    "reaction": (
        "CSUN chemistry faculty: Chemical and Physical Changes",
        "https://www.csun.edu/~hcchm003/100/CHEM100_text_ch4S14.pdf",
        "Chemical equations conserve atom counts through balanced coefficients; magnesium reacts with oxygen to form magnesium oxide. Original mole amounts below are not taken from its exercises.",
        "web open PDF text",
    ),
    "chromatography": (
        "NIST: Multidimensional Chromatography",
        "https://www.nist.gov/programs-projects/multidimensional-chromatography",
        "Compounds can co-elute in one separation; a different retention mechanism can resolve them.",
        "web indexed page text",
    ),
    "boiling": (
        "USGS: Yellowstone Boiling Waters",
        "https://www.usgs.gov/observatories/yvo/news/how-hot-are-yellowstones-boiling-waters-some-are-hotter-others",
        "Water's boiling temperature depends on surrounding pressure and composition, not one universal temperature.",
        "web indexed page text",
    ),
    "selection": (
        "NPS: Florissant Evolution Background",
        "https://www.nps.gov/flfo/learn/education/unit-three-background.htm",
        "Heritable variation with differential survival and reproduction changes populations across generations, not through individuals choosing new traits.",
        "web indexed page text",
    ),
    "division": (
        "NHGRI: Cell Cycle",
        "https://www.genome.gov/genetics-glossary/Cell-Cycle",
        "A completed cell division produces two daughter cells that can begin further cycles; hypothetical constant timing is not a claim about all cells.",
        "web indexed page text",
    ),
    "pollination": (
        "USDA ARS: Pollen Loads and Plant Fertilization",
        "https://www.ars.usda.gov/research/publications/publication/?seqNo115=427751",
        "Bee pollen baskets mostly supply bee food; visitation or collected pollen alone does not establish successful delivery to a floral stigma.",
        "web indexed publication abstract",
    ),
    "foodweb": (
        "NPS: Food Webs",
        "https://www.nps.gov/teachers/classrooms/food-webs.htm",
        "Predator changes can have indirect ecosystem effects, but complex food webs and other conditions limit precise predictions.",
        "web indexed page text",
    ),
    "relative": (
        "USGS: Superposition and Cross-Cutting Relations",
        "https://pubs.usgs.gov/gip/fossils/laws.html",
        "A cross-cutting structure is younger than the pre-existing rock it cuts; relative sequence alone does not give a numerical age.",
        "web indexed page text",
    ),
    "decay": (
        "USGS: Radiometric Time Scale",
        "https://pubs.usgs.gov/gip/geotime/radiometric.html",
        "Each half-life removes half the parent atoms then present; dating requires an interpretable isotope history. No source table's isotope values are used below.",
        "web indexed page text",
    ),
    "seismic": (
        "USGS: P-wave and S-wave Paths",
        "https://www.usgs.gov/media/images/p-wave-and-s-wave-paths-through-earth",
        "P waves propagate through solids and liquids; liquids do not support propagating bulk shear waves.",
        "web indexed page text",
    ),
    "warning": (
        "USGS: Warning, Forecasts, Probabilities and Prediction",
        "https://www.usgs.gov/faqs/what-difference-between-earthquake-early-warning-earthquake-forecasts-earthquake-probabilities?items_per_page=6&page=1",
        "Earthquake early warning detects a rupture already under way; long-term probability is not an exact date prediction.",
        "web indexed page text",
    ),
}


def case(
    subject,
    group,
    split,
    slug,
    references,
    turns,
    misconception,
    core,
    acceptable,
    errors,
    check_goal,
    numeric=None,
):
    return {
        "subject": subject,
        "capability_group": group,
        "split": split,
        "slug": slug,
        "references": references,
        "turns": turns,
        "student_misconception": misconception,
        "core": core,
        "acceptable_responses": acceptable,
        "critical_errors": errors,
        "check_goal": check_goal,
        "numeric": numeric or [],
    }


CASES = [
    case(
        "physics",
        "concept_causal",
        "dev",
        "field-map-empty-gaps",
        ["field"],
        [
            "My textbook draws a few curved lines around a bar magnet. Are the blank spaces between those lines places where the magnetic field is absent?",
            "Are the drawn lines objects in the room, or a way to describe measurements at different locations?",
            "They must be narrow magnetic strings. A compass placed between the strings would have no magnetic field to respond to.",
        ],
        "Treats selected field lines as physical strings separated by field-free space.",
        [
            "Explains that drawn field lines represent a spatial magnetic field, rather than material strings.",
            "Rejects the inference that a blank part of the drawing necessarily has zero magnetic field.",
            "Explains that a compass responds to the local resultant field direction, not whether ink is drawn there.",
            "Distinguishes changing the number of drawn lines from physically changing the magnet or field.",
        ],
        [
            "A map or contour-line analogy is acceptable if its limits are clear.",
            "May acknowledge true zero-field points caused by cancellation; must not equate them with arbitrary drawing gaps.",
        ],
        [
            "Affirms that magnetic field exists only on the drawn lines.",
            "Claims that drawing extra lines increases the physical field strength.",
        ],
        "Ask whether redrawing the same magnet with more lines changes a compass reading.",
    ),
    case(
        "physics",
        "quantitative",
        "final",
        "logger-two-power-modes",
        ["power"],
        [
            "A data logger draws a constant 18 W for 12 minutes, then 3 W for 48 minutes. It has no other operating phases. Find the total electrical energy in Wh and the average power over that hour.",
            "Power is a rate. How will the time spent at each rate affect the energy total?",
            "I added 18 and 3 and got 21 Wh. The average power must also be 21 W because both modes were used.",
        ],
        "Adds power levels without weighting by duration and confuses power with energy.",
        [
            "Uses energy = power × time with minutes converted to hours for Wh.",
            "Calculates the two contributions as 3.6 Wh and 2.4 Wh, totaling 6 Wh (or an explicitly equivalent energy).",
            "Divides total energy by the full one-hour interval to get average power 6 W.",
            "Explains why adding rates from successive intervals is not the requested energy or time-average.",
        ],
        [
            "Equivalent energy 21600 J or 21.6 kJ is acceptable when tied to 6 Wh; average remains 6 W.",
            "A duration-weighted average or an energy-first method is equally valid.",
        ],
        [
            "Endorses 21 Wh as the energy or 21 W as the average power.",
            "Uses minutes directly with watts and labels the result Wh without conversion.",
        ],
        "Ask how the average would move if more of the hour were spent in the high-power mode, without solving it.",
        ["logger_energy", "logger_average"],
    ),
    case(
        "physics",
        "experimental_misconception",
        "final",
        "pendulum-amplitude-trial",
        ["pendulum", "design"],
        [
            "I want to test whether a pendulum's release angle affects its period. I change the angle and also shorten the string for the second trial. Both measured periods are similar.",
            "What changed besides release angle, and what range would your observations actually test?",
            "Length does not matter. Similar results from these two trials prove angle can never affect the period at any angle.",
        ],
        "Ignores changed pendulum length and extrapolates two noisy observations to all amplitudes.",
        [
            "Identifies length as a confound and proposes holding length and the pendulum setup fixed while changing release angle.",
            "Proposes repeated timings of multiple full swings, a consistent release without an extra push, and a consistent definition of period.",
            "Treats similar readings within uncertainty as limited evidence, not proof of exact equality or all-angle independence.",
            "States that approximate amplitude independence is a small-angle model, not an unrestricted law.",
        ],
        [
            "Randomized trial order and timing sensors are useful, not mandatory.",
            "No pendulum equation is required; plain-language reasoning earns full credit.",
        ],
        [
            "States that simple-pendulum period is exactly independent of amplitude at every release angle.",
            "Affirms that the changed length cannot affect the comparison.",
        ],
        "Ask which variable should change in the redesigned comparison and which should remain fixed.",
    ),
    case(
        "physics",
        "adaptive_judgment",
        "dev",
        "wet-sensor-same-room",
        ["wetbulb"],
        [
            "Two checked thermometers share the same shaded moving air. One has a wet cloth on its bulb and reads lower after stabilizing. I am confused: is it measuring colder air?",
            "What process can remove energy from the wet cloth even while both instruments share the same surrounding air?",
            "The water must just have started cold. Once it started at room temperature, a wet thermometer could never read below the dry one.",
        ],
        "Attributes a sustained wet-bulb depression only to initial water temperature.",
        [
            "Explains that evaporation requires energy and can cool the wet sensor below the surrounding dry-bulb air temperature.",
            "Distinguishes the wet sensor's temperature from a claim that its ambient air is a separate colder air mass.",
            "States that air humidity affects evaporation and the wet-dry difference; initial water temperature alone does not explain the stabilized difference.",
            "Qualifies that, ideally at saturation under suitable measurement conditions, evaporation cooling vanishes and the readings coincide.",
        ],
        [
            "A drying-skin analogy is acceptable without health advice.",
            "May discuss airflow or radiation control as measurement caveats, but must answer the stated misconception.",
        ],
        [
            "Claims evaporation cannot cool initially room-temperature water.",
            "Claims a wet-bulb thermometer must always be lower even at ideal saturation.",
        ],
        "Ask what happens to the difference as otherwise comparable air becomes more humid.",
    ),
    case(
        "chemistry",
        "concept_causal",
        "final",
        "uncapped-carbonated-sample",
        ["soda"],
        [
            "An unopened bottle contains carbonated water. When the cap is removed, bubbles appear. Does seeing bubbles alone prove that a brand-new gas was made by a chemical reaction?",
            "Could a substance already present in the liquid move into a gas phase when the pressure changes?",
            "No. If I could not see the gas before, it could not have been present. Bubbles always prove a new substance formed.",
        ],
        "Treats visible bubbling as unique evidence for chemical production of a new gas.",
        [
            "Explains that carbon dioxide can already be dissolved in the unopened liquid despite not being visible as bubbles.",
            "Connects opening the bottle and reduced gas pressure to carbon dioxide leaving solution.",
            "Rejects bubbles alone as a unique diagnostic of a new chemical substance; phase transfer can also create bubbles.",
            "Avoids claiming that no chemical equilibria exist in carbonated water; the observation alone does not identify the mechanism uniquely.",
        ],
        [
            "An explanation of pressure-dependent gas solubility without naming Henry's law is enough.",
            "May mention carbonic-acid equilibria, but they are not required for a beginner explanation.",
        ],
        [
            "Says dissolved gas cannot exist until it becomes visible.",
            "Says every bubble is proof of a chemical reaction creating a new substance.",
        ],
        "Ask whether bubbles from boiling pure water would by themselves establish a new chemical substance.",
    ),
    case(
        "chemistry",
        "quantitative",
        "dev",
        "oxide-limiting-amount",
        ["reaction"],
        [
            "For a paper calculation, 2 Mg + O₂ → 2 MgO is the only reaction. Initially there are 0.20 mol Mg and 0.15 mol O₂. Assume complete reaction with no side reactions. Which reactant limits the product, how many mol MgO form, and how many mol O₂ remain?",
            "Should available mole amounts be compared directly, or compared with the coefficients in the balanced reaction?",
            "Oxygen limits it because 0.15 is smaller than 0.20. So 0.15 mol MgO forms and no oxygen remains.",
        ],
        "Chooses the smaller mole amount without accounting for the 2:1 reaction ratio.",
        [
            "Uses the balanced ratio: 0.20 mol Mg requires only 0.10 mol O₂.",
            "Identifies Mg as limiting because the stated oxygen amount exceeds that requirement.",
            "Calculates 0.20 mol MgO and 0.05 mol unreacted O₂ under the supplied complete-reaction assumption.",
            "Explains that the limiting reagent depends on amount relative to stoichiometric demand, not the smaller raw number.",
        ],
        [
            "Comparing possible reaction extents 0.20/2 and 0.15/1 is equivalent.",
            "Millimole answers are acceptable with correct conversions; this is not a practical combustion instruction.",
        ],
        [
            "Affirms O₂ is limiting for these quantities.",
            "Treats Mg, O₂ and MgO as a 1:1:1 mole ratio.",
        ],
        "Ask whether supplying more oxygen alone could raise product after all magnesium was consumed.",
        ["oxide_product", "oxygen_left"],
    ),
    case(
        "chemistry",
        "experimental_misconception",
        "dev",
        "one-chromatographic-feature",
        ["chromatography"],
        [
            "A liquid-chromatography run of an unknown sample gives one detected peak. My classmate says we have proved the sample contains exactly one compound.",
            "Could the method fail to separate two compounds, or fail to detect one of them?",
            "No. One peak always means one molecule type, so another separation method could add no evidence.",
        ],
        "Confuses one observed chromatographic feature with a proof of chemical purity.",
        [
            "Explains that different compounds may co-elute and appear within one unresolved peak.",
            "Recognizes detection limits or detector response as another reason some components may be missed.",
            "Proposes additional evidence such as a different separation mechanism or suitable complementary detection, rather than declaring purity proven.",
            "Frames the result as one detected feature under the stated method, not proof of exactly one compound or one molecule.",
        ],
        [
            "A plain-language account of two substances traveling together is sufficient.",
            "The answer may recommend standards or blanks as useful controls; no hazardous solvent procedure is required.",
        ],
        [
            "Claims every chromatographic peak necessarily contains exactly one compound.",
            "Concludes purity is proven from the single run alone.",
        ],
        "Ask what two peaks appearing with a second separation method would mean for the original claim.",
    ),
    case(
        "chemistry",
        "adaptive_judgment",
        "final",
        "boiling-reference-pressure",
        ["boiling"],
        [
            "In a supervised demonstration, pure water boils steadily at a mountain site below its familiar sea-level boiling temperature. Does that by itself prove the thermometer is broken? I do not understand how a fixed property could change.",
            "When a table gives a boiling temperature, could it also require a specified surrounding pressure?",
            "No. Pure water must boil at the same temperature everywhere, so pressure measurements would be irrelevant.",
        ],
        "Treats a pressure-dependent phase-change temperature as an unconditional constant.",
        [
            "Explains that boiling temperature depends on surrounding pressure, even for pure water.",
            "States that lower surrounding pressure allows pure water to boil at a lower temperature.",
            "Separates a plausible pressure explanation from proof that the instrument is correct or broken.",
            "Proposes checking pressure and thermometer calibration (and purity if uncertain) before diagnosing the observation.",
        ],
        [
            "May explain that boiling begins when vapor pressure matches surrounding pressure, with a simple definition.",
            "No exact mountain boiling temperature is inferable without additional information.",
        ],
        [
            "Says pure water's boiling temperature is independent of pressure.",
            "Infers a specific numerical boiling temperature from an unspecified altitude or pressure.",
        ],
        "Ask whether a higher surrounding pressure would raise or lower the boiling temperature.",
    ),
    case(
        "biology",
        "concept_causal",
        "dev",
        "beetle-color-selection",
        ["selection"],
        [
            "A beetle population already has inherited dark and pale forms. Birds find pale beetles more easily on dark bark, and dark survivors leave more offspring. After several generations, dark beetles are more common. Did each pale beetle decide to change color?",
            "Which changed in the description: each individual's inherited color, or which individuals contributed more offspring?",
            "The pale beetles must have deliberately changed their inherited color because they needed camouflage.",
        ],
        "Replaces selection among existing inherited variants with purposeful individual transformation.",
        [
            "Uses the stated pre-existing inherited color variation rather than inventing need-directed mutation.",
            "Connects differential detection and survival with the stated greater reproductive contribution of dark beetles.",
            "Explains a change in population trait frequency across generations, not a deliberate change in each pale individual.",
            "Qualifies the advantage as environment-dependent; a different background could change which form is favored.",
        ],
        [
            "A survival-and-offspring story earns full credit without technical population-genetics terms.",
            "May note that survival alone is insufficient unless it affects reproduction; the prompt explicitly supplies this link.",
        ],
        [
            "Affirms that camouflage need intentionally changes the inherited color of every individual.",
            "Claims dark coloration must be advantageous in every environment.",
        ],
        "Ask how a pale background might change the direction of selection.",
    ),
    case(
        "biology",
        "quantitative",
        "final",
        "ideal-cell-count-cycles",
        ["division"],
        [
            "In an explicitly ideal cell-division model, a population starts with 20 cells and every cell completes division into two daughters every 40 minutes. No cells die or leave, and all continue this schedule. How many cells are present after 120 minutes?",
            "How many completed division intervals fit in that time, and what happens to the whole population during each one?",
            "There are three intervals, so I add two cells three times: 20 + 6 = 26. That should also predict any real culture forever.",
        ],
        "Adds a fixed pair of cells per interval instead of doubling every existing cell and ignores model limits.",
        [
            "Finds three complete division intervals from 120/40.",
            "Applies doubling to the entire population each interval: 20, 40, 80, 160.",
            "Gives 160 cells after 120 minutes, not 26, under the exact model assumptions.",
            "States that real growth need not keep that schedule indefinitely because resources, conditions or cell loss may change.",
        ],
        [
            "20 × 2³ or an explicit doubling table is equally valid.",
            "No details of chromosome structure are required and no real species' cell-cycle duration is being asserted.",
        ],
        [
            "Endorses adding only two cells per population per interval.",
            "Claims the hypothetical rate must persist indefinitely in a real finite culture.",
        ],
        "Ask what operation would give the model count after one more interval, without supplying that count.",
        ["division_intervals", "cell_count"],
    ),
    case(
        "biology",
        "experimental_misconception",
        "final",
        "flower-visits-not-seed-proof",
        ["pollination", "design"],
        [
            "We recorded bees visiting many flowers of an unfamiliar plant but did not examine pollen on stigmas or follow fruit and seed formation. Have we proved that every visited flower was successfully fertilized?",
            "What needs to happen between a visit and successful reproduction? Which of those events did you actually measure?",
            "A visit guarantees fertilization. Pollen packed on a bee's legs must all have reached the flower's stigma, so seed observations are unnecessary.",
        ],
        "Treats visitation and collected pollen as guaranteed effective pollen delivery and fertilization.",
        [
            "Distinguishes seeing a bee visit from demonstrating compatible pollen delivery to a stigma.",
            "Rejects the claim that pollen collected on a bee's legs necessarily reaches the stigma; some is carried away as food.",
            "Proposes observing pollen delivery and tracking later reproductive outcomes, with comparable flowers or appropriate pollination controls.",
            "Keeps conclusions limited: even pollen arrival need not guarantee fertilization or mature seeds, and seed outcomes have additional influences.",
        ],
        [
            "May propose pollen-exclusion and hand-pollination controls while noting any bagging or handling effects.",
            "Does not need to describe every reproductive structure to distinguish the evidence stages.",
        ],
        [
            "Says every bee visit guarantees fertilization of the flower.",
            "Says all pollen in a bee's pollen baskets is necessarily delivered to floral stigmas.",
        ],
        "Ask which additional observation would directly test pollen delivery rather than merely visitation.",
    ),
    case(
        "biology",
        "adaptive_judgment",
        "dev",
        "predator-loss-simple-web",
        ["foodweb"],
        [
            "In a simplified meadow model, owls eat seed-eating rodents and the rodents eat grass seeds. Suppose owl predation becomes weaker. Must the grass population increase? I keep losing track of the indirect links.",
            "First consider the rodents' response to weaker predation; then follow their effect on seeds.",
            "Everything below the owls benefits, so both rodents and grasses must increase by the same amount.",
        ],
        "Assumes every lower food-web level responds in the same direction and with an exact shared size.",
        [
            "Explains that weaker owl predation could allow rodents to increase, other conditions held comparable.",
            "Connects more seed-eating rodents with greater seed consumption and possible reduction in grass recruitment.",
            "Distinguishes the indirect plant effect from the direct predator-prey effect; all lower levels need not benefit.",
            "Avoids guaranteed amounts or outcomes for a real meadow and identifies other resources or interactions as relevant.",
        ],
        [
            "A two-link verbal chain is sufficient; formal food-web diagrams are unnecessary.",
            "May distinguish recruitment from total established-grass abundance rather than guaranteeing immediate plant decline.",
        ],
        [
            "Claims removing a predator necessarily increases every population below it.",
            "Predicts an exact shared population increase without any quantitative evidence.",
        ],
        "Ask which link would change if the rodents ate a different food instead of grass seeds.",
    ),
    case(
        "earth_science",
        "concept_causal",
        "final",
        "sealed-fault-relative-order",
        ["relative"],
        [
            "A field description says a fault offsets an older sandstone bed. A later gravel layer rests across the eroded fault surface and is not displaced; assume no later fault movement. Which came first: the sandstone, the faulting, or the gravel? No numerical dates are available.",
            "Could a fault offset a bed before that bed existed, and what does the undisturbed layer across the fault tell you?",
            "The faulting must be oldest because the fault reaches deepest. That also gives the exact ages in years.",
        ],
        "Uses depth instead of cross-cutting relationships and confuses relative order with numerical age.",
        [
            "Places sandstone deposition before the faulting that offsets it.",
            "Places gravel deposition after the faulting under the supplied sealed-surface/no-later-movement conditions.",
            "States the relative order sandstone, faulting, gravel and explains it using the observed relationships rather than depth alone.",
            "Does not invent numerical dates; ordering events is different from measuring elapsed years.",
        ],
        [
            "May mention erosion as an intervening event without changing the requested three-event order.",
            "No unseen diagram, fossil identity or isotope data may be assumed.",
        ],
        [
            "Says faulting is older than the sandstone it displaced solely because the fault extends deeper.",
            "Claims these relationships determine exact ages in years.",
        ],
        "Ask whether a new fault cutting the gravel would be earlier or later than that gravel.",
    ),
    case(
        "earth_science",
        "quantitative",
        "dev",
        "closed-mineral-model-clock",
        ["decay"],
        [
            "For a model geological clock, hypothetical isotope Q has a half-life of 2.4 million years. A mineral has retained all parent and daughter atoms since the clock began, and its initial parent amount is known. Exactly 1/16 of that parent amount remains. Find elapsed time under this model.",
            "After each half-life, do you halve the initial amount again, or halve whatever parent amount remains?",
            "A sixteenth means sixteen half-lives. So I multiply 16 by 2.4, and leakage of parent atoms could never affect the age estimate.",
        ],
        "Confuses a remaining fraction with the number of repeated halvings and ignores closed-system assumptions.",
        [
            "Uses repeated halving: 1, 1/2, 1/4, 1/8, 1/16, hence four half-lives.",
            "Multiplies four by 2.4 million years to obtain 9.6 million years.",
            "Explains why the denominator 16 is not a count of half-lives.",
            "States that the parent-only age inference assumes the original parent amount is known and no parent isotope has entered or left since closure; parent loss or gain can bias the inferred age.",
        ],
        [
            "A logarithmic solution is acceptable but not required for a beginner.",
            "Correctly notes that daughter loss alone does not change this parent-only calculation when the initial and remaining parent amounts are independently known; daughter retention matters for dating methods that infer age from parent-daughter ratios.",
            "9600000 years and 9.6 Myr are equivalent; no real isotope identification is requested.",
        ],
        [
            "Endorses sixteen half-lives or 38.4 million years.",
            "Says parent-atom leakage cannot affect a ratio-based age estimate.",
        ],
        "Ask what fraction would remain after one additional half-life, without answering it.",
        ["clock_halflives", "clock_age"],
    ),
    case(
        "earth_science",
        "experimental_misconception",
        "dev",
        "seismic-missing-signal",
        ["seismic"],
        [
            "One seismic station records a P wave but no clear S wave from an earthquake. A classmate says this alone proves every part of Earth's interior is liquid. How should we test that interpretation?",
            "What else could explain a missing detection, and would one path describe the whole planet?",
            "Nothing else could explain it. Liquids transmit both P and S waves, and a missing trace at one station proves all rocks below us are liquid.",
        ],
        "Misstates shear-wave transmission and overinterprets one missing signal as a global material measurement.",
        [
            "Correctly states that bulk S/shear waves do not propagate through liquids, whereas P/compressional waves can.",
            "Rejects a conclusion about every interior region from one station's missing S detection.",
            "Proposes checking recording quality and comparing consistent observations across stations, earthquakes and paths.",
            "Explains that systematic wave behavior constrains interior structure; an absent signal alone is not direct proof of a completely liquid Earth.",
        ],
        [
            "May mention source radiation pattern, attenuation or noise as alternative detection explanations.",
            "Mode conversion can be noted but is not required; must not turn it into a claim that bulk S waves freely traverse liquid.",
        ],
        [
            "Claims ordinary bulk shear waves propagate through a liquid in the same way as through a solid.",
            "Claims the single missing trace proves the whole interior is liquid.",
        ],
        "Ask why matching observations from several paths would be stronger evidence than one missing trace.",
    ),
    case(
        "earth_science",
        "adaptive_judgment",
        "final",
        "warning-versus-prediction",
        ["warning"],
        [
            "A hypothetical alert reaches a town shortly before strong earthquake shaking. Does that mean the system predicted the earthquake before it began? I thought an early warning and an exact prediction were the same.",
            "Could sensors detect a rupture already happening elsewhere while its shaking waves are still traveling toward the town?",
            "No. Early warning must name the day of an earthquake before any rupture starts, and it guarantees every town gets warning time.",
        ],
        "Confuses rapid detection of an ongoing event with advance exact prediction and assumes universal warning time.",
        [
            "Explains that earthquake early warning can detect an earthquake after rupture starts but before stronger shaking reaches some locations.",
            "Distinguishes this from predicting the exact future event before it begins.",
            "Explains why distance, detection and communication delays can leave some locations with little or no useful warning time.",
            "Does not treat long-term probabilities as exact dates or promise a specific warning duration from missing location and timing data.",
        ],
        [
            "A messages-versus-wave-travel explanation is enough; numerical wave speeds are not needed.",
            "May mention following official alerts without inventing safety guarantees or a current local forecast.",
        ],
        [
            "Says all earthquake early warning is prediction before rupture begins.",
            "Guarantees positive warning time for every location in every earthquake.",
        ],
        "Ask why a town very near the rupture might have less warning time than a farther town.",
    ),
]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def independent_numeric_values():
    """Derive results from the authored givens, not from expected answer strings."""
    energy_wh = Fraction(18) * Fraction(12, 60) + Fraction(3) * Fraction(48, 60)
    extent = min(Fraction("0.20") / 2, Fraction("0.15"))
    intervals = Fraction(120, 40)
    remaining, halflives = Fraction(1), 0
    while remaining > Fraction(1, 16):
        remaining /= 2
        halflives += 1
    return {
        "logger_energy": energy_wh,
        "logger_average": energy_wh / Fraction(12 + 48, 60),
        "oxide_product": 2 * extent,
        "oxygen_left": Fraction("0.15") - extent,
        "division_intervals": intervals,
        "cell_count": Fraction(20 * 2 ** int(intervals)),
        "clock_halflives": Fraction(halflives),
        "clock_age": Fraction("2.4") * 1000000 * halflives,
    }


# value in canonical units, allowed unit => multiplier into canonical units,
# and a required authored-rubric span. No heuristic extraction from model prose.
NUMERIC = {
    "logger_energy": ("6", "Wh", {"Wh": "1", "J": "1/3600", "kJ": "5/18", "kWh": "1000"}, "6 Wh"),
    "logger_average": ("6", "W", {"W": "1", "kW": "1000"}, "6 W"),
    "oxide_product": ("0.20", "mol", {"mol": "1", "mmol": "1/1000"}, "0.20 mol MgO"),
    "oxygen_left": ("0.05", "mol", {"mol": "1", "mmol": "1/1000"}, "0.05 mol"),
    "division_intervals": (
        "3",
        "intervals",
        {"intervals": "1"},
        "three complete division intervals",
    ),
    "cell_count": ("160", "cells", {"cells": "1"}, "160 cells"),
    "clock_halflives": ("4", "half-lives", {"half-lives": "1"}, "four half-lives"),
    "clock_age": (
        "9600000",
        "years",
        {"years": "1", "Myr": "1000000", "million years": "1000000"},
        "9.6 million years",
    ),
}


def build_cases():
    revision = sha(
        canonical(
            {"cases": CASES, "references": REFERENCES, "numeric": NUMERIC, "request": REQUEST}
        ).encode()
    )
    values = independent_numeric_values()
    rows = []
    for item in CASES:
        rubric_text = " ".join(item["core"])
        numeric = []
        for key in item["numeric"]:
            value, unit, units, span = NUMERIC[key]
            if Fraction(value) != values[key] or span not in rubric_text:
                raise ValueError(f"Numeric/rubric mismatch: {key}")
            numeric.append(
                {
                    "id": key,
                    "value_exact": str(values[key]),
                    "canonical_unit": unit,
                    "accepted_units_to_canonical": units,
                    "rubric_span": span,
                    "verification": "independent_exact_arithmetic_passed",
                }
            )
        row_id = "muta_heldout16:" + item["slug"]
        messages = [
            {
                "role": "assistant" if index == 1 else "user",
                "content": text + (REQUEST if index == 2 else ""),
            }
            for index, text in enumerate(item["turns"])
        ]
        rows.append(
            {
                "id": row_id,
                "group_id": row_id,
                "source": "muta_authored_science_heldout",
                "source_id": item["slug"],
                "source_revision": revision,
                "license": "LicenseRef-Project-Original",
                "subject": item["subject"],
                "capabilities": [item["capability_group"]],
                "split": item["split"],
                "original_split": item["split"],
                "usage": "evaluation_only_never_train",
                "train_eligible": False,
                "eligibility": "pending_independent_review_and_overlap_screen",
                "messages": messages,
                "student_misconception": item["student_misconception"],
                "expected_core_science": item["core"],
                "acceptable_responses": item["acceptable_responses"],
                "rubric": {
                    "science": [
                        {"id": f"S{i + 1}", "criterion": text, "points": 1}
                        for i, text in enumerate(item["core"])
                    ],
                    "tutoring": [
                        {
                            "id": "T1",
                            "criterion": "Explicitly identifies and repairs the learner's stated reasoning error, rather than only stating an answer.",
                            "points": 1,
                        },
                        {
                            "id": "T2",
                            "criterion": "Builds an understandable causal or procedural bridge from the learner's current idea, defining necessary terminology; a verdict or unexplained formula alone is insufficient.",
                            "points": 1,
                        },
                        {
                            "id": "T3",
                            "criterion": "Uses a respectful, concise, age-appropriate response without needless overload or pretending the learner already mastered the idea.",
                            "points": 1,
                        },
                        {
                            "id": "T4",
                            "criterion": "Asks one relevant, answerable check question and leaves its answer to the learner. Suggested target: "
                            + item["check_goal"],
                            "points": 1,
                        },
                    ],
                    "critical_errors": [
                        {"id": f"E{i + 1}", "description": text}
                        for i, text in enumerate(item["critical_errors"])
                    ],
                    "critical_error_rule": "Any affirmed critical error caps science at 1/4; tutoring stays separately scored.",
                    "scale": "Each met semantic criterion contributes one point: science 0–4 and tutoring 0–4. Report both, not a blended accuracy claim.",
                    "judge_requirement": "Human or separately validated semantic judge; consider meaning, negation, context and contradictions, not keyword presence. Assess the whole response, including added claims.",
                    "unlisted_error_rule": "Record any additional material scientific falsehood with response evidence; it also caps science at 1/4.",
                },
                "numeric_checks": numeric,
                "quality": {
                    "content_review": "pending_independent_review",
                    "family_independence": "not_claimed",
                    "reference_grounded": True,
                    "all_statements_independently_verified": False,
                },
                "reference_ids": item["references"],
                "reference_urls": [REFERENCES[k][1] for k in item["references"]],
                "authorship": "Original synthetic learner context and evaluation rubric; not a real student's transcript or a copied published exercise.",
            }
        )
    expected = Counter((s, g) for s in SUBJECTS for g in GROUPS)
    if Counter((r["subject"], r["capabilities"][0]) for r in rows) != expected:
        raise ValueError("Expected exactly four subjects by four capability groups")
    if Counter((r["subject"], r["split"]) for r in rows) != Counter(
        {(s, p): 2 for s in SUBJECTS for p in ("dev", "final")}
    ):
        raise ValueError("Expected two dev and two final cases per subject")
    if len({r["id"] for r in rows}) != 16:
        raise ValueError("Duplicate evaluation case ID")
    return rows


def model_input(row):
    """Only this payload is model-facing. Rubrics/answers never enter inference."""
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "split": row["split"],
        "messages": copy.deepcopy(row["messages"]),
    }


def check_numeric_answers(row, answers):
    """Check already semantically extracted values; do not claim prose grading."""
    expected = {item["id"]: item for item in row["numeric_checks"]}
    if not isinstance(answers, dict) or set(answers) != set(expected):
        raise ValueError("Numeric keys must exactly match this case")
    results = {}
    for key, spec in expected.items():
        supplied = answers[key]
        if not isinstance(supplied, dict) or set(supplied) != {"value", "unit"}:
            raise ValueError("Each numeric answer requires value and unit")
        unit = supplied["unit"]
        if not isinstance(unit, str) or unit not in spec["accepted_units_to_canonical"]:
            results[key] = {"passed": False, "reason": "unsupported_or_wrong_unit"}
            continue
        if not isinstance(supplied["value"], str) or len(supplied["value"]) > 100:
            raise ValueError("Values must be finite decimal/fraction strings")
        try:
            value = Fraction(supplied["value"])
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("Invalid finite numeric value") from exc
        converted = value * Fraction(spec["accepted_units_to_canonical"][unit])
        passed = converted == Fraction(spec["value_exact"])
        results[key] = {"passed": passed, "reason": "exact_match" if passed else "wrong_value"}
    return results


def _validate_judgment(item, response, flag):
    if not isinstance(item, dict) or set(item) != {flag, "evidence", "rationale"}:
        raise ValueError(f"Judgment requires {flag}, evidence and rationale")
    if type(item[flag]) is not bool:
        raise ValueError("Judgment flag must be a boolean")
    if not isinstance(item["rationale"], str) or not item["rationale"].strip():
        raise ValueError("A semantic rationale is required")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or any(
        not isinstance(s, str) or not s.strip() or s not in response for s in evidence
    ):
        raise ValueError("Evidence must contain exact nonempty response spans")
    if item[flag] and not evidence:
        raise ValueError("Affirmed judgments need response evidence")


def score_assessment(row, response, assessment):
    """Validate evidence-backed judgments; no automatic semantic inference here.

    Required assessment shape: science/tutoring => criterion ID =>
    {met: bool, evidence: [exact response span], rationale: str}; critical_errors
    => error ID => same shape with present instead of met; additional_errors =>
    list of {present: bool, evidence: [...], rationale: str}.
    Missing evidence for an absent/unsatisfied criterion may be [], with rationale.
    """
    if not isinstance(response, str) or not response.strip():
        raise ValueError("A nonempty model response is required")
    keys = {"science", "tutoring", "critical_errors", "additional_errors"}
    if not isinstance(assessment, dict) or set(assessment) != keys:
        raise ValueError("Assessment must include all scoring dimensions and error checks")
    totals = {}
    for dimension in ("science", "tutoring", "critical_errors"):
        judged = assessment[dimension]
        expected = {c["id"] for c in row["rubric"][dimension]}
        if not isinstance(judged, dict) or set(judged) != expected:
            raise ValueError(f"Exact criterion IDs required: {dimension}")
        flag = "present" if dimension == "critical_errors" else "met"
        for item in judged.values():
            _validate_judgment(item, response, flag)
        totals[dimension] = sum(item[flag] for item in judged.values())
    if not isinstance(assessment["additional_errors"], list):
        raise TypeError("additional_errors must be a list")
    for item in assessment["additional_errors"]:
        _validate_judgment(item, response, "present")
    critical = totals["critical_errors"] + sum(
        item["present"] for item in assessment["additional_errors"]
    )
    return {
        "science": min(totals["science"], 1) if critical else totals["science"],
        "tutoring": totals["tutoring"],
        "science_before_critical_cap": totals["science"],
        "critical_errors_present": critical,
        "scoring_method": "evidence_backed_semantic_judgment_reducer",
        "case_id": row["id"],
        "case_sha256": sha(canonical(row).encode()),
        "response_sha256": sha(response.encode()),
        "assessment_sha256": sha(canonical(assessment).encode()),
        "semantic_judge_validated_by_this_function": False,
    }


def write_artifact(path, value, jsonl=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        ("".join(canonical(row) + "\n" for row in value)) if jsonl else canonical(value) + "\n"
    ).encode()
    path.write_bytes(payload)
    return {"path": str(path), "sha256": sha(payload), "bytes": len(payload)}


def build(output=OUTPUT, provenance=PROVENANCE):
    rows = build_cases()
    artifacts = {}
    for split in ("dev", "final"):
        selected = [r for r in rows if r["split"] == split]
        artifacts[split + "_cases"] = write_artifact(
            output / f"{split}_cases.jsonl", selected, True
        )
        artifacts[split + "_prompts"] = write_artifact(
            output / f"{split}_prompts.jsonl", [model_input(r) for r in selected], True
        )
    artifacts["review_packet"] = write_artifact(
        provenance / "heldout16-review-packet.jsonl",
        [
            {
                "review_status": "pending_independent_review",
                "scope": "All input assertions, expected claims, alternatives, errors, numeric checks and rubric criteria",
                "case": row,
            }
            for row in rows
        ],
        True,
    )
    artifacts["references"] = write_artifact(
        provenance / "heldout16-reference-receipt.json",
        {
            "read_date": "2026-09-19",
            "rights": "Original cases and factual notes only; no source passages, published exercises or images reproduced. LicenseRef-Project-Original is internal provenance, not an external grant.",
            "references": [
                {
                    "id": k,
                    "title": title,
                    "url": url,
                    "original_factual_note": note,
                    "read_method": method,
                }
                for k, (title, url, note, method) in REFERENCES.items()
            ],
            "limits": "Dated web readings, not immutable webpage snapshots. Independent content review and source support verification remain required.",
        },
    )
    manifest = {
        "source": "muta_authored_science_heldout",
        "case_count": 16,
        "dev": 8,
        "final": 8,
        "train": 0,
        "usage": "evaluation_only_never_train",
        "source_revision": rows[0]["source_revision"],
        "pipeline_sha256": sha(Path(__file__).read_bytes()),
        "numeric_checks": sum(len(r["numeric_checks"]) for r in rows),
        "admission": "pending_independent_all_case_review_and_root_overlap_screen",
        "family_independence": "not_claimed",
        "known_suite_content_used_for_authoring": False,
        "inference_performed": False,
        "statistics_limit": "16 diagnostic cases, not a population-level estimate of tutoring quality.",
        "scoring_limit": "Executable evidence validation and score reduction are not validation of a semantic judge; root must validate the reviewer/judge protocol before trusting scores.",
        "score_axes": {"science": [0, 4], "tutoring": [0, 4]},
        "artifacts": artifacts,
    }
    write_artifact(provenance / "heldout16-manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--provenance", type=Path, default=PROVENANCE)
    args = parser.parse_args()
    result = build(args.output, args.provenance)
    print(
        canonical(
            {
                k: result[k]
                for k in ("case_count", "dev", "final", "train", "numeric_checks", "admission")
            }
        )
    )
