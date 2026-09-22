from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import io
import json
import struct
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "full_export_preflight_tested", HERE / "preflight_full_stage_export.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return gate.sha_bytes(path.read_bytes())


def file_receipt(path):
    return {"bytes": path.stat().st_size, "sha256": gate.sha_bytes(path.read_bytes())}


def tree(path):
    helper, _ = gate.load_helper()
    return helper.inventory_tree(path)


def weights(path, number):
    header = json.dumps(
        {"tiny.weight": {"dtype": "F32", "shape": [1, 1], "data_offsets": [0, 4]}}
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(header)) + header + struct.pack("<f", number))


class Fixture:
    def __init__(
        self,
        root,
        monkeypatch,
        candidate_id="full-best-clean-private-enriched",
        best_step=1174,
        losses=None,
    ):
        self.root, self.monkeypatch = root, monkeypatch
        monkeypatch.setattr(gate, "QWEN_SHAPES", {"tiny.weight": [1, 1]})
        self.config = json.loads((ROOT / "provenance/configs/full-runs-v3.json").read_text())
        self.reference = json.loads(
            (
                ROOT / "provenance/exports/pilot-warm-r16-lr5e6/quantization-manifest.json"
            ).read_text()
        )
        self.candidate = next(c for c in self.config["candidates"] if c["id"] == candidate_id)
        self.run = root / "run"
        self.run.mkdir()
        base = root / "base"
        base.mkdir()
        (base / "model.safetensors").write_bytes(b"small base fixture")
        (base / "config.json").write_text("{}")
        observed_base = tree(base)
        lineage = {"lineage": self.candidate["lineage"], "training_base": observed_base}
        lineage_path = root / "lineage.json"
        lineage_sha = write_json(lineage_path, lineage)
        self.config["runtime_input_authority"]["lineages"][self.candidate["lineage"]] = {
            "base_tree_sha256": observed_base["tree_sha256"],
            "lineage_receipt_sha256": lineage_sha,
        }
        self.reference["inputs"]["base"] = observed_base
        dataset_receipts = {}
        for role, count in (("dataset", 300350), ("validation", 5000)):
            value = {
                "row_count": count,
                "dataset_fingerprint_sha256": "a" * 64,
                "shards": [
                    {
                        "path": "private-not-read.jsonl",
                        "rows": count,
                        "bytes": 42,
                        "sha256": "b" * 64,
                    }
                ],
            }
            path = root / f"{role}.json"
            sha = write_json(path, value)
            self.config["runtime_input_authority"][role] = {
                "rows": count,
                "manifest_sha256": sha,
                "fingerprint_sha256": "a" * 64,
            }
            dataset_receipts[role] = {**value, "manifest_path": str(path), "manifest_sha256": sha}
        config_path = root / "config.json"
        config_sha = write_json(config_path, self.config)
        monkeypatch.setattr(gate, "CONFIG_SHA", config_sha)
        llama = root / "llama"
        (llama / "build/bin").mkdir(parents=True)
        for path, key, const in (
            (llama / "convert_hf_to_gguf.py", "converter", "CONVERTER_SHA"),
            (llama / "build/bin/llama-quantize", "quantizer", "QUANTIZER_SHA"),
        ):
            path.write_bytes(b"not executed fixture")
            sha = file_receipt(path)["sha256"]
            monkeypatch.setattr(gate, const, sha)
            self.reference["llama_cpp"][key]["sha256"] = sha
        reference_path = root / "reference.json"
        reference_sha = write_json(reference_path, self.reference)
        monkeypatch.setattr(gate, "REFERENCE_SHA", reference_sha)
        shared = self.config["shared"]
        values = {
            k: shared[k]
            for k in (
                "max_length",
                "epochs",
                "seed",
                "warmup_ratio",
                "weight_decay",
                "batch_size",
                "gradient_accumulation",
                "logging_steps",
            )
        }
        values.update(
            run_name=candidate_id,
            lineage=self.candidate["lineage"],
            rank=16,
            lora_alpha=16,
            learning_rate=self.candidate["learning_rate"],
            private_policy="include",
            pilot_rows=None,
            validation_rows=None,
            max_steps=-1,
            eval_steps=250,
            save_steps=250,
            eval_batch_size=64,
        )
        scripts = {name: self.config["source_code"][key] for name, key in gate.SOURCE_FILES.items()}
        tokenizer = copy.deepcopy(self.config["runtime_input_authority"]["tokenizer"])
        tokenizer.pop("base_tree_sha256")
        for name, entry in tokenizer["files"].items():
            entry["path"] = str(root / "original-tokenizer" / name)
        self.resolved = {
            **values,
            **dataset_receipts,
            "expected_train_rows": 300350,
            "expected_validation_rows": 5000,
            "expected_planned_steps": 4693,
            "dataloader_workers": 8,
            "packages": {"fixture": "1"},
            "campaign_config": {"sha256": config_sha},
            "lineage_receipt_sha256": lineage_sha,
            "tokenizer": tokenizer,
            "script_sha256": scripts["train_lora_round2.py"],
            "campaign_io_sha256": gate.HELPER_SHA,
            "resume_from_checkpoint": None,
            "resume_checkpoint_step": None,
            "initial_adapter_receipt": None,
        }
        self.manifest = {
            **copy.deepcopy(values),
            **dataset_receipts,
            "environment": {"packages": {"fixture": "1"}},
            "schema_version": 2,
            "campaign_config": {"sha256": config_sha},
            "scripts": scripts,
            "tokenizer": tokenizer,
            "base_lineage": {
                "receipt": lineage,
                "receipt_sha256": lineage_sha,
                "observed": observed_base,
            },
            "trainer_global_step": 4693,
            "planned_steps": 4693,
            "trainer_epoch": 1.0,
            "global_batch_per_gpu": 64,
            "training_method": "lora_bf16",
            "completion_only_loss": True,
            "warmup_steps": 141,
            "target_modules": sorted(gate.TARGETS),
            "initial_adapter_receipt": None,
            "initial_adapter_load": None,
            "schedule": {
                "kind": "milestones",
                "requested_steps": gate.MILESTONES,
                "observed_eval_steps": gate.MILESTONES,
                "session_save_callback_steps": gate.MILESTONES,
                "surviving_checkpoint_steps": gate.MILESTONES,
                "trainer_interval": 4694,
            },
            "tokenization": {
                name: {
                    "rows": count,
                    "max_sequence_tokens": 42,
                    "assistant_tokens": count * 8,
                    "sequence_tokens": count * 40,
                }
                for name, count in (("train", 300350), ("validation", 5000))
            },
            "resume": {"requested": False, "retry_from_scratch": False, "checkpoint_step": None},
        }
        if self.candidate["initial_adapter_tree_sha256"] is not None:
            initial = {
                "kind": "completed_pilot_adapter_new_stage",
                "source_run_name": "warm-r16-lr5e6",
                "prior_training_rows": 20000,
                "prior_trainer_global_step": 313,
                "inventory": copy.deepcopy(self.reference["inputs"]["adapter"]),
                "training_base_tree_sha256": observed_base["tree_sha256"],
                "training_manifest_sha256": self.candidate["source_pilot_training_manifest_sha256"],
            }
            loaded = {
                "operation": "copy_exact_adapter_tensors_once_no_merge",
                "tensor_count": 1,
                "trainable_parameters": 1,
                "tensor_keys": ["tiny.weight"],
                "before_tensor_sha256": "b" * 64,
                "exact_source_values_loaded": True,
                "source_tensor_sha256": "a" * 64,
                "loaded_tensor_sha256": "a" * 64,
                "source_tree_sha256_before": self.candidate["initial_adapter_tree_sha256"],
                "source_tree_sha256_after": self.candidate["initial_adapter_tree_sha256"],
            }
            self.manifest.update(initial_adapter_receipt=initial, initial_adapter_load=loaded)
            self.resolved["initial_adapter_receipt"] = initial
            write_json(
                self.run / "initialization-sessions/adapter-load-1.json",
                {
                    "initial_adapter_receipt": initial,
                    "load": loaded,
                    "resume_checkpoint_step": None,
                    "trainer_sha256": scripts["train_lora_round2.py"],
                },
            )
        treatment = {
            **values,
            **{
                key: self.resolved[key]
                for key in (
                    "expected_train_rows",
                    "expected_validation_rows",
                    "expected_planned_steps",
                    "dataloader_workers",
                    "packages",
                )
            },
            **{
                f"{role}_{name}": self.config["runtime_input_authority"][role][authority]
                for role in ("dataset", "validation")
                for name, authority in (
                    ("manifest_sha256", "manifest_sha256"),
                    ("fingerprint_sha256", "fingerprint_sha256"),
                )
            },
            "world_size": 1,
            "tokenizer": tokenizer,
            "scripts": scripts,
            "training_base_tree_sha256": observed_base["tree_sha256"],
            "base_lineage_receipt_sha256": lineage_sha,
            "campaign_config_sha256": config_sha,
            "initial_adapter": self.manifest["initial_adapter_receipt"],
            "milestone_steps": gate.MILESTONES,
        }
        self.resolved["resume_signature"] = {
            "treatment": treatment,
            "sha256": gate.sha_bytes(gate.canonical(treatment)),
        }
        self.manifest["resume"]["treatment_signature_sha256"] = self.resolved["resume_signature"][
            "sha256"
        ]
        self.manifest["resume"]["initial_resolved_config_sha256"] = write_json(
            self.run / "resolved-config.json", self.resolved
        )
        losses = losses or {1174: 0.1, 2347: 0.2, 4693: 0.3}
        self.losses = losses
        self.rows = [{"step": step, "loss": 0.5} for step in [1, *range(47, 4694, 47)]]
        self.rows.extend({"step": step, "eval_loss": losses[step]} for step in gate.MILESTONES)
        self.rows.sort(key=lambda row: row["step"])
        config = {
            "peft_type": "LORA",
            "task_type": "CAUSAL_LM",
            "r": 16,
            "lora_alpha": 16,
            "bias": "none",
            "lora_dropout": 0,
            "target_modules": sorted(gate.TARGETS),
        }
        for step in gate.MILESTONES:
            checkpoint = self.run / "checkpoints" / f"checkpoint-{step}"
            weights(checkpoint / "adapter_model.safetensors", step)
            write_json(checkpoint / "adapter_config.json", config)
            prefix = [r for r in self.rows if r["step"] <= step]
            prior = min((s for s in gate.MILESTONES if s <= step), key=lambda s: (losses[s], s))
            write_json(
                checkpoint / "trainer_state.json",
                {
                    "global_step": step,
                    "max_steps": 4693,
                    "best_metric": losses[prior],
                    "best_model_checkpoint": str(self.run / "checkpoints" / f"checkpoint-{prior}"),
                    "log_history": prefix,
                    "epoch": step / 4693,
                },
            )
            for name in ("optimizer.pt", "scheduler.pt", "rng_state.pth", "training_args.bin"):
                (checkpoint / name).write_bytes(b"not deserialized")
        self.rows.append({"step": 4693, "eval_loss": losses[best_step]})
        self.state = {
            "global_step": 4693,
            "max_steps": 4693,
            "epoch": 1.0,
            "best_metric": losses[best_step],
            "best_model_checkpoint": str(self.run / "checkpoints" / f"checkpoint-{best_step}"),
            "log_history": self.rows,
        }
        write_json(self.run / "checkpoints/trainer_state.json", self.state)
        adapter = self.run / "adapter"
        weights(adapter / "adapter_model.safetensors", best_step)
        write_json(adapter / "adapter_config.json", config)
        (adapter / "README.md").write_text("synthetic test fixture")
        write_json(adapter / "tokenizer.json", {"model": {"vocab": {"a": 0}}})
        write_json(adapter / "tokenizer_config.json", {"tokenizer_class": "Qwen2Tokenizer"})
        (adapter / "chat_template.jinja").write_text("{{ messages }}")
        self.manifest["adapter"] = tree(adapter)
        self.manifest["adapter_selection"] = {
            "policy": "minimum_eval_loss",
            "best_metric_name": "eval_loss",
            "best_metric": losses[best_step],
            "best_checkpoint_step": best_step,
            "best_checkpoint_relative_path": f"checkpoints/checkpoint-{best_step}",
        }
        for name, key in (
            ("adapter_model.safetensors", "model"),
            ("adapter_config.json", "config"),
        ):
            sha = file_receipt(adapter / name)["sha256"]
            self.manifest["adapter_selection"][f"best_checkpoint_adapter_{key}_sha256"] = sha
            self.manifest["adapter_selection"][f"final_adapter_{key}_sha256"] = sha
        self.manifest["validation_metrics"] = {"eval_loss": losses[best_step]}
        (self.run / "loss-curve.png").write_bytes(
            b"\x89PNG\r\n\x1a\nsynthetic\x00\x00\x00\x00IEND1234"
        )
        (self.run / "loss-curve.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.write_metrics()
        self.seal()
        self.args = argparse.Namespace(
            full_config=config_path,
            expected_full_config_sha256=config_sha,
            candidate_id=candidate_id,
            run_dir=self.run,
            training_code=HERE,
            base=base,
            base_lineage=lineage_path,
            dataset_manifest=root / "dataset.json",
            validation_manifest=root / "validation.json",
            exporter=HERE / "merge_and_quantize.py",
            expected_exporter_sha256=gate.EXPORTER_SHA,
            llama_cpp=llama,
            reference_export_manifest=reference_path,
            expected_reference_export_manifest_sha256=reference_sha,
            output=root / "receipt.json",
        )

    def write_metrics(self):
        (self.run / "metrics.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.rows)
        )
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer, fieldnames=sorted({key for row in self.rows for key in row})
        )
        writer.writeheader()
        writer.writerows(self.rows)
        (self.run / "metrics.csv").write_bytes(buffer.getvalue().encode())
        self.manifest["metrics"] = {
            name: file_receipt(self.run / name)
            for name in ("metrics.jsonl", "metrics.csv", "loss-curve.png", "loss-curve.svg")
        }

    def seal(self):
        sha = write_json(self.run / "training-manifest.json", self.manifest)
        write_json(
            self.run / "COMPLETED.json",
            {"run_name": self.manifest["run_name"], "training_manifest_sha256": sha},
        )

    def cli(self):
        return [
            value
            for key, item in vars(self.args).items()
            for value in ("--" + key.replace("_", "-"), str(item))
        ]


