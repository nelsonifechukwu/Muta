"""Deterministic, independently recomputable West-African-context STEM examples."""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

from .core import VERIFIER_VERSION, HoldoutIndex, make_record, normalized_sha256


@dataclass(frozen=True)
class Problem:
    problem: str
    answer: str
    steps: tuple[str, ...]
    self_check: str
    wrong_answer: str
    misconception: str
    misconception_type: str
    subject: str
    topic: str
    difficulty: str
    formula_id: str
    inputs: dict[str, int]


TOWNS = (
    "Abeokuta",
    "Accra",
    "Benin City",
    "Bo",
    "Freetown",
    "Ibadan",
    "Ilorin",
    "Kano",
    "Kumasi",
    "Lagos",
    "Monrovia",
    "Onitsha",
    "Tamale",
)
CURRENCIES = (("₦", "naira"), ("GH₵", "Ghana cedis"), ("Le", "leones"), ("D", "dalasis"))
NAMES = ("Ada", "Aisha", "Bola", "Chidi", "Fatou", "Kofi", "Mariam", "Sorie", "Yaw", "Zainab")
GASES = (
    "ammonia",
    "argon",
    "carbon dioxide",
    "chlorine",
    "ethene",
    "helium",
    "hydrogen",
    "methane",
    "neon",
    "nitrogen",
    "oxygen",
    "sulfur dioxide",
)
STOICHIOMETRY_REACTIONS = (
    ("2H₂ + O₂ → 2H₂O", "O₂", 1, "H₂O", 2),
    ("N₂ + 3H₂ → 2NH₃", "N₂", 1, "NH₃", 2),
    ("2KClO₃ → 2KCl + 3O₂", "KClO₃", 2, "O₂", 3),
    ("2SO₂ + O₂ → 2SO₃", "O₂", 1, "SO₃", 2),
    ("4Fe + 3O₂ → 2Fe₂O₃", "O₂", 3, "Fe₂O₃", 2),
    ("2Mg + O₂ → 2MgO", "O₂", 1, "MgO", 2),
    ("CH₄ + 2O₂ → CO₂ + 2H₂O", "CH₄", 1, "H₂O", 2),
    ("2Na + 2H₂O → 2NaOH + H₂", "H₂O", 2, "H₂", 1),
    ("2Al + 3Cl₂ → 2AlCl₃", "Cl₂", 3, "AlCl₃", 2),
    ("4NH₃ + 5O₂ → 4NO + 6H₂O", "NH₃", 4, "H₂O", 6),
    ("2C₂H₆ + 7O₂ → 4CO₂ + 6H₂O", "C₂H₆", 2, "CO₂", 4),
    ("P₄ + 5O₂ → 2P₂O₅", "P₄", 1, "P₂O₅", 2),
)
TEMPERATURE_SETTINGS = (
    "classroom thermometer",
    "greenhouse thermometer",
    "laboratory thermometer",
    "weather-station display",
    "covered-veranda thermometer",
)


def _rng(seed: int, index: int, label: str) -> random.Random:
    return random.Random(f"muta-stem-v2:{seed}:{index}:{label}")


def _fraction(value: Fraction, decimals: int = 2) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    rounded = _decimal(value, decimals)
    return f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")


def _decimal(value: Fraction, places: int) -> Decimal:
    quantizer = Decimal(1).scaleb(-places)
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        quantizer, rounding=ROUND_HALF_UP
    )


def _fixed(value: Fraction, places: int) -> str:
    return f"{_decimal(value, places):.{places}f}"


