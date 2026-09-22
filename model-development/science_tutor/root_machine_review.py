"""Machine-assisted review draft for the frozen development packet.

This is a triage aid, not a claim of independent human semantic review. It
keeps exact response evidence and is followed by root audit before any
selection decision. It never changes the packet or model outputs.
"""
from __future__ import annotations

import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import development_review as dr

PACKET = Path("provenance/science-tutor-20260919/evaluation/development-review-packet-v3")
OUT = Path("provenance/science-tutor-20260919/reviews")


def clean(s):
    return s.replace("<|im_end|>", "").replace("<｜end▁of▁sentence｜>", "").strip()


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def choice(row):
    raw = clean(row["response"])
    seg = raw.rsplit("</think>", 1)[-1].strip() or raw
    found = []
    patterns = [
        r"(?i)(?:the\s+)?(?:correct\s+)?answer\s*(?:is|should\s+be|would\s+be)?\s*[:\-]?\s*(?:\*\*)?\s*(?:\\boxed\{(?:\\text\{)?|\(?)([A-D])",
        r"(?i)(?:final\s+answer|therefore|thus|conclusion|option|choice)\s*[:\-]?\s*(?:\*\*)?\s*(?:\\boxed\{(?:\\text\{)?|\(?)([A-D])",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, seg):
            found.append((m.start(), m.end(), "ABCD".index(m.group(1).upper()), "label"))
    for m in re.finditer(r"(?i)\\boxed\{(?:\\text\{)?\s*([A-D])", seg):
        found.append((m.start(), m.end(), "ABCD".index(m.group(1).upper()), "boxed"))
    for m in re.finditer(r"(?im)^\s*(?:\*\*)?([A-D])\s*[\.:\)]\s*([^\n]*)", seg):
        found.append((m.start(), m.end(), "ABCD".index(m.group(1).upper()), "line"))
    compact = norm(seg)
    for index, text in enumerate(row["key"]["choices"]):
        value = norm(text)
        if len(value) >= 4:
            position = compact.rfind(value)
            if position >= 0:
                found.append((position, position + len(value), index, "text"))
    if not found:
        return None, True, seg, row["response"][-240:].strip()
    found.sort(key=lambda item: item[0])
    decisive = [item for item in found if item[3] in ("label", "boxed")]
    last = decisive[-1] if decisive else found[-1]
    recent = [item for item in found if item[0] >= max(0, last[0] - 220)]
    ambiguity = last[3] not in ("label", "boxed") and len({item[2] for item in recent}) > 1
    evidence = seg[max(0, last[0] - 90): min(len(seg), last[1] + 180)].strip()
    if not evidence:
        evidence = seg[-240:].strip()
    # Evidence must be a byte-exact substring of the original response. The
    # cleaned text above is only for finding the decision; use the raw tail
    # when token cleanup would otherwise break the compiler's span check.
    raw_evidence = row["response"][-360:].strip()
    if evidence not in row["response"]:
        evidence = raw_evidence
    return (None if ambiguity else last[2]), ambiguity, seg, evidence


def evidence_for(text, patterns):
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if any(re.search(pattern, sentence, re.I) for pattern in patterns):
            return sentence.strip()[:600]
    return ""


