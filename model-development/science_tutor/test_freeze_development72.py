"""CPU-only admission and materialization tests; outputs are temporary only."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "freeze_development72", Path(__file__).with_name("freeze_development72.py")
)
assert SPEC and SPEC.loader
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


@pytest.fixture(scope="module")
def inputs():
    return freeze.load_inputs(freeze.ROOT)


def changed(inputs, path, transform, *, jsonl=False):
    result = dict(inputs)
    value = freeze.rows(result[path]) if jsonl else freeze.parse(result[path])
    transform(value)
    result[path] = (
        b"".join(freeze.canonical(row) + b"\n" for row in value)
        if jsonl
        else freeze.canonical(value)
    )
    return result


def run_freeze(tmp_path, **kwargs):
    return freeze.freeze(
        reviewed_builder_sha256=freeze.sha(Path(freeze.__file__).read_bytes()),
        destination=tmp_path / "development72-v1",
        **kwargs,
    )


def test_actual_reviewed_inputs_exact_72_projection_and_keys(inputs):
    products = freeze.assemble(inputs)
    assert set(products) == {"prompts.jsonl", "mc_keys.jsonl", "tutor_rubrics.jsonl"}
    prompts = freeze.rows(products["prompts.jsonl"])
    keys = freeze.rows(products["mc_keys.jsonl"])
    rubrics = freeze.rows(products["tutor_rubrics.jsonl"])
    review = freeze.parse(inputs[freeze.MC_REVIEW])
    assert len(prompts) == len({r["id"] for r in prompts}) == 72
    assert len(keys) == 64 and len(rubrics) == 8
    assert [r["id"] for r in prompts[:64]] == review["final64_ids"]
    assert freeze.sha(freeze.canonical(review["final64_ids"])) == (
        "b80b4a798c56d5a8f53d09ef82f02503d667163790523851988659b6717b3c3b"
    )
    assert all(set(r) == {"id", "messages"} for r in prompts)
    assert all([m["role"] for m in r["messages"]] == ["user"] for r in prompts[:64])
    assert all(
        [m["role"] for m in r["messages"]] == ["user", "assistant", "user"] for r in prompts[64:]
    )
    pool = freeze.index(freeze.rows(inputs[freeze.PILOT_DEV]))
    dev = freeze.rows(inputs[freeze.HELDOUT + "dev_cases.jsonl"])
    for prompt, key in zip(prompts[:64], keys, strict=True):
        assert prompt["messages"] == pool[prompt["id"]]["messages"][:-1]
        assert key["model_messages_sha256"] == freeze.sha(freeze.canonical(prompt["messages"]))
    assert prompts[64:] == [{"id": r["id"], "messages": r["messages"]} for r in dev]
    assert all("messages" not in r for r in rubrics)
    final = freeze.rows(inputs[freeze.HELDOUT + "final_cases.jsonl"])
    assert not ({r["id"] for r in final} & {r["id"] for r in prompts})
    assert freeze.assemble(inputs) == products


def test_actual_freeze_temp_manifest_complete_and_sources_unchanged(tmp_path, inputs):
    before = {p: freeze.sha(freeze.safe_read(freeze.ROOT, p)) for p in inputs}
    manifest = run_freeze(tmp_path)
    out = tmp_path / "development72-v1"
    assert {p.name for p in out.iterdir()} == {
        "prompts.jsonl",
        "mc_keys.jsonl",
        "tutor_rubrics.jsonl",
        "manifest.json",
    }
    assert json.loads((out / "manifest.json").read_bytes()) == manifest
    assert manifest["rows"] == 72 and manifest["inference_performed"] is False
    assert manifest["reserved_final_cases_included"] is False
    for name, binding in manifest["artifacts"].items():
        raw = (out / name).read_bytes()
        assert freeze.sha(raw) == binding["sha256"]
        assert len(raw) == binding["bytes"]
        assert len(freeze.rows(raw)) == binding["rows"]
    bound = {r["path"]: r["sha256"] for r in manifest["input_bindings"]}
    assert set(bound) == set(inputs) | {freeze.BUILDER, freeze.TESTS, freeze.PLAN}
    assert all(
        bound[p] == digest == freeze.sha(freeze.safe_read(freeze.ROOT, p))
        for p, digest in before.items()
    )


@pytest.mark.parametrize("raw", [b'{"id":1,"id":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_strict_json_rejects_duplicates_nonfinite(raw):
    with pytest.raises(ValueError):
        freeze.parse(raw)


@pytest.mark.parametrize("raw", [b"", b"{}\n\n{}\n", b"[]\n", b"\xff\n"])
def test_jsonl_rejects_empty_blank_nonobject_invalid_utf8(raw):
    with pytest.raises((ValueError, UnicodeError)):
        freeze.rows(raw)


def test_duplicate_ids_rejected(inputs):
    bad = changed(
        inputs, freeze.PILOT_DEV, lambda x: x.__setitem__(1, copy.deepcopy(x[0])), jsonl=True
    )
    with pytest.raises(ValueError, match="duplicate row id"):
        freeze.assemble(bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict", "pending"),
        ("reviewer", "self"),
        ("remaining_blockers_for_proposed64", ["unresolved"]),
        ("original_v1_admission_allowed", True),
    ],
)
def test_mc_review_requires_exact_admission(inputs, field, value):
    bad = changed(inputs, freeze.MC_REVIEW, lambda r: r.__setitem__(field, value))
    with pytest.raises(ValueError, match="MC review not admitted"):
        freeze.assemble(bad)


def test_missing_rank_cannot_skip_to_arbitrary_approved_id(inputs):
    def edit(r):
        # Replace a first-ranked review with a source row outside the consumed prefix.
        r["reviews"][0]["id"] = "scienceqa:unreviewed"

    with pytest.raises(ValueError, match="unreviewed rank gap"):
        freeze.assemble(changed(inputs, freeze.MC_REVIEW, edit))


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("fixed_bucket_rank", 2, "rank mismatch"),
        ("stage", "ranked_replacement_candidate", "stage mismatch"),
        ("row_canonical_sha256", "0" * 64, "row/messages/key mismatch"),
        ("model_messages_sha256", "0" * 64, "row/messages/key mismatch"),
        ("answer_index", 1, "row/messages/key mismatch"),
        ("verified_answer_index", True, "unverified key"),
        ("verdict", "probably_correct", "unrecognized MC review verdict"),
    ],
)
def test_review_rank_source_key_and_verdict_checks(inputs, field, value, error):
    bad = changed(inputs, freeze.MC_REVIEW, lambda r: r["reviews"][0].__setitem__(field, value))
    with pytest.raises(ValueError, match=error):
        freeze.assemble(bad)


def test_rejected_original_not_admitted_even_if_final_ids_edited(inputs):
    def edit(r):
        rejected = next(x for x in r["reviews"] if x["verdict"] == freeze.REJECT)
        r["final64_ids"][40] = rejected["id"]

    with pytest.raises(ValueError, match="final IDs/order mismatch"):
        freeze.assemble(changed(inputs, freeze.MC_REVIEW, edit))


def test_final_key_manifest_cannot_disagree(inputs):
    bad = changed(
        inputs,
        freeze.MC_REVIEW,
        lambda r: r["final64_answer_keys"][0].__setitem__("answer_letter", "Z"),
    )
    with pytest.raises(ValueError, match="final keys mismatch"):
        freeze.assemble(bad)


def test_assistant_target_leakage_role_corruption_refused(inputs):
    def edit(pool):
        row = next(r for r in pool if r["id"] == "scienceqa:5517")
        row["messages"].append({"role": "assistant", "content": "leaked answer"})

    with pytest.raises(ValueError, match="message count mismatch"):
        freeze.assemble(changed(inputs, freeze.PILOT_DEV, edit, jsonl=True))


def test_original_proposal_must_reproduce(inputs):
    with pytest.raises(ValueError, match="original 64 proposal/rank mismatch"):
        freeze.assemble(
            changed(inputs, freeze.ORIGINAL + "review.jsonl", lambda r: r.reverse(), jsonl=True)
        )


@pytest.mark.parametrize(
    "path,field,value,error",
    [
        (freeze.TUTOR_REVIEW, "verdict", "pending", "tutor review not admitted"),
        (freeze.OVERLAP_REVIEW, "status", "pending", "overlap review failed"),
        (freeze.OVERLAP_REVIEW, "hits", [{"match": True}], "overlap review failed"),
        (freeze.OVERLAP_REVIEW, "within_heldout_nonself_hits", ["hit"], "overlap review failed"),
    ],
)
def test_tutor_requires_content_and_overlap_go(inputs, path, field, value, error):
    with pytest.raises(ValueError, match=error):
        freeze.assemble(changed(inputs, path, lambda r: r.__setitem__(field, value)))


def test_tutor_case_hash_not_numeric_agreement_alone(inputs):
    bad = changed(
        inputs,
        freeze.TUTOR_REVIEW,
        lambda r: r["per_case_review"][0].__setitem__("sha256", "0" * 64),
    )
    with pytest.raises(ValueError, match="heldout case hash/split mismatch"):
        freeze.assemble(bad)


def test_final_case_cannot_replace_dev_case(inputs):
    final = freeze.rows(inputs[freeze.HELDOUT + "final_cases.jsonl"])[0]
    bad = changed(
        inputs, freeze.HELDOUT + "dev_cases.jsonl", lambda r: r.__setitem__(0, final), jsonl=True
    )
    with pytest.raises(ValueError, match="heldout source case join mismatch"):
        freeze.assemble(bad)


def test_tutor_context_must_not_drop_prior_assistant(inputs):
    bad = changed(
        inputs, freeze.HELDOUT + "dev_prompts.jsonl", lambda r: r[0]["messages"].pop(1), jsonl=True
    )
    with pytest.raises(ValueError, match="heldout prompt projection mismatch"):
        freeze.assemble(bad)


def test_pinned_review_hash_mismatch_before_parse(monkeypatch):
    original = freeze.safe_read
    monkeypatch.setattr(
        freeze,
        "safe_read",
        lambda root, path: b"not JSON" if path == freeze.MC_REVIEW else original(root, path),
    )
    with pytest.raises(ValueError, match="pinned input hash mismatch"):
        freeze.load_inputs(freeze.ROOT)


def test_source_hash_mismatch_before_parse(monkeypatch):
    original = freeze.safe_read
    monkeypatch.setattr(
        freeze,
        "safe_read",
        lambda root, path: b"not JSON" if path == freeze.PILOT_DEV else original(root, path),
    )
    with pytest.raises(ValueError, match="review source binding mismatch"):
        freeze.load_inputs(freeze.ROOT)


def test_reviewed_builder_hash_required_before_writes(tmp_path):
    out = tmp_path / "packet"
    with pytest.raises(ValueError, match="externally reviewed builder hash mismatch"):
        freeze.freeze(reviewed_builder_sha256="0" * 64, destination=out)
    assert not out.exists()


def test_existing_output_is_not_overwritten(tmp_path):
    out = tmp_path / "development72-v1"
    out.mkdir()
    sentinel = out / "preserve.txt"
    sentinel.write_bytes(b"keep")
    with pytest.raises(ValueError, match="output already exists"):
        run_freeze(tmp_path)
    assert sentinel.read_bytes() == b"keep" and list(out.iterdir()) == [sentinel]


def test_symlinked_output_ancestor_refused(tmp_path):
    target = tmp_path / "actual"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked output path"):
        run_freeze(alias)
    assert not list(target.iterdir())


def test_symlinked_input_refused(tmp_path):
    target = tmp_path / "actual.json"
    target.write_bytes(b"{}")
    (tmp_path / "alias.json").symlink_to(target)
    with pytest.raises(ValueError, match="symlinked input path"):
        freeze.safe_read(tmp_path, "alias.json")


def test_unsafe_relative_input_refused(tmp_path):
    with pytest.raises(ValueError, match="unsafe input path"):
        freeze.safe_read(tmp_path, "../secret")


def test_changed_input_before_writes_refused(tmp_path, monkeypatch):
    def changed_input(root, loaded):
        raise ValueError("input changed during freeze: synthetic")

    monkeypatch.setattr(freeze, "_unchanged", changed_input)
    with pytest.raises(ValueError, match="input changed"):
        run_freeze(tmp_path)
    assert not (tmp_path / "development72-v1").exists()


def test_changed_input_after_writes_preserves_failure_no_seal(tmp_path, monkeypatch):
    original = freeze._unchanged
    calls = []

    def changed_input(root, loaded):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("input changed during freeze: synthetic")
        original(root, loaded)

    monkeypatch.setattr(freeze, "_unchanged", changed_input)
    with pytest.raises(ValueError, match="input changed"):
        run_freeze(tmp_path)
    out = tmp_path / "development72-v1"
    assert not (out / "manifest.json").exists()
    failure = json.loads((out / "FAILED.json").read_bytes())
    assert failure["automatic_retry"] is False and failure["status"] == "failed_before_manifest"
    assert len(freeze.rows((out / "prompts.jsonl").read_bytes())) == 72


def test_failure_marker_write_failure_keeps_original_exception_chain(tmp_path, monkeypatch):
    original_open = Path.open
    original_check = freeze._unchanged
    calls = []

    def fail_after_data(root, loaded):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("original synthetic failure")
        original_check(root, loaded)

    def marker_open(path, *args, **kwargs):
        if path == tmp_path / "development72-v1" / "FAILED.json":
            raise OSError("injected unavailable failure marker")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(freeze, "_unchanged", fail_after_data)
    monkeypatch.setattr(Path, "open", marker_open)
    with pytest.raises(RuntimeError, match="failure marker also could not be written") as caught:
        run_freeze(tmp_path)
    assert str(caught.value.__cause__) == "original synthetic failure"
    assert not (tmp_path / "development72-v1" / "manifest.json").exists()
    with pytest.raises(ValueError, match="output already exists"):
        run_freeze(tmp_path)


def test_real_source_change_check_without_mutating_real_files(inputs, monkeypatch):
    original = freeze.safe_read
    monkeypatch.setattr(
        freeze,
        "safe_read",
        lambda root, path: (
            inputs[path] + b" " if path == freeze.MC_REVIEW else original(root, path)
        ),
    )
    with pytest.raises(ValueError, match="input changed during freeze"):
        freeze._unchanged(freeze.ROOT, inputs)


@pytest.mark.parametrize("failure_stage", ["write", "close"])
def test_manifest_write_or_close_failure_quarantines_evidence(tmp_path, monkeypatch, failure_stage):
    original_open = Path.open

    class BrokenManifest:
        def __init__(self, path, *args, **kwargs):
            self.handle = original_open(path, *args, **kwargs)

        def __enter__(self):
            return self

        def write(self, raw):
            if failure_stage == "write":
                self.handle.write(raw[:20])
                raise OSError("injected manifest write failure")
            return self.handle.write(raw)

        def __exit__(self, *args):
            self.handle.close()
            if failure_stage == "close":
                raise OSError("injected manifest close failure")

    def patched_open(path, *args, **kwargs):
        if path == tmp_path / "development72-v1" / "manifest.json":
            return BrokenManifest(path, *args, **kwargs)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched_open)
    with pytest.raises(OSError, match=f"injected manifest {failure_stage} failure"):
        run_freeze(tmp_path)
    out = tmp_path / "development72-v1"
    assert not (out / "manifest.json").exists()
    preserved = (out / "manifest.FAILED.json").read_bytes()
    if failure_stage == "write":
        assert len(preserved) == 20
    else:
        assert json.loads(preserved)["rows"] == 72
    failure = json.loads((out / "FAILED.json").read_bytes())
    assert failure["terminal_manifest_valid"] is False
    assert failure["automatic_retry"] is False
    assert failure["error"] == f"injected manifest {failure_stage} failure"
    assert len(freeze.rows((out / "prompts.jsonl").read_bytes())) == 72