def _exact(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _money(symbol: str, value: Fraction) -> str:
    if value.denominator == 1:
        return f"{symbol}{value.numerator:,}"
    return f"{symbol}{_decimal(value, 2):,.2f}"


def _percent(value: Fraction) -> str:
    return f"{_decimal(value, 1):.1f}%"


def _profit(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "profit")
    town = r.choice(TOWNS)
    name = r.choice(NAMES)
    currency_index = r.randrange(len(CURRENCIES))
    symbol, currency = CURRENCIES[currency_index]
    quantity = r.randint(24, 120)
    first = r.randint(8, quantity - 8)
    remainder = quantity - first
    cost_price = r.randint(5, 30) * 100 if symbol == "₦" else r.randint(2, 12) * 4
    markup = r.choice((25, 30, 40, 50, 60))
    first_price = Fraction(cost_price * (100 + markup), 100)
    discount = r.choice((5, 10, 15, 20))
    second_price = first_price * Fraction(100 - discount, 100)
    cost = Fraction(quantity * cost_price)
    revenue1 = first * first_price
    revenue2 = remainder * second_price
    revenue = revenue1 + revenue2
    profit = revenue - cost
    profit_pct = profit / cost * 100
    answer = (
        f"revenue {_money(symbol, revenue)}, profit {_money(symbol, profit)}, "
        f"profit percentage {_percent(profit_pct)}"
    )
    return Problem(
        problem=(
            f"{name}, a trader in {town}, buys {quantity} kg of grain at "
            f"{_money(symbol, Fraction(cost_price))} per kg. {name} sells {first} kg at "
            f"{_money(symbol, first_price)} per kg, reduces that selling price by {discount}%, "
            f"and sells the remaining {remainder} kg. Find the total revenue, profit, and "
            f"percentage profit on cost to one decimal place. State every money answer in {currency}."
        ),
        answer=answer,
        steps=(
            f"Total cost = {quantity} × {_money(symbol, Fraction(cost_price))} = {_money(symbol, cost)}.",
            f"Reduced price = {_money(symbol, first_price)} × {(100 - discount)}/100 = {_money(symbol, second_price)} per kg.",
            f"Revenue = {first} × {_money(symbol, first_price)} + {remainder} × {_money(symbol, second_price)} = {_money(symbol, revenue)}.",
            f"Profit = {_money(symbol, revenue)} - {_money(symbol, cost)} = {_money(symbol, profit)}.",
            f"Profit percentage = {_money(symbol, profit)} ÷ {_money(symbol, cost)} × 100 = {_percent(profit_pct)}.",
        ),
        self_check=(
            f"Revenue should also equal cost plus profit: {_money(symbol, cost)} + "
            f"{_money(symbol, profit)} = {_money(symbol, revenue)}."
        ),
        wrong_answer=_money(symbol, first * first_price + remainder * first_price),
        misconception="The reduction changes the price per kilogram, not the number of kilograms left.",
        misconception_type="discount_not_applied",
        subject="mathematics",
        topic="commercial_arithmetic",
        difficulty="advanced",
        formula_id="profit_two_prices",
        inputs={
            "quantity": quantity,
            "first": first,
            "cost_price": cost_price,
            "markup": markup,
            "discount": discount,
            "currency_index": currency_index,
        },
    )


def _average_speed(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "average_speed")
    town = r.choice(TOWNS)
    leg = r.randrange(20, 305, 5)
    slow = r.randrange(15, 71)
    fast = r.randrange(slow + 5, 101)
    total_time = Fraction(leg, slow) + Fraction(leg, fast)
    average = Fraction(2 * leg, 1) / total_time
    arithmetic_mean = Fraction(slow + fast, 2)
    answer = f"{_fixed(average, 2)} km/h"
    return Problem(
        problem=(
            f"A minibus near {town} travels {leg} km at {slow} km/h and then another "
            f"{leg} km at {fast} km/h. Find its average speed for the whole journey. "
            f"Explain why simply averaging {slow} and {fast} is not valid. Give the speed to two decimal places."
        ),
        answer=answer,
        steps=(
            f"Time for the first leg = {leg}/{slow} = {_exact(Fraction(leg, slow))} h.",
            f"Time for the second leg = {leg}/{fast} = {_exact(Fraction(leg, fast))} h.",
            f"Total distance = {2 * leg} km and total time = {_exact(total_time)} h.",
            f"Average speed = total distance ÷ total time = {2 * leg} ÷ ({_exact(total_time)}) = {answer}.",
        ),
        self_check=(
            f"The slower leg takes more time, so the answer must be below the unweighted mean "
            f"of {_fraction(arithmetic_mean)} km/h; {answer} is."
        ),
        wrong_answer=f"{_fraction(arithmetic_mean)} km/h",
        misconception="Speeds may be averaged directly only when the time spent at each speed is equal; here the distances are equal.",
        misconception_type="unweighted_speed_average",
        subject="mathematics",
        topic="rates_and_average_speed",
        difficulty="advanced",
        formula_id="equal_distance_average_speed",
        inputs={"leg": leg, "slow": slow, "fast": fast},
    )


def _linear(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "linear")
    x = r.choice((*range(-40, 0), *range(1, 81)))
    coefficient = r.choice(tuple(i for i in range(-15, 16) if i not in (0, 1)))
    offset = r.randint(-80, 80)
    rhs = coefficient * x + offset
    answer = f"x = {x}"
    undivided = rhs - offset
    coefficient_text = "-x" if coefficient == -1 else f"{coefficient}x"
    offset_text = f"+ {offset}" if offset >= 0 else f"- {abs(offset)}"
    inverse_step = (
        f"Subtract {offset} from both sides" if offset >= 0 else f"Add {abs(offset)} to both sides"
    )
    return Problem(
        problem=f"Solve {coefficient_text} {offset_text} = {rhs}.",
        answer=answer,
        steps=(
            f"{inverse_step}: {coefficient_text} = {rhs - offset}.",
            f"Divide both sides by {coefficient}: x = {rhs - offset}/{coefficient} = {x}.",
        ),
        self_check=f"Substitute x = {x}: {coefficient}({x}) + ({offset}) = {rhs}.",
        wrong_answer=f"x = {undivided}",
        misconception="The coefficient was not divided out after the term containing x was isolated.",
        misconception_type="coefficient_not_divided",
        subject="mathematics",
        topic="linear_equations",
        difficulty="standard",
        formula_id="linear_equation",
        inputs={"coefficient": coefficient, "offset": offset, "rhs": rhs},
    )


def _ratio(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "ratio")
    name_index = r.randrange(len(NAMES))
    name = NAMES[name_index]
    first_ratio = r.randint(2, 9)
    second_ratio = r.randint(2, 9)
    unit = r.randint(4, 80)
    total = (first_ratio + second_ratio) * unit
    answer_value = second_ratio * unit
    answer = str(answer_value)
    return Problem(
        problem=(
            f"{name} arranges red and blue counters in the ratio {first_ratio}:{second_ratio}. "
            f"There are {total} counters altogether. How many are blue? Show how the ratio "
            "units are used."
        ),
        answer=answer,
        steps=(
            f"Total ratio units = {first_ratio} + {second_ratio} = {first_ratio + second_ratio}.",
            f"One ratio unit = {total} ÷ {first_ratio + second_ratio} = {unit}.",
            f"Blue counters = {second_ratio} × {unit} = {answer_value}.",
        ),
        self_check=f"Red counters are {first_ratio * unit}; {first_ratio * unit} + {answer_value} = {total}.",
        wrong_answer=str(second_ratio),
        misconception="A ratio part is a number of equal units, not the final number of objects.",
        misconception_type="ratio_units_as_final_count",
        subject="mathematics",
        topic="ratio_and_proportion",
        difficulty="standard",
        formula_id="ratio_share",
        inputs={
            "first_ratio": first_ratio,
            "second_ratio": second_ratio,
            "total": total,
            "name_index": name_index,
        },
    )


def _interest(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "interest")
    currency_index = r.randrange(len(CURRENCIES))
    symbol, _ = CURRENCIES[currency_index]
    principal_scale = 1000 if symbol == "₦" else 100
    principal = r.randint(10, 200) * principal_scale
    rate = r.choice((2, 3, 4, 5, 6, 8, 10, 12, 15))
    years = r.randint(2, 8)
    interest = Fraction(principal * rate * years, 100)
    amount = Fraction(principal) + interest
    answer = f"interest {_money(symbol, interest)}, amount {_money(symbol, amount)}"
    return Problem(
        problem=(
            f"Find the simple interest and final amount on {_money(symbol, Fraction(principal))} "
            f"invested at {rate}% per year for {years} years."
        ),
        answer=answer,
        steps=(
            "Simple interest = principal × rate × time / 100.",
            f"Interest = {principal} × {rate} × {years} / 100 = {_money(symbol, interest)}.",
            f"Amount = principal + interest = {_money(symbol, amount)}.",
        ),
        self_check=f"Interest per year is {_money(symbol, Fraction(principal * rate, 100))}; multiply by {years} years.",
        wrong_answer=_money(symbol, Fraction(principal * rate, 100)),
        misconception="The annual interest must be multiplied by the number of years.",
        misconception_type="time_factor_omitted",
        subject="mathematics",
        topic="simple_interest",
        difficulty="standard",
        formula_id="simple_interest",
        inputs={
            "principal": principal,
            "rate": rate,
            "years": years,
            "currency_index": currency_index,
        },
    )


def _simultaneous(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "simultaneous")
    x = r.randint(-12, 20)
    y = r.choice(tuple(value for value in range(-12, 21) if value != x))
    a, b, c, d = r.randint(1, 9), r.randint(1, 9), r.randint(1, 9), r.randint(1, 9)
    while a * d == b * c:
        d = r.randint(1, 9)
    first = a * x + b * y
    second = c * x + d * y
    answer = f"x = {x}, y = {y}"
    determinant = a * d - b * c
    determinant_x = first * d - b * second
    determinant_y = a * second - first * c
    return Problem(
        problem=f"Solve simultaneously: {a}x + {b}y = {first} and {c}x + {d}y = {second}.",
        answer=answer,
        steps=(
            f"The determinant is Δ = {a}×{d} - {b}×{c} = {determinant}, so the equations have one solution.",
            f"For x, Δₓ = {first}×{d} - {b}×{second} = {determinant_x}; therefore x = Δₓ/Δ = {determinant_x}/{determinant} = {x}.",
            f"For y, Δᵧ = {a}×{second} - {first}×{c} = {determinant_y}; therefore y = Δᵧ/Δ = {determinant_y}/{determinant} = {y}.",
        ),
        self_check=f"{a}({x}) + {b}({y}) = {first}, and {c}({x}) + {d}({y}) = {second}.",
        wrong_answer=f"x = {y}, y = {x}",
        misconception="The ordered values must be substituted into both original equations; swapping them usually fails the check.",
        misconception_type="variables_swapped",
        subject="mathematics",
        topic="simultaneous_equations",
        difficulty="advanced",
        formula_id="simultaneous_equations",
        inputs={"a": a, "b": b, "c": c, "d": d, "first": first, "second": second},
    )


def _sequence(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "sequence")
    first = r.randint(-20, 40)
    difference = r.choice(tuple(i for i in range(-12, 16) if i != 0))
    n = r.randint(8, 40)
    result = first + (n - 1) * difference
    answer = str(result)
    return Problem(
        problem=(
            f"An arithmetic sequence begins {first}, {first + difference}, "
            f"{first + 2 * difference}, ... . Find its {_ordinal(n)} term."
        ),
        answer=answer,
        steps=(
            "For an arithmetic sequence, aₙ = a₁ + (n - 1)d.",
            f"aₙ = {first} + ({n} - 1)({difference}) = {result}.",
        ),
        self_check=(
            f"Moving from the first to the {_ordinal(n)} term uses {n - 1} equal jumps, "
            f"not {n} jumps."
        ),
        wrong_answer=str(first + n * difference),
        misconception="There are n - 1 intervals between the first and nth terms.",
        misconception_type="sequence_interval_off_by_one",
        subject="mathematics",
        topic="sequences",
        difficulty="standard",
        formula_id="arithmetic_sequence",
        inputs={"first": first, "difference": difference, "n": n},
    )


def _probability(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "probability")
    name_index = r.randrange(len(NAMES))
    name = NAMES[name_index]
    red = r.randint(2, 25)
    blue = r.randint(2, 25)
    green = r.randint(1, 15)
    total = red + blue + green
    value = Fraction(red, total)
    answer = f"{value.numerator}/{value.denominator}"
    return Problem(
        problem=(
            f"{name}'s bag holds {red} red, {blue} blue, and {green} green beads. One bead is "
            "chosen at random. What is the probability that it is red? Give the fraction in "
            "lowest terms."
        ),
        answer=answer,
        steps=(
            f"Total beads = {red} + {blue} + {green} = {total}.",
            f"Probability = favourable outcomes / all outcomes = {red}/{total} = {answer}.",
        ),
        self_check="The probability is between 0 and 1, and the three colour probabilities sum to 1.",
        wrong_answer=f"{red}/{blue + green}",
        misconception="The denominator is the total number of possible beads, not only the non-red beads.",
        misconception_type="wrong_sample_space",
        subject="mathematics",
        topic="probability",
        difficulty="standard",
        formula_id="single_draw_probability",
        inputs={"red": red, "blue": blue, "green": green, "name_index": name_index},
    )


def _force(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "force")
    name_index = r.randrange(len(NAMES))
    town_index = r.randrange(len(TOWNS))
    name = NAMES[name_index]
    town = TOWNS[town_index]
    mass = r.randint(2, 50)
    acceleration = r.randint(1, 8)
    if mass == 2 and acceleration == 2:
        acceleration = 3
    force = mass * acceleration
    answer = f"{force} N"
    return Problem(
        problem=(
            f"In {town}, {name} tests a {mass} kg trolley that accelerates at "
            f"{acceleration} m/s². Find the resultant force."
        ),
        answer=answer,
        steps=("Newton's second law gives F = ma.", f"F = {mass} × {acceleration} = {answer}."),
        self_check="kg·m/s² is the newton, so the unit is consistent.",
        wrong_answer=f"{mass + acceleration} N",
        misconception="Force is mass multiplied by acceleration, not their sum.",
        misconception_type="added_instead_of_multiplied",
        subject="physics",
        topic="newtons_second_law",
        difficulty="foundation",
        formula_id="force",
        inputs={
            "mass": mass,
            "acceleration": acceleration,
            "name_index": name_index,
            "town_index": town_index,
        },
    )


def _density(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "density")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    volume = r.randint(2, 80)
    density = r.randint(2, 20)
    mass = volume * density
    answer = f"{density} g/cm³"
    return Problem(
        problem=(
            f"A laboratory in {town} measures a solid with mass {mass} g and volume "
            f"{volume} cm³. Calculate its density."
        ),
        answer=answer,
        steps=("Density = mass ÷ volume.", f"Density = {mass} ÷ {volume} = {answer}."),
        self_check=f"{density} g/cm³ × {volume} cm³ = {mass} g.",
        wrong_answer=f"{mass * volume} g/cm³",
        misconception="Density divides mass by volume; multiplying gives the wrong dimensions.",
        misconception_type="multiplied_instead_of_divided",
        subject="physics",
        topic="density",
        difficulty="foundation",
        formula_id="density",
        inputs={"mass": mass, "volume": volume, "town_index": town_index},
    )


def _ohm(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "ohm")
    name_index = r.randrange(len(NAMES))
    town_index = r.randrange(len(TOWNS))
    name = NAMES[name_index]
    town = TOWNS[town_index]
    current = r.randint(1, 10)
    resistance = r.randint(2, 50)
    voltage = current * resistance
    answer = f"{voltage} V"
    return Problem(
        problem=(
            f"In a circuit lesson in {town}, {name} sends a current of {current} A through a "
            f"{resistance} Ω resistor. Find the potential difference."
        ),
        answer=answer,
        steps=("Ohm's law gives V = IR.", f"V = {current} × {resistance} = {answer}."),
        self_check=f"V/R = {voltage}/{resistance} = {current} A, the stated current.",
        wrong_answer=f"{_fraction(Fraction(current, resistance))} V",
        misconception="When current and resistance are known, voltage is their product.",
        misconception_type="divided_instead_of_multiplied",
        subject="physics",
        topic="ohms_law",
        difficulty="standard",
        formula_id="ohm_voltage",
        inputs={
            "current": current,
            "resistance": resistance,
            "name_index": name_index,
            "town_index": town_index,
        },
    )


def _wave(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "wave")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    frequency = r.randint(2, 80)
    wavelength = r.randint(2, 30)
    speed = frequency * wavelength
    answer = f"{speed} m/s"
    return Problem(
        problem=(
            f"During a wave experiment in {town}, a wave has frequency {frequency} Hz and "
            f"wavelength {wavelength} m. Calculate its speed."
        ),
        answer=answer,
        steps=("Wave speed v = fλ.", f"v = {frequency} × {wavelength} = {answer}."),
        self_check="Hz means cycles per second; multiplying by metres per cycle gives metres per second.",
        wrong_answer=f"{_fraction(Fraction(frequency, wavelength))} m/s",
        misconception="Wave speed is frequency multiplied by wavelength.",
        misconception_type="divided_instead_of_multiplied",
        subject="physics",
        topic="waves",
        difficulty="standard",
        formula_id="wave_speed",
        inputs={"frequency": frequency, "wavelength": wavelength, "town_index": town_index},
    )


def _moles(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "moles")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    compounds = (
        ("H₂O", 18),
        ("CO₂", 44),
        ("Na₂CO₃", 106),
        ("O₂", 32),
        ("CaCO₃", 100),
        ("NH₃", 17),
        ("CH₄", 16),
        ("KOH", 56),
        ("MgO", 40),
        ("N₂", 28),
        ("H₂", 2),
        ("NaOH", 40),
    )
    formula, molar_mass = r.choice(compounds)
    amount_tenths = r.randint(1, 100)
    moles = Fraction(amount_tenths, 10)
    mass = molar_mass * moles
    answer = f"{_fraction(moles)} mol"
    return Problem(
        problem=(
            f"A laboratory in {town} has {_fraction(mass)} g of {formula}. How many moles "
            f"is this if the molar mass is {molar_mass} g/mol?"
        ),
        answer=answer,
        steps=(
            "Amount in moles = mass ÷ molar mass.",
            f"n = {_fraction(mass)} ÷ {molar_mass} = {answer}.",
        ),
        self_check=(f"{_fraction(moles)} mol × {molar_mass} g/mol = {_fraction(mass)} g."),
        wrong_answer=f"{_fraction(mass * molar_mass)} mol",
        misconception="Moles are found by dividing mass by molar mass.",
        misconception_type="multiplied_by_molar_mass",
        subject="chemistry",
        topic="amount_of_substance",
        difficulty="standard",
        formula_id="moles",
        inputs={
            "mass_numerator": mass.numerator,
            "mass_denominator": mass.denominator,
            "molar_mass": molar_mass,
            "town_index": town_index,
        },
    )


def _concentration(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "concentration")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    volume = r.randrange(50, 2050, 50)
    concentration = Fraction(r.randint(1, 50), 10)
    moles = concentration * volume / 1000
    # Every generated value is a multiple of 0.005 mol, so three decimal
    # places are sufficient and exact. The generic two-decimal renderer can
    # change the visible operand (for example, 0.035 -> 0.04) while leaving the
    # answer based on the hidden exact value.
    moles_text = _fraction(moles, 3)
    volume_dm3_text = _fraction(Fraction(volume, 1000))
    answer = f"{_fraction(concentration)} mol/dm³"
    return Problem(
        problem=(
            f"In a laboratory in {town}, a solution contains {moles_text} mol of solute "
            f"in {volume} cm³. Calculate its concentration in mol/dm³."
        ),
        answer=answer,
        steps=(
            f"Convert volume: {volume} cm³ = {volume_dm3_text} dm³.",
            f"Concentration = moles ÷ volume = {moles_text} ÷ {volume_dm3_text} = {answer}.",
        ),
        self_check=(
            f"{_fraction(concentration)} mol/dm³ × {volume_dm3_text} dm³ = {moles_text} mol."
        ),
        wrong_answer=f"{_fraction(moles / volume, 4)} mol/dm³",
        misconception="Convert cubic centimetres to cubic decimetres before dividing.",
        misconception_type="volume_unit_not_converted",
        subject="chemistry",
        topic="solution_concentration",
        difficulty="standard",
        formula_id="concentration",
        inputs={
            "moles_numerator": moles.numerator,
            "moles_denominator": moles.denominator,
            "volume_cm3": volume,
            "town_index": town_index,
        },
    )


def _dilution(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "dilution")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    initial_concentration = r.randint(1, 5)
    initial_volume = r.randrange(10, 255, 5)
    multiplier = r.choice((2, 3, 4, 5, 6, 8, 10))
    final_volume = initial_volume * multiplier
    final_concentration = Fraction(initial_concentration, multiplier)
    reported_concentration = _fixed(final_concentration, 2)
    relation = "=" if Fraction(reported_concentration) == final_concentration else "≈"
    answer = f"{reported_concentration} mol/dm³"
    return Problem(
        problem=(
            f"In a laboratory in {town}, {initial_volume} cm³ of a "
            f"{initial_concentration} mol/dm³ solution is diluted to {final_volume} cm³. "
            "Find the new concentration and give it to two decimal places."
        ),
        answer=answer,
        steps=(
            "Dilution conserves solute, so C₁V₁ = C₂V₂.",
            f"C₂ = {initial_concentration} × {initial_volume} ÷ {final_volume} {relation} {answer}.",
        ),
        self_check=f"The volume increased by a factor of {multiplier}, so the concentration must fall by the same factor.",
        wrong_answer=(f"{_fixed(Fraction(initial_concentration * multiplier), 2)} mol/dm³"),
        misconception="Adding solvent increases volume but does not add solute, so concentration decreases.",
        misconception_type="concentration_scaled_with_volume",
        subject="chemistry",
        topic="dilution",
        difficulty="advanced",
        formula_id="dilution",
        inputs={
            "initial_concentration": initial_concentration,
            "initial_volume": initial_volume,
            "final_volume": final_volume,
            "town_index": town_index,
        },
    )


def _visible_semantics_valid(problem: Problem) -> bool:
    """Check rendered operands independently of deterministic regeneration.

    Regenerating a row proves reproducibility, but it can faithfully reproduce
    a renderer bug. These checks bind displayed operands and mathematical
    relations back to the exact structured inputs for precision-sensitive
    families.
    """

    if problem.formula_id == "concentration":
        match = re.fullmatch(
            r"In a laboratory in (.+), a solution contains "
            r"([+-]?\d+(?:\.\d+)?) mol of solute in (\d+) cm³\. "
            r"Calculate its concentration in mol/dm³\.",
            problem.problem,
        )
        if match is None:
            return False
        displayed_town = match.group(1)
        displayed_moles = Fraction(match.group(2))
        displayed_volume = int(match.group(3))
        stored_moles = Fraction(
            problem.inputs["moles_numerator"], problem.inputs["moles_denominator"]
        )
        stored_volume = problem.inputs["volume_cm3"]
        stored_town = TOWNS[problem.inputs["town_index"]]
        if (
            displayed_town != stored_town
            or displayed_moles != stored_moles
            or displayed_volume != stored_volume
        ):
            return False
        volume_dm3 = Fraction(displayed_volume, 1000)
        visible_answer = f"{_fraction(displayed_moles / volume_dm3)} mol/dm³"
        volume_dm3_text = _fraction(volume_dm3)
        moles_text = match.group(2)
        return all(
            (
                visible_answer == problem.answer,
                problem.steps
                == (
                    f"Convert volume: {displayed_volume} cm³ = {volume_dm3_text} dm³.",
                    (
                        f"Concentration = moles ÷ volume = {moles_text} ÷ "
                        f"{volume_dm3_text} = {problem.answer}."
                    ),
                ),
                problem.self_check
                == f"{problem.answer} × {volume_dm3_text} dm³ = {moles_text} mol.",
                problem.wrong_answer == f"{_fraction(stored_moles / stored_volume, 4)} mol/dm³",
            )
        )
    if problem.formula_id == "dilution":
        initial_concentration = problem.inputs["initial_concentration"]
        initial_volume = problem.inputs["initial_volume"]
        final_volume = problem.inputs["final_volume"]
        if initial_volume <= 0 or final_volume % initial_volume:
            return False
        multiplier = final_volume // initial_volume
        exact = Fraction(
            initial_concentration * initial_volume,
            final_volume,
        )
        reported = _fixed(exact, 2)
        relation = "=" if Fraction(reported) == exact else "≈"
        expected_answer = f"{reported} mol/dm³"
        expected_problem = (
            f"In a laboratory in {TOWNS[problem.inputs['town_index']]}, {initial_volume} cm³ "
            f"of a {initial_concentration} mol/dm³ solution is diluted to {final_volume} cm³. "
            "Find the new concentration and give it to two decimal places."
        )
        expected_step = (
            f"C₂ = {initial_concentration} × {initial_volume} ÷ {final_volume} "
            f"{relation} {expected_answer}."
        )
        expected_self_check = (
            f"The volume increased by a factor of {multiplier}, so the concentration "
            "must fall by the same factor."
        )
        expected_wrong_answer = f"{_fixed(Fraction(initial_concentration * multiplier), 2)} mol/dm³"
        return all(
            (
                problem.problem == expected_problem,
                problem.answer == expected_answer,
                problem.steps
                == (
                    "Dilution conserves solute, so C₁V₁ = C₂V₂.",
                    expected_step,
                ),
                problem.self_check == expected_self_check,
                problem.wrong_answer == expected_wrong_answer,
            )
        )
    return True


def _magnification(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "magnification")
    specimens = (
        "measured feature on a prepared slide",
        "labelled microscopic feature",
        "measured feature in a tissue section",
        "feature marked on a photomicrograph",
        "measured microscope-scale specimen",
        "feature outlined in a microscope image",
    )
    town_index = r.randrange(len(TOWNS))
    specimen_index = r.randrange(len(specimens))
    town = TOWNS[town_index]
    actual = r.randint(1, 250)
    magnification = r.choice((10, 20, 25, 40, 50, 100, 200, 400, 500, 1000))
    image = actual * magnification
    answer = f"{magnification}×"
    return Problem(
        problem=(
            f"In a microscopy lesson in {town}, a {specimens[specimen_index]} is {actual} μm "
            f"long, but its drawing is {image} μm long. Calculate the magnification of the "
            "drawing."
        ),
        answer=answer,
        steps=(
            "Magnification = image size ÷ actual size.",
            f"Magnification = {image} ÷ {actual} = {answer}.",
        ),
        self_check=f"{actual} μm × {magnification} = {image} μm.",
        wrong_answer=f"{_fraction(Fraction(actual, image), 4)}×",
        misconception="Magnification compares image size with actual size in the same units.",
        misconception_type="magnification_ratio_inverted",
        subject="biology",
        topic="microscopy",
        difficulty="standard",
        formula_id="magnification",
        inputs={
            "actual": actual,
            "image": image,
            "town_index": town_index,
            "specimen_index": specimen_index,
        },
    )


def _population_density(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "population_density")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    area = r.randint(2, 50)
    density = r.randint(2, 80)
    organisms = area * density
    answer = f"{density} organisms/m²"
    return Problem(
        problem=(
            f"Ecologists near {town} count {organisms} seedlings in a sampled area of "
            f"{area} m². Estimate the seedling population density."
        ),
        answer=answer,
        steps=(
            "Population density = number counted ÷ area sampled.",
            f"Density = {organisms} ÷ {area} = {answer}.",
        ),
        self_check=f"{density} organisms/m² × {area} m² = {organisms} organisms.",
        wrong_answer=f"{organisms * area} organisms/m²",
        misconception="Density is a count per unit area, so divide by area.",
        misconception_type="multiplied_by_sample_area",
        subject="biology",
        topic="ecological_sampling",
        difficulty="standard",
        formula_id="population_density",
        inputs={"organisms": organisms, "area": area, "town_index": town_index},
    )


def _inheritance(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "inheritance")
    species = ("maize", "cowpea", "tomato", "groundnut", "okra", "garden pea")
    traits = (
        "seed colour",
        "flower colour",
        "pod texture",
        "stem pigmentation",
        "fruit shape",
        "leaf pattern",
    )
    town_index = r.randrange(len(TOWNS))
    species_index = r.randrange(len(species))
    trait_index = r.randrange(len(traits))
    town = TOWNS[town_index]
    children = 4 * r.randint(1, 1000)
    affected = Fraction(children, 4)
    answer = f"25%, about {_fraction(affected)} of {children} offspring"
    return Problem(
        problem=(
            f"In a large {species[species_index]}-breeding study near {town}, researchers track "
            f"{traits[trait_index]}. Repeated crosses use heterozygous parents Aa and Aa. What "
            "is the probability of an aa offspring, and about how many aa offspring would be "
            f"expected among {children} offspring?"
        ),
        answer=answer,
        steps=(
            "The cross Aa × Aa gives AA, Aa, Aa, and aa in equal Punnett-square cells.",
            "One of the four outcomes is aa, so the probability is 1/4 = 25%.",
            f"Expected aa offspring = 1/4 × {children} = {_fraction(affected)}.",
        ),
        self_check="The genotype probabilities 1/4 AA + 1/2 Aa + 1/4 aa add to 1.",
        wrong_answer=f"50%, about {children // 2} of {children} offspring",
        misconception="Heterozygous offspring Aa carry allele a but do not have genotype aa.",
        misconception_type="heterozygote_counted_as_homozygous_recessive",
        subject="biology",
        topic="mendelian_inheritance",
        difficulty="standard",
        formula_id="recessive_cross",
        inputs={
            "children": children,
            "town_index": town_index,
            "species_index": species_index,
            "trait_index": trait_index,
        },
    )


def _mean(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "mean")
    centre = r.randint(12, 90)
    first_offset = r.randint(1, 11)
    second_offset = r.randint(1, 11)
    values = [
        centre - first_offset,
        centre + first_offset,
        centre - second_offset,
        centre + second_offset,
    ]
    r.shuffle(values)
    total = sum(values)
    answer = str(centre)
    return Problem(
        problem=f"Find the arithmetic mean of {', '.join(str(value) for value in values)}.",
        answer=answer,
        steps=(
            f"Sum = {' + '.join(str(value) for value in values)} = {total}.",
            f"Mean = {total} ÷ 4 = {answer}.",
        ),
        self_check=f"Mean × count = {centre} × 4 = {total}, the original total.",
        wrong_answer=str(total),
        misconception="The total must be divided by the number of observations.",
        misconception_type="sum_not_divided_by_count",
        subject="mathematics",
        topic="arithmetic_mean",
        difficulty="foundation",
        formula_id="arithmetic_mean_four",
        inputs={f"value_{position}": value for position, value in enumerate(values)},
    )


def _triangle_area(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "triangle_area")
    settings = (
        "fabric pennant",
        "roof brace",
        "survey plot",
        "metal sign",
        "cardboard model",
        "garden bed",
    )
    town_index = r.randrange(len(TOWNS))
    setting_index = r.randrange(len(settings))
    town = TOWNS[town_index]
    setting = settings[setting_index]
    base = r.randint(3, 120)
    height = r.randint(2, 100)
    area = Fraction(base * height, 2)
    answer = f"{_fraction(area)} cm²"
    return Problem(
        problem=(
            f"A triangular {setting} in {town} has base {base} cm and perpendicular height "
            f"{height} cm. Find its area."
        ),
        answer=answer,
        steps=(
            "Area of a triangle = 1/2 × base × perpendicular height.",
            f"Area = 1/2 × {base} × {height} = {answer}.",
        ),
        self_check=f"Two copies form a {base} cm by {height} cm parallelogram of area {base * height} cm².",
        wrong_answer=f"{base * height} cm²",
        misconception="A triangle occupies half the area of a parallelogram with the same base and height.",
        misconception_type="triangle_half_factor_omitted",
        subject="mathematics",
        topic="area_of_triangle",
        difficulty="foundation",
        formula_id="triangle_area",
        inputs={
            "base": base,
            "height": height,
            "town_index": town_index,
            "setting_index": setting_index,
        },
    )


def _pythagoras(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "pythagoras")
    name_index = r.randrange(len(NAMES))
    town_index = r.randrange(len(TOWNS))
    name = NAMES[name_index]
    town = TOWNS[town_index]
    m = r.randint(2, 10)
    n = r.randint(1, m - 1)
    scale = r.randint(1, 5)
    first_leg = (m * m - n * n) * scale
    second_leg = 2 * m * n * scale
    hypotenuse = (m * m + n * n) * scale
    if r.choice((False, True)):
        first_leg, second_leg = second_leg, first_leg
    answer = f"{hypotenuse} cm"
    return Problem(
        problem=(
            f"In a geometry lesson in {town}, {name} draws a right-angled triangle with "
            f"perpendicular sides {first_leg} cm and {second_leg} cm. Find the hypotenuse."
        ),
        answer=answer,
        steps=(
            "By Pythagoras' theorem, c² = a² + b².",
            f"c² = {first_leg}² + {second_leg}² = {hypotenuse * hypotenuse}.",
            f"c = √{hypotenuse * hypotenuse} = {answer}.",
        ),
        self_check=f"{first_leg}² + {second_leg}² = {hypotenuse}².",
        wrong_answer=f"{first_leg + second_leg} cm",
        misconception="Side lengths are squared and added before taking the square root; the legs are not added directly.",
        misconception_type="pythagorean_legs_added_directly",
        subject="mathematics",
        topic="pythagoras_theorem",
        difficulty="standard",
        formula_id="pythagorean_hypotenuse",
        inputs={
            "first_leg": first_leg,
            "second_leg": second_leg,
            "name_index": name_index,
            "town_index": town_index,
        },
    )


def _percentage_increase(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "percentage_increase")
    name_index = r.randrange(len(NAMES))
    name = NAMES[name_index]
    original = r.randint(2, 120) * 100
    rate = r.randint(2, 60)
    increase = Fraction(original * rate, 100)
    final = Fraction(original) + increase
    answer = _fraction(final)
    return Problem(
        problem=(
            f"{name} records a quantity of {original}. It then increases by {rate}%. "
            "Find its new value."
        ),
        answer=answer,
        steps=(
            f"Increase = {rate}/100 × {original} = {_fraction(increase)}.",
            f"New value = {original} + {_fraction(increase)} = {answer}.",
        ),
        self_check=(
            f"New value - original = {answer} - {original} = {_fraction(increase)}, "
            "the calculated increase."
        ),
        wrong_answer=_fraction(increase),
        misconception="The percentage calculation gives only the increase; add it to the original value.",
        misconception_type="increase_amount_used_as_final_value",
        subject="mathematics",
        topic="percentage_change",
        difficulty="standard",
        formula_id="percentage_increase",
        inputs={"original": original, "rate": rate, "name_index": name_index},
    )


def _kinetic_energy(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "kinetic_energy")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    mass = r.randint(2, 120)
    speed = r.randint(2, 35)
    energy = Fraction(mass * speed * speed, 2)
    answer = f"{_fraction(energy)} J"
    return Problem(
        problem=(
            f"During a mechanics exercise in {town}, a {mass} kg object moves at {speed} m/s. "
            "Calculate its kinetic energy."
        ),
        answer=answer,
        steps=(
            "Kinetic energy Eₖ = 1/2 mv².",
            f"Eₖ = 1/2 × {mass} × {speed}² = {answer}.",
        ),
        self_check=(f"2Eₖ/m = 2 × {_fraction(energy)} ÷ {mass} = {speed * speed} = {speed}²."),
        wrong_answer=f"{mass * speed * speed} J",
        misconception="The kinetic-energy formula includes the factor 1/2.",
        misconception_type="kinetic_energy_half_factor_omitted",
        subject="physics",
        topic="kinetic_energy",
        difficulty="standard",
        formula_id="kinetic_energy",
        inputs={"mass": mass, "speed": speed, "town_index": town_index},
    )


def _electrical_power(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "electrical_power")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    voltage = r.randint(3, 240)
    current = r.randint(2, 20)
    power = voltage * current
    answer = f"{power} W"
    return Problem(
        problem=(
            f"A device being tested in {town} operates at {voltage} V and draws {current} A. "
            "Calculate its electrical power."
        ),
        answer=answer,
        steps=("Electrical power P = VI.", f"P = {voltage} × {current} = {answer}."),
        self_check=f"P/V = {power}/{voltage} = {current} A, the stated current.",
        wrong_answer=f"{_fraction(Fraction(voltage, current))} W",
        misconception="Electrical power is voltage multiplied by current, not voltage divided by current.",
        misconception_type="power_divided_instead_of_multiplied",
        subject="physics",
        topic="electrical_power",
        difficulty="standard",
        formula_id="electrical_power",
        inputs={"voltage": voltage, "current": current, "town_index": town_index},
    )


def _pressure(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "pressure")
    area = r.randint(2, 30)
    pressure = r.randint(20, 800)
    force = area * pressure
    answer = f"{pressure} Pa"
    return Problem(
        problem=f"A force of {force} N acts uniformly over an area of {area} m². Calculate the pressure.",
        answer=answer,
        steps=("Pressure = force ÷ area.", f"Pressure = {force} ÷ {area} = {answer}."),
        self_check=f"{pressure} Pa × {area} m² = {force} N.",
        wrong_answer=f"{force * area} Pa",
        misconception="Pressure is force per unit area, so force must be divided by area.",
        misconception_type="pressure_multiplied_by_area",
        subject="physics",
        topic="pressure",
        difficulty="standard",
        formula_id="pressure",
        inputs={"force": force, "area": area},
    )


def _work_done(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "work_done")
    force = r.randint(2, 500)
    distance = r.randint(2, 80)
    if force == 2 and distance == 2:
        distance = 3
    work = force * distance
    answer = f"{work} J"
    return Problem(
        problem=f"A constant force of {force} N moves an object {distance} m in the force's direction. Find the work done.",
        answer=answer,
        steps=(
            "Work done W = force × distance in the force's direction.",
            f"W = {force} × {distance} = {answer}.",
        ),
        self_check=f"W/d = {work}/{distance} = {force} N, the stated force.",
        wrong_answer=f"{force + distance} J",
        misconception="Work is the product of force and displacement in the force's direction, not their sum.",
        misconception_type="work_added_instead_of_multiplied",
        subject="physics",
        topic="work_done",
        difficulty="foundation",
        formula_id="work_done",
        inputs={"force": force, "distance": distance},
    )


def _gas_volume(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "gas_volume")
    gas_index = r.randrange(len(GASES))
    town_index = r.randrange(len(TOWNS))
    gas = GASES[gas_index]
    town = TOWNS[town_index]
    amount_tenths = r.randint(1, 100)
    amount = Fraction(amount_tenths, 10)
    volume = amount * 24
    answer = f"{_fraction(volume)} dm³"
    return Problem(
        problem=(
            f"A laboratory in {town} has {_fraction(amount)} mol of {gas} at room temperature "
            "and pressure, where one mole of gas occupies 24 dm³. Find its volume."
        ),
        answer=answer,
        steps=(
            "Gas volume = amount × molar volume.",
            f"Volume = {_fraction(amount)} × 24 = {answer}.",
        ),
        self_check=f"Dividing {_fraction(volume)} dm³ by 24 dm³/mol gives {_fraction(amount)} mol.",
        wrong_answer=f"{_fraction(amount + 24)} dm³",
        misconception="Amount and molar volume must be multiplied, not added.",
        misconception_type="molar_volume_added_to_amount",
        subject="chemistry",
        topic="molar_gas_volume",
        difficulty="standard",
        formula_id="molar_gas_volume",
        inputs={
            "amount_tenths": amount_tenths,
            "gas_index": gas_index,
            "town_index": town_index,
        },
    )


def _stoichiometry(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "stoichiometry")
    reaction_index = r.randrange(len(STOICHIOMETRY_REACTIONS))
    town_index = r.randrange(len(TOWNS))
    equation, reactant, reactant_coefficient, product, product_coefficient = (
        STOICHIOMETRY_REACTIONS[reaction_index]
    )
    units = r.randint(1, 100)
    reactant_amount = Fraction(reactant_coefficient * units, 10)
    product_amount = Fraction(product_coefficient * units, 10)
    answer = f"{_fraction(product_amount)} mol {product}"
    return Problem(
        problem=(
            f"In a chemistry class in {TOWNS[town_index]}, use {equation}. How many moles of "
            f"{product} form from {_fraction(reactant_amount)} mol {reactant} when every other "
            "reactant is in excess?"
        ),
        answer=answer,
        steps=(
            (
                f"The balanced equation gives the ratio {reactant_coefficient} mol "
                f"{reactant} : {product_coefficient} mol {product}."
            ),
            (
                f"Product = {_fraction(reactant_amount)} × {product_coefficient}/"
                f"{reactant_coefficient} = {answer}."
            ),
        ),
        self_check=(
            f"{_fraction(product_amount)} ÷ {_fraction(reactant_amount)} = "
            f"{product_coefficient}/{reactant_coefficient}, matching the coefficient ratio."
        ),
        wrong_answer=f"{_fraction(reactant_amount)} mol {product}",
        misconception=(
            "The product amount must be scaled by the balanced-equation coefficient ratio; "
            "copying the reactant amount ignores that ratio."
        ),
        misconception_type="stoichiometric_coefficient_ignored",
        subject="chemistry",
        topic="stoichiometry",
        difficulty="standard",
        formula_id="stoichiometric_mole_ratio",
        inputs={
            "reaction_index": reaction_index,
            "stoichiometric_units": units,
            "town_index": town_index,
        },
    )


def _mass_percentage(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "mass_percentage")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    total_mass = r.randint(1, 50) * 100
    percentage = r.randint(5, 40)
    solute_mass = total_mass * percentage // 100
    solvent_mass = total_mass - solute_mass
    answer = f"{percentage:.1f}%"
    wrong = Fraction(solute_mass, solvent_mass) * 100
    return Problem(
        problem=(
            f"A solution prepared in {town} contains {solute_mass} g of solute and "
            f"{solvent_mass} g of solvent. Calculate the percentage by mass of solute "
            "to one decimal place."
        ),
        answer=answer,
        steps=(
            f"Total mass of solution = {solute_mass} + {solvent_mass} = {total_mass} g.",
            f"Percentage by mass = {solute_mass}/{total_mass} × 100 = {answer}.",
        ),
        self_check=f"{percentage:.1f}% of {total_mass} g is {solute_mass} g.",
        wrong_answer=_percent(wrong),
        misconception="Percentage by mass uses the total mass of solution, not only the solvent mass, as the denominator.",
        misconception_type="solvent_mass_used_as_denominator",
        subject="chemistry",
        topic="percentage_composition",
        difficulty="standard",
        formula_id="mass_percentage",
        inputs={
            "solute_mass": solute_mass,
            "total_mass": total_mass,
            "town_index": town_index,
        },
    )


def _neutralization(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "neutralization")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    acid_tenths = r.randint(1, 20)
    base_tenths = r.choice(tuple(value for value in range(1, 21) if value != acid_tenths))
    acid_concentration = Fraction(acid_tenths, 10)
    base_concentration = Fraction(base_tenths, 10)
    scale = r.randint(5, 15)
    acid_volume = base_tenths * scale
    base_volume = acid_tenths * scale
    answer = f"{base_volume} cm³"
    return Problem(
        problem=(
            f"In a titration in {town}, HCl reacts with NaOH in a 1:1 mole ratio. What volume of "
            f"{_fraction(base_concentration)} mol/dm³ NaOH neutralizes {acid_volume} cm³ "
            f"of {_fraction(acid_concentration)} mol/dm³ HCl?"
        ),
        answer=answer,
        steps=(
            "For this 1:1 reaction, C₁V₁ = C₂V₂ when both volumes use the same unit.",
            (
                f"NaOH volume = {_fraction(acid_concentration)} × {acid_volume} ÷ "
                f"{_fraction(base_concentration)} = {answer}."
            ),
        ),
        self_check=(
            f"{_fraction(acid_concentration)} × {acid_volume} = "
            f"{_fraction(base_concentration)} × {base_volume}."
        ),
        wrong_answer=f"{acid_volume} cm³",
        misconception="Equal reacting mole amounts do not imply equal volumes when the concentrations differ.",
        misconception_type="equal_moles_assumed_equal_volumes",
        subject="chemistry",
        topic="acid_base_neutralization",
        difficulty="advanced",
        formula_id="neutralization_volume",
        inputs={
            "acid_concentration_tenths": acid_tenths,
            "acid_volume": acid_volume,
            "base_concentration_tenths": base_tenths,
            "town_index": town_index,
        },
    )


def _germination(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "germination")
    crops = ("maize", "cowpea", "rice", "tomato", "okra", "groundnut", "sorghum", "millet")
    conditions = ("moist cotton wool", "topsoil", "sand", "compost")
    town_index = r.randrange(len(TOWNS))
    crop_index = r.randrange(len(crops))
    condition_index = r.randrange(len(conditions))
    town = TOWNS[town_index]
    total = r.randint(5, 30) * 100
    percentage = r.randint(51, 99)
    germinated = total * percentage // 100
    answer = f"{percentage:.1f}%"
    return Problem(
        problem=(
            f"In a {crops[crop_index]} seed test using {conditions[condition_index]} in {town}, "
            f"{germinated} of {total} seeds germinate. Calculate the germination percentage "
            "to one decimal place."
        ),
        answer=answer,
        steps=(
            "Germination percentage = germinated ÷ total × 100.",
            f"Percentage = {germinated}/{total} × 100 = {answer}.",
        ),
        self_check=f"{percentage:.1f}% of {total} is {germinated}.",
        wrong_answer=f"{100 - percentage:.1f}%",
        misconception="The question asks for seeds that germinated, not the complementary percentage that failed to germinate.",
        misconception_type="complement_percentage_reported",
        subject="biology",
        topic="seed_germination",
        difficulty="foundation",
        formula_id="germination_percentage",
        inputs={
            "germinated": germinated,
            "total": total,
            "town_index": town_index,
            "crop_index": crop_index,
            "condition_index": condition_index,
        },
    )


def _pulse_rate(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "pulse_rate")
    measurement_contexts = (
        "during a resting measurement",
        "after a short walk",
        "after light exercise",
        "during recovery after exercise",
    )
    name_index = r.randrange(len(NAMES))
    town_index = r.randrange(len(TOWNS))
    context_index = r.randrange(len(measurement_contexts))
    name = NAMES[name_index]
    town = TOWNS[town_index]
    seconds = r.choice((10, 12, 15, 20, 30))
    possible_rates = tuple(rate for rate in range(48, 141) if rate * seconds % 60 == 0)
    rate = r.choice(possible_rates)
    beats = rate * seconds // 60
    answer = f"{rate} beats/min"
    return Problem(
        problem=(
            f"During a health lesson in {town}, {name} counts {beats} pulse beats "
            f"{measurement_contexts[context_index]} in "
            f"{seconds} seconds. Calculate the pulse rate in beats per minute."
        ),
        answer=answer,
        steps=(
            "Pulse rate = counted beats ÷ time in seconds × 60.",
            f"Rate = {beats}/{seconds} × 60 = {answer}.",
        ),
        self_check=f"{rate} beats/min × {seconds}/60 min = {beats} beats.",
        wrong_answer=f"{beats} beats/min",
        misconception="A short-interval count must be scaled to a full minute.",
        misconception_type="pulse_count_not_scaled_to_minute",
        subject="biology",
        topic="pulse_rate",
        difficulty="foundation",
        formula_id="pulse_rate",
        inputs={
            "beats": beats,
            "seconds": seconds,
            "name_index": name_index,
            "town_index": town_index,
            "context_index": context_index,
        },
    )


def _energy_efficiency(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "energy_efficiency")
    efficiency = r.choice(tuple(value for value in range(20, 91) if value != 50))
    input_energy = r.randint(10, 500) * 100
    useful_energy = input_energy * efficiency // 100
    answer = f"{efficiency:.1f}%"
    return Problem(
        problem=f"A machine receives {input_energy} J and transfers {useful_energy} J usefully. Calculate its efficiency to one decimal place.",
        answer=answer,
        steps=(
            "Efficiency = useful output energy ÷ input energy × 100.",
            f"Efficiency = {useful_energy}/{input_energy} × 100 = {answer}.",
        ),
        self_check=(
            f"{efficiency:.1f}% of {input_energy} J = {useful_energy} J, the stated useful output."
        ),
        wrong_answer=f"{100 - efficiency:.1f}%",
        misconception="Energy lost to the surroundings is the complement, not the machine's useful efficiency.",
        misconception_type="energy_loss_reported_as_efficiency",
        subject="integrated_science",
        topic="energy_efficiency",
        difficulty="standard",
        formula_id="energy_efficiency",
        inputs={"useful_energy": useful_energy, "input_energy": input_energy},
    )


def _water_tank_volume(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "water_tank_volume")
    town_index = r.randrange(len(TOWNS))
    town = TOWNS[town_index]
    length = r.randrange(40, 301, 10)
    width = r.randrange(30, 201, 10)
    height = r.randrange(20, 151, 10)
    cubic_centimetres = length * width * height
    litres = Fraction(cubic_centimetres, 1000)
    answer = f"{_fraction(litres)} L"
    return Problem(
        problem=(
            f"A rectangular water tank in {town} measures {length} cm by {width} cm by "
            f"{height} cm. Find its capacity in litres."
        ),
        answer=answer,
        steps=(
            f"Volume = {length} × {width} × {height} = {cubic_centimetres} cm³.",
            f"Capacity = {cubic_centimetres} ÷ 1000 = {answer}, since 1000 cm³ = 1 L.",
        ),
        self_check=f"{_fraction(litres)} L × 1000 = {cubic_centimetres} cm³.",
        wrong_answer=f"{cubic_centimetres} L",
        misconception="Cubic centimetres must be converted to litres by dividing by 1000.",
        misconception_type="cubic_centimetres_labelled_as_litres",
        subject="integrated_science",
        topic="water_storage_volume",
        difficulty="standard",
        formula_id="rectangular_tank_litres",
        inputs={
            "length": length,
            "width": width,
            "height": height,
            "town_index": town_index,
        },
    )


def _temperature_conversion(index: int, seed: int) -> Problem:
    r = _rng(seed, index, "temperature_conversion")
    name_index = r.randrange(len(NAMES))
    town_index = r.randrange(len(TOWNS))
    setting_index = r.randrange(len(TEMPERATURE_SETTINGS))
    name = NAMES[name_index]
    town = TOWNS[town_index]
    setting = TEMPERATURE_SETTINGS[setting_index]
    celsius = r.randint(15, 45)
    fahrenheit = Fraction(9 * celsius, 5) + 32
    answer = f"{_fixed(fahrenheit, 1)} °F"
    return Problem(
        problem=(
            f"{name} reads {celsius} °C on a {setting} in {town}. Convert this temperature "
            "to degrees Fahrenheit to one decimal place."
        ),
        answer=answer,
        steps=("Use F = 9C/5 + 32.", f"F = 9({celsius})/5 + 32 = {answer}."),
        self_check=f"Converting back gives C = 5(F - 32)/9 = {celsius} °C.",
        wrong_answer=f"{celsius + 32:.1f} °F",
        misconception="The Celsius value must be multiplied by 9/5 before adding 32.",
        misconception_type="temperature_scale_factor_omitted",
        subject="integrated_science",
        topic="temperature_conversion",
        difficulty="standard",
        formula_id="celsius_to_fahrenheit",
        inputs={
            "celsius": celsius,
            "name_index": name_index,
            "town_index": town_index,
            "setting_index": setting_index,
        },
    )


QUARANTINED_GENERATORS: tuple[Callable[[int, int], Problem], ...] = (
    # These families were designed after seeing evaluation prompts with
    # the same semantic structure. Lexical n-gram screening cannot make them
    # safe training data, so they remain executable only for audit evidence.
    _profit,
    _average_speed,
    _ratio,
    _probability,
    _interest,
)

GENERATORS: tuple[Callable[[int, int], Problem], ...] = (
    _linear,
    _simultaneous,
    _sequence,
    _force,
    _density,
    _ohm,
    _wave,
    _moles,
    _concentration,
    _dilution,
    _magnification,
    _population_density,
    _inheritance,
    _mean,
    _triangle_area,
    _pythagoras,
    _percentage_increase,
    _kinetic_energy,
    _electrical_power,
    _pressure,
    _work_done,
    _gas_volume,
    _stoichiometry,
    _mass_percentage,
    _neutralization,
    _germination,
    _pulse_rate,
    _energy_efficiency,
    _water_tank_volume,
    _temperature_conversion,
)


def _matches_sealed_numeric_core(problem: Problem) -> bool:
    """Block exact parameter cores from sealed evaluation prompts.

    Lexical overlap alone misses paraphrases and reverse-unknown variants.  The
    small explicit list below is intentionally conservative and auditable: it
    records operation-family inputs observed in local acceptance suites, not
    broad curricular concepts.
    """

    values = problem.inputs
    if problem.formula_id == "simple_interest":
        return (
            values.get("principal"),
            values.get("rate"),
            values.get("years"),
        ) == (10_000, 5, 2)
    if problem.formula_id == "pythagorean_hypotenuse":
        return tuple(sorted((values["first_leg"], values["second_leg"]))) == (6, 8)
    if problem.formula_id == "ohm_voltage":
        voltage = values["current"] * values["resistance"]
        return (voltage, values["resistance"], values["current"]) == (6, 3, 2)
    if problem.formula_id == "arithmetic_sequence":
        first = values["first"]
        difference = values["difference"]
        return (first, first + difference, first + 2 * difference) == (5, 8, 11)
    if problem.formula_id == "linear_equation":
        return (values["coefficient"], values["offset"], values["rhs"]) == (3, 5, 20)
    return False


PEDAGOGIES = (
    "worked_solution",
    "worked_solution",
    "worked_solution",
    "worked_solution",
    "exam_marking_scheme",
    "exam_marking_scheme",
    "misconception_correction",
    "misconception_correction",
    "socratic_hint",
    "concise_answer",
)


SOCRATIC_SCAFFOLDS: dict[str, tuple[str, str]] = {
    "linear_equation": (
        "Which inverse operation should undo the constant term before you undo the coefficient of x?",
        "Isolate the x-term first, then divide both sides by its coefficient; pause before carrying out the last arithmetic step.",
    ),
    "simultaneous_equations": (
        "How could you combine the two equations so that one variable disappears?",
        "Choose x or y, scale the equations to give that variable opposite coefficients, and write the resulting one-variable equation without solving it yet.",
    ),
    "arithmetic_sequence": (
        "How many equal jumps separate the first term from the requested term?",
        "Identify the common difference and set up aₙ = a₁ + (n − 1)d; leave the final substitution unevaluated.",
    ),
    "force": (
        "Which relationship connects force, mass, and acceleration?",
        "Start with F = ma, check that mass is in kilograms and acceleration in m/s², then set up the product.",
    ),
    "density": (
        "Is density found by sharing mass over volume or volume over mass?",
        "Write ρ = m/V with matching mass and volume units, and substitute without completing the division.",
    ),
    "ohm_voltage": (
        "Which form of Ohm's law has voltage as the subject?",
        "Use V = IR, confirm amperes and ohms are given, and set up their product without evaluating it.",
    ),
    "wave_speed": (
        "How are wave speed, frequency, and wavelength related?",
        "Write v = fλ, check that hertz and metres are compatible, and substitute without multiplying yet.",
    ),
    "moles": (
        "What must mass be divided by to convert it to amount in moles?",
        "Use n = m/M after checking both masses use grams; set up the quotient and stop before evaluating it.",
    ),
    "concentration": (
        "What volume unit must be used with concentration in mol/dm³?",
        "Convert cm³ to dm³ first, then set up c = n/V without performing the final division.",
    ),
    "dilution": (
        "What quantity of solute stays unchanged when only solvent is added?",
        "Use C₁V₁ = C₂V₂ and rearrange for C₂, leaving the supplied values as an unevaluated expression.",
    ),
    "magnification": (
        "Which size belongs in the numerator of the magnification ratio?",
        "Put image size over actual size, first confirming that both measurements use the same unit; stop before dividing.",
    ),
    "population_density": (
        "What does 'per square metre' tell you to do with the sampled area?",
        "Set up population density as number counted divided by sampled area, and keep the quotient unevaluated.",
    ),
    "recessive_cross": (
        "Which gametes can each Aa parent contribute, and which Punnett-square cells give aa?",
        "Label a 2 × 2 Punnett square with A and a for each parent, fill the cells, and count the target genotype yourself.",
    ),
    "arithmetic_mean_four": (
        "What two operations define the arithmetic mean of a list?",
        "Add all four observations, then write that total divided by four without evaluating the quotient.",
    ),
    "triangle_area": (
        "Which two perpendicular measurements determine a triangle's area?",
        "Use A = ½bh with the base and perpendicular height, and leave the product unevaluated.",
    ),
    "pythagorean_hypotenuse": (
        "Which side is opposite the right angle, and how does Pythagoras relate it to the legs?",
        "Set up c² = a² + b² with the two perpendicular sides, but do not take the final square root yet.",
    ),
    "percentage_increase": (
        "Should the percentage increase be calculated from the original value or the new value?",
        "Write increase = original × rate/100, then plan to add that increase to the original; stop before calculating.",
    ),
    "kinetic_energy": (
        "In the kinetic-energy formula, which quantity is squared?",
        "Use Eₖ = ½mv², check kilograms and metres per second, and set up the expression without evaluating it.",
    ),
    "electrical_power": (
        "Which electrical relationship combines voltage and current to give power?",
        "Write P = VI with volts and amperes, then substitute and stop before multiplying.",
    ),
    "pressure": (
        "Does the same force create more pressure over a larger area or a smaller area?",
        "Use P = F/A in newtons per square metre, and leave the division unevaluated.",
    ),
    "work_done": (
        "Which component of displacement matters when a force does work?",
        "Here force and motion are aligned, so set up W = Fd in joules without completing the multiplication.",
    ),
    "molar_gas_volume": (
        "At room conditions, what volume is assigned to one mole of gas in this problem?",
        "Multiply the amount in moles by the stated molar gas volume, but leave the product unevaluated.",
    ),
    "stoichiometric_mole_ratio": (
        "Which coefficients in the balanced equation connect the named reactant and product?",
        "Form product amount = reactant amount × product coefficient/reactant coefficient, then stop before simplifying.",
    ),
    "mass_percentage": (
        "What total mass belongs in the denominator of percentage by mass of solute?",
        "Add solute and solvent to get solution mass, then set up solute mass/solution mass × 100 without evaluating it.",
    ),
    "neutralization_volume": (
        "For this 1:1 reaction, what equality relates acid and base concentration-volume products?",
        "Write CₐVₐ = CᵦVᵦ, rearrange for the unknown volume, and leave the numerical quotient unevaluated.",
    ),
    "germination_percentage": (
        "Which count is the whole when finding the germination percentage?",
        "Set up germinated seeds divided by total seeds, multiplied by 100; do not evaluate it yet.",
    ),
    "pulse_rate": (
        "How can a count made over part of a minute be scaled to one full minute?",
        "Set up beats × 60/measurement seconds and stop before simplifying.",
    ),
    "energy_efficiency": (
        "Which energy is the useful output and which is the total input?",
        "Write efficiency = useful output/input × 100%, substitute the two energies, and leave it unevaluated.",
    ),
    "rectangular_tank_litres": (
        "What solid-volume formula gives the tank's capacity before converting units?",
        "Set up length × width × height in cm³, then plan to divide by 1000 to obtain litres; stop before calculating.",
    ),
    "celsius_to_fahrenheit": (
        "Which scale factor and offset convert a Celsius reading to Fahrenheit?",
        "Use F = (9/5)C + 32, substitute the Celsius value, and leave the expression unevaluated.",
    ),
}


def _socratic_scaffold(problem: Problem) -> tuple[str, str]:
    try:
        return SOCRATIC_SCAFFOLDS[problem.formula_id]
    except KeyError as exc:
        raise ValueError(f"missing Socratic scaffold for {problem.formula_id}") from exc


SOCRATIC_QUESTION_FRAMES = (
    "{question}",
    "Before doing arithmetic, {question_lower}",
    "Focus on the setup first: {question}",
    "To choose the first justified step, {question_lower}",
)
SOCRATIC_HINT_FRAMES = (
    "{hint}",
    "A useful route is this: {hint}",
    "Build only the setup for now: {hint}",
    "Keep the final arithmetic for later: {hint}",
)
SOCRATIC_TURN_PROMPTS = (
    "Your turn: Write that setup for the given information and tell me your next step.",
    "Your turn: Show me the unevaluated expression you would use, then pause.",
    "Your turn: State the relationship and substitute only what the problem gives.",
    "Your turn: What would you write on the next line before calculating?",
)


def _render_socratic(problem: Problem) -> str:
    question, hint = _socratic_scaffold(problem)
    digest = hashlib.sha256(problem.problem.encode("utf-8")).digest()
    question_frame = SOCRATIC_QUESTION_FRAMES[digest[0] % len(SOCRATIC_QUESTION_FRAMES)]
    hint_frame = SOCRATIC_HINT_FRAMES[digest[1] % len(SOCRATIC_HINT_FRAMES)]
    turn = SOCRATIC_TURN_PROMPTS[digest[2] % len(SOCRATIC_TURN_PROMPTS)]
    return "\n".join(
        [
            "Guiding question: "
            + question_frame.format(
                question=question,
                question_lower=question[0].lower() + question[1:],
            ),
            "Hint: " + hint_frame.format(hint=hint),
            turn,
        ]
    )


def _render(problem: Problem, pedagogy: str) -> tuple[str, str, str]:
    if pedagogy == "worked_solution":
        prompt = problem.problem + " Show clear working and finish with a self-check."
        completion = "\n".join(
            [
                *(f"{i}. {step}" for i, step in enumerate(problem.steps, 1)),
                f"Final answer: {problem.answer}.",
                f"Self-check: {problem.self_check}",
            ]
        )
        return prompt, completion, "free_response"
    if pedagogy == "exam_marking_scheme":
        prompt = (
            problem.problem
            + " Write a compact examination solution using a Muta practice marking guide "
            "(not an official examiner marking scheme), and show where method and answer marks are earned."
        )
        method_steps = problem.steps[:-1]
        marks = [f"M{i} (method): {step}" for i, step in enumerate(method_steps, 1)]
        accuracy_work = f"A1 (accuracy working): {problem.steps[-1]}"
        check = problem.self_check.removeprefix("Check:").strip()
        completion = "\n".join(
            [*marks, accuracy_work, f"A2 (reported answer): {problem.answer}.", f"Check: {check}"]
        )
        return prompt, completion, "free_response"
    if pedagogy == "misconception_correction":
        prompt = (
            problem.problem
            + f"\nA learner wrote: '{problem.wrong_answer}'. Identify the first mistake, correct it step by step, and explain how to avoid it."
        )
        completion = "\n".join(
            [
                f"First mistake: {problem.misconception}",
                *(f"{i}. {step}" for i, step in enumerate(problem.steps, 1)),
                f"Final answer: {problem.answer}.",
                f"Future check: {problem.self_check}",
            ]
        )
        return prompt, completion, "misconception"
    if pedagogy == "socratic_hint":
        prompt = (
            problem.problem
            + " Tutor me without giving the final answer. Ask one guiding question, give one "
            "next-step hint, and then stop so I can respond."
        )
        completion = _render_socratic(problem)
        return prompt, completion, "socratic"
    if pedagogy == "concise_answer":
        prompt = problem.problem + " Give the result with one essential calculation."
        essential = (
            " ".join(problem.steps[1:])
            if problem.formula_id == "simultaneous_equations"
            else problem.steps[-1]
        )
        completion = f"{essential} Final answer: {problem.answer}."
        return prompt, completion, "free_response"
    raise ValueError(f"unknown pedagogy: {pedagogy}")


def _symbol_from_index(index: int) -> str:
    return CURRENCIES[index][0]


def recompute_answer(formula_id: str, values: dict[str, int]) -> str:
    if formula_id == "profit_two_prices":
        q = values["quantity"]
        first = values["first"]
        remainder = q - first
        cost_price = values["cost_price"]
        first_price = Fraction(cost_price * (100 + values["markup"]), 100)
        second_price = first_price * Fraction(100 - values["discount"], 100)
        cost = Fraction(q * cost_price)
        revenue = first * first_price + remainder * second_price
        profit = revenue - cost
        symbol = _symbol_from_index(values["currency_index"])
        return f"revenue {_money(symbol, revenue)}, profit {_money(symbol, profit)}, profit percentage {_percent(profit / cost * 100)}"
    if formula_id == "equal_distance_average_speed":
        leg, slow, fast = values["leg"], values["slow"], values["fast"]
        average = Fraction(2 * leg, 1) / (Fraction(leg, slow) + Fraction(leg, fast))
        return f"{_fixed(average, 2)} km/h"
    if formula_id == "linear_equation":
        result = Fraction(values["rhs"] - values["offset"], values["coefficient"])
        return f"x = {_fraction(result)}"
    if formula_id == "ratio_share":
        unit = Fraction(values["total"], values["first_ratio"] + values["second_ratio"])
        return _fraction(values["second_ratio"] * unit)
    if formula_id == "simple_interest":
        interest = Fraction(values["principal"] * values["rate"] * values["years"], 100)
        symbol = _symbol_from_index(values["currency_index"])
        return f"interest {_money(symbol, interest)}, amount {_money(symbol, Fraction(values['principal']) + interest)}"
    if formula_id == "simultaneous_equations":
        a, b, c, d = values["a"], values["b"], values["c"], values["d"]
        determinant = a * d - b * c
        x = Fraction(values["first"] * d - b * values["second"], determinant)
        y = Fraction(a * values["second"] - values["first"] * c, determinant)
        return f"x = {_fraction(x)}, y = {_fraction(y)}"
    if formula_id == "arithmetic_sequence":
        return str(values["first"] + (values["n"] - 1) * values["difference"])
    if formula_id == "single_draw_probability":
        result = Fraction(values["red"], values["red"] + values["blue"] + values["green"])
        return f"{result.numerator}/{result.denominator}"
    if formula_id == "force":
        return f"{values['mass'] * values['acceleration']} N"
    if formula_id == "density":
        return f"{_fraction(Fraction(values['mass'], values['volume']))} g/cm³"
    if formula_id == "ohm_voltage":
        return f"{values['current'] * values['resistance']} V"
    if formula_id == "wave_speed":
        return f"{values['frequency'] * values['wavelength']} m/s"
    if formula_id == "moles":
        mass = Fraction(values["mass_numerator"], values["mass_denominator"])
        return f"{_fraction(mass / values['molar_mass'])} mol"
    if formula_id == "concentration":
        moles = Fraction(values["moles_numerator"], values["moles_denominator"])
        result = moles / Fraction(values["volume_cm3"], 1000)
        return f"{_fraction(result)} mol/dm³"
    if formula_id == "dilution":
        result = Fraction(
            values["initial_concentration"] * values["initial_volume"], values["final_volume"]
        )
        return f"{_fixed(result, 2)} mol/dm³"
    if formula_id == "magnification":
        return f"{_fraction(Fraction(values['image'], values['actual']))}×"
    if formula_id == "population_density":
        return f"{_fraction(Fraction(values['organisms'], values['area']))} organisms/m²"
    if formula_id == "recessive_cross":
        expected = Fraction(values["children"], 4)
        return f"25%, about {_fraction(expected)} of {values['children']} offspring"
    if formula_id == "arithmetic_mean_four":
        total = sum(values[f"value_{position}"] for position in range(4))
        return _fraction(Fraction(total, 4))
    if formula_id == "triangle_area":
        area = Fraction(values["base"] * values["height"], 2)
        return f"{_fraction(area)} cm²"
    if formula_id == "pythagorean_hypotenuse":
        squared = values["first_leg"] ** 2 + values["second_leg"] ** 2
        hypotenuse = math.isqrt(squared)
        if hypotenuse * hypotenuse != squared:
            raise ValueError("pythagorean_hypotenuse inputs do not form an exact right triangle")
        return f"{hypotenuse} cm"
    if formula_id == "percentage_increase":
        increase = Fraction(values["original"] * values["rate"], 100)
        return _fraction(Fraction(values["original"]) + increase)
    if formula_id == "kinetic_energy":
        energy = Fraction(values["mass"] * values["speed"] ** 2, 2)
        return f"{_fraction(energy)} J"
    if formula_id == "electrical_power":
        return f"{values['voltage'] * values['current']} W"
    if formula_id == "pressure":
        pressure = Fraction(values["force"], values["area"])
        return f"{_fraction(pressure)} Pa"
    if formula_id == "work_done":
        return f"{values['force'] * values['distance']} J"
    if formula_id == "molar_gas_volume":
        amount = Fraction(values["amount_tenths"], 10)
        return f"{_fraction(amount * 24)} dm³"
    if formula_id == "stoichiometric_mole_ratio":
        reaction = STOICHIOMETRY_REACTIONS[values["reaction_index"]]
        _, _, _, product, product_coefficient = reaction
        product_amount = Fraction(product_coefficient * values["stoichiometric_units"], 10)
        return f"{_fraction(product_amount)} mol {product}"
    if formula_id == "mass_percentage":
        percentage = Fraction(values["solute_mass"], values["total_mass"]) * 100
        return _percent(percentage)
    if formula_id == "neutralization_volume":
        result = Fraction(
            values["acid_concentration_tenths"] * values["acid_volume"],
            values["base_concentration_tenths"],
        )
        return f"{_fraction(result)} cm³"
    if formula_id == "germination_percentage":
        percentage = Fraction(values["germinated"], values["total"]) * 100
        return _percent(percentage)
    if formula_id == "pulse_rate":
        rate = Fraction(values["beats"] * 60, values["seconds"])
        return f"{_fraction(rate)} beats/min"
    if formula_id == "energy_efficiency":
        efficiency = Fraction(values["useful_energy"], values["input_energy"]) * 100
        return _percent(efficiency)
    if formula_id == "rectangular_tank_litres":
        litres = Fraction(values["length"] * values["width"] * values["height"], 1000)
        return f"{_fraction(litres)} L"
    if formula_id == "celsius_to_fahrenheit":
        fahrenheit = Fraction(9 * values["celsius"], 5) + 32
        return f"{_fixed(fahrenheit, 1)} °F"
    raise ValueError(f"unknown formula: {formula_id}")


def generate_local_example(
    index: int,
    *,
    seed: int,
    holdouts: HoldoutIndex,
    split: str = "train",
    source_revision: str,
) -> dict[str, Any] | None:
    generator = GENERATORS[index % len(GENERATORS)]
    problem = generator(index, seed)
    if not _visible_semantics_valid(problem):
        raise ValueError(f"visible operands do not reproduce the {problem.formula_id} answer")
    if _matches_sealed_numeric_core(problem):
        return None
    pedagogy = PEDAGOGIES[(index // len(GENERATORS)) % len(PEDAGOGIES)]
    prompt, completion, response_format = _render(problem, pedagogy)
    observed = recompute_answer(problem.formula_id, problem.inputs)
    return make_record(
        prompt=prompt,
        completion=completion,
        answer=problem.answer,
        subject=problem.subject,
        topic=problem.topic,
        difficulty=problem.difficulty,
        response_format=response_format,
        pedagogy=pedagogy,
        mode="chat",
        split=split,
        source_id="muta_verified_stem_v2",
        source_revision=source_revision,
        source_split="generated",
        source_row_id=f"generated:{index}",
        semantic_cluster_id=f"formula:{problem.formula_id}",
        license_name="MIT",
        synthetic=True,
        transform=f"generator:{generator.__name__.lstrip('_')}",
        country="multi-country-west-africa",
        curriculum_authority="Muta normalized public-topic taxonomy",
        curriculum_version="2026-09-15",
        exam_era="contemporary",
        alignment="original item; topic-level alignment only",
        verification={
            "status": "programmatic",
            "method": problem.formula_id,
            "expected": problem.answer,
            "observed": observed,
            "verifier_version": VERIFIER_VERSION,
            "inputs": problem.inputs,
            "misconception_type": problem.misconception_type,
            "generator_seed": seed,
            "generator_index": index,
            "generator_name": generator.__name__.lstrip("_"),
            "training_eligible": True,
        },
        holdouts=holdouts,
        source_task=problem.problem,
    )


def verify_local_record(record: dict[str, Any]) -> bool:
    """Regenerate the complete local row from its seed/index and compare it."""

    verification = record.get("verification") or {}
    provenance = record.get("provenance") or {}
    source_row_id = str(provenance.get("source_row_id", ""))
    if verification.get("status") != "programmatic" or not source_row_id.startswith("generated:"):
        return False
    try:
        index = int(source_row_id.removeprefix("generated:"))
        seed = int(verification.get("generator_seed"))
        if index < 0 or verification.get("generator_index") != index:
            return False
        generator = GENERATORS[index % len(GENERATORS)]
        problem = generator(index, seed)
        if not _visible_semantics_valid(problem):
            return False
        if _matches_sealed_numeric_core(problem):
            return False
        pedagogy = PEDAGOGIES[(index // len(GENERATORS)) % len(PEDAGOGIES)]
        prompt, completion, response_format = _render(problem, pedagogy)
        observed = recompute_answer(problem.formula_id, problem.inputs)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    return all(
        (
            verification.get("generator_name") == generator.__name__.lstrip("_"),
            verification.get("method") == problem.formula_id,
            verification.get("inputs") == problem.inputs,
            verification.get("misconception_type") == problem.misconception_type,
            observed == problem.answer == record.get("answer"),
            verification.get("expected") == problem.answer,
            verification.get("observed") == problem.answer,
            verification.get("training_eligible") is True,
            record.get("prompt") == prompt,
            record.get("completion") == completion,
            record.get("subject") == problem.subject,
            record.get("topic") == problem.topic,
            record.get("difficulty") == problem.difficulty,
            record.get("format") == response_format,
            record.get("pedagogy") == pedagogy,
            record.get("mode") == "chat",
            provenance.get("source_id") == "muta_verified_stem_v2",
            provenance.get("source_split") == "generated",
            provenance.get("semantic_cluster_id") == f"formula:{problem.formula_id}",
            provenance.get("transform") == f"generator:{generator.__name__.lstrip('_')}",
            (record.get("contamination") or {}).get("source_task_sha256")
            == normalized_sha256(problem.problem),
        )
    )
