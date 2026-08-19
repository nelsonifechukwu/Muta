"""Unit tests for the dashboard's pure logic: scoring, filename parsing, metadata rewrite."""
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import app
from app import (
    compute_scores,
    extract_metrics,
    model_listing,
    parse_params,
    parse_quant,
    server_options,
    updated_metadata,
)


@contextmanager
def tmp_app_env():
    """Point app's module-level paths at a throwaway dir with a fresh DB."""
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "model").mkdir()
        saved = (
            app.MODEL_DIR,
            app.DB_PATH,
            app.METADATA,
            app.SUBMISSION,
            app.CAMPAIGN_SUMMARY,
            app.CAMPAIGN_PARITY,
            app.CAMPAIGN_ALTERNATIVE,
            app.CAMPAIGN_AVX2_SCORE,
        )
        (
            app.MODEL_DIR,
            app.DB_PATH,
            app.METADATA,
            app.SUBMISSION,
            app.CAMPAIGN_SUMMARY,
            app.CAMPAIGN_PARITY,
            app.CAMPAIGN_ALTERNATIVE,
            app.CAMPAIGN_AVX2_SCORE,
        ) = (
            tmp / "model",
            tmp / "profiler.db",
            tmp / "metadata.json",
            tmp / "submission.json",
            tmp / "campaign-summary.json",
            tmp / "campaign-parity.json",
            tmp / "campaign-alternative.json",
            tmp / "campaign-avx2-score.json",
        )
        try:
            app.init_db()
            yield tmp
        finally:
            (
                app.MODEL_DIR,
                app.DB_PATH,
                app.METADATA,
                app.SUBMISSION,
                app.CAMPAIGN_SUMMARY,
                app.CAMPAIGN_PARITY,
                app.CAMPAIGN_ALTERNATIVE,
                app.CAMPAIGN_AVX2_SCORE,
            ) = saved


class TestComputeScores(unittest.TestCase):
    def test_full_run_scores(self):
        # SmolLM2 real numbers: arc 0.42, 38.27 tok/s, 232.22 MB peak
        s = compute_scores(arc_score=0.42, tps=38.27, peak_rss_mb=232.22,
                           throttled=False, temp_c=None, crashed=False, tps_reference=15.0)
        self.assertAlmostEqual(s["s_acc"], 42.0, places=2)
        self.assertEqual(s["s_perf"], 100.0)  # 38.27/15 capped at 1.0
        self.assertAlmostEqual(s["s_eff"], 96.76, places=1)  # (7 - 0.2268)/7 * 100
        self.assertEqual(s["thermal_penalty"], 0)
        self.assertAlmostEqual(s["s_total"], 0.5 * 42.0 + 0.3 * 100.0 + 0.2 * s["s_eff"], places=2)

    def test_slow_model_perf_not_capped(self):
        s = compute_scores(arc_score=0.5, tps=7.5, peak_rss_mb=1024,
                           throttled=False, temp_c=None, crashed=False, tps_reference=15.0)
        self.assertEqual(s["s_perf"], 50.0)

    def test_thermal_penalty_on_throttle(self):
        s = compute_scores(arc_score=0.5, tps=15.0, peak_rss_mb=1024,
                           throttled=True, temp_c=None, crashed=False, tps_reference=15.0)
        self.assertEqual(s["thermal_penalty"], 10)

    def test_thermal_penalty_on_high_temp(self):
        s = compute_scores(arc_score=0.5, tps=15.0, peak_rss_mb=1024,
                           throttled=False, temp_c=86.0, crashed=False, tps_reference=15.0)
        self.assertEqual(s["thermal_penalty"], 10)

    def test_crash_disqualifies(self):
        s = compute_scores(arc_score=None, tps=None, peak_rss_mb=None,
                           throttled=False, temp_c=None, crashed=True, tps_reference=15.0)
        self.assertEqual(s["s_total"], 0.0)
        self.assertTrue(s["disqualified"])

    def test_skip_accuracy_run_has_no_total(self):
        s = compute_scores(arc_score=None, tps=30.0, peak_rss_mb=500,
                           throttled=False, temp_c=None, crashed=False, tps_reference=15.0)
        self.assertIsNone(s["s_acc"])
        self.assertIsNone(s["s_total"])
        self.assertIsNotNone(s["s_perf"])

    def test_ram_over_budget_floors_at_zero(self):
        s = compute_scores(arc_score=0.5, tps=15.0, peak_rss_mb=8 * 1024,
                           throttled=False, temp_c=None, crashed=False, tps_reference=15.0)
        self.assertEqual(s["s_eff"], 0.0)

    def test_perf_is_relative_to_reference(self):
        # reference = fastest stored run; half its speed scores 50, matching it scores 100
        half = compute_scores(arc_score=0.5, tps=20.0, peak_rss_mb=1024,
                              throttled=False, temp_c=None, crashed=False, tps_reference=40.0)
        self.assertEqual(half["s_perf"], 50.0)
        top = compute_scores(arc_score=0.5, tps=40.0, peak_rss_mb=1024,
                             throttled=False, temp_c=None, crashed=False, tps_reference=40.0)
        self.assertEqual(top["s_perf"], 100.0)

    def test_perf_none_without_reference(self):
        s = compute_scores(arc_score=0.5, tps=20.0, peak_rss_mb=1024,
                           throttled=False, temp_c=None, crashed=False, tps_reference=None)
        self.assertIsNone(s["s_perf"])
        self.assertIsNone(s["s_total"])
        s0 = compute_scores(arc_score=0.5, tps=0.0, peak_rss_mb=1024,
                            throttled=False, temp_c=None, crashed=False, tps_reference=0.0)
        self.assertIsNone(s0["s_perf"])