@pytest.mark.parametrize("candidate", list(gate.CANDIDATES))
def test_three_fresh_stages_pass_artifact_only(tmp_path, monkeypatch, candidate):
    fixture = Fixture(tmp_path, monkeypatch, candidate)
    report = gate.preflight(fixture.args)
    assert report["status"] == "artifact_preflight_passed"
    assert report["runtime_admission"] == "not_assessed"
    assert report["export_performed"] is False and report["model_loaded"] is False
    assert report["selection"]["selected_step"] == 1174
    assert report["selection"]["selected_example_exposures_in_this_stage"] == 75136
    assert report["run_steps"] == 4693
    assert report["tokenizer_directory"] == str(fixture.run / "adapter")
    assert "PRIVATE" not in json.dumps(report)


def test_exact_tie_uses_earliest_checkpoint(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch, losses={1174: 0.1, 2347: 0.1, 4693: 0.2})
    assert gate.preflight(fixture.args)["selection"]["selected_step"] == 1174


def test_actual_shape_contract_not_fixture_shape():
    shapes = gate.expected_shapes()
    assert len(shapes) == 392
    assert sum(__import__("math").prod(s) for s in shapes.values()) == 18464768


@pytest.mark.parametrize(
    "mutation",
    [
        "resume",
        "retry",
        "running",
        "failed",
        "wrong_config",
        "wrong_reference",
        "manifest_bytes",
        "adapter_bytes",
        "tokenizer_bytes",
        "wrong_parent",
        "wrong_selection",
        "missing_checkpoint",
        "extra_evaluation",
        "nan",
        "duplicate_key",
        "symlink",
        "bad_csv",
        "bad_source",
        "wrong_final_weights",
    ],
)
def test_fails_closed(tmp_path, monkeypatch, mutation):
    fixture = Fixture(tmp_path, monkeypatch)
    if mutation in {"resume", "retry"}:
        fixture.manifest["resume"][
            "requested" if mutation == "resume" else "retry_from_scratch"
        ] = True
        fixture.seal()
    elif mutation in {"running", "failed"}:
        write_json(fixture.run / (mutation.upper() + ".json"), {})
    elif mutation == "wrong_config":
        fixture.args.expected_full_config_sha256 = "0" * 64
    elif mutation == "wrong_reference":
        fixture.args.expected_reference_export_manifest_sha256 = "0" * 64
    elif mutation == "manifest_bytes":
        with (fixture.run / "training-manifest.json").open("a") as handle:
            handle.write(" ")
    elif mutation in {"adapter_bytes", "tokenizer_bytes"}:
        (
            fixture.run
            / "adapter"
            / ("adapter_model.safetensors" if mutation == "adapter_bytes" else "tokenizer.json")
        ).write_bytes(b"changed")
    elif mutation == "wrong_parent":
        (fixture.args.base / "model.safetensors").write_bytes(b"another valid base")
        replacement = {"lineage": "clean", "training_base": tree(fixture.args.base)}
        write_json(fixture.args.base_lineage, replacement)
    elif mutation == "wrong_selection":
        fixture.manifest["adapter_selection"]["best_checkpoint_step"] = 4693
        fixture.seal()
    elif mutation == "missing_checkpoint":
        (fixture.run / "checkpoints/checkpoint-2347/trainer_state.json").unlink()
    elif mutation in {"extra_evaluation", "nan"}:
        if mutation == "extra_evaluation":
            fixture.rows.append({"step": 4693, "eval_loss": 0.1})
        else:
            fixture.rows[0]["loss"] = float("nan")
        fixture.write_metrics()
        fixture.seal()
    elif mutation == "duplicate_key":
        (fixture.run / "COMPLETED.json").write_text('{"run_name":"x","run_name":"y"}')
    elif mutation == "symlink":
        path = fixture.run / "adapter/tokenizer.json"
        real = tmp_path / "real.json"
        path.rename(real)
        path.symlink_to(real)
    elif mutation == "bad_csv":
        (fixture.run / "metrics.csv").write_text("a,b\n1,2\n")
        fixture.manifest["metrics"]["metrics.csv"] = file_receipt(fixture.run / "metrics.csv")
        fixture.seal()
    elif mutation == "bad_source":
        fixture.args.training_code = tmp_path
    elif mutation == "wrong_final_weights":
        weights(fixture.run / "adapter/adapter_model.safetensors", 4693)
        fixture.manifest["adapter"] = tree(fixture.run / "adapter")
        fixture.seal()
    with pytest.raises((gate.PreflightError, ValueError, OSError, KeyError)):
        gate.preflight(fixture.args)


