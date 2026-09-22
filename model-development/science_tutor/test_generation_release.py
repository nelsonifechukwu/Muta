"""CPU-only materialization/queue safety checks against captured real inventory."""

import argparse
import json
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor import generation_release as release

train = release.train
BASE = Path(__file__).resolve().parents[2] / "provenance/science-tutor-20260919/evaluation"
INVENTORY = BASE / "pilot-inventory-20260919T1850.json"
PROMPTS = BASE / "development72-v1/prompts.jsonl"


@pytest.fixture
def inventory():
    value = train.read_json(INVENTORY)
    assert (
        train.sha256_file(INVENTORY)
        == "32312e633b610c4d171530bfac597e69fef20d4db93119e01fdfc4565df43956"
    )
    return value


def prompt_ref(inventory):
    return {
        "path": inventory["host"]["release"] + "/prompts.jsonl",
        "sha256": train.sha256_file(PROMPTS),
    }


def test_actual_inventory_maps_exact_12_and_p3_single_adapter(inventory):
    config = release.make_config(inventory, prompt_ref(inventory), release.source_hashes())
    assert list(config["candidates"]) == release.ORDER
    assert len(config["candidates"]) == 12
    for i in range(1, 5):
        for stage, step in (("half", 63), ("end", 126)):
            candidate = config["candidates"][f"P{i}-{stage}"]
            assert candidate["base"] == config["candidates"][f"C{i}"]["base"]
            assert candidate["tokenizer"] == config["candidates"][f"C{i}"]["tokenizer"]
            assert Path(candidate["adapter"]["path"]).name == f"checkpoint-{step}"
    assert config["candidates"]["P3-half"]["adapter"]["tree_sha256"] != train.PILOT_TREE
    assert config["candidates"]["C3"]["adapter"]["tree_sha256"] == train.PILOT_TREE


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "duplicate_checkpoint",
        "lr",
        "tokens",
        "source",
        "tree",
        "seal",
        "incomplete",
        "parent",
        "relocation",
        "control_provenance",
        "tree_inventory",
    ],
)
def test_inventory_rejects_treatment_or_lineage_changes(inventory, attack):
    run = inventory["runs"]["P2"]
    if attack == "missing":
        inventory["controls"].pop("C4")
    elif attack == "duplicate_checkpoint":
        run["checkpoint_refs"][1] = run["checkpoint_refs"][0]
    elif attack == "lr":
        run["configuration"]["training"]["learning_rate"] = 1e-5
    elif attack == "tokens":
        run["completion"]["consumed_trainable_tokens"] += 1
    elif attack == "source":
        run["completion"]["source_sha256"]["train.py"] = "0" * 64
    elif attack == "tree":
        run["checkpoint_refs"][0]["tree_sha256"] = "0" * 64
    elif attack == "seal":
        run["checkpoint_refs"][0]["checkpoint_seal"]["sha256"] = "0" * 64
    elif attack == "incomplete":
        run["completion"]["status"] = "failed"
    elif attack == "parent":
        inventory["controls"]["C2"]["base"]["tree_sha256"] = train.BASE_TREES["upstream_fresh"]
    elif attack == "relocation":
        run["run_id"] = "science-pilot-muta-fresh-v1"
    elif attack == "control_provenance":
        inventory["control_verification"]["P4"]["original_control_inventory_existed"] = True
    else:
        tree = next(iter(inventory["input_trees"].values()))
        tree["files"][0]["sha256"] = "0" * 64
    with pytest.raises(train.AdmissionError):
        release.make_config(inventory, prompt_ref(inventory), release.source_hashes())


@pytest.fixture
def bundle(inventory, tmp_path, monkeypatch):
    old_root = str(release.ROOT)
    new_root = str(tmp_path / "campaign")
    monkeypatch.setattr(release, "ROOT", Path(new_root))
    for field in ("release", "outputs", "control"):
        inventory["host"][field] = inventory["host"][field].replace(old_root, new_root)
    inventory["host"]["python"] = sys.executable
    for run in inventory["runs"].values():
        run["configuration"]["output"] = run["configuration"]["output"].replace(old_root, new_root)
        run["completion_ref"]["path"] = run["completion_ref"]["path"].replace(old_root, new_root)
        for cp in run["checkpoint_refs"]:
            cp["path"] = cp["path"].replace(old_root, new_root)
            cp["checkpoint_seal"]["path"] = cp["checkpoint_seal"]["path"].replace(
                old_root, new_root
            )
        for tree in run["completion"]["all_checkpoints"]:
            tree["root"] = tree["root"].replace(old_root, new_root)
    captured = tmp_path / "captured.json"
    train.write_new(captured, inventory)
    args = argparse.Namespace(
        inventory=captured,
        inventory_sha256=train.sha256_file(captured),
        prompts=PROMPTS,
        remote_prompts=Path(inventory["host"]["release"]) / "prompts.jsonl",
        output=Path(inventory["host"]["release"]),
    )
    receipt = release.materialize(args)
    monkeypatch.setattr(release, "__file__", str(args.output / "sources/generation_release.py"))
    monkeypatch.setattr(release.os, "getuid", lambda: 1000)
    return argparse.Namespace(
        manifest=args.output / "manifest.json", manifest_sha256=receipt["manifest_sha256"]
    )


def rewrite(path, value):
    path = Path(path)
    path.chmod(0o644)
    path.write_text(json.dumps(value))


