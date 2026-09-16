"""Exact Gate 1 judge-prompt replay set recovered from the Muta ADTC evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class JudgePrompt:
    id: str
    source: str
    title: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


_PROMPTS = (
    JudgePrompt(
        "automated_01",
        "automated",
        "Two Sigma proportional model",
        """Derive a mathematical model that represents the 'Two Sigma' learning effect where an individual's knowledge acquisition rate is proportional to the personalization factor provided by a tutor. Explain how this model behaves as the personalization factor approaches zero versus infinity.""",
    ),
    JudgePrompt(
        "automated_02",
        "automated",
        "Mastery differential equation",
        """If a student's learning progress is defined by the differential equation dS/dt = k * (T - S), where S is the student's mastery, T is the tutor's expertise level, and k is a constant related to the student's learning efficiency, solve for S(t) given an initial mastery S(0). How does this equation demonstrate the limit of educational scaling described in the Two Sigma problem?""",
    ),
    JudgePrompt(
        "automated_03",
        "automated",
        "Offline LLM capacity",
        """Analyze the computational constraints of deploying a localized, offline Large Language Model for tutoring. If a student requires a response latency of less than 200ms to maintain cognitive flow, calculate the maximum allowable parameter size for an LLM running on a device with 4 TOPS (Trillion Operations Per Second) capacity, assuming an average of 2 tokens generated per character.""",
    ),
    JudgePrompt(
        "automated_04",
        "automated",
        "Lagos chalk calculation",
        """Multiple choice: A school in Lagos buys 6 boxes of chalk at ₦500 per box. What is the total cost? A. ₦1,000 B. ₦2,500 C. ₦3,000 D. ₦3,500. Answer with the correct option and one calculation.""",
    ),
    JudgePrompt(
        "automated_05",
        "automated",
        "Photosynthesis multiple choice",
        """Multiple choice: Which process allows green plants to use sunlight to make food? A. Respiration B. Photosynthesis C. Evaporation D. Condensation. Answer with the correct option and one sentence of explanation.""",
    ),
    JudgePrompt(
        "human_01",
        "human judge",
        "Average-speed misconception",
        """A secondary-school student says:
“If a car travels 120 km in 2 hours, its average speed is 60 km/h. But if it travels the first 60 km at 40 km/h and the second 60 km at 80 km/h, shouldn’t the average speed still be 60 km/h because (40 + 80) / 2 = 60?”
Explain clearly why this reasoning is incorrect. Calculate the correct average speed step by step. Then explain the concept again using an intuitive example that a 15-year-old student could understand.
Do not just give the answer; teach the student how to recognize this type of mistake in the future.""",
    ),
    JudgePrompt(
        "human_02",
        "human judge",
        "DNA genes chromosomes and proteins",
        """You are tutoring a student who says:
“I understand that DNA contains genetic information, but I don’t understand how DNA, genes, chromosomes, and proteins are related. They all sound like different names for the same thing.”
Teach this concept in a personalized tutoring style. Start by identifying the likely misconception. Then explain the relationship between DNA, genes, chromosomes, and proteins using:
a simple analogy,
a scientifically accurate explanation,
one question to check whether the student understands, and
a short follow-up explanation you would give if the student answered that question incorrectly.
Keep the explanation appropriate for a secondary-school student.""",
    ),
    JudgePrompt(
        "human_03",
        "human judge",
        "Bilingual photosynthesis tutoring",
        """A 14-year-old student in Nigeria is learning about photosynthesis but is struggling with the English explanation. Explain photosynthesis first in simple English, and then explain the same concept in Yorùbá.
Use an everyday example that would be familiar to a student in West Africa, but do not sacrifice scientific accuracy. Your explanation must correctly include:
sunlight,
carbon dioxide,
water,
glucose,
oxygen,
and the role of chlorophyll.
End with two short quiz questions in English and Yorùbá that test understanding rather than memorization.""",
    ),
    JudgePrompt(
        "human_04",
        "human judge",
        "Two Sigma model repeat",
        """Derive a mathematical model that represents the 'Two Sigma' learning effect where an individual's knowledge acquisition rate is proportional to the personalization factor provided by a tutor. Explain how this model behaves as the personalization factor approaches zero versus infinity.""",
    ),
    JudgePrompt(
        "human_05",
        "human judge",
        "Onitsha rice profit",
        """A trader in Onitsha buys 40 kg of rice at ₦1,850 per kg. She sells 25 kg at ₦2,300 per kg, then reduces the price by 15% and sells the rest. Find (a) her total revenue, (b) her profit, and (c) her percentage profit on cost, to one decimal place. Show your working step by step, then check your answer for (c) by a different method.""",
    ),
)


def prompts() -> tuple[JudgePrompt, ...]:
    return _PROMPTS
