"""Fixed 100-prompt mathematics and science battery used by the Muta reports.

The suite is intentionally independent of the ADTC profiler. ARC-Easy remains the
quantitative score proxy; this battery exposes answer and explanation failures on a
common set of 50 mathematics and 50 science prompts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Prompt:
    id: str
    subject: str
    format: str
    text: str
    expected: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _multiple_choice() -> list[Prompt]:
    rows = [
        (
            "M01",
            "math",
            "A school in Lagos buys 6 boxes of chalk at ₦500 per box. What is the total cost? A. ₦1,000 B. ₦2,500 C. ₦3,000 D. ₦3,500. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M02",
            "math",
            "A pupil buys 8 exercise books at ₦250 each. What is the total cost? A. ₦1,000 B. ₦1,500 C. ₦2,000 D. ₦2,500. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M03",
            "math",
            "A teacher divides 36 pupils equally into 6 groups. How many pupils are in each group? A. 5 B. 8 C. 7 D. 6. Answer with the correct option and one calculation.",
            "D",
        ),
        (
            "M04",
            "math",
            "A bus travels at 60 kilometres per hour for 3 hours. How far does it travel? A. 120 km B. 180 km C. 240 km D. 60 km. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M05",
            "math",
            "A rectangular classroom is 8 metres long and 5 metres wide. What is its area? A. 13 m² B. 80 m² C. 26 m² D. 40 m². Answer with the correct option and one calculation.",
            "D",
        ),
        (
            "M06",
            "math",
            "What is one-quarter of 80 mangoes? A. 20 B. 10 C. 40 D. 60. Answer with the correct option and one calculation.",
            "A",
        ),
        (
            "M07",
            "math",
            "Chidi pays with ₦5,000 for 3 pens costing ₦600 each. How much change should he receive? A. ₦2,800 B. ₦3,000 C. ₦3,200 D. ₦3,800. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M08",
            "math",
            "A class has 18 boys and 22 girls. How many pupils are there altogether? A. 36 B. 40 C. 44 D. 30. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M09",
            "math",
            "A basket contains 15 mangoes, but 3 are spoiled. How many good mangoes remain? A. 13 B. 10 C. 11 D. 12. Answer with the correct option and one calculation.",
            "D",
        ),
        (
            "M10",
            "math",
            "Four identical containers each hold 2 litres of water. How much water do they hold altogether? A. 8 litres B. 6 litres C. 12 litres D. 10 litres. Answer with the correct option and one calculation.",
            "A",
        ),
        (
            "M11",
            "math",
            "A ₦2,000 school bag is discounted by 15%. How much is the discount? A. ₦150 B. ₦300 C. ₦350 D. ₦1,700. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M12",
            "math",
            "Red and blue beads are in the ratio 2:3, with 25 beads altogether. How many are blue? A. 10 B. 12 C. 15 D. 20. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M13",
            "math",
            "What is the simple interest on ₦10,000 at 5% per year for 2 years? A. ₦500 B. ₦1,000 C. ₦1,500 D. ₦2,000. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M14",
            "math",
            "What is the mean of 12, 15, and 18? A. 14 B. 15 C. 16 D. 45. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M15",
            "math",
            "What is the perimeter of a rectangle 9 metres long and 4 metres wide? A. 13 m B. 26 m C. 36 m D. 72 m. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M16",
            "math",
            "Solve 3x + 5 = 20. A. x = 3 B. x = 4 C. x = 5 D. x = 6. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M17",
            "math",
            "What is three-quarters of 120? A. 30 B. 60 C. 90 D. 100. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M18",
            "math",
            "Convert 2.5 kilometres to metres. A. 250 m B. 2,500 m C. 25,000 m D. 250,000 m. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M19",
            "math",
            "A trader buys an item for ₦800 and sells it for ₦1,000. What is the profit percentage on cost? A. 20% B. 25% C. 40% D. 80%. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M20",
            "math",
            "A car travels 150 kilometres in 3 hours at constant speed. What is its speed? A. 30 km/h B. 45 km/h C. 50 km/h D. 75 km/h. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M21",
            "math",
            "A bag contains 3 red and 7 blue counters. What is the probability of drawing a red counter once? A. 3/7 B. 3/10 C. 7/10 D. 1/3. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M22",
            "math",
            "Two angles of a triangle are 50° and 60°. What is the third angle? A. 60° B. 70° C. 80° D. 110°. Answer with the correct option and one calculation.",
            "B",
        ),
        (
            "M23",
            "math",
            "A square has area 144 cm². What is its side length? A. 12 cm B. 24 cm C. 36 cm D. 72 cm. Answer with the correct option and one calculation.",
            "A",
        ),
        (
            "M24",
            "math",
            "What is the highest common factor of 18 and 24? A. 2 B. 3 C. 6 D. 12. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "M25",
            "math",
            "What is the next term in 5, 8, 11, 14, ...? A. 15 B. 16 C. 17 D. 18. Answer with the correct option and one calculation.",
            "C",
        ),
        (
            "S01",
            "science",
            "Which process allows green plants to use sunlight to make food? A. Respiration B. Photosynthesis C. Evaporation D. Condensation. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S02",
            "science",
            "Which organ pumps blood around the human body? A. Lungs B. Heart C. Kidneys D. Stomach. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S03",
            "science",
            "What process changes liquid water into water vapour? A. Freezing B. Condensation C. Melting D. Evaporation. Answer with the correct option and one sentence of explanation.",
            "D",
        ),
        (
            "S04",
            "science",
            "Which gas do humans need for aerobic respiration? A. Carbon dioxide B. Hydrogen C. Oxygen D. Nitrogen. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S05",
            "science",
            "Which force pulls objects toward the Earth? A. Gravity B. Friction C. Magnetism D. Electricity. Answer with the correct option and one sentence of explanation.",
            "A",
        ),
        (
            "S06",
            "science",
            "Which plant part absorbs most water and minerals from soil? A. Leaf B. Root C. Flower D. Fruit. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S07",
            "science",
            "At sea level, what is the boiling point of pure water? A. 0°C B. 50°C C. 100°C D. 212°C. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S08",
            "science",
            "The Earth revolves around which object? A. Moon B. Venus C. Mars D. Sun. Answer with the correct option and one sentence of explanation.",
            "D",
        ),
        (
            "S09",
            "science",
            "What simple machine is a sloping surface used to raise a load? A. Inclined plane B. Lever C. Pulley D. Wheel and axle. Answer with the correct option and one sentence of explanation.",
            "A",
        ),
        (
            "S10",
            "science",
            "Which blood cells carry most oxygen around the body? A. Plasma B. White blood cells C. Red blood cells D. Platelets. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S11",
            "science",
            "What is the SI unit of electric current? A. Volt B. Watt C. Ampere D. Ohm. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S12",
            "science",
            "What colour does blue litmus paper turn in an acid? A. Red B. Green C. White D. It stays blue. Answer with the correct option and one sentence of explanation.",
            "A",
        ),
        (
            "S13",
            "science",
            "Which law relates force, mass, and acceleration as F = ma? A. Newton's first law B. Newton's second law C. Newton's third law D. Hooke's law. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S14",
            "science",
            "Which organelle releases most usable energy from food in a cell? A. Nucleus B. Ribosome C. Mitochondrion D. Vacuole. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S15",
            "science",
            "Which gas is released by green plants during photosynthesis? A. Carbon dioxide B. Oxygen C. Nitrogen D. Methane. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S16",
            "science",
            "Through which medium can sound not travel? A. Air B. Water C. Steel D. Vacuum. Answer with the correct option and one sentence of explanation.",
            "D",
        ),
        (
            "S17",
            "science",
            "Density is calculated as which quantity? A. Mass × volume B. Mass ÷ volume C. Volume ÷ mass D. Weight × area. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S18",
            "science",
            "Which element has atomic number 6? A. Oxygen B. Nitrogen C. Carbon D. Hydrogen. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S19",
            "science",
            "What is the chemical formula for water? A. CO₂ B. O₂ C. H₂O D. NaCl. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S20",
            "science",
            "Which energy source is renewable? A. Coal B. Diesel C. Natural gas D. Solar energy. Answer with the correct option and one sentence of explanation.",
            "D",
        ),
        (
            "S21",
            "science",
            "What is the female reproductive cell in humans called? A. Sperm B. Ovum C. Zygote D. Embryo. Answer with the correct option and one sentence of explanation.",
            "B",
        ),
        (
            "S22",
            "science",
            "In which atmospheric layer does most weather occur? A. Stratosphere B. Mesosphere C. Troposphere D. Thermosphere. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S23",
            "science",
            "Which two substances are normally required for iron to rust? A. Oxygen and water B. Nitrogen and salt C. Carbon dioxide and sunlight D. Hydrogen and oil. Answer with the correct option and one sentence of explanation.",
            "A",
        ),
        (
            "S24",
            "science",
            "In which state of matter is heat conduction generally strongest? A. Gases B. Liquids C. Solids D. Vacuum. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
        (
            "S25",
            "science",
            "A solution with pH 7 is described as what? A. Acidic B. Alkaline C. Neutral D. Concentrated. Answer with the correct option and one sentence of explanation.",
            "C",
        ),
    ]
    return [
        Prompt(pid, subject, "multiple_choice", text, expected)
        for pid, subject, text, expected in rows
    ]


def _written_math() -> list[Prompt]:
    rows = [
        (
            "M26",
            "A market woman in Onitsha buys 50 tubers of yam at 300 naira each. On the way to the market, 5 tubers spoil and cannot be sold. What price must she sell each of the remaining tubers for, so that she still makes a 20% profit on everything she spent? Show your working and check your answer.",
            "₦400 each; cost ₦15,000; target revenue ₦18,000; 45 sold",
        ),
        (
            "M27",
            "A student uses 3 GB of data each day for 7 days from a 25 GB bundle. How much data remains? Show one calculation and check it. Keep your answer under 100 words.",
            "4 GB",
        ),
        (
            "M28",
            "Ada is twice Bisi's age, and together they are 36 years old. Find both ages and verify the sum. Keep your answer under 100 words.",
            "Bisi 12; Ada 24",
        ),
        (
            "M29",
            "A ₦5,000 textbook is discounted by 12%. Find the discount and the new price. Show working and check. Keep your answer under 100 words.",
            "discount ₦600; new price ₦4,400",
        ),
        (
            "M30",
            "A tank contains 120 litres of water and leaks 3 litres per hour for 8 hours. How much remains? Show working and check. Keep your answer under 100 words.",
            "96 L",
        ),
        (
            "M31",
            "A learner expands 2(x + 3) as 2x + 3. Identify the mistake, give the correct expansion, and verify it with x = 4. Keep your answer under 120 words.",
            "distribute 2 to both terms; 2x + 6; both equal 14 at x = 4",
        ),
        (
            "M32",
            "A farmer plants maize on two-thirds of a field. She plants beans on one-quarter of the remaining land. What fraction of the whole field is left unused? Show working. Keep your answer under 120 words.",
            "1/4 unused",
        ),
        (
            "M33",
            "Two notebooks and one pen cost ₦1,100. Each notebook costs ₦400. Find the pen's price and check the total. Keep your answer under 100 words.",
            "₦300",
        ),
        (
            "M34",
            "The sequence is 2, 6, 12, 20, ... State a rule that fits these terms and use it to find the next term. Keep your answer under 100 words.",
            "n(n + 1); next 30",
        ),
        (
            "M35",
            "A bakery uses 4 cups of flour for 10 loaves. At the same rate, how many cups are needed for 25 loaves? Show a proportion and check. Keep your answer under 100 words.",
            "10 cups",
        ),
        (
            "M36",
            "Find the simple interest and total amount on ₦50,000 at 8% per year for 18 months. Show working. Keep your answer under 120 words.",
            "interest ₦6,000; total ₦56,000",
        ),
        (
            "M37",
            "After a 20% increase, a worker's monthly pay is ₦36,000. What was the original pay? Show working and check. Keep your answer under 100 words.",
            "₦30,000",
        ),
        (
            "M38",
            "A circular garden has radius 7 m. Using π = 22/7, calculate its circumference and area. Keep your answer under 120 words.",
            "circumference 44 m; area 154 m²",
        ),
        (
            "M39",
            "A ladder reaches 8 m up a wall and its foot is 6 m from the wall. Assuming a right angle, find the ladder length and check using Pythagoras. Keep your answer under 100 words.",
            "10 m",
        ),
        (
            "M40",
            "A bag has 5 red, 3 blue, and 2 green counters. Find the probability of drawing a counter that is not blue. Show working. Keep your answer under 100 words.",
            "7/10",
        ),
        (
            "M41",
            "Four test scores have mean 75. Three scores are 60, 70, and 80. Find the fourth score and check the mean. Keep your answer under 100 words.",
            "90",
        ),
        (
            "M42",
            "A student has ₦5,000. Transport costs ₦1,200 and each meal costs ₦800. What is the greatest whole number of meals the student can buy without exceeding the budget, and how much remains? Keep your answer under 120 words.",
            "4 meals; ₦600 remains",
        ),
        (
            "M43",
            "A builder buys 12 bags of cement at ₦6,500 each and pays ₦8,000 delivery. Find the total cost and check. Keep your answer under 100 words.",
            "₦86,000",
        ),
        (
            "M44",
            "For the data 4, 7, 7, 9, 12, state the median and the mode and briefly distinguish them. Keep your answer under 100 words.",
            "median 7; mode 7",
        ),
        (
            "M45",
            "A student says 25% of 80 is 20. Decide whether the answer is correct, show a calculation, and explain what 25% means. Keep your answer under 100 words.",
            "correct; 20; one quarter",
        ),
        (
            "M46",
            "On a map, 1 cm represents 5 km. Two towns are 7.2 cm apart on the map. Find the real distance and show working. Keep your answer under 100 words.",
            "36 km",
        ),
        (
            "M47",
            "Four pumps each deliver 15 litres per minute. How much water do they deliver altogether in 12 minutes? Show working and units. Keep your answer under 100 words.",
            "720 L",
        ),
        (
            "M48",
            "Solve 5(x − 2) = 3x + 6, and substitute your answer to check both sides. Keep your answer under 120 words.",
            "x = 8; both sides 30",
        ),
        (
            "M49",
            "A 10 m by 8 m classroom floor includes a 2 m by 3 m raised platform that will not be tiled. Find the area to be tiled. Show working. Keep your answer under 100 words.",
            "74 m²",
        ),
        (
            "M50",
            "A student argues: 'Every square is a rectangle, so every rectangle is a square.' Say which implication is true, identify the logical mistake, and give a counterexample. Keep your answer under 120 words.",
            "square implies rectangle; converse false; nonsquare rectangle such as 2 by 3",
        ),
    ]
    return [Prompt(pid, "math", "written", text, expected) for pid, text, expected in rows]


def _written_science() -> list[Prompt]:
    rows = [
        (
            "S26",
            "A student writes: 'A heavier ball falls faster than a lighter one, because gravity pulls harder on it.' Say exactly what is correct and what is mistaken in that reasoning, explain what actually determines how fast each ball speeds up, and describe one simple observation the student could make to test it.",
            "gravity force is larger but free-fall acceleration is equal without appreciable drag; compare simultaneous drop",
        ),
        (
            "S27",
            "A pupil notices that sweat makes the skin feel cooler. Explain how evaporation causes this cooling and state what happens to the faster-moving water molecules.",
            "higher-energy molecules escape and remove energy from the skin",
        ),
        (
            "S28",
            "Two identical bulbs are connected first in series and then in parallel to the same battery. Explain what happens to the other bulb if one bulb is removed in each circuit, and why.",
            "series circuit opens and both go off; parallel branch remains complete",
        ),
        (
            "S29",
            "Design a simple experiment to show that light is needed for a green leaf to make starch. Include the preparation, the comparison, the test used, and the expected observation.",
            "destarch; cover part; expose; iodine test; exposed part blue-black",
        ),
        (
            "S30",
            "A learner says every heavy object sinks and every light object floats. Explain why this is not a reliable rule, state the role of average density and upthrust, and give a simple comparison that disproves the learner's claim.",
            "floating depends on average density and buoyancy, not weight alone",
        ),
        (
            "S31",
            "A student with a cold asks for antibiotics because antibiotics kill germs. Explain why antibiotics usually do not cure a cold and state the kind of infection they are designed to treat.",
            "colds are usually viral; antibiotics treat susceptible bacterial infections",
        ),
        (
            "S32",
            "People often breathe faster when they first reach a high mountain. Explain the change in terms of air pressure, oxygen availability, and the body's response.",
            "lower pressure and oxygen partial pressure; increased ventilation compensates",
        ),
        (
            "S33",
            "A metal spoon and a wooden spoon have been in the same room all night. The metal spoon feels colder. Are they necessarily at different temperatures? Explain the observation using heat transfer.",
            "same temperature possible; metal conducts heat from hand faster",
        ),
        (
            "S34",
            "A student says summer happens because Earth is much closer to the Sun then. Correct the reasoning and give one observation about the two hemispheres that supports the correct explanation.",
            "axial tilt changes sunlight angle/day length; hemispheres have opposite seasons",
        ),
        (
            "S35",
            "A 6 V battery is connected across a 3 ohm resistor. Calculate the current. If the resistance is doubled while the voltage stays 6 V, calculate the new current and explain the change.",
            "2 A; then 1 A by Ohm's law",
        ),
        (
            "S36",
            "Sugar dissolves in water, but sugar can also burn. Classify each change as physical or chemical and give evidence for each classification.",
            "dissolving physical and reversible; burning chemical with new substances",
        ),
        (
            "S37",
            "A chemical reaction occurs inside a tightly closed flask. The measured total mass before and after should be the same. Explain why, including what may mislead someone in an open container.",
            "mass conserved; escaping gas can reduce measured mass in open container",
        ),
        (
            "S38",
            "Hydrochloric acid is slowly added to sodium hydroxide solution. Name the kind of reaction, state the main products, and describe how the pH changes as the mixture approaches the neutral point.",
            "neutralization; sodium chloride and water; pH falls toward 7",
        ),
        (
            "S39",
            "A plant wilts briefly at midday even though its soil is wet, then recovers in the evening. Explain this using transpiration, water uptake, and the role of stomata.",
            "transpiration temporarily exceeds uptake; stomatal response and lower evening loss restore turgor",
        ),
        (
            "S40",
            "A student claims that a dominant allele must become more common in every generation. Explain why dominance alone does not determine allele frequency and distinguish dominance from probability of inheritance.",
            "dominance concerns heterozygote phenotype; allele transmission frequency depends on population processes",
        ),
        (
            "S41",
            "In the food chain grass → grasshopper → frog → snake, a pesticide greatly reduces the grasshopper population. Predict the likely short-term effect on frogs and then on snakes, and explain the energy link.",
            "fewer grasshoppers reduce energy available to frogs, then snakes",
        ),
        (
            "S42",
            "Design a fair experiment to test how the amount of fertilizer affects bean-plant growth. State the independent variable, dependent variable, important controls, and why repeats are needed.",
            "fertilizer amount independent; growth dependent; control other conditions; repeat for reliability",
        ),
        (
            "S43",
            "A bicycle increases its speed uniformly from 0 m/s to 20 m/s in 5 seconds. Calculate its acceleration, include the unit, and explain what the value means.",
            "4 m/s²; speed rises by 4 m/s each second",
        ),
        (
            "S44",
            "A sharp knife cuts more easily than a blunt knife when the same force is applied. Explain this using pressure, force, and contact area.",
            "same force over smaller area produces greater pressure",
        ),
        (
            "S45",
            "Explain why touching an electrical switch with wet hands is more dangerous than with dry hands, using resistance and current. Give one appropriate safety action.",
            "water lowers resistance and permits greater current; dry hands/turn off power",
        ),
        (
            "S46",
            "A learner says the phases of the Moon are caused by Earth's shadow falling on the Moon. Correct this idea, explain what causes the phases, and say when Earth's shadow really does fall on the Moon.",
            "phases show changing visible illuminated fraction; Earth's shadow causes lunar eclipse",
        ),
        (
            "S47",
            "Water boils at a lower temperature on a high mountain than at sea level. Explain why in terms of atmospheric pressure and vapour pressure.",
            "lower atmospheric pressure means vapour pressure reaches it at a lower temperature",
        ),
        (
            "S48",
            "Compare photosynthesis and aerobic respiration: state the main energy change and key reactants and products in each, then explain how the two processes are linked.",
            "photosynthesis stores light energy in glucose; respiration releases usable energy; complementary reactants/products",
        ),
        (
            "S49",
            "A student says a vaccine cures a disease immediately after infection. Correct the claim and explain how vaccination uses the adaptive immune system and immune memory.",
            "vaccination primes antigen-specific response and memory; it is not an immediate cure",
        ),
        (
            "S50",
            "A pupil says malaria is caught by drinking dirty water. Identify the cause and usual mode of transmission of malaria, then give one prevention method that follows from the correct explanation.",
            "Plasmodium transmitted by infected female Anopheles mosquito; prevent mosquito bites or breeding",
        ),
    ]
    return [Prompt(pid, "science", "written", text, expected) for pid, text, expected in rows]


def prompts() -> list[Prompt]:
    """Return the suite in stable report order: M01–M50, then S01–S50."""
    mc = _multiple_choice()
    math_mc = [row for row in mc if row.subject == "math"]
    science_mc = [row for row in mc if row.subject == "science"]
    suite = math_mc + _written_math() + science_mc + _written_science()
    assert len(suite) == 100
    assert len({row.id for row in suite}) == 100
    return suite