def test_materialization_preserves_reviewed_source_and_prompts(bundle):
    manifest, _, config, _ = release.load_manifest(bundle)
    assert (
        train.sha256_file(bundle.manifest.parent / "sources/evaluate_pilots.py")
        == release.EVALUATOR_SHA
    )
    assert train.sha256_file(bundle.manifest.parent / "prompts.jsonl") == train.sha256_file(PROMPTS)
    assert config["prompts"] == manifest["prompts"]
    assert not (bundle.manifest.parent / "campaign.json").stat().st_mode & 0o222


def test_rehashed_config_change_rejected(bundle):
    manifest = train.read_json(bundle.manifest)
    config = train.read_json(manifest["config"]["path"])
    config["generation"]["max_new_tokens"] = 512
    rewrite(manifest["config"]["path"], config)
    manifest["config"]["sha256"] = train.sha256_file(manifest["config"]["path"])
    rewrite(bundle.manifest, manifest)
    bundle.manifest_sha256 = train.sha256_file(bundle.manifest)
    with pytest.raises(train.AdmissionError, match="captured inventory"):
        release.load_manifest(bundle)


def test_existing_control_or_candidate_cannot_duplicate_launch(bundle, monkeypatch):
    manifest, _, config, _ = release.load_manifest(bundle)
    monkeypatch.setattr(release, "verify_remote", lambda *_: pytest.fail("remote work reached"))
    candidate = Path(config["output"]) / "C1"
    candidate.mkdir(parents=True)
    with pytest.raises(train.AdmissionError, match="output exists"):
        release.launch(bundle)
    assert (Path(manifest["host"]["control"]) / "FAILED.json").exists()
    with pytest.raises(FileExistsError):
        release.launch(bundle)


@pytest.mark.parametrize("failed_candidate", [None, "C2"])
def test_serial_queue_fails_stop_without_retry(bundle, monkeypatch, failed_candidate):
    manifest, _, _, _ = release.load_manifest(bundle)
    monkeypatch.setattr(release, "verify_remote", lambda *_: None)
    monkeypatch.setattr(release.evaluate.calibrate, "oracle_lock", lambda *_: nullcontext())
    monkeypatch.setattr(release.evaluate.calibrate, "host_snapshot", lambda: {"gpu": "fixture"})
    seen, verified = [], []

    def child(argv, log):
        candidate = argv[-1]
        seen.append(candidate)
        train.write_new(log, {"candidate": candidate})
        if candidate == failed_candidate:
            raise RuntimeError("owned child failed")

    def verify(config, config_ref, candidate, ids):
        assert candidate in seen
        assert len(ids) == 72
        verified.append(candidate)
        return {"path": config["output"] + "/" + candidate + "/COMPLETED.json", "sha256": "0" * 64}

    monkeypatch.setattr(release, "child", child)
    monkeypatch.setattr(release, "verify_candidate", verify)
    control = Path(manifest["host"]["control"])
    if failed_candidate:
        with pytest.raises(RuntimeError, match="owned child failed"):
            release.launch(bundle)
        assert seen == ["C1", "C2"]
        assert verified == ["C1"]
        assert (control / "FAILED.json").exists() and not (control / "COMPLETED.json").exists()
    else:
        result = release.launch(bundle)
        assert seen == release.ORDER
        assert verified == release.ORDER * 2
        assert result["candidate_count"] == 12


def fake_candidate(config, config_ref, name, ids):
    output = Path(config["output"]) / name
    prompts = release.evaluate.load_prompts(config["prompts"])
    rendered = [{**item, "prompt_ids": [10], "rendered_prompt": "fixture"} for item in prompts]
    for i in range(9):
        train.write_new(
            output / "batches" / f"batch-{i:04d}.json",
            {
                "offset": i * 8,
                "config_sha256": config_ref["sha256"],
                "candidate_id": name,
                "prompts": rendered[i * 8 : i * 8 + 8],
                "padded_prompt_ids": [[10]] * 8,
                "attention_mask": [[1]] * 8,
                "returned_sequence_ids": [[10, 1, 9]] * 8,
            },
        )
    responses = output / "responses.jsonl"
    responses.write_text(
        "\n".join(
            json.dumps(
                {
                    **item,
                    "candidate_id": name,
                    "generated_ids": [1, 9],
                    "padded_prompt_ids": [10],
                    "attention_mask": [1],
                }
            )
            for item in rendered
        )
    )
    result = {
        "status": "complete",
        "candidate_id": name,
        "config": config_ref,
        "source_sha256": config["source_sha256"],
        "prompts": config["prompts"],
        "completed_ids": ids,
        "completed_count": 72,
        "ranking_performed": False,
        "responses": train.file_receipt(responses),
        "inventory": train.tree_receipt(output),
    }
    train.write_new(output / "COMPLETED.json", result)


@pytest.mark.parametrize("attack", [None, "extra", "response", "batch", "source"])
def test_candidate_completion_inventory(bundle, attack):
    manifest, _, config, _ = release.load_manifest(bundle)
    ids = [row["id"] for row in release.evaluate.load_prompts(config["prompts"])]
    fake_candidate(config, manifest["config"], "C1", ids)
    output = Path(config["output"]) / "C1"
    if attack == "extra":
        train.write_new(output / "extra.json", {})
    elif attack == "response":
        (output / "responses.jsonl").write_text("{}\n")
    elif attack == "batch":
        (output / "batches/batch-0000.json").unlink()
    elif attack == "source":
        receipt = train.read_json(output / "COMPLETED.json")
        receipt["source_sha256"]["train.py"] = "0" * 64
        rewrite(output / "COMPLETED.json", receipt)
    if attack is None:
        assert release.verify_candidate(config, manifest["config"], "C1", ids)["sha256"]
    else:
        with pytest.raises(train.AdmissionError):
            release.verify_candidate(config, manifest["config"], "C1", ids)
