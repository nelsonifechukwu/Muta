"""Build deterministic, sharded Muta STEM candidate datasets.

This command builds a review pack locally by default.  The multi-million-row
warehouse is opt-in because it materializes pinned open datasets and requires a
pinned DeepMind Mathematics checkout plus an authenticated local TemplateGSM snapshot.  The warehouse is not automatically a
training set: rows marked ``training_eligible=false`` must pass their stated
audit and have a matching exact-row receipt whose decision is ``approved``
before selection.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .adapters import (
    TemplateGSMSnapshot,
    iter_deepmind_mathematics,
    iter_gsm8k,
    iter_nemotron_science,
    iter_qasc,
    iter_templategsm,
    public_evaluation_holdouts,
    validate_templategsm_snapshot,
)
from .core import (
    HoldoutIndex,
    _local_holdout_prompts,
    current_git_revision,
    index_source_registry_document,
    normalize_text,
    normalized_sha256,
    repository_root,
    sha256_file,
    validate_record,
)
from .deepmind_overlay import OVERLAY_VERSION
from .generators import GENERATORS, PEDAGOGIES, generate_local_example, verify_local_record
from .tokenization import (
    DEFAULT_MAX_SEQUENCE_TOKENS,
    QwenTokenCounter,
    TokenLimitError,
)

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_REVIEW_ROWS = 10_000
QASC_TRAIN_CAPACITY = 8_126
GSM8K_TRAIN_CAPACITY = 6_999
# Exhaustively audited adapter-emitted capacities for the pinned source
# revisions under the sealed holdout and verifier gates. Anchors are divided
# as evenly as possible, so GSM8K determines the balanced aggregate ceiling.
MAX_BALANCED_ANCHOR_ROWS = 2 * GSM8K_TRAIN_CAPACITY
PROVENANCE_FILES = (
    "__init__.py",
    "adapters.py",
    "build.py",
    "core.py",
    "deepmind_overlay.py",
    "generators.py",
    "recipe.json",
    "schema.json",
    "source_registry.json",
    "templategsm_filter_audit.json",
    "templategsm_full_audit.json",
    "templategsm_static_prefilter_v1.py",
    "requirements-build.lock.txt",
    "requirements-build.txt",
    "tokenization.py",
)
PROVENANCE_CODE_DIR = "provenance-code"
PROVENANCE_HOLDOUT_DIR = "provenance-holdouts"
PROVENANCE_SOURCE_EVIDENCE_DIR = "provenance-source-evidence"
HOLDOUT_SOURCE_FILES = (
    "bench/judges_prompt_suite.py",
    "bench/stem_prompt_suite.py",
    "bench/live_prompt_battery.py",
    "bench/submission/metadata.json",
    "muta-adtc-2026/metadata.json",
)
EXECUTED_CODE_FILES = (
    "__init__.py",
    "adapters.py",
    "build.py",
    "core.py",
    "deepmind_overlay.py",
    "generators.py",
    "tokenization.py",
)
IMPORTED_CODE_SHA256 = {name: sha256_file(PACKAGE_DIR / name) for name in EXECUTED_CODE_FILES}

SOURCE_VERIFICATION_SEMANTICS: dict[str, dict[str, Any]] = {
    "muta_verified_stem_v2": {
        "scope": "full_record_regeneration_and_answer_recomputation",
        "independent_answer_rederivation": True,
        "semantic_correctness_assurance": "programmatic_local_generator_specification",
        "summary": (
            "Regenerates the complete row from its recorded seed and index, recomputes the "
            "answer from stored structured inputs, and compares the prompt, completion, answer, "
            "metadata, and provenance. This is programmatic verification against the local "
            "generator specification, not independent human review."
        ),
    },
    "deepmind_mathematics": {
        "scope": "pinned_generator_self_emitted_problem_and_answer",
        "independent_answer_rederivation": False,
        "semantic_correctness_assurance": "not_independently_certified",
        "summary": (
            "The pinned DeepMind generator emits the problem and answer together. The build "
            "records the generator seed and checks deterministic replay, but it does not "
            "independently derive the answer from the generated problem."
        ),
    },
    "template_gsm": {
        "scope": "pinned_static_prefilter_and_whole_template_quarantine",
        "independent_answer_rederivation": False,
        "semantic_correctness_assurance": "not_independently_certified",
        "summary": (
            "Binds a full pinned-source audit, quarantines every template with any observed "
            "failure, and rechecks each survivor for a finite canonical result, terminal target "
            "support, float artifacts, and exact numeric-only equality contradictions. Publisher "
            "solution code is neither parsed nor executed, the prompt is not independently "
            "solved, and every surviving row still requires exact-row human approval."
        ),
    },
    "qasc": {
        "scope": "publisher_answer_key_and_supporting_facts_only",
        "independent_answer_rederivation": False,
        "semantic_correctness_assurance": "not_independently_certified",
        "summary": (
            "Expands the publisher answer key to its choice text and uses the publisher fact1 and "
            "fact2 fields as the rationale. Neither the key nor the supporting facts are "
            "independently verified."
        ),
    },
    "gsm8k": {
        "scope": "calculator_annotation_recomputation_only",
        "independent_answer_rederivation": False,
        "semantic_correctness_assurance": "not_independently_certified",
        "summary": (
            "Recomputes every inline calculator annotation with a restricted arithmetic AST and "
            "requires the last annotation to equal the published final answer. It does not "
            "independently solve the prompt or semantically certify the narrative reasoning."
        ),
    },
}


class JsonlShardWriter:
    """Write compact JSONL shards while hashing every completed artifact."""

    def __init__(self, output_dir: Path, shard_rows: int) -> None:
        self.output_dir = output_dir
        self.shard_rows = shard_rows
        self.total_rows = 0
        self._shard_rows = 0
        self._handle = None
        self._partial_path: Path | None = None
        self.shards: list[dict[str, Any]] = []

    def _open(self) -> None:
        index = len(self.shards)
        self._partial_path = self.output_dir / f"part-{index:05d}.jsonl.partial"
        self._handle = self._partial_path.open("w", encoding="utf-8", newline="\n")
        self._shard_rows = 0

    def write(self, record: dict[str, Any]) -> None:
        if self._handle is None:
            self._open()
        assert self._handle is not None
        self._handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._shard_rows += 1
        self.total_rows += 1
        if self._shard_rows >= self.shard_rows:
            self._close_shard()

    def _close_shard(self) -> None:
        if self._handle is None or self._partial_path is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        final_path = self._partial_path.with_suffix("")
        self._partial_path.replace(final_path)
        self.shards.append(
            {
                "path": final_path.name,
                "rows": self._shard_rows,
                "bytes": final_path.stat().st_size,
                "sha256": sha256_file(final_path),
            }
        )
        self._handle = None
        self._partial_path = None
        self._shard_rows = 0

    def close(self) -> None:
        self._close_shard()

    def abort(self) -> dict[str, Any] | None:
        """Flush but retain an unmistakably partial shard after a failed build."""

        if self._handle is None or self._partial_path is None:
            return None
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        receipt = {
            "path": self._partial_path.name,
            "rows": self._shard_rows,
            "bytes": self._partial_path.stat().st_size,
            "sha256": sha256_file(self._partial_path),
        }
        self._handle = None
        self._partial_path = None
        self._shard_rows = 0
        return receipt


def _load_hashed_json(path: Path) -> tuple[dict[str, Any], str]:
    """Load one immutable byte snapshot and return its content digest."""

    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Fsync a JSON document before atomically promoting it to its final name."""

    partial_path = path.with_name(f"{path.name}.partial")
    with partial_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    partial_path.replace(path)


