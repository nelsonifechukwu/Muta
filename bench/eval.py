"""Product-level tutoring-quality evaluation — the first harness for the 50 % S_acc term.

Why this file exists
--------------------
The scoring function weights accuracy/quality at **0.50** — the heaviest term (ROADMAP
lines 31-36). Everything already in `bench/` measures S_perf and S_eff; the only accuracy
signal is `lm-eval` run against the **raw GGUF with no chat template** (see the note in
`bench/autotest.py`: "our tutoring layer is invisible to it"). That measures the model, not
the *tutor*. This harness measures the tutor: it drives the real `/v1/chat` endpoint — the
same path a student's browser takes — and grades the replies.

The mode-aware catch (ROADMAP line 34)
--------------------------------------
A Socratic reply that *deliberately never states the final answer* is **correct behaviour**
and would score zero under exact-match. So grading is split by mode:

* **subgoal** (worked solution) — the accuracy track. Extract the final answer from the
  reply and check it against the item's canonical answer with SymPy equivalence (reusing
  `orchestrator.tools.verifier`, the same checker the live `/v1/tutor/verify` endpoint uses).
  Score = fraction correct.

* **socratic** (guided dialogue) — a lightweight, **transparent, heuristic** rubric that
  does NOT penalise withholding the answer: (a) does it ask a guiding question, (b) does it
  avoid dumping the final answer immediately, (c) is it non-empty / substantive. These are
  cheap proxies. A real qualitative pedagogy score needs a human or an LLM judge — see the
  `run_judge` TODO and the `--judge` flag.

Design constraints honoured
---------------------------
* **Importable and `--help`-able without a live server.** Every network touch is behind
  `post_chat`; the scorers are pure functions over a reply string; `--selftest` exercises the
  whole grading path on canned replies with no server at all.
* **Degradation, not errors** (CLAUDE.md). An unreachable server exits non-zero with a clear
  message; a per-item transport failure is recorded as an error and the run continues.
  Nothing is skipped silently.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from runtime.chat import strip_visualization_protocol

_HERE = Path(__file__).resolve().parent
DEFAULT_ITEMS = _HERE / "eval_items.json"
DEFAULT_ARTIFACT_DIR = _HERE / ".artifacts"
DEFAULT_BASE = "http://127.0.0.1:8000"
# Generous: on the emulated x86 CPU one thinking turn can take minutes (RUN.md notes the
# engine's own request budget is 600 s). A tight client timeout would score a slow-but-correct
# tutor as an error.
DEFAULT_TIMEOUT_S = 600.0
ALL_MODES = ("subgoal", "socratic")
# The two subjects `/v1/chat` accepts beyond math are physics/chemistry/biology (Subject enum);
# anything else in an item degrades to math rather than failing the request.
_KNOWN_SUBJECTS = {"math", "physics", "chemistry", "biology"}
# A socratic reply shorter than this is treated as non-substantive. Deliberately low — the
# point is to catch empty/one-word degradations, not to judge quality (that needs `--judge`).
_MIN_SOCRATIC_CHARS = 15


# --- the answer checker: reuse the production verifier, fall back to inline SymPy -----------
# Primary path is `orchestrator.tools.verifier.AnswerVerifier` — the exact SymPy-in-a-sandbox
# checker the live `/v1/tutor/verify` endpoint uses, so the harness grades answers the same way
# the product does. If the sandbox is unavailable at runtime (returns checked=False) the checker
# falls back to an inline SymPy equivalence so grading still produces a verdict.
try:
    from orchestrator.tools.verifier import AnswerVerifier, extract_answer

    _HAVE_VERIFIER = True
except Exception:  # noqa: BLE001 — a missing orchestrator dep must not make the harness unimportable
    AnswerVerifier = None  # type: ignore[assignment,misc]
    extract_answer = None  # type: ignore[assignment]
    _HAVE_VERIFIER = False

# Unicode maths that SymPy's parser does not read, normalised before any check. `²`→`^2` etc.
_UNICODE_MATH = str.maketrans(
    {"²": "^2", "³": "^3", "·": "*", "×": "*", "÷": "/", "−": "-", "–": "-"}
)
# A trailing physical unit on an answer ("154 cm^2", "12 m/s", "80°"). The production verifier
# only cancels a unit when BOTH sides carry the identical one, so a unit-bearing model answer vs
# a bare canonical answer would read as WRONG. We strip the unit from both sides and retry.
_TRAILING_UNIT = re.compile(
    r"(?:\s+|^|(?<=[0-9)]))(?:m\s*/\s*s(?:\s*\^?\s*2)?"
    r"|(?:cm|mm|km|kg|mg|ms|mol|min|hr|ml|rad|degrees?|deg|°|N|J|W|V|A|K|L|m|s|g|h)"
    r"(?:\s*\^?\s*[23])?)\s*$",
    re.IGNORECASE,
)


def strip_units(text: str) -> str:
    """Drop a trailing physical unit (repeatedly), after normalising unicode maths.

    Conservative: a unit is only stripped when it sits at the very end after whitespace, a
    closing paren, or a digit — so `154 cm^2`→`154` and `80°`→`80`, but `35 apples` and the
    variable in `6x + 2` are left untouched.
    """
    out = str(text).translate(_UNICODE_MATH).strip()
    prev = None
    while out != prev:
        prev = out
        out = _TRAILING_UNIT.sub("", out).strip()
    return out


def _inline_extract_answer(text: str) -> str | None:
    """Fallback extractor used only when `orchestrator.tools.verifier` is unimportable.

    Mirrors the production extractor's ordering: `\\boxed{}`, then an explicit answer lead-in,
    then a trailing `= value`. Returns None when there is no final answer — a Socratic turn
    genuinely has none, and inventing one would grade the wrong thing.
    """
    if not text or not text.strip():
        return None
    boxed = re.findall(r"\\boxed\s*\{([^{}]+)\}", text)
    if boxed:
        return boxed[-1].strip()
    lead = re.compile(
        r"(?:final\s+answer|the\s+answer\s+is|answer\s*[:=]|therefore|hence)\s*[:,]?\s*(.+)",
        re.IGNORECASE,
    )
    for line in reversed(text.strip().splitlines()):
        m = lead.search(line)
        if m:
            cand = m.group(1).strip(" .*_`$")
            if cand and not cand.endswith("?"):
                return cand
    last = text.strip().splitlines()[-1].strip()
    if "=" in last and re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{2,}", last):
        return last.rsplit("=", 1)[1].strip(" .*_`$") or None
    return None


def get_extractor():
    """The final-answer extractor: production one if importable, else the inline fallback."""
    return extract_answer if _HAVE_VERIFIER else _inline_extract_answer


@dataclass
class CheckOutcome:
    checked: bool  # False = no verdict possible (never the same as "wrong")
    verified: bool
    method: str = ""  # "sandbox" | "sandbox+unitstrip" | "inline" | "inline+unitstrip"
    detail: str = ""


class Checker:
    """Grades a candidate answer against a canonical one and its acceptable variants.

    A candidate is *correct* when it is SymPy-equivalent to the canonical answer OR to any
    acceptable form. Each comparison is tried raw first, then with trailing units stripped from
    both sides (the verifier only cancels matching units, so a `12 m/s` reply vs a bare `12`
    canonical would otherwise miss).
    """

    def __init__(self, prefer_verifier: bool = True) -> None:
        self._verifier = AnswerVerifier() if (prefer_verifier and _HAVE_VERIFIER) else None

    def _one(self, candidate: str, expected: str, tolerance: float) -> CheckOutcome:
        """A single candidate-vs-expected verdict, sandbox first with an inline SymPy fallback."""
        if self._verifier is not None:
            o = self._verifier.check(candidate, expected, tolerance=tolerance)
            if o.checked:
                return CheckOutcome(True, bool(o.verified), "sandbox", o.detail or "")
            # checked=False => sandbox unavailable/died. Fall through to inline rather than
            # reporting "no verdict" for what is really a tooling problem.
        ok, checked, detail = _inline_equivalent(candidate, expected, tolerance)
        return CheckOutcome(checked, ok, "inline", detail)

    def correct(
        self, candidate: str, expected: str, acceptable: list[str], tolerance: float
    ) -> CheckOutcome:
        """True when `candidate` matches `expected` or any `acceptable` form (raw or unit-stripped)."""
        forms = [expected, *acceptable]
        last = CheckOutcome(False, False, "", "no forms to check")
        for form in forms:
            out = self._one(candidate, form, tolerance)
            if out.verified:
                return out
            if out.checked:
                last = out
            # Retry with units stripped from both sides.
            cs, fs = strip_units(candidate), strip_units(form)
            if (cs, fs) != (candidate, form):
                out2 = self._one(cs, fs, tolerance)
                if out2.verified:
                    return CheckOutcome(True, True, out2.method + "+unitstrip", out2.detail)
                if out2.checked:
                    last = out2
        return last


def _inline_equivalent(candidate: str, expected: str, tolerance: float) -> tuple[bool, bool, str]:
    """Self-contained SymPy equivalence for when the sandboxed verifier is unavailable.

    Returns (verified, checked, detail). Handles relations (`x = 2`), numeric tolerance, and a
    symbolic `simplify(a - b) == 0` fallback. Unparseable input returns checked=False rather
    than claiming a verdict — "we couldn't check" must never collapse into "wrong".
    """
    try:
        import sympy as sp
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except Exception as e:  # noqa: BLE001
        return False, False, f"sympy unavailable: {e}"

    tf = standard_transformations + (implicit_multiplication_application,)

    def prep(s: str) -> str:
        s = str(s).translate(_UNICODE_MATH).replace("$", "").strip()
        s = re.sub(r"\\boxed\s*\{([^{}]+)\}", r"\1", s)
        return s.replace("^", "**").rstrip(".").strip()

    def parse(s: str):
        return parse_expr(prep(s), transformations=tf, evaluate=True)

    def as_expr(s: str):
        # `lhs = rhs` -> lhs - rhs so an equation and a value compare on the same footing.
        p = prep(s)
        if p.count("=") == 1 and not re.search(r"[<>!]=|==", p):
            lhs, rhs = p.split("=")
            return parse(lhs) - parse(rhs), True
        return parse(p), False

    try:
        a, a_rel = as_expr(candidate)
        b, b_rel = as_expr(expected)
        if a_rel != b_rel:
            # One side is `x = 2`, the other bare `2`: compare the value to the relation's roots.
            rel, val = (a, b) if a_rel else (b, a)
            syms = sorted(rel.free_symbols, key=str)
            if len(syms) == 1:
                roots = sp.solve(rel, syms[0])
                return (
                    any(bool(sp.simplify(r - val) == 0) for r in roots),
                    True,
                    "relation-vs-value",
                )
            return False, True, "cannot align relation and value"
        if tolerance > 0:
            try:
                fa, fb = float(a.evalf()), float(b.evalf())
                scale = max(abs(fa), abs(fb), 1e-12)
                if abs(fa - fb) / scale <= tolerance:
                    return True, True, "numeric-close"
            except (TypeError, ValueError):
                pass
        eq = a.equals(b)
        if eq is True:
            return True, True, ""
        if eq is False:
            return False, True, ""
        return bool(sp.simplify(a - b) == 0), True, "simplify"
    except Exception as e:  # noqa: BLE001 — unparseable => no verdict, not "wrong"
        return False, False, f"{type(e).__name__}: compared as text"


# --- items ----------------------------------------------------------------------------------


@dataclass
class EvalItem:
    id: str
    subject: str
    topic: str
    question: str
    expected_answer: str
    acceptable: list[str] = field(default_factory=list)
    tolerance: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "EvalItem":
        missing = [
            k for k in ("id", "subject", "topic", "question", "expected_answer") if k not in d
        ]
        if missing:
            raise ValueError(f"item {d.get('id', '?')!r} missing required keys: {missing}")
        subject = str(d["subject"]).lower()
        if subject not in _KNOWN_SUBJECTS:
            subject = "math"  # degrade unknown subjects rather than reject the item
        return cls(
            id=str(d["id"]),
            subject=subject,
            topic=str(d["topic"]),
            question=str(d["question"]),
            expected_answer=str(d["expected_answer"]),
            acceptable=[str(a) for a in d.get("acceptable", [])],
            tolerance=float(d.get("tolerance", 0.0) or 0.0),
        )


def load_items(path: Path) -> list[EvalItem]:
    """Read the item file. Accepts either a bare list or `{"items": [...]}` (keys starting with
    `_` are treated as comments). Raises on malformed items — a silently dropped item is a
    silently unmeasured topic."""
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, dict):
        raw = raw.get("items", [])
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: expected a non-empty list of items (or an 'items' list)")
    items = [
        EvalItem.from_dict(d)
        for d in raw
        if not (isinstance(d, dict) and str(d.get("id", "")).startswith("_"))
    ]
    ids = [it.id for it in items]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"{path}: duplicate item ids {sorted(dupes)}")
    return items


# --- network (the ONLY server touch; kept behind a function so the module is server-free) ---


class ServerUnreachable(RuntimeError):
    """The server could not be reached at all — a run-ending condition, not a per-item error."""


def preflight(base: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Probe `/v1/ready`. Returns (ready, human message). Reachability is required to run;
    ready=false is a loud warning (chats will 503) but not fatal."""
    try:
        r = httpx.get(f"{base}/v1/ready", timeout=timeout)
    except httpx.HTTPError as e:
        raise ServerUnreachable(
            f"cannot reach {base}/v1/ready ({type(e).__name__}). Is the stack up? See RUN.md "
            f"(./run.sh, then --base http://localhost:3000 for the proxy or :8000 for the backend)."
        ) from e
    try:
        body = r.json()
    except ValueError:
        return False, f"/v1/ready returned non-JSON (HTTP {r.status_code})"
    ready = bool(body.get("ready"))
    return ready, ("ready" if ready else f"NOT ready — checks={body.get('checks')} (chats may 503)")