class TestFilenameParsing(unittest.TestCase):
    def test_quant_variants(self):
        self.assertEqual(parse_quant("SmolLM2-135M-Instruct-Q4_K_M.gguf"), "Q4_K_M")
        self.assertEqual(parse_quant("Qwen3.5-4B-IQ4_XS.gguf"), "IQ4_XS")
        self.assertEqual(parse_quant("model-F16.gguf"), "F16")
        self.assertIsNone(parse_quant("mystery-model.gguf"))

    def test_params_variants(self):
        self.assertEqual(parse_params("SmolLM2-135M-Instruct-Q4_K_M.gguf"), "135M")
        self.assertEqual(parse_params("Qwen3.5-0.8B-MTP-Q4_K_M.gguf"), "0.8B")
        self.assertEqual(parse_params("Qwen3.5-4B-Q4_K_M.gguf"), "4B")

    def test_params_does_not_match_quant_digits(self):
        # Phi-4-mini: the "4" is part of the family name, not a param count;
        # Q4_K_M must not be read as "4B" either.
        self.assertIsNone(parse_params("Phi-4-mini-reasoning-Q4_K_M.gguf"))


class TestUpdatedMetadata(unittest.TestCase):
    BASE = {
        "team_id": "team-muta",
        "test_prompts": [{"prompt_id": "tp_001", "prompt": "x"}],
        "model": {
            "name": "old-name",
            "runtime": "llama.cpp",
            "quantization": "GGUF Q4_K_M",
            "parameters_estimate": "135M",
            "packaging": "binary_bundle",
        },
        "_runtime": {"model_path": "model/old.gguf"},
    }

    def test_rewrites_model_block_and_path(self):
        meta = updated_metadata(self.BASE, "Qwen3.5-0.8B-MTP-Q4_K_M.gguf")
        self.assertEqual(meta["_runtime"]["model_path"], "model/Qwen3.5-0.8B-MTP-Q4_K_M.gguf")
        self.assertEqual(meta["model"]["name"], "Qwen3.5-0.8B-MTP-Q4_K_M")
        self.assertEqual(meta["model"]["quantization"], "GGUF Q4_K_M")
        self.assertEqual(meta["model"]["parameters_estimate"], "0.8B")

    def test_preserves_unrelated_fields_and_leaves_unknowns(self):
        meta = updated_metadata(self.BASE, "mystery.gguf")
        self.assertEqual(meta["team_id"], "team-muta")
        self.assertEqual(meta["test_prompts"], self.BASE["test_prompts"])
        # unknown quant/params: keep previous values rather than writing junk
        self.assertEqual(meta["model"]["quantization"], "GGUF Q4_K_M")
        self.assertEqual(meta["model"]["parameters_estimate"], "135M")
        self.assertEqual(meta["model"]["runtime"], "llama.cpp")

    def test_does_not_mutate_input(self):
        before = json.loads(json.dumps(self.BASE))
        updated_metadata(self.BASE, "Qwen3.5-4B-Q4_K_M.gguf")
        self.assertEqual(self.BASE, before)