@pytest.mark.parametrize(
    "mutation", ["missing", "fresh", "double_merge", "loaded_hash", "second_session"]
)
def test_continuation_proof_cannot_be_omitted_or_stacked(tmp_path, monkeypatch, mutation):
    fixture = Fixture(tmp_path, monkeypatch, "full-best-warm-pilot-continuation")
    if mutation == "missing":
        fixture.manifest["initial_adapter_receipt"] = None
    elif mutation == "fresh":
        fixture.manifest["initial_adapter_load"] = None
    elif mutation == "double_merge":
        fixture.manifest["initial_adapter_receipt"]["training_base_tree_sha256"] = "0" * 64
    elif mutation == "loaded_hash":
        fixture.manifest["initial_adapter_load"]["loaded_tensor_sha256"] = "b" * 64
    else:
        write_json(fixture.run / "initialization-sessions/adapter-load-2.json", {})
    fixture.seal()
    with pytest.raises(gate.PreflightError):
        gate.preflight(fixture.args)


def test_input_mutation_during_scan_rejected(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch)
    original = gate.verify_initializer

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        (fixture.run / "adapter/tokenizer.json").write_text("changed after inspection")
        return result

    monkeypatch.setattr(gate, "verify_initializer", mutate)
    with pytest.raises(gate.PreflightError, match="input_changed"):
        gate.preflight(fixture.args)


