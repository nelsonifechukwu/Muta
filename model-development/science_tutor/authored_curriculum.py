"""A bounded, original 32-scenario science tutoring review packet, not admitted data.

No source passage or published exercise is copied into the messages. References
are factual checks, outside model messages. Every row requires separate review.
Run: .venv/bin/python model-development/science_tutor/authored_curriculum.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/muta-science-tutor-20260919/sources/muta_authored_science"
PROVENANCE = ROOT / "provenance/science-tutor-20260919/sources"
CAPABILITIES = (
    "conceptual_reasoning",
    "causal_reasoning",
    "quantitative_reasoning",
    "experimental_reasoning",
    "misconception_repair",
    "adaptive_dialogue",
    "scientific_judgment",
    "accessible_explanation",
)
SUBJECTS = ("physics", "chemistry", "biology", "earth_science")

# Each URL was read through the web research tool on 2026-09-19. These are
# original factual-reading notes, not cached source passages or license grants.
REFERENCES = {
    "waves": (
        "NASA: Anatomy of an Electromagnetic Wave",
        "https://science.nasa.gov/ems/02_anatomy/",
        "Mechanical waves require matter; electromagnetic waves can propagate through vacuum.",
    ),
    "radio": (
        "NASA: Radio Waves",
        "https://science.nasa.gov/ems/05_radiowaves/",
        "A receiver converts electromagnetic signals into speaker vibrations.",
    ),
    "refraction": (
        "NASA: Wave Behaviors",
        "https://science.nasa.gov/ems/03_behaviors/",
        "Light changes speed between media; oblique transmission can change direction.",
    ),
    "heat": (
        "NASA Glenn: Specific Heat Cp and Cv",
        "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-heat-cp-cv/",
        "Specified heat capacity relates supplied heat to temperature rise under stated process conditions.",
    ),
    "momentum": (
        "NASA Glenn: Conservation of Momentum",
        "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/conservation-of-momentum-2/",
        "Momentum has direction; the system momentum changes according to external force.",
    ),
    "mass": (
        "NASA Glenn: Conservation of Mass",
        "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/conservation-of-mass/",
        "Ordinary closed-system material accounting conserves mass; mass equals density times volume.",
    ),
    "density": (
        "USGS: Water Density",
        "https://www.usgs.gov/water-science-school/science/water-density",
        "Density is mass divided by volume; ordinary ice is less dense than liquid water. We do not use the page's loose mass/weight equivalence.",
    ),
    "precision": (
        "NIST TN 1297: Appendix D1 Terminology",
        "https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-d1-terminology",
        "Repeatability describes agreement of repeated measurements under the same conditions; accuracy is a different property.",
    ),
    "uncertainty": (
        "NIST: Measurement Uncertainty Approach",
        "https://www.itl.nist.gov/div898/handbook/mpc/section5/mpc52.htm",
        "Uncertainty depends on both random variation and potential systematic errors.",
    ),
    "design": (
        "NIST: Completely Randomized Designs",
        "https://www.itl.nist.gov/div898/handbook/pri/section3/pri331.htm",
        "Random allocation and replicated experimental units help assess treatment effects.",
    ),
    "replication": (
        "NIST: Design of Experiments Glossary",
        "https://www.itl.nist.gov/div898/handbook/pri/section7/pri7.htm",
        "Replication estimates random experimental variation; uncontrolled factors can confound effects.",
    ),
    "sound": (
        "NASA: Sounds of Mars",
        "https://science.nasa.gov/mission/mars-2020-perseverance/sounds-of-mars/",
        "Sound reaches ears as pressure disturbances and can travel through solids, liquids and gases.",
    ),
    "solvent": (
        "USGS: Water, the Universal Solvent",
        "https://www.usgs.gov/water-science-school/science/water-universal-solvent",
        "Water dissolves many substances, including salts. We do not adopt the page's misleading covalent-versus-ionic bond-strength explanation.",
    ),
    "conductivity": (
        "USGS: Conductivity and Water",
        "https://www.usgs.gov/water-science-school/science/conductivity-electrical-conductance-and-water",
        "Mobile dissolved ions enable appreciable electrical conductivity; total solution charge can remain neutral.",
    ),
    "gas": (
        "NASA Glenn: Boyle's Law",
        "https://www.grc.nasa.gov/WWW/K-12/airplane/aaboyle.htm",
        "For a fixed amount of ideal gas at constant temperature, pressure times volume is constant.",
    ),
    "enzyme": (
        "NHGRI: Enzyme",
        "https://www.genome.gov/genetics-glossary/Enzyme",
        "An enzyme catalyzes a specific reaction and is available again after a completed reaction.",
    ),
    "catalyst": (
        "DOE Explains: Catalysts",
        "https://www.energy.gov/science/doe-explainscatalysts",
        "Catalysts speed reactions without being consumed in the catalytic reaction; product atoms still come from reacting material.",
    ),
    "vapor": (
        "USGS: Vapor Pressure and Water",
        "https://www.usgs.gov/water-science-school/science/vapor-pressure-and-water",
        "Liquid-vapor equilibrium is dynamic: molecules move both ways at matching average rates.",
    ),
    "condensation": (
        "USGS: Condensation and the Water Cycle",
        "https://www.usgs.gov/water-science-school/science/condensation-and-water-cycle?page=1",
        "Condensation changes gaseous water to liquid water; cooling moist air can produce droplets.",
    ),
    "cloud": (
        "NASA: How Do Clouds Form?",
        "https://science.nasa.gov/kids/earth/how-do-clouds-form/",
        "Clouds contain many liquid droplets or ice crystals; saturation and condensation/deposition matter, not cooling alone.",
    ),
    "atom": (
        "DOE: Atomic Number and Atomic Weight",
        "https://ehss.energy.gov/ohre/roadmap/achre/intro_9_3.html",
        "Element identity depends on proton count; ionization changes electron count, not element identity.",
    ),
    "membrane": (
        "NHGRI: Cell Membrane",
        "https://www.genome.gov/genetics-glossary/Cell-Membrane-Plasma-Membrane",
        "Cell membranes separate inside from outside and regulate entry and exit of substances.",
    ),
    "mitochondria": (
        "NHGRI: Mitochondria",
        "https://www.genome.gov/genetics-glossary/Mitochondria",
        "Mitochondria help transfer chemical energy into ATP; their abundance varies among cell types.",
    ),
    "foodweb": (
        "NOAA: Aquatic Food Webs",
        "https://prod-01-alb-www-noaa.woc.noaa.gov/education/resource-collections/marine-life/aquatic-food-webs",
        "Feeding connects trophic levels and transfers energy from prey to consumers.",
    ),
    "mutation": (
        "NHGRI: Mutation",
        "https://www.genome.gov/genetics-glossary/Mutation",
        "Somatic and germline changes differ in their potential for inheritance.",
    ),
    "lungs": (
        "NHLBI: The Respiratory System",
        "https://www.nhlbi.nih.gov/health/lungs/respiratory-system",
        "Oxygen crosses from alveolar air into blood; carbon dioxide crosses in the opposite direction.",
    ),
    "aquifer": (
        "USGS: Aquifers and Groundwater",
        "https://www.usgs.gov/water-science-school/science/aquifers-and-groundwater",
        "Groundwater occupies pores and fractures; connected spaces allow flow; extraction can exceed recharge.",
    ),
    "seasons": (
        "NASA: A Planet for All Seasons",
        "https://science.nasa.gov/blogs/new-horizons/2015/10/23/a-planet-for-all-seasons/",
        "Earth's axial tilt produces opposite seasonal illumination in the two hemispheres.",
    ),
    "rain": (
        "USGS: How Much Water Is There on Earth?",
        "https://www.usgs.gov/water-science-school/science/how-much-water-there-earth",
        "Rainfall and water stores can be expressed as volumes; our numerical roof scenario is original geometry.",
    ),
    "turbidity": (
        "USGS: Turbidity and Water",
        "https://www.usgs.gov/water-science-school/science/turbidity-and-water",
        "Scattering by suspended material influences turbidity; clarity alone does not establish water quality.",
    ),
    "moon": (
        "NASA: Moon Phases",
        "https://science.nasa.gov/moon/moon-phases/",
        "Normal lunar phases reflect how much of the illuminated hemisphere is visible; lunar eclipses are distinct.",
    ),
    "rocks": (
        "USGS: What Are Igneous Rocks?",
        "https://www.usgs.gov/faqs/what-are-igneous-rocks",
        "Melt cooling history influences crystal growth; slower underground cooling can produce large crystals.",
    ),
    "climate": (
        "NOAA Climate.gov: Climate and Weather",
        "https://prod-01-asg-www-climate.woc.noaa.gov/maps-data/climate-data-primer/whats-difference-between-climate-and-weather",
        "Weather concerns short-term conditions; climate concerns long-term distributions and patterns.",
    ),
}


def scenario(subject, capability, slug, references, claims, turns, numeric=None):
    return {
        "subject": subject,
        "capability": capability,
        "slug": slug,
        "references": references,
        "claims_for_review": claims,
        "turns": turns,
        "numeric": numeric or [],
    }


SCENARIOS = [
    scenario(
        "physics",
        "conceptual_reasoning",
        "radio-across-empty-gap",
        ["waves", "radio"],
        [
            "Radio propagation and the speaker's sound are different wave processes.",
            "A vacuum prevents airborne sound but not radio transmission.",
        ],
        [
            "A spacecraft sends a voice recording through space. Does that mean sound crosses empty space?",
            "Separate the journey to the antenna from the journey from a speaker to your ear. What do you think travels between the antennas?",
            "The same sound wave, just much louder.",
            "Between antennas, the signal is an electromagnetic radio wave. The receiver makes a speaker vibrate, creating a new sound wave in air. Making a sound louder cannot supply a missing medium. Could a radio signal cross an evacuated chamber even if a bell inside could not be heard through the vacuum?",
            "Yes. The radio signal does not need air, but the bell's sound needs matter to carry it.",
            "That distinction is right. Sound could still reach a detector through solid supports, so an experiment must also check those alternative paths.",
        ],
    ),
    scenario(
        "physics",
        "causal_reasoning",
        "light-at-glass-boundary",
        ["refraction"],
        [
            "Light crossing an oblique boundary can change direction because its propagation speed changes.",
            "Normal incidence need not bend despite a speed change.",
        ],
        [
            "A narrow light beam enters clear glass at a slant and bends. Is gravity pulling it sideways?",
            "The bend occurs at the boundary. Which property of the light's travel changes when it enters the glass?",
            "Its speed changes, but every speed change must make it turn.",
            "The speed does change. At an oblique boundary this can change the ray's direction: refraction. But a beam entering straight along the normal can slow without turning. The normal is a line perpendicular to the surface. What would you predict for straight-on entry?",
            "It would change speed but continue straight through the boundary.",
            "Yes. That special case helps separate a speed change from a direction change; the angle of entry matters.",
        ],
    ),
    scenario(
        "physics",
        "quantitative_reasoning",
        "thermal-block-energy-budget",
        ["heat"],
        [
            "Under the stated ideal model, Q equals mass times specific heat capacity times temperature rise.",
            "The same energy produces half the temperature rise in twice the mass.",
        ],
        [
            "An insulated 0.30 kg block absorbs 900 J. Its specific heat capacity is 750 J/(kg K), constant over this range. With no phase change or other work, how much does its temperature rise?",
            "First find the heat capacity of the whole block by multiplying its mass by the specific heat capacity. What does that quantity mean?",
            "I would divide 900 by 750 and get a rise of 1.2 K. The mass seems unnecessary.",
            "The 750 J/(kg K) is for each kilogram. This block needs 0.30 × 750 = 225 J for each kelvin, so its rise is 900/225 = 4 K. What rise would the same energy produce in a 0.60 kg block of this material?",
            "Its heat capacity is 450 J/K, so the rise is 2 K.",
            "Correct. We calculated a temperature change, not a final temperature; an initial temperature would be needed for that. Heat loss would reduce the rise.",
        ],
        ["heat_capacity", "heat_rise", "heat_transfer_capacity", "heat_transfer_rise"],
    ),
    scenario(
        "physics",
        "experimental_reasoning",
        "lamp-distance-confound",
        ["design", "replication"],
        [
            "Changing lamp type and distance together confounds a comparison.",
            "Replicates and randomized order help assess variation and drift.",
        ],
        [
            "To compare two small lamps' illumination, I put lamp A close to a sensor and lamp B farther away. A gives a larger reading. Have I shown that A is the brighter lamp?",
            "Besides lamp type, what changed between your measurements?",
            "Distance changed, but using the same sensor makes the comparison fair.",
            "The same sensor helps, but the distance difference could explain the readings. Compare at the same distance, orientation and ambient light, allow stable operation, and repeat in varied order. If the sensor reading changes when a lamp is moved, what has the original experiment failed to isolate?",
            "It did not isolate lamp type from distance.",
            "Exactly. State the result as illumination at a specified position. A single sensor reading also does not measure the lamp's total light output in all directions.",
        ],
    ),
    scenario(
        "physics",
        "misconception_repair",
        "carts-stick-momentum",
        ["momentum"],
        [
            "Total momentum can be conserved in an inelastic collision when external impulse is negligible.",
            "Conservation of momentum does not require kinetic energy conservation.",
        ],
        [
            "Two carts collide and stick on a nearly frictionless horizontal track. Their motion energy decreases, so their total momentum must disappear too, right?",
            "Momentum includes direction and depends on mass and velocity. Are momentum and kinetic energy the same quantity?",
            "They both describe motion, so losing either should mean losing both.",
            "They obey different accounting rules. With negligible external impulse, the carts' combined momentum stays constant even when some kinetic energy becomes internal energy and sound. If the carts approach with equal and opposite momenta, can the joined pair stop without violating momentum conservation?",
            "Yes. The total momentum was zero before and is zero afterward.",
            "Right. Choose both carts as the system. Their mutual collision forces are internal; a significant push from the track would change the momentum account.",
        ],
    ),
    scenario(
        "physics",
        "adaptive_dialogue",
        "equal-mass-unequal-volume",
        ["density"],
        [
            "Equal masses need not have equal densities.",
            "For fixed mass, greater volume means lower average density.",
        ],
        [
            "Two sealed blocks have equal mass, but one is much larger. Which has the greater average density? I get lost in formulas.",
            "Imagine spreading the same amount of material through a small box and a large box. Which has more mass in each equal-sized part of its volume?",
            "The larger block, because it takes up more space.",
            "Keep the mass fixed in your picture. More space means that same mass is spread more thinly. The smaller block therefore has more mass per unit volume. If the larger block were compressed without losing mass, would its average density rise or fall?",
            "Rise, because the same mass would occupy less volume.",
            "Yes. That is the meaning of density = mass/volume. We used average density, so the reasoning still works if a block contains enclosed air spaces.",
        ],
    ),
    scenario(
        "physics",
        "scientific_judgment",
        "repeatable-miscalibrated-balance",
        ["precision", "uncertainty"],
        [
            "Repeatability alone does not establish accuracy.",
            "A shared calibration error is not removed by averaging repeats.",
        ],
        [
            "My balance gives nearly identical readings every time. Can I report that its measurements must be accurate?",
            "Those repeats tell you about consistency. How could all of them agree yet still be wrong?",
            "Maybe random error, but averaging lots of readings removes every kind of error.",
            "A calibration offset could shift every reading together. Averaging helps some random variation, but it does not automatically remove that shared offset. Check a suitable reference mass and the zero setting. If repeated readings stay tight but disagree with the reference, which claim should you revise?",
            "I should revise the accuracy claim, even though the balance is repeatable.",
            "Yes. Report the calibration evidence and measurement uncertainty separately from the repeatability you observed.",
        ],
    ),
    scenario(
        "physics",
        "accessible_explanation",
        "sound-is-not-a-wind-parcel",
        ["sound", "waves"],
        [
            "A sound disturbance transfers energy through a medium without bulk transport of the same air from source to receiver.",
            "Sound can propagate in liquids and solids.",
        ],
        [
            "When I hear a drum across a room, do the air particles beside the drum fly all the way into my ear? Please explain without a diagram.",
            "Think of neighboring people passing a gentle nudge along a line while staying near their places. What travels along the line?",
            "The people must travel from one end to the other.",
            "In this model the nudge travels, while each person moves locally. Air sound similarly involves local pressure changes passed between neighboring regions. The analogy does not mean air particles form a fixed line. Could a vibration also pass through a solid desk?",
            "Yes, the solid's particles can pass on the disturbance without the whole desk moving across the room.",
            "That is the useful idea. Sound needs a material medium, which can be a gas, liquid or solid.",
        ],
    ),
    scenario(
        "chemistry",
        "conceptual_reasoning",
        "salt-solution-neutral-current",
        ["conductivity"],
        [
            "A solution can be electrically neutral overall while containing mobile ions.",
            "Dissolved ions, rather than a net overall charge, enable appreciable conduction.",
        ],
        [
            "A salt solution has equal total positive and negative charge. Does that mean it cannot conduct electricity?",
            "Does equal total charge tell us whether the charged particles can move?",
            "I thought opposite charges cancel, so there are no charged particles left.",
            "Their total charges balance, but the ions still exist. In solution they can move and carry current when an electric field is applied. Overall neutrality is not the same as having no mobile charges. Would a neutral solution necessarily become positively charged just because it conducts?",
            "No. It can carry current while remaining approximately neutral overall.",
            "Correct. Conductivity concerns mobile charge carriers, not simply the net charge of the sample.",
        ],
    ),
    scenario(
        "chemistry",
        "causal_reasoning",
        "slow-gas-compression",
        ["gas"],
        [
            "With fixed amount and temperature, reducing ideal-gas volume raises pressure.",
            "Pressure arises from momentum transfer in particle collisions with walls.",
        ],
        [
            "A sealed gas sample is slowly compressed while its temperature is kept constant. Why does its pressure rise if no extra gas was added?",
            "We kept the amount and temperature fixed. What changed about the space available to the particles?",
            "The particles became larger and hotter as the space shrank.",
            "The model does not make the particles larger, and the stated temperature control rules out a lasting temperature rise. The same particles occupy less space and collide with the walls more frequently per area. If the gas expanded again at the same temperature without leaking, what would happen to pressure?",
            "It would fall as the volume increased.",
            "Yes, for an approximately ideal gas. Fast compression without temperature control would need a different account because the gas can warm.",
        ],
    ),
    scenario(
        "chemistry",
        "quantitative_reasoning",
        "dye-dilution-final-volume",
        ["mass"],
        [
            "Dilution with pure solvent conserves solute mass when no reaction or loss occurs.",
            "Concentration uses final solution volume; a homogeneous half-volume sample contains half the solute.",
        ],
        [
            "A solution contains 12 g of dye in 200 mL. Pure solvent is added until the final volume is 500 mL, with no loss or reaction. What is its new mass concentration in g/L?",
            "Which quantity stays fixed: the amount of dye or the concentration?",
            "The concentration stays fixed, because adding solvent also creates more dye.",
            "Pure solvent adds no dye. There are still 12 g, now in 0.500 L, giving 12/0.500 = 24 g/L. After thorough mixing, how much dye is in a 250 mL sample?",
            "That is half the final volume, so it contains 6 g of dye.",
            "Correct. The sample's concentration is still 24 g/L. Note that 500 mL was the final volume, not the amount of solvent added.",
        ],
        ["dilution_concentration", "dilution_sample_mass"],
    ),
    scenario(
        "chemistry",
        "experimental_reasoning",
        "stirring-dissolution-design",
        ["solvent", "design", "replication"],
        [
            "Changing temperature and stirring together cannot isolate stirring's effect.",
            "A dissolution-rate experiment needs a defined endpoint and matched starting conditions.",
        ],
        [
            "I stirred a warm sugar solution and left a cold one still. The sugar disappeared sooner in the warm cup. Can I conclude stirring caused the difference?",
            "List the conditions that differed between the cups before deciding what caused the timing difference.",
            "Only stirring matters; temperature is just background.",
            "Temperature also differed, so its effect is mixed with stirring. To test stirring, keep water temperature and volume, sugar mass and grain size alike; define the same endpoint and repeat. If both cups are stirred but one has much finer sugar, what new difference must you control?",
            "The sugar grain size, since that could affect how quickly it dissolves.",
            "Yes. Measure disappearance of visible crystals consistently, and distinguish dissolving faster from being able to dissolve a larger final amount.",
        ],
    ),
    scenario(
        "chemistry",
        "misconception_repair",
        "catalyst-not-extra-product",
        ["catalyst", "mass"],
        [
            "A catalyst increases reaction rate and is regenerated in the catalytic cycle.",
            "Faster reaction need not mean a greater stoichiometric maximum yield.",
        ],
        [
            "A catalyst makes a reaction faster. Does that mean it supplies extra atoms so the same reactants can make unlimited product?",
            "Where would the atoms in that extra product have to come from?",
            "From the catalyst, which must be used up each time it helps.",
            "In a catalytic cycle the catalyst is regenerated; it is not a new unlimited supply of product atoms. Product still depends on available reactants. A catalyst may help a reaction get further within a fixed time. If all limiting reactant is already consumed, can adding catalyst alone create more product?",
            "No. More product would require more of the necessary reactant.",
            "Correct. Real catalysts can lose activity through side processes, but that does not make them an unlimited reactant source.",
        ],
    ),
    scenario(
        "chemistry",
        "adaptive_dialogue",
        "equilibrium-moving-particles",
        ["vapor"],
        [
            "Phase equilibrium is dynamic, with evaporation and condensation continuing.",
            "A constant macroscopic amount does not imply microscopic stillness.",
        ],
        [
            "Water in a sealed container has reached liquid-vapor equilibrium at constant temperature. Does equilibrium mean the molecules stop moving? I don't understand the word dynamic.",
            "Think about a room whose number of people stays constant. Must nobody enter or leave?",
            "Yes. If anyone leaves, the number must keep going down.",
            "It can stay constant if people enter at the same average rate as others leave. Likewise, water molecules continue evaporating and condensing at matching average rates. The analogy is about rates, not people behaving like molecules. If the number of vapor molecules stays steady, does that prove no individual molecule changes phase?",
            "No. Individual molecules can change phase while the total stays steady.",
            "That is what dynamic means here: continuing microscopic change with stable large-scale amounts, under the stated conditions.",
        ],
    ),
    scenario(
        "chemistry",
        "scientific_judgment",
        "clear-sample-identity",
        ["conductivity", "turbidity"],
        [
            "Visual clarity does not establish chemical purity or identify dissolved material.",
            "Conductivity is evidence about mobile ions, not a unique chemical identification.",
        ],
        [
            "A clear laboratory water sample conducts better than our reference water. My partner says that proves it contains table salt. Is that a justified identification?",
            "What does conductivity measure, and could more than one dissolved substance affect it?",
            "It measures how clear the sample is, so only invisible table salt could explain it.",
            "Clarity and conductivity are different properties. Conductivity responds to mobile ions; many dissolved salts can raise it. Match temperature and check the instrument, then use an ion-specific test if identification matters. If another clear sample has the same conductivity, must its chemical composition be identical?",
            "No. Different ions or concentrations could give a similar reading.",
            "Right. Report the measured property and its limits. Neither clarity nor this measurement alone establishes purity or suitability for drinking.",
        ],
    ),
    scenario(
        "chemistry",
        "accessible_explanation",
        "ion-element-name",
        ["atom"],
        [
            "Proton count determines element identity.",
            "Gaining or losing electrons changes ionic charge without changing proton count.",
        ],
        [
            "If an atom loses an electron, does it become a different element? Please keep the explanation simple.",
            "An element's identity is set by the number of protons in its nucleus. Does losing an electron remove a proton?",
            "I think all particles are interchangeable, so it should.",
            "Electrons and protons are different particles in different parts of the atom. Losing an electron changes the balance of electric charge, but leaves the proton count unchanged. The atom becomes an ion of the same element. What if it gains an electron instead?",
            "Its charge changes the other way, but it is still the same element.",
            "Yes. Ordinary ion formation changes electron count; changing the nucleus's proton count would change the element.",
        ],
    ),
    scenario(
        "biology",
        "conceptual_reasoning",
        "membrane-selective-not-wall",
        ["membrane"],
        [
            "A cell membrane regulates transport rather than blocking all substances.",
            "Permeability to one substance does not establish permeability to another.",
        ],
        [
            "If a cell membrane protects a cell, why doesn't it block absolutely everything?",
            "What would happen to a cell that could never take in useful materials or let wastes leave?",
            "It would be safer and could keep working forever with what it already has.",
            "Living cells need exchange with their surroundings. A membrane regulates that exchange; it is a selective boundary rather than an impermeable shell. Different substances cross in different ways. If one small substance crosses a membrane, can we conclude every large molecule can cross it too?",
            "No. We need to know the membrane's properties and the substance involved.",
            "Exactly. Selective transport is the key idea; protection and exchange are compatible functions.",
        ],
    ),
    scenario(
        "biology",
        "causal_reasoning",
        "muscle-atp-demand",
        ["mitochondria"],
        [
            "Mitochondria support ATP production rather than creating energy from nothing.",
            "ATP demand can help explain differences in mitochondrial abundance, without uniquely predicting all cell traits.",
        ],
        [
            "Why might a muscle cell contain many mitochondria? Is it because mitochondria make energy out of nothing?",
            "Muscle contraction needs usable chemical energy. What could mitochondria do with energy already present in nutrients?",
            "They could convert it, but conversion means the original energy disappears.",
            "Energy is transferred into forms the cell can use, including ATP, and some is dispersed as heat. Mitochondria do not create it from nothing. Cells with sustained high ATP demand often have many mitochondria. Would counting mitochondria alone tell you everything about how active a cell is?",
            "No. Their condition and other cell processes also matter.",
            "Good. High demand provides a possible explanation for abundance, while a complete comparison needs more measurements.",
        ],
    ),
    scenario(
        "biology",
        "quantitative_reasoning",
        "measured-trophic-transfers",
        ["foodweb"],
        [
            "Transfer efficiency is an energy ratio for specified trophic levels and period.",
            "Efficiencies supplied by data need not equal a fixed universal percentage.",
        ],
        [
            "In a simplified food-chain budget for the same area and period, producers store 2400 kJ in new biomass and herbivores store 480 kJ. What is the transfer efficiency?",
            "Which value is the energy available at the starting level, and which is the energy at the next level?",
            "I divide 2400 by 480 and call the efficiency 500%.",
            "Use next-level energy divided by starting-level energy: 480/2400 × 100 = 20%. Now suppose carnivores store 120 kJ. What fraction of the herbivore biomass energy appears as new carnivore biomass?",
            "120/480 × 100 = 25%.",
            "Correct. These are efficiencies for the given model and period, not a universal rule. Energy absent from new consumer biomass can include respiration, waste and uneaten material.",
        ],
        ["herbivore_efficiency", "carnivore_efficiency"],
    ),
    scenario(
        "biology",
        "experimental_reasoning",
        "seedling-watering-control",
        ["design", "replication"],
        [
            "Watering treatment is confounded if location changes systematically with treatment.",
            "Independent plants, random allocation and matched measurements improve the experiment.",
        ],
        [
            "I want to test whether a watering schedule changes seedling growth. I put one schedule's seedlings by a sunny window and the other schedule's seedlings in a darker corner. Is that fair?",
            "Which difference besides watering could affect growth?",
            "There are several seedlings, so the light difference cancels automatically.",
            "More seedlings do not remove a shared light difference. Randomly assign comparable seedlings to watering schedules, give groups comparable light, soil and containers, and measure growth consistently. If only the larger seedlings get one schedule, what new problem appears?",
            "Starting size becomes mixed with the watering treatment.",
            "Yes. Record initial sizes and distribute them fairly. Repeated measurements of one plant are also not the same as independent replicate plants.",
        ],
    ),
    scenario(
        "biology",
        "misconception_repair",
        "somatic-change-inheritance",
        ["mutation"],
        [
            "A somatic mutation is not automatically inherited by offspring.",
            "A germline mutation can be transmitted, but transmission and effect are separate questions.",
        ],
        [
            "If a skin cell acquires a mutation, will all of that person's future children inherit it?",
            "Which cells ordinarily contribute genetic material directly to a new embryo?",
            "Every body cell contributes, including that skin cell.",
            "In ordinary human reproduction, the egg and sperm contribute. A change confined to a skin-cell lineage is a somatic change and is not automatically present in those reproductive cells. If a mutation is present in an egg or sperm, could the inheritance answer differ?",
            "Yes. It could be passed on through that reproductive cell.",
            "Right. Keep location, transmission and biological effect separate; the word mutation alone does not answer all three.",
        ],
    ),
    scenario(
        "biology",
        "adaptive_dialogue",
        "enzyme-reuse-limited-substrate",
        ["enzyme"],
        [
            "Enzymes catalyze particular reactions and are reused.",
            "Adding enzyme cannot sustain product formation after substrate is exhausted.",
        ],
        [
            "I keep mixing up enzyme and substrate. Which one gets changed into product?",
            "For a simple enzyme reaction, call the substrate the material being changed and the enzyme the helper. Which one should match the product's starting material?",
            "The enzyme is the starting material, and the substrate is the helper.",
            "Swap those roles: the substrate becomes product, while the enzyme helps the reaction and can work again. This is a role distinction, not a claim that every enzyme works on every substrate. If all suitable substrate is gone, will adding more enzyme alone keep making product?",
            "No. There is no suitable starting material left to change.",
            "Exactly. Next time, ask what is transformed and what helps the transformation; that separates the two terms.",
        ],
    ),
    scenario(
        "biology",
        "scientific_judgment",
        "pond-count-detection-bias",
        ["design", "turbidity"],
        [
            "A lower observed count need not equal a lower true population if detectability changes.",
            "Observational association alone does not establish a single cause.",
        ],
        [
            "After rain made a pond cloudy, we saw fewer small animals from the bank. Can we conclude the rain killed them?",
            "What changed about your ability to see the animals, apart from any possible change in their number?",
            "Nothing relevant. A count is always the exact population size.",
            "Cloudier water can reduce visibility, so your method may detect fewer animals even if the population is unchanged. Other causes are also possible. Use a consistent sampling method that accounts for detection and compare repeated observations. If counts recover when the water clears, does that alone prove no animals died?",
            "No. It supports a visibility explanation but does not settle every possible population change.",
            "Good. Separate what you observed from the biological cause you propose, and identify evidence that can distinguish explanations.",
        ],
    ),
    scenario(
        "biology",
        "accessible_explanation",
        "lungs-blood-separate-spaces",
        ["lungs"],
        [
            "Gas exchange occurs across the boundary between alveolar air and nearby blood.",
            "Bulk air is not normally pumped through blood vessels.",
        ],
        [
            "Does the air I breathe flow through my blood vessels like air through a hose? I need a word-only explanation.",
            "Air reaches tiny sacs in the lungs, with blood flowing in tiny vessels nearby. Do those have to be one open space for gases to pass between them?",
            "Yes. The blood vessels must fill with air bubbles.",
            "They remain separate spaces with a very thin barrier. Oxygen crosses into the blood and carbon dioxide crosses toward the air. Blood carries the gases onward without normally filling with air bubbles. Which direction does carbon dioxide move at this exchange surface?",
            "From the blood toward the air in the lung sacs, so it can be breathed out.",
            "That's right. Breathing moves air; circulation moves blood; gas exchange connects their functions across a barrier.",
        ],
    ),
    scenario(
        "earth_science",
        "conceptual_reasoning",
        "porous-versus-permeable-rock",
        ["aquifer"],
        [
            "Pore space stores water; connected sufficiently open paths enable groundwater flow.",
            "High porosity alone does not ensure high permeability.",
        ],
        [
            "A rock has many tiny spaces. Does that automatically mean water flows through it easily?",
            "Suppose those spaces were mostly isolated from one another. How would water get from one side of the rock to the other?",
            "The amount of empty space is all that matters; connections are irrelevant.",
            "Spaces provide storage, but connected pathways allow flow. Porosity describes the fraction of space; permeability describes how readily fluid passes through. Tiny or poorly connected paths can limit flow. Could a fractured rock transmit water even if its solid pieces have little pore space?",
            "Yes, if the fractures form connected paths.",
            "Correct. Storage and transmission are related but distinct questions when assessing an aquifer.",
        ],
    ),
    scenario(
        "earth_science",
        "causal_reasoning",
        "opposite-season-illumination",
        ["seasons"],
        [
            "Opposite hemispheric seasons are mainly explained by axial tilt, not a shared Earth-Sun distance change.",
            "Sun angle and daylight duration affect received solar energy.",
        ],
        [
            "When it is summer in one hemisphere and winter in the other, could Earth simply be closer to the Sun on the summer side?",
            "Both hemispheres share almost the same Earth-Sun distance. What feature changes how sunlight is distributed between them during the year?",
            "Earth's daily rotation, because summer lasts until that side turns away at night.",
            "Rotation produces day and night. The tilted axis, carried around the Sun during the year, changes each hemisphere's sunlight angle and day length. That explains opposite seasons. When one hemisphere tilts toward the Sun, what happens to the other?",
            "It tilts away and generally gets less direct sunlight and shorter days.",
            "Yes, away from the equator that contrast is especially clear. Local seasons also depend on atmosphere and geography, so this is the main astronomical cause, not a full weather forecast.",
        ],
    ),
    scenario(
        "earth_science",
        "quantitative_reasoning",
        "roof-rainfall-volume",
        ["rain"],
        [
            "Uniform rainfall volume equals depth times horizontal collection area.",
            "A stated collection fraction applies to that volume; geometry and losses must be explicit.",
        ],
        [
            "Rainfall is uniformly 18 mm over a roof with horizontal collection area 80 m². Ignore wind and assume all rain initially reaches the collector. What volume falls on that area?",
            "Use volume = depth × area, but first make the length units consistent. How many metres is 18 mm?",
            "18 metres, so the volume is 1440 cubic metres.",
            "A millimetre is one-thousandth of a metre: 18 mm is 0.018 m. The volume is 0.018 × 80 = 1.44 m³. If only 75% is collected after losses, how many litres reach the tank? Use 1000 L per m³.",
            "1.44 × 0.75 = 1.08 m³, which is 1080 L.",
            "Correct. The horizontal collection area matters, not a larger sloping surface area. The collection percentage is an assumption supplied here, not a universal property of roofs.",
        ],
        ["rain_volume", "rain_collected_volume", "rain_collected_litres"],
    ),
    scenario(
        "earth_science",
        "experimental_reasoning",
        "soil-cover-runoff-sediment",
        ["turbidity", "design", "replication"],
        [
            "A cover-versus-bare-soil test must control rain input, slope and soil conditions.",
            "Water cloudiness is a proxy affected by more than total sediment mass.",
        ],
        [
            "To test whether ground cover reduces soil washing away, I pour a little water on a covered tray and much more on a bare tray. The bare tray's runoff looks muddier. Is that enough?",
            "What changed besides the presence of cover?",
            "The amount of water, but the muddy color directly measures all soil lost.",
            "Water input is a confound. Use matched soil, slopes and rain input, repeat the comparison, and collect runoff consistently. Cloudiness is only a proxy; particle properties also affect it. If you want total sediment loss, would collecting and measuring dried sediment be more direct than comparing color alone?",
            "Yes, provided I collect the runoff fully and measure it consistently.",
            "Right. State that this is a controlled tray model, and check whether its conditions represent the landscape before generalizing.",
        ],
    ),
    scenario(
        "earth_science",
        "misconception_repair",
        "crescent-not-earth-shadow",
        ["moon"],
        [
            "Ordinary phases depend on viewing geometry of the sunlit lunar hemisphere.",
            "Earth's shadow produces a lunar eclipse, not the ordinary monthly phase pattern.",
        ],
        [
            "Is a crescent Moon made by Earth's shadow covering most of the Moon every month?",
            "Normally the Sun lights roughly half the Moon. Could our view of that lit half change as the Moon orbits Earth?",
            "No. If part looks dark to us, Earth must be blocking its sunlight.",
            "We can see a changing portion of the Moon's sunlit hemisphere without Earth blocking the light. Earth's shadow matters during a lunar eclipse, which is a special alignment. In an ordinary crescent phase, does most of the far-facing side have to receive no sunlight?",
            "No. Much of the sunlit part can be turned away from our view.",
            "Exactly. Distinguish what is illuminated from what is visible to an observer on Earth.",
        ],
    ),
    scenario(
        "earth_science",
        "adaptive_dialogue",
        "crystal-growth-time",
        ["rocks"],
        [
            "Slower cooling generally allows more time for larger crystals to develop in comparable melts.",
            "Crystal size alone does not determine an exact formation time.",
        ],
        [
            "My rock sample has large crystals. Does that mean it cooled especially fast? I can't connect the texture to the process.",
            "A crystal grows as particles join an ordered structure. Which cooling situation usually leaves more time for growth?",
            "Rapid cooling, because everything has to form immediately.",
            "Rapid cooling gives less time to build large crystals. For otherwise comparable melts, slower cooling generally permits larger crystals. Extremely rapid cooling can even leave glass. If two melts have similar composition but one cools more slowly, which would you expect to have larger crystals?",
            "The more slowly cooled one, other things being equal.",
            "That's the expected trend. Texture gives evidence about cooling history, but it is not an exact clock by itself.",
        ],
    ),
    scenario(
        "earth_science",
        "scientific_judgment",
        "cold-week-climate-trend",
        ["climate"],
        [
            "A short local cold event does not alone determine a long-term climate trend.",
            "Climate inference needs representative records over appropriate time and space.",
        ],
        [
            "Our town had a very cold week. Does that single week prove the region's long-term warming trend has reversed?",
            "Does a claim about a long-term pattern use the same time scale as a claim about this week's weather?",
            "Yes. The newest observation should replace the whole earlier record.",
            "A cold week is a weather event and belongs in the record, but it cannot by itself establish a new long-term trend. Compare consistent observations across many years, seasons and locations. Would a very hot afternoon alone prove the opposite long-term claim?",
            "No. That would make the same mistake with a hot event.",
            "Correct. Use the full relevant evidence and distinguish short-term variability from changes in the long-term distribution.",
        ],
    ),
    scenario(
        "earth_science",
        "accessible_explanation",
        "cloud-droplets-not-visible-gas",
        ["condensation", "cloud"],
        [
            "Water vapor is gaseous water; ordinary visible cloud material consists of droplets and/or ice crystals.",
            "Condensation can occur when moist air cools sufficiently; not every temperature decrease makes a cloud.",
        ],
        [
            "Are clouds just patches of water vapor that became white? Explain without a picture.",
            "Water vapor is an invisible gas. What small visible form of water might appear when moist air cools enough?",
            "The gas molecules turn white but stay a gas.",
            "Some water vapor condenses into tiny liquid droplets; clouds can also contain ice crystals. These particles scatter light, making the cloud visible. The molecules do not acquire white paint. If air cools only a little and remains unsaturated, must a cloud appear?",
            "No. Cooling must be enough for the conditions to allow condensation.",
            "Yes. Keep the invisible vapor distinct from visible droplets or crystals, and remember that humidity as well as temperature matters.",
        ],
    ),
]


def independent_numeric_values():
    """Exact arithmetic from problem givens; never parse or reuse target answers."""
    return {
        "heat_capacity": Fraction(3, 10) * 750,
        "heat_rise": Fraction(900) / (Fraction(3, 10) * 750),
        "heat_transfer_capacity": Fraction(6, 10) * 750,
        "heat_transfer_rise": Fraction(900) / (Fraction(6, 10) * 750),
        "dilution_concentration": Fraction(12) / Fraction(500, 1000),
        "dilution_sample_mass": Fraction(12) * Fraction(250, 500),
        "herbivore_efficiency": Fraction(480, 2400) * 100,
        "carnivore_efficiency": Fraction(120, 480) * 100,
        "rain_volume": Fraction(18, 1000) * 80,
        "rain_collected_volume": Fraction(18, 1000) * 80 * Fraction(75, 100),
        "rain_collected_litres": Fraction(18, 1000) * 80 * Fraction(75, 100) * 1000,
    }


NUMERIC_TARGETS = {
    "heat_capacity": ("225", "J/K"),
    "heat_rise": ("4", "K"),
    "heat_transfer_capacity": ("450", "J/K"),
    "heat_transfer_rise": ("2", "K"),
    "dilution_concentration": ("24", "g/L"),
    "dilution_sample_mass": ("6", "g"),
    "herbivore_efficiency": ("20", "%"),
    "carnivore_efficiency": ("25", "%"),
    "rain_volume": ("1.44", "m³"),
    "rain_collected_volume": ("1.08", "m³"),
    "rain_collected_litres": ("1080", "L"),
}

# Bind each independently computed result to its actual authored target text.
# Deliberately incorrect learner turns are not targets. The correct learner
# transfer answers are included because the final tutor explicitly endorses them.
NUMERIC_SPANS = {
    "heat_capacity": (3, "225 J"),
    "heat_rise": (3, "4 K"),
    "heat_transfer_capacity": (4, "450 J/K"),
    "heat_transfer_rise": (4, "2 K"),
    "dilution_concentration": (3, "24 g/L"),
    "dilution_sample_mass": (4, "6 g"),
    "herbivore_efficiency": (3, "20%"),
    "carnivore_efficiency": (4, "25%"),
    "rain_volume": (3, "1.44 m³"),
    "rain_collected_volume": (4, "1.08 m³"),
    "rain_collected_litres": (4, "1080 L"),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def build_rows():
    revision = digest(canonical(SCENARIOS).encode())
    rows = []
    numeric_values = independent_numeric_values()
    for item in SCENARIOS:
        checks = []
        for key in item["numeric"]:
            target, unit = NUMERIC_TARGETS[key]
            computed = numeric_values[key]
            if computed != Fraction(target):
                raise ValueError(f"Numeric mismatch in {item['slug']}: {key}")
            turn_index, target_span = NUMERIC_SPANS[key]
            if target_span not in item["turns"][turn_index] or not target_span.startswith(target):
                raise ValueError(f"Numeric target text mismatch in {item['slug']}: {key}")
            checks.append(
                {
                    "check": key,
                    "computed_exact": str(computed),
                    "target_decimal": target,
                    "unit": unit,
                    "status": "passed",
                    "target_turn_index": turn_index,
                    "target_span": target_span,
                }
            )
        row_id = "muta_authored_science:" + item["slug"]
        rows.append(
            {
                "id": row_id,
                "group_id": row_id,
                "source": "muta_authored_science",
                "source_revision": revision,
                "source_id": item["slug"],
                "license": "LicenseRef-Project-Original",
                "license_evidence_status": "original_project_authorship_not_external_source_license",
                "subject": item["subject"],
                "capabilities": [item["capability"]],
                "quality": {
                    "tier": "original_authored_pending_independent_review",
                    "independent_scientific_verification": False,
                    "numeric_checks": checks,
                    "content_review": "pending_all_assistant_statements",
                    "evidence_limit": "Primary-reference grounding and arithmetic checks do not independently validate every explanation.",
                },
                "messages": [
                    {"role": "user" if i % 2 == 0 else "assistant", "content": text}
                    for i, text in enumerate(item["turns"])
                ],
                "original_split": "authored_unsplit",
                "eligibility": "candidate_pending_review",
                "fresh_holdout_admission": "not_claimed; campaign_and_historical_overlap_screen_pending",
                "source_metadata": {
                    "authorship": "Original assistant-authored synthetic learner/tutor conversation for this project; not a real student transcript.",
                    "primary_capability": item["capability"],
                    "reference_ids": item["references"],
                    "reference_urls": [REFERENCES[key][1] for key in item["references"]],
                    "claims_for_review": item["claims_for_review"],
                    "learner_error_turn_indices": [2],
                    "repair_and_transfer_turn_index": 3,
                    "transfer_response_turn_index": 4,
                    "source_passages_reproduced": False,
                    "family_independence": "not_claimed",
                },
            }
        )
    return rows


def write_artifact(path, value, jsonl=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(canonical(row) + "\n" for row in value) if jsonl else canonical(value) + "\n"
    payload = text.encode()
    path.write_bytes(payload)
    return {"path": str(path), "sha256": digest(payload), "bytes": len(payload)}


def build(output=OUTPUT, provenance=PROVENANCE):
    rows = build_rows()
    if Counter((row["subject"], row["capabilities"][0]) for row in rows) != Counter(
        (subject, capability) for subject in SUBJECTS for capability in CAPABILITIES
    ):
        raise ValueError("Expected exactly one scenario in every subject/capability cell")
    artifact = write_artifact(output / "candidates.jsonl", rows, jsonl=True)
    receipt = {
        "read_date": "2026-09-19",
        "method": "Primary pages read using web research tools; no bulk text ingestion.",
        "references": [
            {"id": key, "title": title, "url": url, "factual_reading_note": note}
            for key, (title, url, note) in REFERENCES.items()
        ],
        "reference_rights": "URLs and original factual notes only; no claim that every page/image is public domain. No source passages or worked exercises are reproduced.",
        "excluded_reference_family": "Current OpenStax pages were inspected but not used as content sources because they state a restriction on training/ingestion.",
        "original_text_rights": "Generated for the user's authorized project. LicenseRef-Project-Original is an internal provenance label, not a public license grant.",
    }
    references = write_artifact(provenance / "authored-reference-receipt.json", receipt)
    review = write_artifact(
        provenance / "authored-review-packet.jsonl",
        [
            {
                "review_status": "pending_independent_review",
                "review_scope": "all assistant statements and final learner transfer answer",
                "row": row,
            }
            for row in rows
        ],
        jsonl=True,
    )
    manifest = {
        "source": "muta_authored_science",
        "rows": len(rows),
        "groups": len({r["group_id"] for r in rows}),
        "assistant_turns": sum(m["role"] == "assistant" for r in rows for m in r["messages"]),
        "subject_counts": dict(Counter(r["subject"] for r in rows)),
        "capability_counts": dict(Counter(r["capabilities"][0] for r in rows)),
        "numeric_checks_passed": sum(len(r["quality"]["numeric_checks"]) for r in rows),
        "content_review_status": "pending_independent_review",
        "admitted_to_training": False,
        "no_holdout_constructed": True,
        "no_family_independence_claim": True,
        "known_exclusions_during_authoring": [
            "falling-object comparisons",
            "photosynthesis multiple-choice",
            "DNA metaphors",
            "40/80 km average-speed variants",
        ],
        "overlap_screen": "Pending root's exact/near-match screen against judges, STEM100 and campaign histories.",
        "pipeline_sha256": digest(Path(__file__).read_bytes()),
        "artifacts": {
            "candidates": artifact,
            "reference_receipt": references,
            "review_packet": review,
        },
    }
    write_artifact(provenance / "authored-manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--provenance", type=Path, default=PROVENANCE)
    args = parser.parse_args()
    result = build(args.output, args.provenance)
    print(
        canonical(
            {
                key: result[key]
                for key in [
                    "rows",
                    "groups",
                    "assistant_turns",
                    "numeric_checks_passed",
                    "admitted_to_training",
                ]
            }
        )
    )
