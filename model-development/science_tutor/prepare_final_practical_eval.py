"""Freeze the final science roster for the existing practical-2,000 runner.

This module only prepares append-only configuration and launch artifacts.  It
does not connect to Oracle, start a server, acquire a GPU lock, or run
inference.  The inherited transport decision is deliberately narrow: the
reviewed transport-only smoke exercised only the first candidate, and the new
roster retains that exact first candidate, runner, runtime, battery, and
execution settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path


class PreparationError(ValueError):
    """Raised when the frozen evidence cannot support the new configuration."""


OLD_CONFIG_SHA256 = "8fcb4c889bfdedd1116f78efcd05914146569831f9c158b15588430c80c4dcee"
OLD_TRANSPORT_SHA256 = "be8cf288448121c18b380d51fc35c5e116d71a0e9c9a3f28179239ed6495ef84"
NEW_ROSTER_SHA256 = "67f8241a125b3b9b7fbb9df36eb6f183b0f020ef23b9ac4b1acff45152411a63"

REMOTE_ROOT = Path("/lambda/nfs/awf-tmp/muta/campaign-20260918")
REMOTE_CONFIG_DIR = REMOTE_ROOT / "configs/science-tutor-final-practical-2000-v2"
REMOTE_OUTPUT = REMOTE_ROOT / "evaluation/science-tutor-final-practical-2000-v2"
REMOTE_CODE_ROOT = REMOTE_ROOT / "code/practical-v1-20260919T0604"


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def object_sha256(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise PreparationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path, expected_sha256: str | None = None) -> dict:
    raw = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PreparationError(f"frozen input hash mismatch: {path}")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                PreparationError(f"non-finite JSON value: {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise PreparationError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PreparationError(f"JSON root must be an object: {path}")
    return value


def write_json_exclusive(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def write_text_exclusive(path: Path, value: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
    if executable:
        path.chmod(0o755)


def validate_roster(roster: dict) -> list[dict]:
    candidates = roster.get("candidates")
    if roster.get("schema_version") != 1 or not isinstance(candidates, list):
        raise PreparationError("invalid final candidate manifest")
    if len(candidates) != 5:
        raise PreparationError("exactly five final candidates are required")
    ids = [candidate.get("id") for candidate in candidates]
    if len(set(ids)) != 5 or any(
        not isinstance(candidate_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", candidate_id) is None
        for candidate_id in ids
    ):
        raise PreparationError("candidate IDs must be unique and safe")
    for candidate in candidates:
        if candidate.get("backend") != "gguf":
            raise PreparationError("final roster must contain only GGUF candidates")
        expected = candidate.get("expected", {})
        for key in ("model_sha256", "server_sha256"):
            if re.fullmatch(r"[0-9a-f]{64}", str(expected.get(key))) is None:
                raise PreparationError(f"invalid candidate {key}")
    server_hashes = {candidate["expected"]["server_sha256"] for candidate in candidates}
    if len(server_hashes) != 1:
        raise PreparationError("all candidates must use one exact server")
    return candidates


def inherited_transport(
    old_config: dict,
    old_transport: dict,
    roster: dict,
) -> dict:
    candidates = validate_roster(roster)
    settings = old_config.get("settings")
    required_settings = {
        "slots": 8,
        "context_per_slot": 4096,
        "max_tokens": 1024,
        "threads": 2,
        "gpu_layers": 99,
        "port": 18190,
    }
    if settings != required_settings or old_transport.get("settings") != required_settings:
        raise PreparationError("transport settings changed")
    if old_transport.get("status") != "pass":
        raise PreparationError("parent transport was not accepted")
    if old_transport.get("acceptance_kind") != "external_non_bitwise_transport_reconciliation":
        raise PreparationError("unexpected parent transport acceptance kind")
    if old_transport.get("duplicate_integrity_passed") is not False:
        raise PreparationError("parent failed byte identity must remain explicit")
    if old_transport.get("repeated_inference") is not False:
        raise PreparationError("parent receipt unexpectedly reports repeated inference")
    if old_transport.get("candidate_expected") != candidates[0].get("expected"):
        raise PreparationError("the transport-smoke candidate changed")
    if old_transport.get("code_files_sha256") != object_sha256(old_config["code_files"]):
        raise PreparationError("parent code inventory binding mismatch")
    if old_transport.get("runtime_files_sha256") != object_sha256(
        old_config.get("runtime_files", [])
    ):
        raise PreparationError("parent runtime inventory binding mismatch")
    if old_transport.get("battery_sha256") != old_config["battery"]["sha256"]:
        raise PreparationError("parent battery binding mismatch")
    if old_transport.get("candidates_sha256") != old_config["candidates"]["sha256"]:
        raise PreparationError("parent roster binding mismatch")

    return {
        "schema_version": 1,
        "status": "pass",
        "acceptance_kind": "inherited_external_non_bitwise_transport_reconciliation",
        "inheritance_scope": (
            "The transport-only runner verifies all five roster artifacts, then performs "
            "transport inference with candidates[:1]. The final roster retains the exact "
            "first incumbent, runner, runtime, battery, and execution settings. Candidates "
            "2-5 were not used for transport inference; their new preflight identities must "
            "be verified by the full-run runner before inherited transport acceptance applies."
        ),
        "new_roster_preflight_status": (
            "all five Oracle hashes observed during preparation; mandatory runner preflight "
            "and postflight reverification pending"
        ),
        "new_inference_performed": False,
        "responses": old_transport.get("responses"),
        "responses_source": {
            "path": str(
                REMOTE_ROOT
                / "configs/practical-winner-2000-20260919/transport-acceptance.json"
            ),
            "sha256": OLD_TRANSPORT_SHA256,
        },
        "parent_acceptance_kind": old_transport["acceptance_kind"],
        "parent_original_attempt_status": old_transport.get("original_attempt_status"),
        "parent_candidates_sha256": old_config["candidates"]["sha256"],
        "candidates_sha256": NEW_ROSTER_SHA256,
        "candidate_expected": candidates[0]["expected"],
        "settings": required_settings,
        "config_sha256": old_transport.get("config_sha256"),
        "code_files_sha256": old_transport["code_files_sha256"],
        "runtime_files_sha256": old_transport["runtime_files_sha256"],
        "battery_sha256": old_transport["battery_sha256"],
        "duplicate_integrity_passed": False,
        "repeated_inference": False,
        "fresh_grader_changed": False,
        "inference_repeatability_uncertainty_included": False,
        "limitation": old_transport.get("limitation"),
        "review_status": "independent_review_required_before_launch",
        "required_runtime_checks": [
            "verify all five model and server hashes before and after inference",
            "require an idle GPU and acquire the existing nonblocking shared lock",
            "preserve the original failed strict-byte-identity attempt and parent acceptance",
            "report that backend/batching repeatability uncertainty is excluded",
        ],
    }


def build_config(old_config: dict, transport_sha256: str) -> dict:
    config = deepcopy(old_config)
    config["protocol"] = "science-tutor-final-practical-2000-v2"
    config["candidates"] = {
        "path": str(REMOTE_CONFIG_DIR / "final-five-candidate-manifest.json"),
        "sha256": NEW_ROSTER_SHA256,
    }
    config["transport_gate"] = {
        "path": str(REMOTE_CONFIG_DIR / "inherited-transport-acceptance.json"),
        "sha256": transport_sha256,
    }
    config["transport_acceptance_kind"] = (
        "inherited_external_non_bitwise_reconciliation_original_failure_preserved"
    )
    config["inference_repeatability_uncertainty_included"] = False
    config["lineage_note"] = (
        "The final roster is append-only. R1 refinement was skipped after its reviewed "
        "admission gate; p2-half-finalist is the unchanged selected 8,002-row checkpoint."
    )
    return config


def remote_supervisor(config_sha256: str) -> str:
    config = REMOTE_CONFIG_DIR / "config.json"
    roster = REMOTE_CONFIG_DIR / "final-five-candidate-manifest.json"
    transport = REMOTE_CONFIG_DIR / "inherited-transport-acceptance.json"
    return f"""#!/usr/bin/env bash