class TestExtractMetrics(unittest.TestCase):
    REPORT = {
        "submission": {
            "african_alpha_claim": True,
            "budget_laptop_claim": True,
        },
        "throughput": {
            "tokens_per_second_generation": 38.27,
            "first_token_latency_ms": 966.56,
        },
        "memory": {"peak_rss_mb": 232.22},
        "accuracy": [
            {"benchmark": "arc_easy", "score": 0.42, "metric": "acc_norm", "samples": 50}
        ],
        "cpu_thermal": {"cpu_percent_p99": 86.6, "core_temp_c_peak": None, "throttled": False},
    }

    def test_extracts_flat_metrics(self):
        m = extract_metrics(self.REPORT)
        self.assertEqual(m["tps"], 38.27)
        self.assertEqual(m["ttft_ms"], 966.56)
        self.assertEqual(m["peak_rss_mb"], 232.22)
        self.assertEqual(m["arc_score"], 0.42)
        self.assertEqual(m["arc_samples"], 50)
        self.assertIsNone(m["temp_c"])
        self.assertFalse(m["throttled"])
        self.assertTrue(m["african_claim"])
        self.assertTrue(m["budget_claim"])

    def test_empty_accuracy_list(self):
        report = json.loads(json.dumps(self.REPORT))
        report["accuracy"] = []
        m = extract_metrics(report)
        self.assertIsNone(m["arc_score"])

    def test_missing_blocks_are_none(self):
        m = extract_metrics({})
        self.assertIsNone(m["tps"])
        self.assertIsNone(m["arc_score"])
        self.assertIsNone(m["african_claim"])


class TestModelListing(unittest.TestCase):
    def test_merges_disk_and_db_only_models(self):
        # a is both on disk and in the DB, b is disk-only, c is history-only:
        # present models first (sorted), then deleted-but-profiled ones.
        out = model_listing(["b.gguf", "a.gguf"], ["c.gguf", "a.gguf"])
        self.assertEqual(out, [("a.gguf", True), ("b.gguf", True), ("c.gguf", False)])

    def test_no_history_means_no_ghost_entries(self):
        self.assertEqual(model_listing(["a.gguf"], []), [("a.gguf", True)])

    def test_empty_model_dir_still_lists_history(self):
        self.assertEqual(model_listing([], ["gone.gguf"]), [("gone.gguf", False)])


