import ast
import collections
import decimal
import hashlib
import json
import multiprocessing as mp
import re
import time
from fractions import Fraction
from pathlib import Path

from datasets import load_dataset

REV = "0c8ed6b60fea0a84f25ddb1b8b761db695df2e19"
CONFIG = "templategsm-2000-1k"
SEED = 3407
CAP = 400
CAN_INPUT = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\Z")
LIT = re.compile(r"(?<![\w.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)")
LONG = re.compile(r"(?<![\w.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{7,}(?!\w|\.\d)")
N = r"(?:[$£€₦]\s*)?[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
OP = r"(?:\+|-|\*|/|×|÷|[xX])"
EQ = re.compile(
    rf"(?<![\w.])(?P<lhs>{N}(?:\s*{OP}\s*{N})+)\s*=\s*"
    rf"(?P<rhs>(?:[$£€₦]\s*)?[+-]?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)"
    rf"(?:\.\d+)?)(?!\w|\.\d)"
)
APPROX = re.compile(
    r"\b(?:approximately|approx(?:imately)?\.?|about|roughly|estimate(?:d)?|"
    r"rounded|rounding|nearest)\b|[≈~]",
    re.IGNORECASE,
)
PERCENT = re.compile(r"(?<![\w.])([+-]?(?:\d+(?:\.\d+)?|\.\d+))%")


def clean_reasoning(text):
    text = re.sub(
        r"<think\b[^>]*>.*?</think\s*>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<<[^<>]*>>", "", text)
    text = re.sub(r"\\boxed\{([^{}]+)\}", r"Final answer: \1", text)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


def normalize_answer(text):
    value = text.strip().replace(",", "")
    if re.fullmatch(r"[-+]?\d+\.0+", value):
        return value.split(".", 1)[0]
    return value


def fraction_number(text):
    text = re.sub(r"[$£€₦\s,]", "", text)
    percentage = text.endswith("%")
    text = text.removesuffix("%")
    value = Fraction(decimal.Decimal(text))
    return value / 100 if percentage else value


def evaluate_expression(lhs):
    expression = re.sub(r"[$£€₦,\s]", "", lhs)
    expression = expression.replace("×", "*").replace("x", "*").replace("X", "*").replace("÷", "/")
    expression = PERCENT.sub(r"(\1/100)", expression)
    tree = ast.parse(expression, mode="eval")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("outside restricted arithmetic grammar")

    return evaluate(tree)


def row_flags(row, stats):
    prompt = str(row.get("problem", "")).strip()
    answer = normalize_answer(str(row.get("result", "")).strip())
    solution = clean_reasoning(str(row.get("solution_wocode", "")))
    code = str(row.get("solution_code", "")).strip()
    flags = []
    if not prompt or not answer or not solution or "result" not in code:
        flags.append("base_missing")
    answer_value = None
    if not CAN_INPUT.fullmatch(answer):
        flags.append("result_noncanonical")
    else:
        try:
            answer_value = decimal.Decimal(answer.replace(",", ""))
            fractional = answer.replace(",", "").lstrip("+-").partition(".")[2].rstrip("0")
            if (
                not answer_value.is_finite()
                or len(fractional) > 6
                or (answer_value == 0 and answer.startswith("-"))
            ):
                flags.append("result_noncanonical")
        except decimal.InvalidOperation:
            flags.append("result_noncanonical")
    if LONG.search(solution):
        flags.append("solution_float_artifact")
    if answer_value is None or not answer_value.is_finite():
        flags.append("target_unsupported")
    else:
        values = []
        for match in LIT.finditer(solution[-512:]):
            try:
                values.append(decimal.Decimal(match.group().replace(",", "")))
            except decimal.InvalidOperation:
                pass
        if answer_value not in values:
            flags.append("target_unsupported")
    contradiction = False
    for match in EQ.finditer(solution):
        stats["equalities_extracted"] += 1
        context = solution[max(0, match.start() - 120) : min(len(solution), match.end() + 120)]
        if APPROX.search(context):
            stats["equalities_skipped_explicit_approximation"] += 1
            continue
        try:
            left = evaluate_expression(match.group("lhs"))
            right = fraction_number(match.group("rhs"))
            stats["equalities_evaluated"] += 1
            if left != right:
                contradiction = True
                stats["contradictory_equalities"] += 1
        except (SyntaxError, ValueError, ZeroDivisionError, decimal.InvalidOperation):
            stats["equalities_parse_failed"] += 1
    if contradiction:
        flags.append("arithmetic_contradiction")
    return sorted(set(flags))