set -euo pipefail
trap 'status=$?; printf "FINAL_PRACTICAL_EXIT=%s UTC=" "$status"; date -u +%Y-%m-%dT%H:%M:%SZ' EXIT
test "$(sha256sum {config} | awk '{{print $1}}')" = "{config_sha256}"
test "$(sha256sum {roster} | awk '{{print $1}}')" = "{NEW_ROSTER_SHA256}"
test "$(sha256sum {transport} | awk '{{print $1}}')" = "__TRANSPORT_SHA256__"
test ! -e {REMOTE_OUTPUT}
cd {REMOTE_CODE_ROOT}
printf 'FINAL_PRACTICAL_STARTED UTC='
date -u +%Y-%m-%dT%H:%M:%SZ
env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 NO_PROXY=127.0.0.1,localhost \
  /home/ubuntu/muta-finetune/.venv/bin/python -u -m bench.winner_battery.practical_runner \
  --config {config} \
  --sha256 {config_sha256} \
  --output {REMOTE_OUTPUT}
"""


def stage_and_launch(
    hashes: dict[str, str], local_artifact_dir: Path, roster_path: Path
) -> str:
    remote_stage = Path(str(REMOTE_CONFIG_DIR) + ".staging")
    controller_log = REMOTE_CONFIG_DIR / "full-controller.log"
    controller_pid = REMOTE_CONFIG_DIR / "controller.pid"
    return f"""#!/usr/bin/env bash