class TestStatePayloadKeepsDeletedModels(unittest.TestCase):
    """Deleting a .gguf from model/ must not hide its profile runs."""

    def test_deleted_model_keeps_history(self):
        with tmp_app_env() as tmp:
            (tmp / "model" / "OnDisk-1B-Q4_K_M.gguf").write_bytes(b"\0" * 16)
            with app.db() as conn:
                conn.execute(
                    "INSERT INTO runs (model_file, started_at, status, tps)"
                    " VALUES (?,?,?,?)",
                    ("Deleted-1B-Q4_K_M.gguf", "2026-08-14T00:00:00", "ok", 20.0))
            models = {m["file"]: m for m in app.state_payload()["models"]}

            self.assertIn("Deleted-1B-Q4_K_M.gguf", models)
            ghost = models["Deleted-1B-Q4_K_M.gguf"]
            self.assertFalse(ghost["present"])
            self.assertIsNone(ghost["size_bytes"])
            self.assertEqual(ghost["runs_count"], 1)
            self.assertEqual(ghost["latest"]["tps"], 20.0)
            self.assertTrue(models["OnDisk-1B-Q4_K_M.gguf"]["present"])

    def test_campaign_summary_is_exposed_without_entering_legacy_db(self):
        with tmp_app_env():
            campaign = {"schema_version": 1, "models": [{"model": "exact.gguf"}]}
            app.CAMPAIGN_SUMMARY.write_text(json.dumps(campaign))
            self.assertEqual(app.state_payload()["campaign"], campaign)

    def test_alternative_campaign_is_exposed_separately(self):
        with tmp_app_env():
            alternative = {"schema_version": 1, "performance_formula": "website"}
            app.CAMPAIGN_ALTERNATIVE.write_text(json.dumps(alternative))
            payload = app.state_payload()
            self.assertEqual(payload["campaign_alternative"], alternative)
            self.assertIsNone(payload["campaign"])


    def test_profiler_parity_campaign_is_exposed_separately(self):
        with tmp_app_env():
            parity = {"schema_version": 1, "models": [{"model": "screen.gguf"}]}
            app.CAMPAIGN_PARITY.write_text(json.dumps(parity))
            payload = app.state_payload()
            self.assertEqual(payload["campaign_parity"], parity)
            self.assertIsNone(payload["campaign"])

    def test_avx2_score_of_record_is_exposed_separately(self):
        with tmp_app_env():
            avx2_score = {"schema_version": 1, "winners": {"avx2": {"model": "q4km"}}}
            app.CAMPAIGN_AVX2_SCORE.write_text(json.dumps(avx2_score))
            payload = app.state_payload()
            self.assertEqual(payload["campaign_avx2_score"], avx2_score)
            self.assertIsNone(payload["campaign"])


class TestServerOptions(unittest.TestCase):
    def test_default_is_loopback_and_writable(self):
        self.assertEqual(server_options([]), ("127.0.0.1", 8765, True, False))

    def test_lan_mode_is_read_only(self):
        self.assertEqual(server_options(["9000", "--lan", "--no-open"]),
                         ("0.0.0.0", 9000, False, True))

    def test_lan_handler_rejects_mutations(self):
        handler = app.Handler.__new__(app.Handler)
        handler.server = type("Server", (), {"read_only": True})()
        responses = []
        handler._json = lambda body, code=200: responses.append((body, code))

        handler.do_POST()
        handler.do_DELETE()

        self.assertEqual(responses, [
            ({"error": "The LAN report is read-only."}, 403),
            ({"error": "The LAN report is read-only."}, 403),
        ])


class TestTpsReferenceFromRuns(unittest.TestCase):
    """S_perf's reference is the fastest tok/s among all stored runs."""

    def _run(self, model_file, tps, status="ok"):
        with app.db() as conn:
            return conn.execute(
                "INSERT INTO runs (model_file, started_at, status, tps) VALUES (?,?,?,?)",
                (model_file, "2026-08-14T00:00:00", status, tps)).lastrowid

    def test_fastest_run_sets_reference_for_all_models(self):
        with tmp_app_env() as tmp:
            for f in ("Fast.gguf", "Slow.gguf"):
                (tmp / "model" / f).write_bytes(b"\0")
            fast_id = self._run("Fast.gguf", 40.0)
            self._run("Slow.gguf", 20.0)
            d = app.state_payload()
            models = {m["file"]: m for m in d["models"]}
            self.assertEqual(models["Fast.gguf"]["latest"]["scores"]["s_perf"], 100.0)
            self.assertEqual(models["Slow.gguf"]["latest"]["scores"]["s_perf"], 50.0)
            self.assertEqual(d["scoring"]["tps_reference"], 40.0)
            self.assertEqual(d["scoring"]["tps_reference_run"]["id"], fast_id)
            self.assertEqual(d["scoring"]["tps_reference_run"]["model_file"], "Fast.gguf")

    def test_deleted_models_kept_runs_still_count(self):
        with tmp_app_env() as tmp:
            (tmp / "model" / "OnDisk.gguf").write_bytes(b"\0")
            self._run("OnDisk.gguf", 20.0)
            self._run("Deleted.gguf", 50.0)
            d = app.state_payload()
            self.assertEqual(d["scoring"]["tps_reference"], 50.0)
            on_disk = next(m for m in d["models"] if m["file"] == "OnDisk.gguf")
            self.assertEqual(on_disk["latest"]["scores"]["s_perf"], 40.0)

    def test_quick_runs_count_and_ties_go_to_earliest(self):
        with tmp_app_env() as tmp:
            (tmp / "model" / "M.gguf").write_bytes(b"\0")
            with app.db() as conn:
                quick_id = conn.execute(
                    "INSERT INTO runs (model_file, started_at, status, skip_accuracy, tps)"
                    " VALUES (?,?,?,?,?)", ("M.gguf", "2026-08-14T00:00:00", "ok", 1, 41.0)).lastrowid
            self._run("M.gguf", 41.0)   # full run, same speed, later id
            self._run("M.gguf", 38.7)
            d = app.state_payload()
            ref = d["scoring"]["tps_reference_run"]
            self.assertEqual(d["scoring"]["tps_reference"], 41.0)
            self.assertEqual(ref["id"], quick_id)
            self.assertTrue(ref["quick"])
            # the model's latest (slower) run is scored against its own best run
            self.assertEqual(d["models"][0]["latest"]["scores"]["s_perf"], 94.39)

    def test_no_measured_runs_means_no_reference(self):
        with tmp_app_env():
            self._run("Crashed.gguf", None, status="failed")
            d = app.state_payload()
            self.assertIsNone(d["scoring"]["tps_reference"])
            self.assertIsNone(d["scoring"]["tps_reference_run"])


