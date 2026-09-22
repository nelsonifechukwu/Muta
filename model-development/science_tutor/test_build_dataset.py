import pytest
from build_dataset import (
    NearIndex,
    choose_groups,
    group_rows,
    source_split,
    training_view,
    validate,
)


def row(id="a", group="g", source="s", question="How does ice melt?"):
    return {
        "id": id,
        "group_id": group,
        "source": source,
        "source_id": id,
        "source_revision": "abc",
        "license": "MIT",
        "subject": "science",
        "capabilities": ["conceptual"],
        "quality": {"independent_verification": False},
        "source_split": "train",
        "messages": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": "Heat is transferred."},
        ],
    }


def test_roles_and_control_tokens():
    validate(row())
    bad = row()
    bad["messages"][1]["role"] = "user"
    with pytest.raises(ValueError, match="nonalternating"):
        validate(bad)
    bad = row()
    bad["messages"][0]["content"] = "<|im_start|>"
    with pytest.raises(ValueError, match="control"):
        validate(bad)


def test_exact_prompt_cross_source_group_union():
    rows = [
        row(),
        row("b", "another", "s2"),
        row("c", "another", "s2", "A different conversation variant"),
    ]
    groups = group_rows(rows)
    assert len(groups) == 1
    assert len(next(iter(groups.values()))) == 3


def test_source_tests_never_return_train():
    r = row()
    r["source_split"] = "test"
    assert source_split(r) == "holdout"
    r["source_split"] = "validation"
    assert source_split(r) == "dev"


def test_near_index_containment():
    index = NearIndex()
    text = "Explain how the movement of particles changes when the liquid is heated"
    index.add("frozen", text)
    assert index.matches("Please answer: " + text) == ["frozen"]
    assert not index.matches("Identify the different parts of a living cell")


def test_cap_never_splits_conversation_group():
    selected, reserve = choose_groups({"g": [row(), row("b")]}, {"s": 1})
    assert not selected
    assert len(reserve) == 2


def test_trailing_student_preserved_as_unsupervised_source_evidence():
    original = row()
    original["messages"].append({"role": "user", "content": "Now I understand."})
    result = training_view(original)
    validate(result)
    assert len(original["messages"]) == 3
    assert len(result["messages"]) == 2
    assert result["unsupervised_trailing_student_turn"] == original["messages"][-1]
    assert result["source_messages_sha256"]


def test_builder_split_priority_group_exclusion_and_quarantine(tmp_path, monkeypatch):
    import argparse
    import json

    import build_dataset as module

    known = NearIndex()
    known.add("frozen", "A known benchmark problem exactly repeated for this example")
    monkeypatch.setattr(module, "known_index", lambda _: (known, {}))
    train = row("train")
    test = row("test")
    test["source_split"] = "test"
    leak = row(
        "leak", "bad", question="A known benchmark problem exactly repeated for this example"
    )
    sibling = row(
        "sibling", "bad", question="A paraphrased version with completely different words"
    )
    bad = row("blocked", "blocked", question="A wholly separate rejected item")
    bad["eligibility"] = "quarantine"
    inp = tmp_path / "input.jsonl"
    inp.write_text("\n".join(json.dumps(x) for x in [train, test, leak, sibling, bad]) + "\n")
    out = tmp_path / "out"
    module.build(
        argparse.Namespace(output=out, repo=tmp_path, sources=[inp], cap=[], blocklist=None)
    )
    assert not (out / "train.jsonl").read_text()
    held = [json.loads(x) for x in (out / "holdout.jsonl").read_text().splitlines()]
    assert [x["id"] for x in held] == ["test"]
    reasons = {
        x["id"]: x["reason"]
        for x in map(json.loads, (out / "exclusions.jsonl").read_text().splitlines())
    }
    assert reasons["sibling"] == "known_evaluation_group_overlap"
    assert reasons["blocked"] == "source_not_eligible"


def test_sciq_distractors_do_not_separate_identical_questions():
    a, b = row("a", "a", "sciq"), row("b", "b", "sciq")
    a.update(question="Which element is essential to life?", choices=["carbon", "argon"])
    b.update(question=a["question"], choices=["sulfur", "carbon"])
    assert len(group_rows([a, b])) == 1


def test_reviewed_policy_binds_exact_raw_bytes_and_receipts(tmp_path, monkeypatch):
    import argparse
    import json

    import build_dataset as b

    original = row(source="muta_authored_science")
    original["eligibility"] = "candidate_pending_review"
    reviewed = {
        "items": [
            {
                "id": "a",
                "decision": "acceptable_bounded_review",
                "row_canonical_sha256": b.digest(b.canonical(original)),
            }
        ]
    }
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(reviewed))
    policy = {
        "require_reviewed_ids_for_sources": {"muta_authored_science": ["a"]},
        "review_receipts": [{"path": "review.json", "sha256": b.file_hash(review_path)}],
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy))
    assert b.reviewed_policy(policy_path)[1]["a"] == reviewed["items"][0]["row_canonical_sha256"]
    altered = dict(original, messages=[dict(m) for m in original["messages"]])
    altered["messages"][1]["content"] = "An altered, unreviewed answer."
    inp = tmp_path / "input.jsonl"
    inp.write_text(json.dumps(altered) + "\n")
    monkeypatch.setattr(b, "known_index", lambda _: (NearIndex(), {}))
    with pytest.raises(ValueError, match="reviewed raw-row hash"):
        b.build(
            argparse.Namespace(
                output=tmp_path / "out", repo=tmp_path, sources=[inp], cap=[], blocklist=policy_path
            )
        )
    review_path.write_text("{}")
    with pytest.raises(ValueError, match="receipt hash"):
        b.reviewed_policy(policy_path)


def test_index_all_student_turns_without_overwriting_earlier_shingles():
    from build_dataset import index_row, student_texts

    original = row()
    followup = "Explain why the same experimental result does not establish the proposed cause"
    original["messages"] += [
        {"role": "user", "content": followup},
        {"role": "assistant", "content": "Consider confounding variables."},
    ]
    index = NearIndex()
    keys = index_row(index, original)
    assert len(keys) == 2
    assert index.matches(followup) == [keys[1]]
    assert index.matches(original["messages"][0]["content"]) == [keys[0]]
    assert followup in student_texts(original)


def test_scienceqa_plaintext_repairs_record_original_target():
    source = row(source="scienceqa")
    source["messages"][1]["content"] = (
        "Read the underlined text carefully. They are not physical changes."
    )
    transformed = training_view(source)
    assert (
        transformed["messages"][1]["content"]
        == "Read the relevant passage carefully. They are not only physical changes."
    )
    assert transformed["training_transformations"][0]["original_target_sha256"]
    assert source["messages"][1]["content"].startswith("Read the underlined")