set -euo pipefail
local_dir={local_artifact_dir}
roster={roster_path}
remote_host=ubuntu@129.213.31.157
remote_dir={REMOTE_CONFIG_DIR}
remote_stage={remote_stage}
remote_output={REMOTE_OUTPUT}

test "$(shasum -a 256 "$local_dir/config.json" | awk '{{print $1}}')" = "{hashes['config.json']}"
test "$(shasum -a 256 "$local_dir/inherited-transport-acceptance.json" | awk '{{print $1}}')" = "{hashes['inherited-transport-acceptance.json']}"
test "$(shasum -a 256 "$local_dir/remote-supervisor.sh" | awk '{{print $1}}')" = "{hashes['remote-supervisor.sh']}"
test "$(shasum -a 256 "$roster" | awk '{{print $1}}')" = "{NEW_ROSTER_SHA256}"

ssh "$remote_host" "set -eu; test ! -e '$remote_dir'; test ! -e '$remote_stage'; test ! -e '$remote_output'; mkdir '$remote_stage'"
scp "$local_dir/config.json" "$local_dir/inherited-transport-acceptance.json" \
  "$local_dir/remote-supervisor.sh" \
  "$roster" \
  "$remote_host:$remote_stage/"
ssh "$remote_host" bash -s <<'REMOTE'
set -eu
test "$(sha256sum '{remote_stage / 'config.json'}' | awk '{{print $1}}')" = "{hashes['config.json']}"
test "$(sha256sum '{remote_stage / 'inherited-transport-acceptance.json'}' | awk '{{print $1}}')" = "{hashes['inherited-transport-acceptance.json']}"
test "$(sha256sum '{remote_stage / 'remote-supervisor.sh'}' | awk '{{print $1}}')" = "{hashes['remote-supervisor.sh']}"
test "$(sha256sum '{remote_stage / 'final-five-candidate-manifest.json'}' | awk '{{print $1}}')" = "{NEW_ROSTER_SHA256}"
test "$(find '{remote_stage}' -mindepth 1 -maxdepth 1 -type f -printf '%f\\n' | LC_ALL=C sort | tr '\\n' ' ')" = "config.json final-five-candidate-manifest.json inherited-transport-acceptance.json remote-supervisor.sh "
test "$(find '{remote_stage}' -mindepth 1 -maxdepth 1 | wc -l)" -eq 4
mkdir -m 700 '{REMOTE_CONFIG_DIR}'
mv '{remote_stage / 'config.json'}' '{REMOTE_CONFIG_DIR / 'config.json'}'
mv '{remote_stage / 'final-five-candidate-manifest.json'}' '{REMOTE_CONFIG_DIR / 'final-five-candidate-manifest.json'}'
mv '{remote_stage / 'inherited-transport-acceptance.json'}' '{REMOTE_CONFIG_DIR / 'inherited-transport-acceptance.json'}'
mv '{remote_stage / 'remote-supervisor.sh'}' '{REMOTE_CONFIG_DIR / 'remote-supervisor.sh'}'
rmdir '{remote_stage}'
test "$(find '{REMOTE_CONFIG_DIR}' -mindepth 1 -maxdepth 1 -type f -printf '%f\\n' | LC_ALL=C sort | tr '\\n' ' ')" = "config.json final-five-candidate-manifest.json inherited-transport-acceptance.json remote-supervisor.sh "
test "$(find '{REMOTE_CONFIG_DIR}' -mindepth 1 -maxdepth 1 | wc -l)" -eq 4
test "$(sha256sum '{REMOTE_CONFIG_DIR / 'config.json'}' | awk '{{print $1}}')" = "{hashes['config.json']}"
test "$(sha256sum '{REMOTE_CONFIG_DIR / 'inherited-transport-acceptance.json'}' | awk '{{print $1}}')" = "{hashes['inherited-transport-acceptance.json']}"
test "$(sha256sum '{REMOTE_CONFIG_DIR / 'remote-supervisor.sh'}' | awk '{{print $1}}')" = "{hashes['remote-supervisor.sh']}"
test "$(sha256sum '{REMOTE_CONFIG_DIR / 'final-five-candidate-manifest.json'}' | awk '{{print $1}}')" = "{NEW_ROSTER_SHA256}"
nohup bash '{REMOTE_CONFIG_DIR / 'remote-supervisor.sh'}' > '{controller_log}' 2>&1 < /dev/null &
printf '%s\\n' $! > '{controller_pid}'
printf 'FINAL_PRACTICAL_PID=%s\\n' $!
REMOTE
"""


def prepare(old_config_path: Path, old_transport_path: Path, roster_path: Path, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        old_config = load_json(old_config_path, OLD_CONFIG_SHA256)
        old_transport = load_json(old_transport_path, OLD_TRANSPORT_SHA256)
        roster = load_json(roster_path, NEW_ROSTER_SHA256)
        transport = inherited_transport(old_config, old_transport, roster)
        transport_path = output / "inherited-transport-acceptance.json"
        write_json_exclusive(transport_path, transport)
        transport_sha = file_sha256(transport_path)

        config = build_config(old_config, transport_sha)
        config_path = output / "config.json"
        write_json_exclusive(config_path, config)
        config_sha = file_sha256(config_path)

        supervisor_path = output / "remote-supervisor.sh"
        supervisor = remote_supervisor(config_sha).replace("__TRANSPORT_SHA256__", transport_sha)
        write_text_exclusive(supervisor_path, supervisor, executable=True)
        first_hashes = {
            "config.json": config_sha,
            "inherited-transport-acceptance.json": transport_sha,
            "remote-supervisor.sh": file_sha256(supervisor_path),
        }
        launcher_path = output / "stage-and-launch.sh"
        write_text_exclusive(
            launcher_path,
            stage_and_launch(first_hashes, output, roster_path.resolve()),
            executable=True,
        )

        prepared = {
            "schema_version": 1,
            "status": "prepared_not_launched",
            "decision": "GO_AFTER_INDEPENDENT_STATIC_REVIEW",
            "transport_decision": "inherit_exact_first-candidate_transport_without_new_smoke",
            "remote_config_dir": str(REMOTE_CONFIG_DIR),
            "remote_output": str(REMOTE_OUTPUT),
            "expected_responses": 10000,
            "artifacts": {
                **{
                    key: {"path": str(output / key), "sha256": value}
                    for key, value in first_hashes.items()
                },
                "stage-and-launch.sh": {
                    "path": str(launcher_path),
                    "sha256": file_sha256(launcher_path),
                },
                "final-five-candidate-manifest.json": {
                    "path": str(roster_path),
                    "sha256": NEW_ROSTER_SHA256,
                },
            },
            "inherited_parent": {
                "config": {"path": str(old_config_path), "sha256": OLD_CONFIG_SHA256},
                "transport": {
                    "path": str(old_transport_path),
                    "sha256": OLD_TRANSPORT_SHA256,
                },
            },
            "execution_requirements": [
                "independent static review must change decision to GO before execution",
                "run stage-and-launch.sh once only; it refuses existing config/output paths",
                "runner must observe an idle GPU and acquire its nonblocking shared lock",
                "after completion require 10,000 joined responses and postflight hashes",
            ],
        }
        write_json_exclusive(output / "PREPARED.json", prepared)
        return prepared
    except BaseException as exc:
        failure = output / "PREPARATION_FAILED.json"
        if not failure.exists():
            write_json_exclusive(
                failure,
                {
                    "schema_version": 1,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "inference_launched": False,
                },
            )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-config", type=Path, required=True)
    parser.add_argument("--old-transport", type=Path, required=True)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.old_config, args.old_transport, args.roster, args.output)


if __name__ == "__main__":
    main()
