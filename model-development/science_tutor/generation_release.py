"""Immutable 12-candidate manifest and serial fail-stop science generation queue."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

try:
    from . import evaluate_pilots as evaluate
except ImportError:
    import evaluate_pilots as evaluate

train = evaluate.train
EVALUATOR_SHA = "74c1037f298533a37f8637fb37fb358e58555766a054d8289892871a19f189df"
KINDS = {"P1": "upstream_fresh", "P2": "muta_fresh", "P3": "pilot_adapter", "P4": "deepseek_fresh"}
ORDER = ["C1", "C2", "C3", "C4"] + [
    f"{pilot}-{stage}" for pilot in KINDS for stage in ("half", "end")
]
ROOT = Path("/lambda/nfs/awf-tmp/muta/campaign-20260918/science-tutor-20260919")
CHILD_SECONDS = 7200


def require(condition, message):
    if not condition:
        raise train.AdmissionError(message)


def source_hashes():
    result = evaluate.source_hashes()
    require(result["evaluate_pilots.py"] == EVALUATOR_SHA, "reviewed evaluator changed")
    result["generation_release.py"] = train.sha256_file(__file__)
    return result


def checked_ref(ref, *, tree=False):
    key = "tree_sha256" if tree else "sha256"
    require(isinstance(ref, dict) and {"path", key} <= ref.keys(), "missing path/hash reference")
    require(
        Path(ref["path"]).is_absolute() and ".." not in Path(ref["path"]).parts,
        "unsafe inventory path",
    )
    require(
        isinstance(ref[key], str)
        and len(ref[key]) == 64
        and all(c in "0123456789abcdef" for c in ref[key]),
        "invalid SHA256 reference",
    )
    return {"path": ref["path"], key: ref[key]}


def validate_tree(receipt):
    files = receipt["files"]
    paths = [row["path"] for row in files]
    require(
        files
        and paths == sorted(set(paths))
        and all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in paths),
        "unsafe/duplicate tree inventory paths",
    )
    digest = hashlib.sha256(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in files).encode()
    ).hexdigest()
    require(
        receipt["tree_sha256"] == digest
        and receipt["bytes"] == sum(row["bytes"] for row in files)
        and receipt["file_count"] == len(files),
        "tree inventory digest/size mismatch",
    )


def validate_inventory(inventory):
    require(
        set(inventory)
        == {
            "schema_version",
            "host",
            "controls",
            "runs",
            "remote_verification",
            "input_trees",
            "control_verification",
            "collector",
        }
        and inventory["schema_version"] == 1,
        "unexpected remote inventory schema",
    )
    host = inventory["host"]
    require(set(host) == {"python", "release", "outputs", "control"}, "unexpected host descriptor")
    for path in host.values():
        require(
            isinstance(path, str) and Path(path).is_absolute() and ".." not in Path(path).parts,
            "absolute normalized host path required",
        )
    locations = [Path(host[field]) for field in ("release", "outputs", "control")]
    require(
        all(path.is_relative_to(ROOT) and path != ROOT for path in locations),
        "new paths must stay in science campaign",
    )
    require(
        len(set(locations)) == 3
        and not any(
            first.is_relative_to(second)
            for first in locations
            for second in locations
            if first != second
        ),
        "release/output/control paths must be disjoint",
    )
    require(
        inventory["remote_verification"]
        == {
            "all_run_inventories_verified": True,
            "all_control_completions_verified": True,
            "all_input_trees_verified": True,
        },
        "remote verification is incomplete",
    )
    require(
        set(inventory["controls"]) == {"C1", "C2", "C3", "C4"}
        and set(inventory["runs"]) == set(KINDS),
        "exact four controls/four terminal pilots required",
    )
    controls = copy.deepcopy(inventory["controls"])
    checked_ref(inventory["collector"])
    require(
        set(inventory["control_verification"]) == set(KINDS),
        "missing controller verification notes",
    )
    expected_input_paths = set()
    for index, (pilot, kind) in enumerate(KINDS.items(), 1):
        control = controls[f"C{index}"]
        profile = "deepseek_native" if index == 4 else "qwen_native"
        require(
            set(control)
            == (
                {"profile", "chat_template_sha256", "base", "tokenizer", "adapter"}
                if index == 3
                else {"profile", "chat_template_sha256", "base", "tokenizer"}
            ),
            "unexpected control fields/adapter",
        )
        base = checked_ref(control["base"], tree=True)
        tokenizer = checked_ref(control["tokenizer"], tree=True)
        for name in ("base", "tokenizer", "adapter"):
            if name in control:
                source_ref = control[name]
                expected_input_paths.add(source_ref["path"])
                source_tree = inventory["input_trees"][source_ref["path"]]
                validate_tree(source_tree)
                require(
                    source_tree["root"] == source_ref["path"]
                    and source_tree["tree_sha256"] == source_ref["tree_sha256"],
                    "captured input tree identity mismatch",
                )
        verification = inventory["control_verification"][pilot]
        if index == 4:
            require(
                verification.get("mode")
                == "original_explicit_refs_verified_plus_retrospective_directory_snapshot"
                and verification.get("original_control_inventory_existed") is False,
                "P4 retrospective controller provenance missing",
            )
            validate_tree(verification["observed_inventory"])
        else:
            require(
                verification == {"mode": "original_control_inventory_verified"},
                "original controller inventory was not verified",
            )
        expected_base = evaluate.DEEPSEEK_TREE if index == 4 else train.BASE_TREES[kind]
        require(
            base["tree_sha256"] == expected_base
            and control["profile"] == profile
            and control["chat_template_sha256"] == evaluate.PROFILES[profile]["template"],
            "control parent/native profile mismatch",
        )
        if index == 3:
            adapter = control["adapter"]
            require(
                set(adapter) == {"path", "tree_sha256", "parent_base_tree_sha256"}
                and checked_ref(adapter, tree=True)["tree_sha256"] == train.PILOT_TREE
                and adapter["parent_base_tree_sha256"] == expected_base,
                "C3 must be exact original winning adapter",
            )
        run = inventory["runs"][pilot]
        require(
            set(run)
            == {
                "run_id",
                "configuration",
                "config_ref",
                "completion_ref",
                "completion",
                "control_completion_ref",
                "checkpoint_refs",
                "base",
                "tokenizer",
            },
            "unexpected pilot inventory fields",
        )
        config = run["configuration"]
        config_ref = checked_ref(run["config_ref"])
        completion_ref = checked_ref(run["completion_ref"])
        checked_ref(run["control_completion_ref"])
        output = Path(config["output"])
        require(
            output.is_relative_to(ROOT / "runs") and output != ROOT / "runs",
            "training output outside Oracle science runs",
        )
        expected_run = (
            "science-pilot-"
            + kind.replace("_", "-")
            + "-v1"
            + ("-oracle-relocation" if index in (2, 3) else "")
        )
        require(
            run["run_id"] == config["run_id"] == expected_run
            and config["initialization"]["kind"] == kind,
            "pilot run identity/relocation mismatch",
        )
        require(
            completion_ref["path"] == str(output / "COMPLETED.json"),
            "trainer completion path mismatch",
        )
        require(
            checked_ref(run["base"], tree=True) == base == config["initialization"]["base"]
            and checked_ref(run["tokenizer"], tree=True)
            == tokenizer
            == config["initialization"]["tokenizer"],
            "pilot/control parent or tokenizer mismatch",
        )
        require(
            config["tokenization"]
            == {
                "max_length": 4096,
                "chat_template_sha256": control["chat_template_sha256"],
                "split_policy": "preserve_whole_conversation",
            },
            "pilot tokenization treatment mismatch",
        )
        expected_tokens = 249164 if index == 4 else 257341
        expected_training = {
            "seed": 3407,
            "micro_batch_size": 4,
            "gradient_accumulation": 16,
            "effective_batch_size": 64,
            "max_steps": 126,
            "expected_trainable_tokens": expected_tokens,
            "learning_rate": 5e-6,
            "weight_decay": 0.0,
            "warmup_ratio": 0.03,
            "logging_steps": 1,
            "eval_batch_size": 1,
            "gradient_checkpointing": True,
        }
        require(
            train.canonical(config["training"]) == train.canonical(expected_training),
            "pilot numeric training treatment changed",
        )
        require(
            config["lora"]
            == {"r": 16, "alpha": 16, "dropout": 0.0, "target_modules": sorted(train.TARGETS)},
            "pilot LoRA treatment changed",
        )
        if index == 3:
            require(
                config["initialization"].get("adapter") == {**controls["C3"]["adapter"]},
                "P3 must continue the exact C3 adapter",
            )
        else:
            require(
                "adapter" not in config["initialization"],
                "fresh pilot unexpectedly initialized an adapter",
            )
        completion = run["completion"]
        require(
            completion.get("status") == "complete"
            and completion.get("run_id") == expected_run
            and completion.get("config_sha256") == config_ref["sha256"]
            and completion.get("completed_steps") == 126
            and completion.get("consumed_trainable_tokens") == expected_tokens
            and completion.get("source_sha256") == evaluate.PROFILES[profile]["training_sources"]
            and completion.get("resumed_from_step") == 0,
            "pilot terminal evidence mismatch",
        )
        checkpoints = run["checkpoint_refs"]
        require(
            len(checkpoints) == 2 and [ref["step"] for ref in checkpoints] == [63, 126],
            "exact ordered half/end checkpoints required",
        )
        terminal_checkpoints = completion["all_checkpoints"]
        require(len(terminal_checkpoints) == 2, "terminal checkpoint inventory count mismatch")
        for ref, terminal in zip(checkpoints, terminal_checkpoints, strict=True):
            require(
                set(ref) == {"step", "path", "tree_sha256", "checkpoint_seal"},
                "unexpected checkpoint reference fields",
            )
            adapter_ref = checked_ref(ref, tree=True)
            seal_ref = checked_ref(ref["checkpoint_seal"])
            path = output / "checkpoints" / f"checkpoint-{ref['step']}"
            require(
                adapter_ref["path"] == terminal["root"] == str(path)
                and adapter_ref["tree_sha256"] == terminal["tree_sha256"]
                and seal_ref["path"] == str(path / "COMPLETE.json"),
                "checkpoint path/tree/seal binding mismatch",
            )
            validate_tree(terminal)
            files = terminal["files"]
            names = {row["path"] for row in files}
            require(
                evaluate.CHECKPOINT_FILES <= names
                and not names - evaluate.CHECKPOINT_FILES - {"README.md"}
                and len(names) == len(files)
                and all(row["bytes"] > 0 for row in files),
                "terminal checkpoint artifacts missing/duplicated",
            )
            require(
                next(row["sha256"] for row in files if row["path"] == "COMPLETE.json")
                == seal_ref["sha256"],
                "checkpoint COMPLETE hash mismatch",
            )
    require(
        len({run["configuration"]["output"] for run in inventory["runs"].values()}) == 4,
        "duplicate pilot output",
    )
    require(
        set(inventory["input_trees"]) == expected_input_paths,
        "unexpected/missing captured input trees",
    )
    return controls


def make_config(inventory, prompt_ref, sources):
    candidates = validate_inventory(inventory)
    checked_ref(prompt_ref)
    require(
        prompt_ref["path"] == str(Path(inventory["host"]["release"]) / "prompts.jsonl"),
        "prompts must be staged at the new release/prompts.jsonl",
    )
    for index, pilot in enumerate(KINDS, 1):
        for stage, checkpoint in zip(
            ("half", "end"), inventory["runs"][pilot]["checkpoint_refs"], strict=True
        ):
            candidate = copy.deepcopy(candidates[f"C{index}"])
            candidate["adapter"] = {
                "path": checkpoint["path"],
                "tree_sha256": checkpoint["tree_sha256"],
                "parent_base_tree_sha256": candidate["base"]["tree_sha256"],
                "checkpoint_seal": checked_ref(checkpoint["checkpoint_seal"]),
            }
            candidates[f"{pilot}-{stage}"] = candidate
    return {
        "schema_version": 1,
        "output": inventory["host"]["outputs"],
        "gpu_lock": evaluate.calibrate.GPU_LOCK,
        "prompts": prompt_ref,
        "source_sha256": {name: sources[name] for name in evaluate.source_hashes()},
        "generation": evaluate.GENERATION,
        "candidates": candidates,
    }


def materialize(args):
    inventory_ref = train.verify_ref(
        {"path": str(Path(args.inventory).absolute()), "sha256": args.inventory_sha256}
    )
    inventory = train.read_json(args.inventory)
    sources = source_hashes()
    local_prompts = train.file_receipt(args.prompts)
    evaluate.load_prompts(local_prompts)
    prompt_ref = {"path": str(args.remote_prompts), "sha256": local_prompts["sha256"]}
    config = make_config(inventory, prompt_ref, sources)
    output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    copies = {f"sources/{name}": Path(__file__).with_name(name) for name in sources}
    copies.update(
        {
            "inputs/remote-inventory.json": Path(args.inventory),
            "prompts.jsonl": Path(args.prompts),
        }
    )
    for relative, path in copies.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(path.read_bytes())
    host = inventory["host"]
    train.write_new(output / "campaign.json", config)
    manifest = {
        "schema_version": 1,
        "inventory": {
            "path": str(Path(host["release"]) / "inputs/remote-inventory.json"),
            "sha256": inventory_ref["sha256"],
        },
        "config": {
            "path": str(Path(host["release"]) / "campaign.json"),
            "sha256": train.sha256_file(output / "campaign.json"),
        },
        "source_sha256": sources,
        "host": host,
        "prompts": prompt_ref,
        "order": ORDER,
        "child_timeout_seconds": CHILD_SECONDS,
    }
    train.write_new(output / "manifest.json", manifest)
    require(source_hashes() == sources, "source changed during materialization")
    for relative, source in copies.items():
        require(
            train.sha256_file(output / relative) == train.sha256_file(source),
            "copied input/source hash mismatch",
        )
    require(
        train.sha256_file(output / "inputs/remote-inventory.json") == inventory_ref["sha256"]
        and train.sha256_file(output / "prompts.jsonl") == prompt_ref["sha256"],
        "materialization input changed",
    )
    receipt = {
        "status": "materialized_not_launched",
        "manifest_sha256": train.sha256_file(output / "manifest.json"),
        "config_sha256": manifest["config"]["sha256"],
        "inventory": train.tree_receipt(output),
        "candidate_count": 12,
    }
    train.write_new(output / "BUNDLE.json", receipt)
    for target in output.rglob("*"):
        if target.is_file():
            target.chmod(0o444)
    return receipt


def load_manifest(args):
    ref = train.verify_ref(
        {"path": str(Path(args.manifest).absolute()), "sha256": args.manifest_sha256}
    )
    manifest = train.read_json(args.manifest)
    require(
        set(manifest)
        == {
            "schema_version",
            "inventory",
            "config",
            "source_sha256",
            "host",
            "prompts",
            "order",
            "child_timeout_seconds",
        }
        and manifest["schema_version"] == 1
        and manifest["order"] == ORDER
        and manifest["child_timeout_seconds"] == CHILD_SECONDS
        and manifest["source_sha256"] == source_hashes(),
        "queue manifest/source/protocol mismatch",
    )
    host = manifest["host"]
    require(
        os.getuid() == 1000
        and Path(sys.executable).resolve() == Path(host["python"]).resolve()
        and Path(__file__).resolve()
        == (Path(host["release"]) / "sources/generation_release.py").resolve(),
        "wrong Oracle UID/interpreter/release",
    )
    require(
        Path(args.manifest).resolve() == (Path(host["release"]) / "manifest.json").resolve()
        and manifest["inventory"]["path"]
        == str(Path(host["release"]) / "inputs/remote-inventory.json")
        and manifest["config"]["path"] == str(Path(host["release"]) / "campaign.json"),
        "manifest paths are not in declared release",
    )
    train.verify_ref(manifest["inventory"])
    train.verify_ref(manifest["config"])
    inventory = train.read_json(manifest["inventory"]["path"])
    config = train.read_json(manifest["config"]["path"])
    require(
        host == inventory["host"]
        and config == make_config(inventory, manifest["prompts"], manifest["source_sha256"]),
        "generation config changed from captured inventory",
    )
    return manifest, inventory, config, ref


def verify_remote(inventory, config):
    for run in inventory["runs"].values():
        for key in ("config_ref", "completion_ref", "control_completion_ref"):
            train.verify_ref(run[key])
        require(
            train.read_json(run["config_ref"]["path"]) == run["configuration"]
            and train.read_json(run["completion_ref"]["path"]) == run["completion"],
            "remote trainer receipt/config changed",
        )
        control = train.read_json(run["control_completion_ref"]["path"])
        cfg_sha = control.get(
            "config_sha256", control.get("refs", {}).get("config", {}).get("sha256")
        )
        require(
            control.get("status") == "complete"
            and cfg_sha == run["config_ref"]["sha256"]
            and control["trainer_completion"]["sha256"] == run["completion_ref"]["sha256"],
            "remote controller/trainer completion mismatch",
        )
    checked_trees = set()
    for candidate in config["candidates"].values():
        for name in ("base", "tokenizer"):
            key = (candidate[name]["path"], candidate[name]["tree_sha256"])
            if key not in checked_trees:
                train.verify_ref(candidate[name], tree=True)
                checked_trees.add(key)
        evaluate.verify_adapter(candidate)


def verify_candidate(config, config_ref, candidate_id, expected_ids):
    output = Path(config["output"]) / candidate_id
    completion_ref = train.file_receipt(output / "COMPLETED.json")
    result = train.read_json(completion_ref["path"])
    require(
        result.get("status") == "complete"
        and result.get("candidate_id") == candidate_id
        and result.get("source_sha256") == config["source_sha256"]
        and result.get("config", {}).get("sha256") == config_ref["sha256"]
        and result["config"]["path"] == config_ref["path"]
        and result.get("prompts") == config["prompts"]
        and result.get("completed_ids") == expected_ids
        and result.get("completed_count") == 72
        and result.get("ranking_performed") is False,
        "candidate terminal identity/completeness mismatch",
    )
    observed = train.tree_receipt(output)
    files = [row for row in observed["files"] if row["path"] != "COMPLETED.json"]
    sealed = result["inventory"]
    digest = hashlib.sha256(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in files).encode()
    ).hexdigest()
    require(
        sealed["root"] == str(output.resolve())
        and sealed["files"] == files
        and sealed["file_count"] == len(files)
        and sealed["bytes"] == sum(row["bytes"] for row in files)
        and sealed["tree_sha256"] == digest,
        "candidate terminal inventory mismatch",
    )
    require(
        {row["path"] for row in files if row["path"].startswith("batches/")}
        == {f"batches/batch-{index:04d}.json" for index in range(9)},
        "missing/extra raw generation batch",
    )
    responses = evaluate.verify_responses(output / "responses.jsonl", expected_ids, candidate_id)
    require(result["responses"] == responses, "candidate response receipt mismatch")
    rows = [json.loads(line) for line in (output / "responses.jsonl").read_text().splitlines()]
    prompts = evaluate.load_prompts(config["prompts"])
    for index in range(9):
        batch = train.read_json(output / "batches" / f"batch-{index:04d}.json")
        require(
            batch["offset"] == index * 8
            and batch["config_sha256"] == config_ref["sha256"]
            and batch["candidate_id"] == candidate_id
            and all(
                len(batch[key]) == 8
                for key in (
                    "prompts",
                    "padded_prompt_ids",
                    "attention_mask",
                    "returned_sequence_ids",
                )
            ),
            "raw batch identity/count mismatch",
        )
        for offset in range(8):
            position = index * 8 + offset
            row, prompt = rows[position], batch["prompts"][offset]
            padded, mask, sequence = (
                batch[key][offset]
                for key in ("padded_prompt_ids", "attention_mask", "returned_sequence_ids")
            )
            require(
                prompt["id"] == row["id"] == prompts[position]["id"]
                and prompt["messages"] == row["messages"] == prompts[position]["messages"]
                and prompt["rendered_prompt"] == row["rendered_prompt"]
                and prompt["prompt_ids"] == row["prompt_ids"]
                and row["padded_prompt_ids"] == padded
                and row["attention_mask"] == mask
                and sequence == padded + row["generated_ids"],
                "raw batch and durable response differ",
            )
    return completion_ref


def child(argv, log_path):
    with Path(log_path).open("xb") as handle:
        process = subprocess.Popen(
            argv,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        try:
            code = process.wait(timeout=CHILD_SECONDS)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)
            raise
    require(code == 0, f"owned generation child exited {code}; no retry")


def launch(args):
    manifest, inventory, config, ref = load_manifest(args)
    control = Path(manifest["host"]["control"])
    control.mkdir(parents=True, exist_ok=False)
    try:
        require(
            not any((Path(config["output"]) / name).exists() for name in ORDER),
            "candidate output exists; no automatic retry/resume",
        )
        train.write_new(
            control / "REQUEST.json",
            {
                "manifest": ref,
                "config": manifest["config"],
                "order": ORDER,
                "pid": os.getpid(),
                "time_unix": time.time(),
            },
        )
        expected_ids = [row["id"] for row in evaluate.load_prompts(config["prompts"])]
        verify_remote(inventory, config)
        for index, candidate_id in enumerate(ORDER):
            load_manifest(args)
            with evaluate.calibrate.oracle_lock(config["gpu_lock"]):
                snapshot = evaluate.calibrate.host_snapshot()
            train.write_new(
                control / f"{index:02d}-{candidate_id}-admission.json",
                {"host": snapshot, "config": manifest["config"], "candidate": candidate_id},
            )
            child(
                [
                    manifest["host"]["python"],
                    str(Path(__file__).with_name("evaluate_pilots.py")),
                    "--config",
                    manifest["config"]["path"],
                    "--config-sha256",
                    manifest["config"]["sha256"],
                    "--candidate",
                    candidate_id,
                ],
                control / f"{index:02d}-{candidate_id}.stdout.log",
            )
            completed = verify_candidate(config, manifest["config"], candidate_id, expected_ids)
            train.write_new(control / f"{index:02d}-{candidate_id}-COMPLETED.json", completed)
        load_manifest(args)
        completed = {
            name: verify_candidate(config, manifest["config"], name, expected_ids) for name in ORDER
        }
        result = {
            "status": "complete",
            "manifest": ref,
            "config": manifest["config"],
            "candidates": completed,
            "candidate_count": 12,
            "responses_per_candidate": 72,
            "ranking_performed": False,
            "inventory": train.tree_receipt(control),
            "ended_unix": time.time(),
        }
        train.write_new(control / "COMPLETED.json", result)
        return result
    except BaseException as exc:
        train.write_new(
            control / "FAILED.json",
            {
                "status": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "automatic_retry": False,
                "ranking_performed": False,
                "time_unix": time.time(),
            },
        )
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    make = sub.add_parser("materialize")
    make.add_argument("--inventory", type=Path, required=True)
    make.add_argument("--inventory-sha256", required=True)
    make.add_argument("--prompts", type=Path, required=True)
    make.add_argument("--remote-prompts", type=Path, required=True)
    make.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("launch")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args(argv)

    def stopped(signum, _frame):
        raise RuntimeError(f"received signal {signum}; no retry")

    signal.signal(signal.SIGTERM, stopped)
    print(json.dumps((materialize if args.mode == "materialize" else launch)(args), sort_keys=True))


if __name__ == "__main__":
    main()