def post_chat(
    client: httpx.Client, base: str, item: EvalItem, mode: str, student_id: str, timeout: float
) -> str:
    """POST one tutoring turn to `/v1/chat` and return the reply text.

    This is the single network entry point. It raises `httpx.HTTPError` on transport/HTTP
    failure; the caller records that as a per-item error and moves on.
    """
    resp = client.post(
        f"{base}/v1/chat",
        json={
            "student_id": student_id,
            "message": item.question,
            "mode": mode,
            "subject": item.subject,
            "language": "en",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return str(resp.json().get("reply", ""))


# --- scoring (pure functions over a reply string — no network, unit-testable) ---------------


@dataclass
class SubgoalScore:
    extracted: str | None
    correct: bool
    checked: bool  # a verdict was reached (extractor found an answer and the checker ran)
    matched_form: str | None
    method: str
    detail: str


def score_subgoal(reply: str, item: EvalItem, checker: Checker) -> SubgoalScore:
    """Accuracy track: extract the final answer and check it against the canonical answer.

    No extractable answer in a *subgoal* reply is a miss (the worked solution failed to
    conclude), reported as correct=False with checked=False so it is visibly distinct from a
    wrong answer.
    """
    extractor = get_extractor()
    candidate = extractor(strip_visualization_protocol(reply))
    if candidate is None:
        return SubgoalScore(None, False, False, None, "", "no final answer extracted")
    out = checker.correct(candidate, item.expected_answer, item.acceptable, item.tolerance)
    matched = None
    if out.verified:
        # Re-identify which form matched, for the report (cheap: the check already passed).
        for form in [item.expected_answer, *item.acceptable]:
            if checker.correct(candidate, form, [], item.tolerance).verified:
                matched = form
                break
    return SubgoalScore(candidate, bool(out.verified), out.checked, matched, out.method, out.detail)


@dataclass
class SocraticScore:
    asks_question: bool
    withholds_answer: bool  # did NOT dump the final answer straight away
    substantive: bool  # non-empty and past the length floor
    rubric_pass: bool  # all three
    dumped_answer: str | None
    detail: str


def score_socratic(reply: str, item: EvalItem, checker: Checker) -> SocraticScore:
    """HEURISTIC pedagogy rubric — transparent by design, NOT a quality judgement.

    Three cheap proxies, none of which penalise withholding the answer:
      (a) asks_question   — contains a '?'
      (b) withholds_answer— it did not immediately state the canonical final answer
      (c) substantive     — non-empty and past a short length floor (catches degradations)

    True pedagogy quality (does the question actually scaffold the student's next step?) needs
    a human or LLM judge. See `run_judge` / `--judge`. Do not read `rubric_pass` as a quality
    score; read it as "structurally behaves like a Socratic turn".
    """
    text = strip_visualization_protocol(reply)
    asks = "?" in text
    substantive = len(text) >= _MIN_SOCRATIC_CHARS

    # Did it dump the answer? Only a penalty if the reply *states a final answer equal to the
    # canonical one* — mentioning intermediate numbers is fine and expected.
    extractor = get_extractor()
    candidate = extractor(text)
    dumped = None
    if candidate is not None:
        out = checker.correct(candidate, item.expected_answer, item.acceptable, item.tolerance)
        if out.verified:
            dumped = candidate
    withholds = dumped is None

    return SocraticScore(
        asks_question=asks,
        withholds_answer=withholds,
        substantive=substantive,
        rubric_pass=asks and withholds and substantive,
        dumped_answer=dumped,
        detail=("dumped final answer" if dumped else ""),
    )


# --- per-item run + aggregation -------------------------------------------------------------


@dataclass
class ItemResult:
    id: str
    subject: str
    topic: str
    mode: str
    ok: bool  # the turn completed (a reply came back)
    error: str | None
    reply_chars: int
    subgoal: dict | None = None
    socratic: dict | None = None


def run_item(
    client: httpx.Client,
    base: str,
    item: EvalItem,
    mode: str,
    checker: Checker,
    student_id: str,
    timeout: float,
) -> ItemResult:
    """Drive one item in one mode and grade the reply. Transport failures are recorded, not raised."""
    try:
        reply = post_chat(client, base, item, mode, f"{student_id}-{item.id}-{mode}", timeout)
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = e.response.text[:200]
        return ItemResult(
            item.id,
            item.subject,
            item.topic,
            mode,
            False,
            f"HTTP {e.response.status_code}: {detail}",
            0,
        )
    except httpx.HTTPError as e:
        return ItemResult(
            item.id, item.subject, item.topic, mode, False, f"{type(e).__name__}: {e}", 0
        )

    res = ItemResult(item.id, item.subject, item.topic, mode, True, None, len(reply))
    if mode == "subgoal":
        res.subgoal = asdict(score_subgoal(reply, item, checker))
    elif mode == "socratic":
        res.socratic = asdict(score_socratic(reply, item, checker))
    return res


def aggregate(results: list[ItemResult]) -> dict:
    """Roll per-item results up into the two headline numbers, keeping errors visible."""
    sub = [r for r in results if r.mode == "subgoal"]
    soc = [r for r in results if r.mode == "socratic"]

    sub_ok = [r for r in sub if r.ok]
    sub_correct = sum(1 for r in sub_ok if r.subgoal and r.subgoal["correct"])
    sub_unextracted = sum(1 for r in sub_ok if r.subgoal and not r.subgoal["checked"])

    soc_ok = [r for r in soc if r.ok]
    soc_pass = sum(1 for r in soc_ok if r.socratic and r.socratic["rubric_pass"])

    def pct(n: int, d: int) -> float | None:
        return round(100.0 * n / d, 1) if d else None

    summary = {
        "subgoal": {
            "total": len(sub),
            "scored": len(sub_ok),
            "errors": len(sub) - len(sub_ok),
            "correct": sub_correct,
            "unextracted": sub_unextracted,
            "accuracy_pct": pct(sub_correct, len(sub_ok)),
        },
        "socratic": {
            "total": len(soc),
            "scored": len(soc_ok),
            "errors": len(soc) - len(soc_ok),
            "rubric_pass": soc_pass,
            "rubric_pass_pct": pct(soc_pass, len(soc_ok)),
            # Per-check rates make it obvious WHICH heuristic drove the number.
            "asks_question_pct": pct(
                sum(1 for r in soc_ok if r.socratic and r.socratic["asks_question"]), len(soc_ok)
            ),
            "withholds_answer_pct": pct(
                sum(1 for r in soc_ok if r.socratic and r.socratic["withholds_answer"]), len(soc_ok)
            ),
            "substantive_pct": pct(
                sum(1 for r in soc_ok if r.socratic and r.socratic["substantive"]), len(soc_ok)
            ),
        },
    }
    return summary


# --- reporting ------------------------------------------------------------------------------


def _git_sha() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=_HERE,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            or "unknown"
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def print_tables(results: list[ItemResult], summary: dict) -> None:
    sub = [r for r in results if r.mode == "subgoal"]
    soc = [r for r in results if r.mode == "socratic"]

    if sub:
        print("\n=== subgoal (accuracy track: final-answer correctness) ===")
        print(f"{'id':<5} {'topic':<28} {'result':<8} {'extracted':<20} {'detail'}")
        print("-" * 90)
        for r in sub:
            if not r.ok:
                print(f"{r.id:<5} {r.topic:<28} {'ERROR':<8} {'-':<20} {r.error}")
                continue
            s = r.subgoal or {}
            verdict = "PASS" if s.get("correct") else ("MISS" if s.get("checked") else "NO-ANS")
            ext = (s.get("extracted") or "-")[:19]
            note = s.get("detail") or (
                f"matched {s.get('matched_form')!r}" if s.get("correct") else ""
            )
            print(f"{r.id:<5} {r.topic:<28} {verdict:<8} {ext:<20} {note}")

    if soc:
        print("\n=== socratic (HEURISTIC rubric — structural, not a quality judgement) ===")
        print(
            f"{'id':<5} {'topic':<28} {'pass':<6} {'ask?':<5} {'withhold?':<10} {'subst?':<7} {'detail'}"
        )
        print("-" * 90)
        for r in soc:
            if not r.ok:
                print(f"{r.id:<5} {r.topic:<28} {'ERROR':<6} {'-':<5} {'-':<10} {'-':<7} {r.error}")
                continue
            s = r.socratic or {}
            yn = lambda b: "yes" if b else "no"  # noqa: E731
            print(
                f"{r.id:<5} {r.topic:<28} {yn(s.get('rubric_pass')):<6} "
                f"{yn(s.get('asks_question')):<5} {yn(s.get('withholds_answer')):<10} "
                f"{yn(s.get('substantive')):<7} {s.get('detail') or ''}"
            )

    sub_s, soc_s = summary["subgoal"], summary["socratic"]
    print("\n=== AGGREGATE ===")
    print(
        f"subgoal  : accuracy {sub_s['accuracy_pct']}%  "
        f"({sub_s['correct']}/{sub_s['scored']} correct; "
        f"{sub_s['unextracted']} no-answer; {sub_s['errors']} errors)"
    )
    print(
        f"socratic : rubric pass {soc_s['rubric_pass_pct']}%  "
        f"({soc_s['rubric_pass']}/{soc_s['scored']}; "
        f"asks {soc_s['asks_question_pct']}%, withholds {soc_s['withholds_answer_pct']}%, "
        f"substantive {soc_s['substantive_pct']}%; {soc_s['errors']} errors)"
    )
    print(
        "note: socratic rubric is a transparent heuristic — a real pedagogy score needs "
        "human/LLM-judge grading (--judge; see run_judge TODO)."
    )


# --- LLM-judge hook (NOT IMPLEMENTED) -------------------------------------------------------


def run_judge(reply: str, item: EvalItem, mode: str) -> dict:
    """TODO(judge): qualitative pedagogy grade for the socratic track.

    The heuristic rubric in `score_socratic` measures *structure* (does it ask a question, does
    it withhold the answer). It cannot measure whether the guiding question actually scaffolds
    the student's next step — the thing the 50 % S_acc "tutoring quality" term is really about.

    Intended design: send the item, the reply, and a fixed pedagogy rubric to a strong
    instruction-following LLM judge and parse a small structured score (e.g. 1-5 on
    scaffolding, correctness-of-hint, tone) plus a one-line justification. Runs offline-optional
    (judge is a dev-time / report-time tool, never in the student path). Multiple judges or
    self-consistency would reduce variance. Until built, `--judge` prints a clear notice and the
    run continues on the heuristic rubric.
    """
    raise NotImplementedError("LLM-judge grading is not implemented yet (see run_judge docstring)")


# --- CLI ------------------------------------------------------------------------------------


def selftest() -> int:
    """Exercise the whole grading path on canned replies — proves the harness runs with NO
    server. Returns 0 on success, 1 if any internal expectation is violated."""
    checker = Checker()
    item = EvalItem("t1", "math", "indices", "Evaluate 27^(2/3).", "9", [])
    failures: list[str] = []

    # subgoal: a correct worked solution.
    s1 = score_subgoal(
        "27 = 3^3, so 27^(2/3) = 3^2. Therefore the answer is \\boxed{9}.", item, checker
    )
    if not (s1.correct and s1.checked):
        failures.append(f"subgoal-correct expected PASS, got {s1}")

    # subgoal: a wrong worked solution.
    s2 = score_subgoal("Working it out, the answer is 27.", item, checker)
    if s2.correct or not s2.checked:
        failures.append(f"subgoal-wrong expected MISS(checked), got {s2}")

    # subgoal: no final answer -> not correct, not checked (distinct from wrong).
    s3 = score_subgoal("Let us think about what a fractional index means.", item, checker)
    if s3.correct or s3.checked:
        failures.append(f"subgoal-noanswer expected NO-ANS, got {s3}")

    # socratic: guiding question that withholds the answer -> pass.
    s4 = score_socratic(
        "What is 27 written as a power of 3? Once you have that, what happens to the exponent?",
        item,
        checker,
    )
    if not s4.rubric_pass:
        failures.append(f"socratic-good expected PASS, got {s4}")

    # socratic: dumping the answer immediately -> withholds=False -> fail.
    s5 = score_socratic("The answer is 9.", item, checker)
    if s5.withholds_answer or s5.rubric_pass:
        failures.append(f"socratic-dump expected withholds=False, got {s5}")

    # unit-strip: a physics answer with units grades correct against a bare canonical.
    phys = EvalItem("t2", "physics", "kinematics", "final velocity?", "12", ["12 m/s"])
    s6 = score_subgoal(
        "Using v = u + at, v = 0 + 3*4 = 12 m/s. Therefore \\boxed{12 m/s}.", phys, checker
    )
    if not s6.correct:
        failures.append(f"unit-strip expected PASS, got {s6}")

    for f in failures:
        print("FAIL:", f)
    print(
        f"\nselftest: {'PASS' if not failures else 'FAIL'} "
        f"(verifier={'sandbox' if _HAVE_VERIFIER else 'inline-fallback'})"
    )
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bench.eval",
        description="Product-level tutoring-quality eval: drives /v1/chat and grades replies "
        "mode-aware (subgoal=final-answer accuracy via SymPy; socratic=heuristic rubric).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Server base URL, no trailing /v1 (default {DEFAULT_BASE}; use "
        "http://localhost:3000 for the nginx proxy).",
    )
    p.add_argument(
        "--items", type=Path, default=DEFAULT_ITEMS, help=f"Item file (default {DEFAULT_ITEMS})."
    )
    p.add_argument(
        "--modes",
        default=",".join(ALL_MODES),
        help=f"Comma-separated modes to test (default '{','.join(ALL_MODES)}').",
    )
    p.add_argument("--limit", type=int, default=0, help="Only run the first N items (0 = all).")
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-request timeout in seconds (default {DEFAULT_TIMEOUT_S:g}; CPU is slow).",
    )
    p.add_argument("--student-id", default="eval-bot", help="student_id prefix sent to /v1/chat.")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Results JSON path (default bench/.artifacts/eval-<timestamp>.json).",
    )
    p.add_argument(
        "--no-verifier",
        action="store_true",
        help="Skip the sandboxed AnswerVerifier and grade with the inline SymPy check.",
    )
    p.add_argument(
        "--judge",
        action="store_true",
        help="Request LLM-judge qualitative grading (NOT IMPLEMENTED — prints a notice; "
        "run continues on the heuristic rubric).",
    )
    p.add_argument(
        "--selftest",
        action="store_true",
        help="Run the scorers on canned replies with NO server, then exit.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest:
        return selftest()

    if args.judge:
        print(
            "NOTICE: --judge (LLM-judge grading) is not implemented yet; continuing on the "
            "heuristic socratic rubric. See run_judge() TODO.",
            file=sys.stderr,
        )

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in ALL_MODES]
    if unknown:
        print(f"error: unknown mode(s) {unknown}; valid: {list(ALL_MODES)}", file=sys.stderr)
        return 2

    try:
        items = load_items(args.items)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: could not load items from {args.items}: {e}", file=sys.stderr)
        return 2
    if args.limit > 0:
        items = items[: args.limit]

    base = args.base.rstrip("/")
    try:
        ready, msg = preflight(base)
    except ServerUnreachable as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"preflight {base}: {msg}")
    if not ready:
        print(
            "warning: server reports NOT ready — the model may still be loading; "
            "expect 503s below (recorded as errors, not skipped).",
            file=sys.stderr,
        )

    checker = Checker(prefer_verifier=not args.no_verifier)
    print(
        f"grading with: {'inline SymPy' if args.no_verifier or not _HAVE_VERIFIER else 'sandboxed AnswerVerifier'}"
    )
    print(
        f"running {len(items)} items x {len(modes)} mode(s) = {len(items) * len(modes)} turns "
        f"(timeout {args.timeout:g}s each)"
    )

    results: list[ItemResult] = []
    with httpx.Client() as client:
        for item in items:
            for mode in modes:
                r = run_item(client, base, item, mode, checker, args.student_id, args.timeout)
                status = "ok" if r.ok else f"ERR({r.error})"
                print(f"  [{item.id}/{mode}] {status}", flush=True)
                results.append(r)

    summary = aggregate(results)
    print_tables(results, summary)

    out_path = args.out or (
        DEFAULT_ARTIFACT_DIR / f"eval-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "base": base,
            "modes": modes,
            "items_file": str(args.items),
            "n_items": len(items),
            "git_sha": _git_sha(),
            "grader": "inline" if (args.no_verifier or not _HAVE_VERIFIER) else "sandbox",
        },
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out_path}")

    # Exit non-zero if nothing scored (server up but every turn errored) — a run that measured
    # nothing must not look like a pass.
    if all(not r.ok for r in results):
        print("error: every turn errored — nothing was measured.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