def test_oversized_json_read_is_bounded(tmp_path):
    inputs = gate.Inputs()
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * 65)
    with pytest.raises(gate.PreflightError, match="file_size_bound"):
        inputs.json(path, maximum=64)


def test_oversized_safetensors_header_is_bounded(tmp_path):
    inputs = gate.Inputs()
    path = tmp_path / "large-header.safetensors"
    path.write_bytes(struct.pack("<Q", gate.MAX_LINE + 1) + b"not read")
    with pytest.raises(gate.PreflightError, match="safetensors_header"):
        gate.adapter_weights(inputs, path)


def test_oversized_metrics_line_is_bounded(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch)
    path = fixture.run / "metrics.jsonl"
    path.write_bytes(b" " * (gate.MAX_LINE + 1))
    fixture.manifest["metrics"]["metrics.jsonl"] = file_receipt(path)
    fixture.seal()
    with pytest.raises(gate.PreflightError, match="metrics_bound"):
        gate.preflight(fixture.args)


@pytest.mark.parametrize("epoch", [None, "PRIVATE_PROSE", {"PRIVATE_PROSE": 1}, -1, 2, True, 0.75])
@pytest.mark.parametrize(
    "relative", ["checkpoints/trainer_state.json", "checkpoints/checkpoint-1174/trainer_state.json"]
)
def test_untrusted_epoch_cannot_enter_receipt(tmp_path, monkeypatch, epoch, relative):
    fixture = Fixture(tmp_path, monkeypatch)
    path = fixture.run / relative
    state = json.loads(path.read_text())
    if epoch is None:
        state.pop("epoch")
    else:
        state["epoch"] = epoch
    write_json(path, state)
    with pytest.raises(gate.PreflightError, match="trainer_state|checkpoint_state"):
        gate.preflight(fixture.args)