def worker(index, queue):
    dataset = load_dataset(
        "math-ai/TemplateGSM",
        CONFIG,
        split="train",
        revision=REV,
        streaming=True,
    ).shard(num_shards=4, index=index, contiguous=True)
    stats = collections.Counter()
    reason_templates = collections.defaultdict(set)
    template_total = collections.Counter()
    template_pass = collections.Counter()
    combinations = collections.Counter()
    started = time.time()
    for row in dataset:
        template_id = str(row.get("template_id", ""))
        stats["total_rows"] += 1
        template_total[template_id] += 1
        flags = row_flags(row, stats)
        combinations["|".join(flags) if flags else "PASS"] += 1
        if flags:
            stats["rejected_rows"] += 1
            for reason in flags:
                stats[f"rejected_{reason}"] += 1
                reason_templates[reason].add(template_id)
        else:
            stats["accepted_rows"] += 1
            template_pass[template_id] += 1
        if stats["total_rows"] % 100_000 == 0:
            print(
                "WORKER",
                index,
                stats["total_rows"],
                stats["accepted_rows"],
                round(time.time() - started, 1),
                flush=True,
            )
    queue.put(
        {
            "stats": dict(stats),
            "reason_templates": {key: list(value) for key, value in reason_templates.items()},
            "template_total": dict(template_total),
            "template_pass": dict(template_pass),
            "combinations": dict(combinations),
        }
    )


def main():
    context = mp.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=worker, args=(index, queue)) for index in range(4)]
    for process in processes:
        process.start()
    parts = [queue.get() for _ in processes]
    for process in processes:
        process.join()
    if any(process.exitcode for process in processes):
        raise SystemExit([process.exitcode for process in processes])
    stats = collections.Counter()
    reason_templates = collections.defaultdict(set)
    template_total = collections.Counter()
    template_pass = collections.Counter()
    combinations = collections.Counter()
    for part in parts:
        stats.update(part["stats"])
        combinations.update(part["combinations"])
        template_total.update(part["template_total"])
        template_pass.update(part["template_pass"])
        for reason, values in part["reason_templates"].items():
            reason_templates[reason].update(values)
    all_templates = set(template_total)
    failing_templates = set().union(*reason_templates.values()) if reason_templates else set()
    passing_templates = all_templates - failing_templates
    implementation_path = Path(__file__)
    implementation_sha256 = hashlib.sha256(implementation_path.read_bytes()).hexdigest()
    report = {
        "schema_version": 1,
        "checker_version": "templategsm-static-prefilter-v1",
        "checker_implementation": {
            "path": "data/templategsm-static-prefilter-v1.py",
            "sha256": implementation_sha256,
        },
        "source_id": "template_gsm",
        "source_revision": REV,
        "configuration": CONFIG,
        "seed_for_builder_replay": SEED,
        "full_scan_order": "repository shard order; row-level counts and template quarantine are order-independent",
        "per_template_cap": CAP,
        "rules": [
            "Require nonempty problem, result, and solution_wocode, and literal substring result in solution_code; solution_code is never executed.",
            "Normalize commas and all-zero decimal suffixes, then require a finite plain decimal result with no exponent, no negative zero, and at most six non-trailing fractional digits.",
            "Reject solution_wocode containing any numeric literal with seven or more fractional digits as a float artifact.",
            "Require a Decimal-equivalent result literal within the final 512 characters of cleaned solution_wocode.",
            "Extract numeric-only equalities supporting currency marks, thousands commas, percentages, + - * / x X × ÷, unary signs, and parentheses introduced only by percent normalization; evaluate with Fraction through a restricted AST; reject exact disagreements.",
            "Skip an equality mismatch only when a 120-character surrounding context explicitly contains approximately/approx/about/roughly/estimate/rounded/nearest/≈/~.",
            "No publisher solution_code parsing or execution and no claim of independent semantic verification; surviving rows remain audit-gated.",
        ],
        "counts": dict(sorted(stats.items())),
        "row_flag_combinations": dict(
            sorted(combinations.items(), key=lambda item: (-item[1], item[0]))
        ),
        "templates": {
            "total": len(all_templates),
            "fully_passing": len(passing_templates),
            "failing_any_rule": len(failing_templates),
            "fully_passing_ids": sorted(passing_templates, key=int),
            "failing_any_rule_ids": sorted(failing_templates, key=int),
            "failing_ids_by_reason": {
                reason: sorted(values, key=int)
                for reason, values in sorted(reason_templates.items())
            },
            "pass_row_capacity_with_row_filter_and_cap400": sum(
                min(CAP, template_pass[template]) for template in all_templates
            ),
            "capacity_with_every_failing_template_quarantined_and_cap400": len(passing_templates)
            * CAP,
            "target_350000_feasible_after_full_template_quarantine": len(passing_templates) * CAP
            >= 350_000,
            "target_400000_feasible_after_full_template_quarantine": len(passing_templates) * CAP
            >= 400_000,
            "target_430000_feasible_after_full_template_quarantine": len(passing_templates) * CAP
            >= 430_000,
        },
        "limitations": [
            "Static checks prove only narrow textual/numeric invariants; they do not solve the word problem or establish semantic correctness.",
            "The six-fractional-digit and float-artifact rules intentionally trade false negatives for conservative precision and may reject correct repeating-decimal narratives.",
            "Numeric-only equality extraction misses equations with variables, words, or units embedded inside the arithmetic expression.",
            "Target-literal support can still be coincidental; exact-row human audit remains mandatory before SFT.",
        ],
    }
    output = Path("data/templategsm-semantic-audit-20260916.json")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "counts": report["counts"],
        "templates": {
            key: value
            for key, value in report["templates"].items()
            if not key.endswith("_ids") and key != "failing_ids_by_reason"
        },
    }
    print("FINAL_REPORT", output, json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