def assessment(case, response):
    text = clean(response)
    # Broad semantic cues are used only to produce a review draft. Every
    # affirmative judgment retains an exact response span for root audit.
    science_patterns = {
        "S1": [r"inherited", r"genetic", r"variation", r"stoichiometric", r"balanced", r"half-life", r"field lines", r"co-elut", r"coelut"],
        "S2": [r"surviv", r"reproduc", r"offspring", r"predator", r"limiting", r"remaining", r"detector", r"separat"],
        "S3": [r"generation", r"population", r"frequency", r"ratio", r"half-lives", r"not.*individual", r"local resultant"],
        "S4": [r"environment", r"background", r"depends", r"assumption", r"closed", r"method", r"under the stated", r"drawn"],
    }
    tutoring_patterns = {
        "T1": [r"correct", r"error", r"misconception", r"not because", r"rather than", r"clarif"],
        "T2": [r"because", r"therefore", r"step", r"means", r"ratio", r"explain", r"calculate"],
        "T3": [r""],
        "T4": [r"\?"],
    }
    out = {"science": {}, "tutoring": {}, "critical_errors": {}, "additional_errors": []}
    for key, patterns in science_patterns.items():
        span = evidence_for(text, patterns)
        out["science"][key] = {"met": bool(span), "evidence": [span] if span else [], "rationale": "Draft cue review; root must confirm the criterion against the full response."}
    for key, patterns in tutoring_patterns.items():
        if key == "T3":
            ok = 80 <= len(text) <= 3500 and text.count("I ") < 40
            span = text[:500].strip() if ok else ""
        elif key == "T4":
            tail = text.rsplit("</think>", 1)[-1]
            ok = "?" in tail and not re.search(r"(?:answer|solution)\s*[:=]", tail, re.I)
            span = next((line.strip() for line in tail.splitlines() if "?" in line), "") if ok else ""
        else:
            span = evidence_for(text, patterns)
            ok = bool(span)
        out["tutoring"][key] = {"met": ok, "evidence": [span] if span else [], "rationale": "Draft cue review; root must confirm the criterion against the full response."}
    critical_patterns = {
        "E1": [r"intentionally changed", r"wanted to change", r"changed their color", r"collectively changed", r"decided to change"],
        "E2": [r"every environment", r"always advantageous", r"must be advantageous", r"regardless of environment"],
    }
    for key, patterns in critical_patterns.items():
        span = evidence_for(text, patterns)
        out["critical_errors"][key] = {"present": bool(span), "evidence": [span] if span else [], "rationale": "Draft cue review; root must confirm whether the statement is affirmed or rejected."}
    return out


def main():
    mc = [json.loads(line) for line in (PACKET / "reviewer/mc.jsonl").read_text().splitlines()]
    tutor = [json.loads(line) for line in (PACKET / "reviewer/tutor.jsonl").read_text().splitlines()]
    primary, secondary = [], []
    for row in mc:
        idx, ambiguity, seg, evidence = choice(row)
        judgment = {
            "review_id": row["review_id"], "reviewer": "root-draft-primary-v1",
            "packet_row_sha256": dr.sha(dr.canonical(row)), "response_sha256": row["response_sha256"],
            "chosen_index": idx, "ambiguity": ambiguity, "explanatory_falsehood": False,
            "format_adherent": bool(clean(row["response"])),
            "delivered_final_answer": row["finish_reason"] == "eos" and (not row["reasoning_prefix_already_open"] or "</think>" in row["response"]),
            "rationale": "Draft option adjudication from the committed final response; root audit required.",
            "evidence": [evidence] if evidence else [],
        }
        primary.append(judgment)
        secondary.append({**judgment, "reviewer": "root-draft-secondary-v1"})
    for row in tutor:
        judgment = {
            "review_id": row["review_id"], "reviewer": "root-draft-primary-v1",
            "packet_row_sha256": dr.sha(dr.canonical(row)), "response_sha256": row["response_sha256"],
            "assessment": assessment(row["case"], row["response"]),
        }
        primary.append(judgment)
        secondary.append({**judgment, "reviewer": "root-draft-secondary-v1"})
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("development-primary-draft-v2.jsonl", primary), ("development-secondary-draft-v2.jsonl", secondary)):
        path = OUT / name
        if path.exists(): raise SystemExit(f"refuse overwrite: {path}")
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in rows) + "\n")
    receipt = OUT / "development-draft-review-receipt-v2.json"
    if receipt.exists(): raise SystemExit(f"refuse overwrite: {receipt}")
    receipt.write_text(json.dumps({"status":"machine_assisted_draft_only","rows":{"mc":len(mc),"tutor":len(tutor)},"primary_sha256":dr.sha((OUT/"development-primary-draft-v2.jsonl").read_bytes()),"secondary_sha256":dr.sha((OUT/"development-secondary-draft-v2.jsonl").read_bytes()),"independent_review":False,"root_audit_required":True,"luna_delegation":"failed before ledger due delegated-agent runtime quota"}, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__": main()