def test_output_cannot_escape_into_input_tree(tmp_path, monkeypatch, capsys):
    fixture = Fixture(tmp_path, monkeypatch)
    fixture.args.output = tmp_path / "run" / "checkpoints" / ".." / "new.json"
    assert gate.main(fixture.cli()) == 2
    assert "output_inside_input_tree" in capsys.readouterr().err
    assert not (fixture.run / "new.json").exists()


def test_cli_receipt_no_overwrite_and_no_execution(tmp_path, monkeypatch, capsys):
    fixture = Fixture(tmp_path, monkeypatch)
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("no subprocess allowed"))
    before = set(sys.modules)
    assert gate.main(fixture.cli()) == 0
    assert not ({"torch", "peft", "transformers"} & (set(sys.modules) - before))
    assert json.loads(capsys.readouterr().out)["runtime_admission"] == "not_assessed"
    prior = fixture.args.output.read_bytes()
    assert gate.main(fixture.cli()) == 2
    assert "output_exists" in capsys.readouterr().err
    assert fixture.args.output.read_bytes() == prior


def test_cli_failure_no_private_text_or_partial_receipt(tmp_path, monkeypatch, capsys):
    fixture = Fixture(tmp_path, monkeypatch)
    (fixture.run / "COMPLETED.json").write_text('{"PRIVATE_QUESTION_TEXT": null}')
    assert gate.main(fixture.cli()) == 2
    assert "PRIVATE" not in capsys.readouterr().err
    assert not fixture.args.output.exists()