class TestInitDbStaleRunCleanup(unittest.TestCase):
    """A daemon-thread death (Ctrl-C mid-profile) leaves status='running' rows
    behind forever; init_db must fail them at startup or they become
    undeletable zombie entries."""

    def test_init_db_fails_stale_running_rows(self):
        with tmp_app_env():
            with app.db() as conn:
                conn.execute(
                    "INSERT INTO runs (model_file, started_at, status)"
                    " VALUES (?,?,?)", ("Gone.gguf", "2026-08-14T00:00:00", "running"))
            app.init_db()  # server restart
            with app.db() as conn:
                row = conn.execute("SELECT * FROM runs").fetchone()
            self.assertEqual(row["status"], "failed")
            self.assertIsNotNone(row["finished_at"])
            self.assertIn("interrupted", row["error"])


class TestPromoteRun(unittest.TestCase):
    METADATA = {"team_id": "team-muta", "model": {"name": "old"},
                "_runtime": {"model_path": "model/old.gguf"}}

    def _insert_run(self, model_file: str) -> int:
        with app.db() as conn:
            cur = conn.execute(
                "INSERT INTO runs (model_file, started_at, status, report_json)"
                " VALUES (?,?,?,?)",
                (model_file, "2026-08-14T00:00:00", "ok",
                 json.dumps({"throughput": {"tokens_per_second_generation": 20.0}})))
            return cur.lastrowid

    def test_promote_refuses_deleted_model(self):
        with tmp_app_env():
            app.METADATA.write_text(json.dumps(self.METADATA))
            run_id = self._insert_run("Deleted-1B-Q4_K_M.gguf")
            result, err = app.promote_run(run_id)
            self.assertIsNone(result)
            self.assertIn("no longer exists", err)
            self.assertFalse(app.SUBMISSION.exists())
            self.assertEqual(json.loads(app.METADATA.read_text()), self.METADATA)

    def test_promote_writes_submission_for_present_model(self):
        with tmp_app_env() as tmp:
            app.METADATA.write_text(json.dumps(self.METADATA))
            (tmp / "model" / "OnDisk-1B-Q4_K_M.gguf").write_bytes(b"\0" * 16)
            run_id = self._insert_run("OnDisk-1B-Q4_K_M.gguf")
            result, err = app.promote_run(run_id)
            self.assertIsNone(err)
            self.assertTrue(result["promoted"])
            self.assertEqual(
                json.loads(app.SUBMISSION.read_text())["throughput"]
                ["tokens_per_second_generation"], 20.0)
            meta = json.loads(app.METADATA.read_text())
            self.assertEqual(meta["_runtime"]["model_path"], "model/OnDisk-1B-Q4_K_M.gguf")

    def test_promote_refuses_run_without_report(self):
        with tmp_app_env():
            result, err = app.promote_run(999)
            self.assertIsNone(result)
            self.assertEqual(err, "run has no report")


if __name__ == "__main__":
    unittest.main()