def _archive_provenance_files(*, output_dir: Path, root: Path) -> dict[str, Any]:
    """Snapshot exact build inputs and issue deterministic hash receipts."""

    archive_dir = output_dir / PROVENANCE_CODE_DIR
    archive_dir.mkdir()
    file_receipts: list[dict[str, Any]] = []
    source_files = [(PACKAGE_DIR / name, name) for name in PROVENANCE_FILES]
    source_files.append((root / "LICENSE", "MUTA-LICENSE"))
    for source_path, archive_name in source_files:
        if not source_path.is_file():
            raise FileNotFoundError(f"required provenance input is missing: {source_path}")
        source_hash_before = sha256_file(source_path)
        if archive_name in IMPORTED_CODE_SHA256:
            imported_hash = IMPORTED_CODE_SHA256[archive_name]
            if source_hash_before != imported_hash:
                raise RuntimeError(
                    f"loaded code differs from the source being archived: {source_path}; "
                    "restart the build in a fresh Python process"
                )
        archived_path = archive_dir / archive_name
        shutil.copyfile(source_path, archived_path)
        source_hash_after = sha256_file(source_path)
        archived_hash = sha256_file(archived_path)
        if source_hash_before != source_hash_after or archived_hash != source_hash_before:
            raise RuntimeError(f"provenance input changed while it was archived: {source_path}")
        file_receipts.append(
            {
                "path": archived_path.relative_to(output_dir).as_posix(),
                "source_path": source_path.relative_to(root).as_posix(),
                "bytes": archived_path.stat().st_size,
                "sha256": archived_hash,
            }
        )

    receipts_path = archive_dir / "receipts.json"
    receipts_path.write_text(
        json.dumps(
            {"schema_version": 1, "files": file_receipts},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "directory": archive_dir.relative_to(output_dir).as_posix(),
        "files": file_receipts,
        "receipts": {
            "path": receipts_path.relative_to(output_dir).as_posix(),
            "bytes": receipts_path.stat().st_size,
            "sha256": sha256_file(receipts_path),
        },
    }


def _archive_holdout_sources(*, output_dir: Path, root: Path) -> dict[str, Any]:
    """Snapshot local sealed-evaluation definitions used by contamination checks."""

    archive_dir = output_dir / PROVENANCE_HOLDOUT_DIR
    archive_dir.mkdir()
    receipts: list[dict[str, Any]] = []
    for relative in HOLDOUT_SOURCE_FILES:
        source_path = root / relative
        if not source_path.is_file():
            if relative.startswith("bench/") and "/submission/" not in relative:
                raise FileNotFoundError(f"required holdout input is missing: {source_path}")
            continue
        before = sha256_file(source_path)
        archived_path = archive_dir / relative
        archived_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, archived_path)
        after = sha256_file(source_path)
        archived = sha256_file(archived_path)
        if before != after or archived != before:
            raise RuntimeError(f"holdout input changed while archived: {source_path}")
        receipts.append(
            {
                "source_path": relative,
                "path": archived_path.relative_to(output_dir).as_posix(),
                "bytes": archived_path.stat().st_size,
                "sha256": archived,
                "sealed_evaluation_input": True,
            }
        )
    receipts_path = archive_dir / "receipts.json"
    receipts_path.write_text(
        json.dumps(
            {"schema_version": 1, "files": receipts},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "directory": archive_dir.relative_to(output_dir).as_posix(),
        "files": receipts,
        "receipts": {
            "path": receipts_path.relative_to(output_dir).as_posix(),
            "bytes": receipts_path.stat().st_size,
            "sha256": sha256_file(receipts_path),
        },
    }


def _archive_source_evidence(
    *,
    output_dir: Path,
    requested_source_ids: set[str],
    registry: dict[str, dict[str, Any]],
    deepmind_checkout: Path | None,
    templategsm_snapshot: TemplateGSMSnapshot | None,
) -> dict[str, Any]:
    """Freeze pinned source cards, citations, and licence evidence for used sources."""

    archive_dir = output_dir / PROVENANCE_SOURCE_EVIDENCE_DIR
    archive_dir.mkdir()
    receipts: list[dict[str, Any]] = []

    def archive_file(source_id: str, source_path: Path, name: str, locator: str) -> None:
        before = sha256_file(source_path)
        destination = archive_dir / source_id / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)
        after = sha256_file(source_path)
        archived = sha256_file(destination)
        if before != after or archived != before:
            raise RuntimeError(f"source evidence changed while archived: {source_path}")
        receipts.append(
            {
                "source_id": source_id,
                "revision": registry[source_id]["revision"],
                "locator": locator,
                "path": destination.relative_to(output_dir).as_posix(),
                "bytes": destination.stat().st_size,
                "sha256": archived,
            }
        )

    if "deepmind_mathematics" in requested_source_ids:
        if deepmind_checkout is None:
            raise ValueError("DeepMind source evidence requires its pinned checkout")
        for name in ("LICENSE", "README.md"):
            source_path = deepmind_checkout.resolve() / name
            if not source_path.is_file():
                raise FileNotFoundError(f"DeepMind source evidence is missing: {source_path}")
            archive_file(
                "deepmind_mathematics",
                source_path,
                name,
                f"git:{registry['deepmind_mathematics']['revision']}:{name}",
            )

    if "template_gsm" in requested_source_ids and templategsm_snapshot is not None:
        archive_file(
            "template_gsm",
            templategsm_snapshot.root / "README.md",
            "README.md",
            (f"local-snapshot:{templategsm_snapshot.receipt['inventory_sha256']}:README.md"),
        )

    huggingface_sources = sorted(
        source_id
        for source_id in requested_source_ids
        if registry[source_id].get("repository_type") == "huggingface_dataset"
        and not (source_id == "template_gsm" and templategsm_snapshot is not None)
    )
    if huggingface_sources:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import EntryNotFoundError

        for source_id in huggingface_sources:
            source = registry[source_id]
            repo_id = source["repository_id"]
            revision = source["revision"]
            downloaded = 0
            for name in ("README.md", "LICENSE", "LICENSE.md", "LICENSE.txt", "CITATION.cff"):
                try:
                    cached = Path(
                        hf_hub_download(
                            repo_id=repo_id,
                            filename=name,
                            repo_type="dataset",
                            revision=revision,
                        )
                    )
                except EntryNotFoundError:
                    continue
                archive_file(
                    source_id,
                    cached,
                    name,
                    f"hf://datasets/{repo_id}@{revision}/{name}",
                )
                downloaded += 1
            if downloaded == 0:
                raise FileNotFoundError(
                    f"no source-card or licence evidence found for {source_id}@{revision}"
                )

    receipts_path = archive_dir / "receipts.json"
    receipts_path.write_text(
        json.dumps(
            {"schema_version": 1, "files": receipts},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "directory": archive_dir.relative_to(output_dir).as_posix(),
        "files": receipts,
        "receipts": {
            "path": receipts_path.relative_to(output_dir).as_posix(),
            "bytes": receipts_path.stat().st_size,
            "sha256": sha256_file(receipts_path),
        },
    }


def _content_revision(*archives: dict[str, Any]) -> str:
    """Identify uncommitted build and holdout inputs by archived receipts, not HEAD."""

    receipt_hashes = [archive["receipts"]["sha256"] for archive in archives]
    if not receipt_hashes or any(
        not isinstance(receipt_hash, str) or len(receipt_hash) != 64
        for receipt_hash in receipt_hashes
    ):
        raise ValueError("invalid provenance receipt hash")
    composite = hashlib.sha256("\n".join(receipt_hashes).encode("ascii")).hexdigest()
    return f"sha256:{composite}"


def _git_worktree_receipt(root: Path) -> dict[str, Any]:
    """Record a bounded, content-free snapshot of dirty and untracked state."""

    status_result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    raw_status = status_result.stdout
    tokens = raw_status.split(b"\0")
    if tokens and not tokens[-1]:
        tokens.pop()
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if len(token) < 4 or token[2:3] != b" ":
            raise RuntimeError("unexpected git status --porcelain=v1 -z output")
        status = token[:2].decode("ascii", errors="replace")
        path = os.fsdecode(token[3:])
        entry = {"status": status, "path": path}
        if "R" in status or "C" in status:
            index += 1
            if index >= len(tokens):
                raise RuntimeError("truncated rename/copy entry in git status output")
            entry["original_path"] = os.fsdecode(tokens[index])
        entries.append(entry)
        index += 1

    provenance_paths = [
        (PACKAGE_DIR / name).relative_to(root).as_posix() for name in PROVENANCE_FILES
    ]
    provenance_paths.extend(["LICENSE", *HOLDOUT_SOURCE_FILES])
    tracked_result = subprocess.run(
        ["git", "ls-files", "-z", "--", *provenance_paths],
        cwd=root,
        check=True,
        capture_output=True,
    )
    tracked_paths = {os.fsdecode(path) for path in tracked_result.stdout.split(b"\0") if path}
    statuses_by_path: dict[str, list[str]] = {}
    for entry in entries:
        statuses_by_path.setdefault(entry["path"], []).append(entry["status"])
        if "original_path" in entry:
            statuses_by_path.setdefault(entry["original_path"], []).append(entry["status"])

    input_files = []
    for path in provenance_paths:
        statuses = sorted(set(statuses_by_path.get(path, [])))
        tracked = path in tracked_paths
        input_files.append(
            {
                "path": path,
                "tracked": tracked,
                "status": statuses or (["clean"] if tracked else ["not_tracked_or_ignored"]),
                "untracked": "??" in statuses,
            }
        )

    untracked_paths = sorted(entry["path"] for entry in entries if entry["status"] == "??")
    untracked_pathset = b"\0".join(os.fsencode(path) for path in untracked_paths)
    return {
        "dirty": bool(entries),
        "entry_count": len(entries),
        "tracked_change_count": sum(entry["status"] != "??" for entry in entries),
        "untracked_count": len(untracked_paths),
        "staged_change_count": sum(entry["status"][0] not in {" ", "?", "!"} for entry in entries),
        "unstaged_change_count": sum(
            entry["status"][1] not in {" ", "?", "!"} for entry in entries
        ),
        "porcelain_v1_z_sha256": hashlib.sha256(raw_status).hexdigest(),
        "untracked_pathset_sha256": hashlib.sha256(untracked_pathset).hexdigest(),
        "input_files": input_files,
        "path_disclosure": "only provenance input paths are recorded; repository-wide paths are hashed",
    }


def _deepmind_checkout_receipt(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.resolve()

    def git_output(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=resolved,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    working_tree_status = git_output("status", "--porcelain=v1", "--untracked-files=all")
    license_path = resolved / "LICENSE"
    return {
        "path": str(resolved),
        "git_revision": git_output("rev-parse", "HEAD"),
        "git_tree": git_output("rev-parse", "HEAD^{tree}"),
        "working_tree_clean_including_untracked": not working_tree_status,
        "working_tree_status_sha256": hashlib.sha256(
            working_tree_status.encode("utf-8")
        ).hexdigest(),
        "license_path": "LICENSE",
        "license_sha256": sha256_file(license_path),
    }


def _deepmind_determinism_receipt(
    *, checkout: Path | None, seed: int, root: Path, rows: int = 200
) -> dict[str, Any] | None:
    """Prove the pinned generator + overlay matches across fresh hash seeds."""

    if checkout is None:
        return None
    probe = """\
import hashlib
import importlib
import json
import sys
from pathlib import Path

package = "model-development.finetune.muta_dataset_v2"
adapters = importlib.import_module(package + ".adapters")
core = importlib.import_module(package + ".core")
iterator = adapters.iter_deepmind_mathematics(
    checkout=Path(sys.argv[1]),
    holdouts=core.HoldoutIndex([]),
    limit=int(sys.argv[3]),
    seed=int(sys.argv[2]),
    split="train",
)
digest = hashlib.sha256()
for _, record in zip(range(int(sys.argv[3])), iterator):
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest.update((payload + "\\n").encode("utf-8"))
print(digest.hexdigest())
"""
    hashes: dict[str, str] = {}
    for hash_seed in ("1", "777"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = hash_seed
        result = subprocess.run(
            [sys.executable, "-c", probe, str(checkout.resolve()), str(seed), str(rows)],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        observed = result.stdout.strip().splitlines()[-1]
        if not re.fullmatch(r"[0-9a-f]{64}", observed):
            raise RuntimeError("DeepMind determinism probe returned an invalid digest")
        hashes[hash_seed] = observed
    if len(set(hashes.values())) != 1:
        raise RuntimeError(f"DeepMind generator is not cross-process deterministic: {hashes}")
    overlay_path = PACKAGE_DIR / "deepmind_overlay.py"
    return {
        "status": "passed",
        "rows": rows,
        "dataset_seed": seed,
        "python_hash_seeds": [1, 777],
        "record_stream_sha256": next(iter(hashes.values())),
        "probe_script_sha256": hashlib.sha256(probe.encode("utf-8")).hexdigest(),
        "overlay_version": OVERLAY_VERSION,
        "overlay_sha256": sha256_file(overlay_path),
    }


def _formula_template_method_key(record: dict[str, Any]) -> str:
    verification = record.get("verification") or {}
    formula_id = str(verification.get("formula_id", "")).strip()
    if formula_id:
        return f"formula:{formula_id}"
    template_id = str(verification.get("template_id", "")).strip()
    if template_id:
        return f"template:{template_id}"
    method = str(verification.get("method", "")).strip() or "unspecified"
    if record.get("provenance", {}).get("source_id") == "muta_verified_stem_v2":
        return f"formula:{method}"
    return f"method:{method}"


def _audit_eligibility_key(record: dict[str, Any]) -> str:
    training_eligible = (record.get("verification") or {}).get("training_eligible")
    if training_eligible is True:
        return "training_eligible"
    if training_eligible is False:
        return "audit_required"
    return "eligibility_unspecified"


def _training_disposition_key(
    record: dict[str, Any], source_registry: dict[str, dict[str, Any]]
) -> str:
    """Classify every warehouse row into one conservative training disposition."""

    if record.get("split") != "train":
        return "non_train_holdout"
    source_id = str((record.get("provenance") or {}).get("source_id", ""))
    source = source_registry.get(source_id) or {}
    if (record.get("verification") or {}).get("training_eligible") is True and source.get(
        "sft_approval_scope"
    ) == "native":
        return "native_eligible_train"
    return "audit_required_train"


def _source_split_eligibility_matrix(
    counts: Counter[tuple[str, str, str]],
) -> dict[str, dict[str, dict[str, int]]]:
    """Return deterministic source × warehouse-split × eligibility counts."""

    matrix: dict[str, dict[str, dict[str, int]]] = {}
    for (source_id, warehouse_split, eligibility), count in sorted(counts.items()):
        matrix.setdefault(source_id, {}).setdefault(warehouse_split, {})[eligibility] = count
    return matrix


def _token_count_bucket(count: int) -> str:
    if count <= 128:
        return "0001-0128"
    if count <= 256:
        return "0129-0256"
    if count <= 512:
        return "0257-0512"
    if count <= 768:
        return "0513-0768"
    return "0769-plus"


def _deterministic_split(record: dict[str, Any], template_holdout_fraction: float) -> str:
    """Keep real reusable template/module clusters wholly in the OOD holdout.

    Local formulas are scarce skill families, while QASC/GSM8K already have
    sealed upstream validation/test sets and only singleton row identifiers.
    Calling a singleton hash or an entire local skill family "template OOD"
    would be misleading, so those sources remain train-pool candidates.
    """

    provenance = record["provenance"]
    if provenance["source_id"] in {"muta_verified_stem_v2", "qasc", "gsm8k"}:
        return "train"
    cluster_key = f"{provenance['source_id']}::{provenance['semantic_cluster_id']}"
    digest = hashlib.sha256(cluster_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return "template_holdout" if bucket < template_holdout_fraction else "train"


def _apportion(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Turn positive weights into exact integer quotas with stable tie-breaking."""

    positive = {key: value for key, value in weights.items() if value > 0}
    scale = sum(positive.values())
    exact = {key: total * value / scale for key, value in positive.items()}
    quotas = {key: int(value) for key, value in exact.items()}
    remaining = total - sum(quotas.values())
    order = sorted(positive, key=lambda key: (-(exact[key] - quotas[key]), key))
    for key in order[:remaining]:
        quotas[key] += 1
    return quotas


def _local_rows(
    *,
    holdouts: HoldoutIndex,
    target: int,
    seed: int,
    source_revision: str,
    subject_weights: dict[str, float],
    pedagogy_weights: dict[str, float],
) -> Iterable[dict[str, Any]]:
    topic_subject: dict[str, str] = {}
    topic_generator_index: dict[str, int] = {}
    for index, generator in enumerate(GENERATORS):
        problem = generator(index, seed)
        if problem.topic in topic_generator_index:
            raise ValueError(f"duplicate local generator topic: {problem.topic}")
        topic_subject[problem.topic] = problem.subject
        topic_generator_index[problem.topic] = index
    available_subjects = set(topic_subject.values())
    subject_quotas = _apportion(
        target,
        {key: value for key, value in subject_weights.items() if key in available_subjects},
    )
    topic_quotas: dict[str, int] = {}
    for subject, subject_quota in subject_quotas.items():
        topics = sorted(topic for topic, owner in topic_subject.items() if owner == subject)
        topic_quotas.update(_apportion(subject_quota, {topic: 1.0 for topic in topics}))
    topic_pedagogy_quotas = {
        (topic, pedagogy): quota
        for topic, topic_quota in topic_quotas.items()
        for pedagogy, quota in _apportion(topic_quota, pedagogy_weights).items()
    }

    pedagogy_slots: dict[str, list[int]] = {}
    for slot, pedagogy in enumerate(PEDAGOGIES):
        pedagogy_slots.setdefault(pedagogy, []).append(slot)

    emitted = 0
    seen_prompts: set[str] = set()
    for topic, pedagogy in sorted(topic_pedagogy_quotas):
        quota = topic_pedagogy_quotas[(topic, pedagogy)]
        generator_index = topic_generator_index[topic]
        slots = pedagogy_slots[pedagogy]
        accepted = 0
        attempt = 0
        attempt_ceiling = max(quota * 100, 10_000)
        while accepted < quota and attempt < attempt_ceiling:
            slot = slots[attempt % len(slots)]
            cycle = attempt // len(slots)
            record_index = generator_index + len(GENERATORS) * (slot + len(PEDAGOGIES) * cycle)
            attempt += 1
            record = generate_local_example(
                record_index,
                seed=seed,
                holdouts=holdouts,
                split="train",
                source_revision=source_revision,
            )
            if record is None or not verify_local_record(record):
                continue
            if record["topic"] != topic or record["pedagogy"] != pedagogy:
                raise RuntimeError("local generator index mapping produced the wrong quota cell")
            key = normalize_text(record["prompt"])
            if key in seen_prompts:
                continue
            seen_prompts.add(key)
            accepted += 1
            emitted += 1
            yield record
        if accepted < quota:
            raise RuntimeError(
                f"local generator cell {topic}/{pedagogy} produced only {accepted:,} "
                f"unique verified rows after {attempt:,} attempts; requested {quota:,}"
            )
    if emitted < target:
        raise RuntimeError(
            f"local generator produced only {emitted:,} unique verified rows; requested {target:,}"
        )


def _requested_allocations(args: argparse.Namespace, recipe: dict[str, Any]) -> dict[str, int]:
    if args.profile == "review":
        return {
            "muta_verified_stem_v2": args.local_rows
            if args.local_rows is not None
            else DEFAULT_REVIEW_ROWS
        }
    allocations = dict(recipe["warehouse_allocations"])
    overrides = {
        "muta_verified_stem_v2": args.local_rows,
        "deepmind_mathematics": args.deepmind_rows,
        "template_gsm": args.templategsm_rows,
        "nemotron_science_v1": args.nemotron_rows,
        "licensed_anchors": args.anchor_rows,
    }
    allocations.update({key: value for key, value in overrides.items() if value is not None})
    return allocations


def _source_streams(
    args: argparse.Namespace,
    holdouts: HoldoutIndex,
    allocations: dict[str, int],
    recipe: dict[str, Any],
    local_source_revision: str,
    templategsm_snapshot: TemplateGSMSnapshot | None,
) -> list[tuple[str, int, Iterable[dict[str, Any]]]]:

    streams: list[tuple[str, int, Iterable[dict[str, Any]]]] = []
    local_target = int(allocations.get("muta_verified_stem_v2", 0))
    if local_target:
        streams.append(
            (
                "muta_verified_stem_v2",
                local_target,
                _local_rows(
                    holdouts=holdouts,
                    target=local_target,
                    seed=args.seed,
                    source_revision=local_source_revision,
                    subject_weights=recipe["local_generation_subject_targets"],
                    pedagogy_weights=recipe["local_generation_pedagogy_targets"],
                ),
            )
        )

    deepmind_target = int(allocations.get("deepmind_mathematics", 0))
    if deepmind_target:
        if args.deepmind_checkout is None:
            raise ValueError("--deepmind-checkout is required when DeepMind rows are requested")
        streams.append(
            (
                "deepmind_mathematics",
                deepmind_target,
                iter_deepmind_mathematics(
                    checkout=args.deepmind_checkout,
                    holdouts=holdouts,
                    limit=deepmind_target,
                    seed=args.seed,
                    split="train",
                ),
            )
        )

    templategsm_target = int(allocations.get("template_gsm", 0))
    if templategsm_target:
        streams.append(
            (
                "template_gsm",
                templategsm_target,
                iter_templategsm(
                    holdouts=holdouts,
                    limit=templategsm_target,
                    seed=args.seed,
                    split="train",
                    per_template_cap=args.templategsm_template_cap,
                    snapshot=templategsm_snapshot,
                ),
            )
        )

    nemotron_target = int(allocations.get("nemotron_science_v1", 0))
    if nemotron_target:
        streams.append(
            (
                "nemotron_science_v1",
                nemotron_target,
                iter_nemotron_science(
                    holdouts=holdouts,
                    limit=nemotron_target,
                    seed=args.seed,
                    split="train",
                ),
            )
        )

    anchor_target = int(allocations.get("licensed_anchors", 0))
    if anchor_target:
        qasc_target = anchor_target // 2 + anchor_target % 2
        gsm_target = anchor_target - qasc_target
        if qasc_target > QASC_TRAIN_CAPACITY or gsm_target > GSM8K_TRAIN_CAPACITY:
            raise ValueError(
                "licensed anchor request exceeds the balanced QASC/GSM8K train capacity: "
                f"requested={anchor_target}, maximum={MAX_BALANCED_ANCHOR_ROWS}"
            )
        streams.extend(
            [
                (
                    "qasc",
                    qasc_target,
                    iter_qasc(
                        holdouts=holdouts,
                        limit=qasc_target,
                        seed=args.seed,
                        split="train",
                    ),
                ),
                (
                    "gsm8k",
                    gsm_target,
                    iter_gsm8k(
                        holdouts=holdouts,
                        limit=gsm_target,
                        seed=args.seed,
                        split="train",
                    ),
                ),
            ]
        )
    return streams


def _build_impl(args: argparse.Namespace) -> dict[str, Any]:
    args._output_touched_by_build = False
    if args.profile not in {"review", "warehouse"}:
        raise ValueError(f"unsupported build profile: {args.profile!r}")
    root = repository_root()
    recipe_path = PACKAGE_DIR / "recipe.json"
    schema_path = PACKAGE_DIR / "schema.json"
    registry_path = PACKAGE_DIR / "source_registry.json"
    recipe, recipe_loaded_sha256 = _load_hashed_json(recipe_path)
    registry_document, registry_loaded_sha256 = _load_hashed_json(registry_path)
    registry = index_source_registry_document(registry_document)
    schema_document, schema_loaded_sha256 = _load_hashed_json(schema_path)
    schema_validator = Draft202012Validator(schema_document)
    loaded_input_sha256 = {
        recipe_path.name: recipe_loaded_sha256,
        registry_path.name: registry_loaded_sha256,
        schema_path.name: schema_loaded_sha256,
    }

    allocations = _requested_allocations(args, recipe)
    anchor_target = int(allocations.get("licensed_anchors", 0))
    if anchor_target > MAX_BALANCED_ANCHOR_ROWS:
        raise ValueError(
            "licensed anchor request exceeds the balanced QASC/GSM8K train capacity: "
            f"requested={anchor_target}, maximum={MAX_BALANCED_ANCHOR_ROWS}"
        )
    remote_target = sum(
        count for source_id, count in allocations.items() if source_id != "muta_verified_stem_v2"
    )
    if remote_target and not args.include_public_holdouts:
        raise ValueError(
            "external rows require --include-public-holdouts so public validation/test "
            "sets are sealed before materialization"
        )
    if allocations.get("deepmind_mathematics", 0) and args.deepmind_checkout is None:
        raise ValueError("--deepmind-checkout is required when DeepMind rows are requested")
    templategsm_target = int(allocations.get("template_gsm", 0))
    if templategsm_target and args.templategsm_snapshot is None:
        raise ValueError("--templategsm-snapshot is required when TemplateGSM rows are requested")
    if allocations.get("deepmind_mathematics", 0) and os.environ.get("PYTHONHASHSEED") != str(
        args.seed
    ):
        raise RuntimeError(
            "DeepMind generation depends on Python hash iteration order; relaunch the build with "
            f"PYTHONHASHSEED={args.seed} so the startup hash seed is fixed"
        )

    allowed_licenses = set(registry_document["policy"].get("allowed_licenses") or ())
    allocation_sources = {
        "muta_verified_stem_v2": ("muta_verified_stem_v2",),
        "deepmind_mathematics": ("deepmind_mathematics",),
        "template_gsm": ("template_gsm",),
        "nemotron_science_v1": ("nemotron_science_v1",),
        "licensed_anchors": ("qasc", "gsm8k"),
    }
    for allocation, source_ids in allocation_sources.items():
        if not allocations.get(allocation, 0):
            continue
        for source_id in source_ids:
            if registry[source_id].get("status") not in {
                "enabled",
                "enabled_anchor",
                "enabled_optional",
                "enabled_silver",
            }:
                raise ValueError(f"requested source {source_id} is not enabled")
    for source in registry.values():
        if source.get("status") not in {
            "enabled",
            "enabled_anchor",
            "enabled_optional",
            "enabled_silver",
        }:
            continue
        if source.get("license") not in allowed_licenses:
            raise ValueError(f"enabled source {source['id']} has a non-allowlisted licence")
        for required in (
            "allowed_splits",
            "allowed_verification_statuses",
            "warehouse_training_eligible",
            "sft_approval_scope",
            "synthetic",
        ):
            if required not in source:
                raise ValueError(f"enabled source {source['id']} omits {required}")
        expected_scope = "native" if source["warehouse_training_eligible"] is True else "row_only"
        if source["sft_approval_scope"] != expected_scope:
            raise ValueError(f"enabled source {source['id']} has inconsistent SFT approval scope")

    output_dir = args.output.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    if args.profile == "warehouse" and args.tokenization != "required":
        raise ValueError("warehouse builds require exact tokenizer accounting")
    templategsm_snapshot = (
        validate_templategsm_snapshot(args.templategsm_snapshot)
        if templategsm_target and args.templategsm_snapshot is not None
        else None
    )
    deepmind_determinism = _deepmind_determinism_receipt(
        checkout=args.deepmind_checkout if allocations.get("deepmind_mathematics", 0) else None,
        seed=args.seed,
        root=root,
    )

    source_local_holdouts = _local_holdout_prompts(root)
    remote_holdouts: list[str] = []
    public_holdout_source_receipts: list[dict[str, Any]] = []
    if args.include_public_holdouts:
        remote_holdouts, public_holdout_source_receipts = public_evaluation_holdouts()
    git_revision = current_git_revision(root)

    token_counter = (
        QwenTokenCounter(max_sequence_tokens=args.max_sequence_tokens)
        if args.tokenization == "required"
        else None
    )
    git_worktree = _git_worktree_receipt(root)
    args._output_touched_by_build = True
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
    provenance_archive = _archive_provenance_files(output_dir=output_dir, root=root)
    archived_input_hashes = {
        Path(receipt["path"]).name: receipt["sha256"] for receipt in provenance_archive["files"]
    }
    for name, loaded_hash in loaded_input_sha256.items():
        if archived_input_hashes.get(name) != loaded_hash:
            raise RuntimeError(
                f"loaded {name} differs from its provenance archive; restart the build"
            )
    holdout_archive = _archive_holdout_sources(output_dir=output_dir, root=root)
    requested_source_ids = {
        source_id
        for allocation, source_ids in allocation_sources.items()
        if allocations.get(allocation, 0)
        for source_id in source_ids
    }
    source_evidence_archive = _archive_source_evidence(
        output_dir=output_dir,
        requested_source_ids=requested_source_ids,
        registry=registry,
        deepmind_checkout=args.deepmind_checkout,
        templategsm_snapshot=templategsm_snapshot,
    )
    archived_holdout_root = output_dir / PROVENANCE_HOLDOUT_DIR
    local_holdouts = _local_holdout_prompts(archived_holdout_root)
    if local_holdouts != source_local_holdouts:
        raise RuntimeError("local holdout sources changed between loading and archival")
    holdouts = HoldoutIndex([*local_holdouts, *remote_holdouts], threshold=args.holdout_threshold)
    local_source_revision = _content_revision(provenance_archive, holdout_archive)

    writer = JsonlShardWriter(output_dir, args.shard_rows)
    source_counts: Counter[str] = Counter()
    subject_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    pedagogy_counts: Counter[str] = Counter()
    formula_template_method_counts: Counter[str] = Counter()
    curriculum_alignment_counts: Counter[str] = Counter()
    source_subject_pedagogy_counts: Counter[str] = Counter()
    source_split_counts: Counter[str] = Counter()
    semantic_clusters_by_source: dict[str, set[str]] = {}
    semantic_cluster_splits: dict[tuple[str, str], set[str]] = {}
    verification_counts: Counter[str] = Counter()
    eligibility_counts: Counter[str] = Counter()
    audit_eligibility_counts: Counter[str] = Counter()
    source_warehouse_split_eligibility_counts: Counter[tuple[str, str, str]] = Counter()
    training_disposition_totals: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    token_bucket_counts: Counter[str] = Counter()
    token_total = 0
    token_minimum: int | None = None
    token_maximum: int | None = None
    rejections: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    source_task_owner: dict[str, str] = {}
    cross_source_task_collision_pairs: Counter[str] = Counter()
    requested_counts: dict[str, int] = {}

    generation_succeeded = False
    generation_failure: BaseException | None = None
    try:
        for stream_name, target, stream in _source_streams(
            args,
            holdouts,
            allocations,
            recipe,
            local_source_revision,
            templategsm_snapshot,
        ):
            requested_counts[stream_name] = target
            accepted_for_stream = 0
            for record in stream:
                source_id = record["provenance"]["source_id"]
                source_task_hash = record["contamination"]["source_task_sha256"]
                prior_owner = source_task_owner.get(source_task_hash)
                if prior_owner is not None and prior_owner != source_id:
                    rejections["cross_source_duplicate_task"] += 1
                    pair = " :: ".join(sorted((prior_owner, source_id)))
                    cross_source_task_collision_pairs[pair] += 1
                    continue
                if record["id"] in seen_ids:
                    rejections["duplicate_id"] += 1
                    continue
                prompt_key = normalize_text(record["prompt"])
                if prompt_key in seen_prompts:
                    rejections["duplicate_prompt"] += 1
                    continue
                record["split"] = (
                    "review"
                    if args.profile == "review"
                    else _deterministic_split(record, args.template_holdout_fraction)
                )
                if token_counter is not None:
                    try:
                        token_counter.annotate(record)
                    except TokenLimitError:
                        rejections["token_limit"] += 1
                        continue
                errors = validate_record(
                    record,
                    source_registry=registry,
                    source_policy=registry_document["policy"],
                    holdouts=holdouts,
                )
                schema_errors = sorted(
                    schema_validator.iter_errors(record), key=lambda item: item.path
                )
                if errors or schema_errors:
                    rejections["invalid_record"] += 1
                    details = errors + [error.message for error in schema_errors]
                    raise ValueError(f"invalid {stream_name} row {record['id']}: {details}")
                seen_ids.add(record["id"])
                seen_prompts.add(prompt_key)
                source_task_owner.setdefault(source_task_hash, source_id)
                writer.write(record)
                accepted_for_stream += 1
                source_counts[record["provenance"]["source_id"]] += 1
                source_split_counts[
                    f"{record['provenance']['source_id']} :: {record['provenance']['source_split']}"
                ] += 1
                cluster_id = record["provenance"]["semantic_cluster_id"]
                semantic_clusters_by_source.setdefault(source_id, set()).add(cluster_id)
                semantic_cluster_splits.setdefault((source_id, cluster_id), set()).add(
                    record["split"]
                )
                subject_counts[record["subject"]] += 1
                topic_counts[record["topic"]] += 1
                difficulty_counts[record["difficulty"]] += 1
                pedagogy_counts[record["pedagogy"]] += 1
                formula_template_method_counts[_formula_template_method_key(record)] += 1
                curriculum_alignment_counts[record["curriculum"]["alignment"]] += 1
                source_subject_pedagogy_counts[
                    " :: ".join(
                        (
                            record["provenance"]["source_id"],
                            record["subject"],
                            record["pedagogy"],
                        )
                    )
                ] += 1
                verification_counts[record["verification"]["status"]] += 1
                eligibility_counts[
                    "eligible"
                    if record["verification"].get("training_eligible") is True
                    else "audit_required"
                ] += 1
                audit_eligibility = _audit_eligibility_key(record)
                audit_eligibility_counts[audit_eligibility] += 1
                source_warehouse_split_eligibility_counts[
                    (source_id, record["split"], audit_eligibility)
                ] += 1
                training_disposition_totals[_training_disposition_key(record, registry)] += 1
                split_counts[record["split"]] += 1
                if token_counter is not None:
                    token_count = record["tokenization"]["sequence_tokens"]
                    token_bucket_counts[_token_count_bucket(token_count)] += 1
                    token_total += token_count
                    token_minimum = (
                        token_count if token_minimum is None else min(token_minimum, token_count)
                    )
                    token_maximum = (
                        token_count if token_maximum is None else max(token_maximum, token_count)
                    )
                if args.progress_every and accepted_for_stream % args.progress_every == 0:
                    print(
                        f"{stream_name}: accepted {accepted_for_stream:,}/{target:,}",
                        file=sys.stderr,
                        flush=True,
                    )
                if accepted_for_stream >= target:
                    break
            if accepted_for_stream != target:
                raise RuntimeError(
                    f"source {stream_name} emitted {accepted_for_stream:,} valid unique rows; "
                    f"requested {target:,}"
                )
        generation_succeeded = True
    except BaseException as exc:
        generation_failure = exc
        raise
    finally:
        if generation_succeeded:
            writer.close()
        else:
            partial = writer.abort()
            failure_receipt = {
                "schema_version": 1,
                "status": "failed_or_interrupted",
                "error_type": type(generation_failure).__name__
                if generation_failure is not None
                else "unknown",
                "error": str(generation_failure) if generation_failure is not None else "unknown",
                "completed_rows": writer.total_rows - (partial["rows"] if partial else 0),
                "completed_shards": writer.shards,
                "partial_shard": partial,
                "recoverability": (
                    "No partial shard was promoted and no manifest was issued. Resume is not "
                    "implemented; retain this receipt for diagnosis and restart into a new directory."
                ),
            }
            (output_dir / "FAILED.json").write_text(
                json.dumps(failure_receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    if templategsm_snapshot is not None:
        postflight_snapshot = validate_templategsm_snapshot(templategsm_snapshot.root)
        if (
            postflight_snapshot.receipt != templategsm_snapshot.receipt
            or postflight_snapshot.filesystem_identity != templategsm_snapshot.filesystem_identity
        ):
            raise RuntimeError("TemplateGSM snapshot changed during row materialization")

    source_receipts = []
    for source_id, row_count in sorted(source_counts.items()):
        source = registry[source_id]
        source_receipts.append(
            {
                "id": source_id,
                "name": source["name"],
                "url": source["url"],
                "revision": source["revision"]
                if source["revision"] != "resolved_from_content_snapshot_at_build_time"
                else local_source_revision,
                "license": source["license"],
                "license_url": source["license_url"],
                "source_kind": source["source_kind"],
                "registry_status": source["status"],
                "rows": row_count,
            }
        )
    missing_verification_semantics = sorted(
        set(source_counts).difference(SOURCE_VERIFICATION_SEMANTICS)
    )
    if missing_verification_semantics:
        raise RuntimeError(
            "manifest verification semantics are missing for sources: "
            + ", ".join(missing_verification_semantics)
        )
    verification_semantics_by_source = {
        source_id: dict(SOURCE_VERIFICATION_SEMANTICS[source_id])
        for source_id in sorted(source_counts)
    }
    disposition_keys = (
        "native_eligible_train",
        "audit_required_train",
        "non_train_holdout",
    )
    training_disposition_summary = {
        key: training_disposition_totals[key] for key in disposition_keys
    }
    if sum(training_disposition_summary.values()) != writer.total_rows:
        raise RuntimeError("training disposition totals do not cover every warehouse row")
    if sum(source_warehouse_split_eligibility_counts.values()) != writer.total_rows:
        raise RuntimeError(
            "source × warehouse split × eligibility matrix does not cover every warehouse row"
        )
    archived_by_name = {
        Path(receipt["path"]).name: receipt for receipt in provenance_archive["files"]
    }

    def archived_input_receipt(name: str) -> dict[str, Any]:
        receipt = archived_by_name[name]
        return {
            "path": name,
            "archive_path": receipt["path"],
            "bytes": receipt["bytes"],
            "sha256": receipt["sha256"],
        }

    code_files = (
        "__init__.py",
        "adapters.py",
        "build.py",
        "core.py",
        "deepmind_overlay.py",
        "generators.py",
        "tokenization.py",
    )
    code_receipts = [archived_input_receipt(name) for name in code_files]
    dataset_fingerprint = hashlib.sha256(
        "\n".join(shard["sha256"] for shard in writer.shards).encode("ascii")
    ).hexdigest()

    package_versions = {}
    for package in (
        "datasets",
        "huggingface-hub",
        "jinja2",
        "jsonschema",
        "numpy",
        "sympy",
        "tokenizers",
        "transformers",
    ):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = None

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset_name": "muta-stem-sft-v2-candidate-warehouse",
        "artifact_role": "candidate_warehouse",
        "whole_artifact_training_authorized": False,
        "profile": args.profile,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision,
        "git_worktree": git_worktree,
        "seed": args.seed,
        "row_count": writer.total_rows,
        "dataset_fingerprint_sha256": dataset_fingerprint,
        "requested_counts": requested_counts,
        "sources": source_receipts,
        "verification_semantics_by_source": verification_semantics_by_source,
        "training_disposition_totals": training_disposition_summary,
        "counts": {
            "source": dict(sorted(source_counts.items())),
            "source_split": dict(sorted(source_split_counts.items())),
            "source_warehouse_split_eligibility": _source_split_eligibility_matrix(
                source_warehouse_split_eligibility_counts
            ),
            "semantic_cluster_count_by_source": {
                source_id: len(clusters)
                for source_id, clusters in sorted(semantic_clusters_by_source.items())
            },
            "semantic_cluster_split_overlap_count": sum(
                len(splits) > 1 for splits in semantic_cluster_splits.values()
            ),
            "cross_source_task_collision_pairs": dict(
                sorted(cross_source_task_collision_pairs.items())
            ),
            "subject": dict(sorted(subject_counts.items())),
            "topic": dict(sorted(topic_counts.items())),
            "difficulty": dict(sorted(difficulty_counts.items())),
            "pedagogy": dict(sorted(pedagogy_counts.items())),
            "formula_template_method": dict(sorted(formula_template_method_counts.items())),
            "curriculum_alignment": dict(sorted(curriculum_alignment_counts.items())),
            "source_subject_pedagogy": dict(sorted(source_subject_pedagogy_counts.items())),
            "verification": dict(sorted(verification_counts.items())),
            "eligibility": dict(sorted(eligibility_counts.items())),
            "audit_eligibility": dict(sorted(audit_eligibility_counts.items())),
            "split": dict(sorted(split_counts.items())),
        },
        "rejections": dict(sorted(rejections.items())),
        "holdouts": {
            "count": holdouts.count,
            "local_count": len(local_holdouts),
            "public_evaluation_count": len(remote_holdouts),
            "public_evaluation_source_receipts": public_holdout_source_receipts,
            "normalized_prompt_set_sha256": holdouts.digest,
            "fivegram_similarity_threshold": args.holdout_threshold,
            "local_normalized_prompt_sha256_inventory": sorted(
                {normalized_sha256(prompt) for prompt in local_holdouts}
            ),
        },
        "tokenization": (
            {
                "status": "exact",
                "tokenizer_id": token_counter.tokenizer_id,
                "tokenizer_revision": token_counter.revision,
                "chat_template_sha256": token_counter.chat_template_sha256,
                "max_sequence_tokens": token_counter.max_sequence_tokens,
                "minimum_sequence_tokens": token_minimum,
                "maximum_sequence_tokens": token_maximum,
                "mean_sequence_tokens": round(token_total / writer.total_rows, 6)
                if writer.total_rows
                else None,
                "buckets": dict(sorted(token_bucket_counts.items())),
                "truncated_rows": 0,
            }
            if token_counter is not None
            else {"status": "skipped_for_nonrelease_test"}
        ),
        "inputs": {
            "recipe": archived_input_receipt(recipe_path.name),
            "schema": archived_input_receipt(schema_path.name),
            "source_registry": archived_input_receipt(registry_path.name),
            "requirements": archived_input_receipt("requirements-build.txt"),
            "requirements_lock": archived_input_receipt("requirements-build.lock.txt"),
            "muta_license": archived_input_receipt("MUTA-LICENSE"),
            "code": code_receipts,
            "provenance_archive": provenance_archive,
            "executed_code_import_sha256": dict(sorted(IMPORTED_CODE_SHA256.items())),
            "holdout_source_archive": holdout_archive,
            "source_evidence_archive": source_evidence_archive,
            "deepmind_checkout": _deepmind_checkout_receipt(args.deepmind_checkout),
            "deepmind_determinism": deepmind_determinism,
            "templategsm_snapshot": (
                templategsm_snapshot.receipt if templategsm_snapshot is not None else None
            ),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "python_hash_probe": hash("muta-stem-dataset-v2"),
            "packages": package_versions,
        },
        "parameters": {
            "template_holdout_fraction": args.template_holdout_fraction,
            "holdout_threshold": args.holdout_threshold,
            "shard_rows": args.shard_rows,
            "templategsm_template_cap": args.templategsm_template_cap,
            "include_public_holdouts": args.include_public_holdouts,
            "tokenization": args.tokenization,
            "max_sequence_tokens": args.max_sequence_tokens,
            "progress_every": args.progress_every,
            "split_policy": (
                "template_gsm templates and deepmind_mathematics modules are cluster-hashed; "
                "local Muta, QASC, and GSM8K remain train-pool candidates because local formulas "
                "are scarce skills and anchor rows use sealed upstream validation/test sets"
            ),
        },
        "shards": writer.shards,
        "training_warning": (
            "This is a candidate warehouse. Exclude every row with split!=train or "
            "verification.training_eligible=false unless a matching immutable exact-row receipt "
            "whose decision is approved and whose rubric artifact is archived authorizes it; "
            "never train on template_holdout "
            "rows or blanket-authorize a semantic cluster."
        ),
    }
    manifest_path = output_dir / "manifest.json"
    _write_json_atomic(manifest_path, manifest)
    return manifest


def build(args: argparse.Namespace) -> dict[str, Any]:
    """Build with a durable failure marker whenever an output directory was touched."""

    try:
        return _build_impl(args)
    except BaseException as exc:
        output_dir = args.output.resolve()
        manifest_path = output_dir / "manifest.json"
        failure_path = output_dir / "FAILED.json"
        if (
            getattr(args, "_output_touched_by_build", False)
            and output_dir.is_dir()
            and not manifest_path.exists()
            and not failure_path.exists()
        ):
            completed_shards = []
            for path in sorted(output_dir.glob("part-*.jsonl")):
                completed_shards.append(
                    {
                        "path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            partial_shards = []
            for path in sorted(output_dir.glob("part-*.jsonl.partial")):
                partial_shards.append(
                    {
                        "path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            failure_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "failed_or_interrupted",
                        "stage": "setup_or_finalize",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "completed_shards": completed_shards,
                        "partial_shards": partial_shards,
                        "recoverability": (
                            "No valid manifest was issued. Retain this receipt for diagnosis and "
                            "restart into a new output directory."
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("review", "warehouse"), default="review")
    parser.add_argument(
        "--output", type=Path, default=repository_root() / "data" / "muta-stem-v2-review"
    )
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--shard-rows", type=int, default=25_000)
    parser.add_argument("--template-holdout-fraction", type=float, default=0.02)
    parser.add_argument("--holdout-threshold", type=float, default=0.82)
    parser.add_argument("--include-public-holdouts", action="store_true")
    parser.add_argument("--deepmind-checkout", type=Path)
    parser.add_argument("--templategsm-snapshot", type=Path)
    parser.add_argument("--local-rows", type=int)
    parser.add_argument("--deepmind-rows", type=int)
    parser.add_argument("--templategsm-rows", type=int)
    parser.add_argument("--nemotron-rows", type=int)
    parser.add_argument("--anchor-rows", type=int)
    parser.add_argument("--templategsm-template-cap", type=int, default=400)
    parser.add_argument(
        "--tokenization",
        choices=("required", "skip"),
        default="required",
        help="Use exact pinned Qwen chat-template token counts; skip is allowed only for tests.",
    )
    parser.add_argument("--max-sequence-tokens", type=int, default=DEFAULT_MAX_SEQUENCE_TOKENS)
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25_000,
        help="Write a progress line after this many accepted rows per source; 0 disables it.",
    )
    args = parser.parse_args(argv)
    for field in (
        "local_rows",
        "deepmind_rows",
        "templategsm_rows",
        "nemotron_rows",
        "anchor_rows",
    ):
        value = getattr(args, field)
        if value is not None and value < 0:
            parser.error(f"--{field.replace('_', '-')} must be non-negative")
    if args.shard_rows <= 0:
        parser.error("--shard-rows must be positive")
    if not 0 <= args.template_holdout_fraction < 0.5:
        parser.error("--template-holdout-fraction must be in [0, 0.5)")
    if not 0 < args.holdout_threshold <= 1:
        parser.error("--holdout-threshold must be in (0, 1]")
    if args.max_sequence_tokens <= 0:
        parser.error("--max-sequence-tokens must be positive")
    if args.progress_every < 0:
        parser.error("--progress-every must be non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
