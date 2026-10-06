"""Synthetic result fixtures test bookkeeping, not model quality."""
import importlib.util
import copy
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

SPEC = importlib.util.spec_from_file_location("eval_workspace", Path(__file__).parents[1] / "scripts/eval_workspace.py")
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)
from validate_evals import validate


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / "sample"
        (self.skill / "evals/files").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("---\nname: sample\ndescription: test\n---\nWrite JSON.\n")
        (self.skill / "evals/files/input.txt").write_text("original")
        self.suite = {"skill_name": "sample", "evals": [{"id": 1, "prompt": "Process input.txt",
                      "expected_output": "EXPECTED_SECRET", "files": ["evals/files/input.txt"],
                      "assertions": ["ASSERTION_SECRET"]}]}
        ev.write(self.skill / "evals/evals.json", self.suite)

    def prepare(self, **options):
        args = dict(skill=str(self.skill), evals=None, workspace=None, ids=None, repeat=1,
                    baseline_skill=None, candidate_only=False)
        args.update(options)
        out = ev.prepare(Namespace(**args))
        iteration = Path(out["iteration"])
        return iteration, ev.read(iteration / "manifest.json")

    def complete(self, iteration, item, passed=True, tokens=None, **env_overrides):
        run_dir = iteration / item["path"]
        (run_dir / "outputs/result.json").write_text('{"ok":true}')
        (run_dir / "transcript.md").write_text("Synthetic fixture; no model was executed.")
        environment = {"model": "test-model", "settings": "test-budget", "tools": [],
                       "isolation": "verified", "isolation_evidence": "synthetic test fixture",
                       "comparison_key": "test-env"}
        environment.update(env_overrides)
        ev.write(run_dir / "run.json", {"status": "completed", "environment": environment,
                                       "limitations": [], "error": None})
        ev.write(run_dir / "timing.json", {"total_tokens": tokens, "duration_ms": 1000})
        ev.write(run_dir / "grading.json", {"assertion_results": [
            {"text": text, "passed": passed, "evidence": "Synthetic evidence in outputs/result.json"}
            for text in item["assertions"]]})

    def summarize(self, iteration):
        ev.summarize(Namespace(iteration=str(iteration)))
        return ev.read(iteration / "benchmark.json")

    def test_prepare_isolated_copies_no_answers_in_task_and_no_execution(self):
        iteration, manifest = self.prepare()
        self.assertEqual(len(manifest["runs"]), 2)
        a, b = [iteration / r["path"] for r in manifest["runs"]]
        task = (a / "task.json").read_text()
        self.assertNotIn("EXPECTED_SECRET", task)
        self.assertNotIn("ASSERTION_SECRET", task)
        self.assertIsNone(ev.read(b / "task.json")["skill_path"])
        (a / "inputs/evals/files/input.txt").write_text("changed")
        self.assertEqual((b / "inputs/evals/files/input.txt").read_text(), "original")
        self.assertEqual((self.skill / "evals/files/input.txt").read_text(), "original")
        result = self.summarize(iteration)
        self.assertIsNone(result["delta"])
        self.assertEqual(result["run_summary"]["with_skill"]["status_counts"], {"pending": 1})
        next_iteration, _ = self.prepare()
        self.assertNotEqual(iteration, next_iteration)

    def test_missing_fixture_rejected_before_workspace(self):
        self.suite["evals"][0]["files"] = ["evals/files/missing.csv"]
        ev.write(self.skill / "evals/evals.json", self.suite)
        with self.assertRaisesRegex(ValueError, "Missing"):
            self.prepare()
        self.assertFalse((self.root / "sample-workspace").exists())

    def test_selected_candidate_only_ignores_unselected_missing_files(self):
        self.suite["evals"].append({"id": 2, "prompt": "other", "expected_output": "other",
                                    "files": ["missing.txt"]})
        ev.write(self.skill / "evals/evals.json", self.suite)
        iteration, manifest = self.prepare(ids=["1"], candidate_only=True)
        self.assertEqual(len(manifest["runs"]), 1)
        self.assertEqual(manifest["configs"], ["with_skill"])
        self.complete(iteration, manifest["runs"][0])
        self.assertIsNone(self.summarize(iteration)["delta"])

    def test_invalid_schema_and_path_escape(self):
        for field, value in [("files", ["../secret"]), ("assertions", [{"text": "check"}]), ("id", "../case")]:
            original = self.suite["evals"][0][field]
            self.suite["evals"][0][field] = value
            ev.write(self.skill / "evals/evals.json", self.suite)
            with self.assertRaises(ValueError):
                self.prepare()
            self.suite["evals"][0][field] = original

    def test_successful_pair_and_missing_tokens_are_not_zero(self):
        iteration, manifest = self.prepare()
        self.complete(iteration, manifest["runs"][0], True, 50)
        self.complete(iteration, manifest["runs"][1], False)
        result = self.summarize(iteration)
        self.assertEqual(result["delta"]["pass_rate"], 1)
        self.assertEqual(result["delta"]["tokens"], {"n": 0, "mean": None})
        self.assertIsNone(result["per_case_variability"][0]["stddev"])

    def test_failed_baseline_is_visible_and_excluded(self):
        iteration, manifest = self.prepare()
        self.complete(iteration, manifest["runs"][0])
        ev.write(iteration / manifest["runs"][1]["path"] / "run.json", {"status": "failed", "error": "timeout"})
        result = self.summarize(iteration)
        self.assertIsNone(result["delta"])
        self.assertEqual(result["run_summary"]["without_skill"]["status_counts"], {"failed": 1})

    def test_no_assertions_does_not_mean_full_marks(self):
        self.suite["evals"][0].pop("assertions")
        ev.write(self.skill / "evals/evals.json", self.suite)
        iteration, manifest = self.prepare()
        for item in manifest["runs"]:
            self.complete(iteration, item)
        result = self.summarize(iteration)
        self.assertIsNone(result["delta"])
        self.assertIsNone(result["run_summary"]["with_skill"]["pass_rate"])

    def test_incomplete_grading_or_contamination_excludes_pair(self):
        for overrides in ({"isolation": "limited"}, {"model": "other"}, {"isolation_evidence": ""}):
            iteration, manifest = self.prepare()
            self.complete(iteration, manifest["runs"][0])
            self.complete(iteration, manifest["runs"][1], **overrides)
            self.assertIsNone(self.summarize(iteration)["delta"])
        iteration, manifest = self.prepare()
        self.complete(iteration, manifest["runs"][0], passed=None)
        self.complete(iteration, manifest["runs"][1])
        self.assertIsNone(self.summarize(iteration)["delta"])

    def test_evidence_mismatch_and_corrupt_json_are_reported(self):
        iteration, manifest = self.prepare()
        for item in manifest["runs"]:
            self.complete(iteration, item)
        grading_path = iteration / manifest["runs"][0]["path"] / "grading.json"
        ev.write(grading_path, {"assertion_results": [{"text": "changed", "passed": True, "evidence": "x"}]})
        (iteration / manifest["runs"][1]["path"] / "run.json").write_text("{broken")
        result = self.summarize(iteration)
        self.assertTrue(all(r["errors"] for r in result["runs"]))
        self.assertIsNone(result["delta"])

    def test_repeats_pair_correctly_and_stddev_is_within_case(self):
        iteration, manifest = self.prepare(repeat=2)
        for item in manifest["runs"]:
            self.complete(iteration, item, passed=item["repeat"] == 1, tokens=item["repeat"] * 10)
        result = self.summarize(iteration)
        self.assertEqual(result["paired_runs"], 2)
        self.assertEqual(result["delta"]["pass_rate"], 0)
        self.assertAlmostEqual(result["per_case_variability"][0]["stddev"], 2 ** -0.5)

    def test_old_skill_snapshot_and_tamper_detection(self):
        old = self.root / "old"
        old.mkdir()
        (old / "SKILL.md").write_text("Old version")
        iteration, manifest = self.prepare(baseline_skill=str(old))
        self.assertEqual(manifest["configs"], ["with_skill", "old_skill"])
        for item in manifest["runs"]:
            self.complete(iteration, item)
        self.assertEqual(self.summarize(iteration)["paired_runs"], 1)
        (iteration / "snapshots/old_skill/SKILL.md").write_text("Modified")
        result = self.summarize(iteration)
        self.assertTrue(result["errors"])
        self.assertIsNone(result["delta"])

    def test_runtime_bytecode_cache_does_not_change_snapshot_digest(self):
        iteration, manifest = self.prepare(candidate_only=True)
        snapshot = Path(manifest["snapshots"]["with_skill"]["path"])
        cache = snapshot / "scripts/__pycache__"
        cache.mkdir(parents=True)
        (cache / "helper.cpython-314.pyc").write_bytes(b"runtime-generated bytecode")
        self.assertEqual(ev.digest(snapshot), manifest["snapshots"]["with_skill"]["sha256"])
        self.complete(iteration, manifest["runs"][0])
        self.assertEqual(self.summarize(iteration)["errors"], [])
        (snapshot / "SKILL.md").write_text("Changed actual source")
        self.assertTrue(self.summarize(iteration)["errors"])

    def test_fake_completion_and_negative_timing_fail_validation(self):
        iteration, manifest = self.prepare()
        a, b = manifest["runs"]
        self.complete(iteration, a)
        self.complete(iteration, b)
        (iteration / a["path"] / "outputs/result.json").unlink()
        ev.write(iteration / b["path"] / "timing.json", {"duration_ms": -1})
        result = self.summarize(iteration)
        self.assertTrue(all(r["errors"] for r in result["runs"]))
        self.assertIsNone(result["delta"])

    def rubric(self):
        return {"status": "confirmed", "confirmation": "Synthetic user confirmation fixture, cases 1-2",
                "dimensions": [
                    {"id": "clarity", "description": "Clarity", "weight_percent": 60,
                     "anchors": {"0": "Unexplained", "3": "Some gaps", "5": "Clear throughout"}},
                    {"id": "example", "description": "Helpful example", "weight_percent": 40,
                     "anchors": {"0": "Missing", "3": "Relevant", "5": "Mapped step by step"}}]}

    def scored_prepare(self, **options):
        self.suite["evals"][0]["scoring"] = self.rubric()
        ev.write(self.skill / "evals/evals.json", self.suite)
        return self.prepare(**options)

    def quality(self, iteration, item, scores=(4, 3)):
        path = iteration / item["path"] / "grading.json"
        grading = ev.read(path)
        grading["score_results"] = [
            {"id": dim["id"], "score": score, "evidence": "outputs/result.json:1 synthetic observation"}
            for dim, score in zip(item["scoring"]["dimensions"], scores)]
        grading["total"] = 100  # A grader-provided total must never override recalculation.
        ev.write(path, grading)

    def test_quality_recomputed_per_case_and_hard_failure_stays_visible(self):
        iteration, manifest = self.scored_prepare(candidate_only=True)
        item = manifest["runs"][0]
        self.complete(iteration, item, passed=False)
        self.quality(iteration, item)
        result = self.summarize(iteration)
        record = result["runs"][0]
        self.assertEqual(record["quality_score"]["total"], 72)
        self.assertEqual(record["grade"]["pass_rate"], 0)
        self.assertEqual(result["run_summary"]["with_skill"]["quality_scored"], 1)
        report = (iteration / "report.md").read_text()
        for expected in ("72.00/100", "不通过", "60%", "48.00", "24.00", "outputs/result.json:1"):
            self.assertIn(expected, report)

    def test_draft_structurally_valid_but_confirmation_required_before_prepare(self):
        rubric = self.rubric()
        rubric["status"] = "proposed"
        rubric.pop("confirmation")
        self.suite["evals"][0]["scoring"] = rubric
        ev.write(self.skill / "evals/evals.json", self.suite)
        self.assertEqual(validate(self.skill / "evals/evals.json", self.skill), [])
        with self.assertRaisesRegex(ValueError, "user confirmation"):
            self.prepare()
        self.assertFalse((self.root / "sample-workspace").exists())
        rubric["status"] = "confirmed"
        ev.write(self.skill / "evals/evals.json", self.suite)
        with self.assertRaisesRegex(ValueError, "confirmation reference"):
            self.prepare()

    def test_invalid_rubrics_rejected_by_validator_and_prepare(self):
        for mutate in (
            lambda r: r["dimensions"][0].update(weight_percent=50),
            lambda r: r["dimensions"][0].update(weight_percent=True),
            lambda r: r["dimensions"][0].update(weight_percent=float("nan")),
            lambda r: r["dimensions"][0].update(weight_percent=0),
            lambda r: r["dimensions"][1].update(id="clarity"),
            lambda r: r["dimensions"][0].update(anchors={"0": "a"}),
            lambda r: r.update(dimensions=[]),
            lambda r: r.update(status="approved"),
        ):
            rubric = self.rubric()
            mutate(rubric)
            with self.subTest(rubric=rubric):
                self.suite["evals"][0]["scoring"] = rubric
                ev.write(self.skill / "evals/evals.json", self.suite)
                self.assertTrue(validate(self.skill / "evals/evals.json", self.skill))
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_missing_quality_evidence_and_invalid_scores_never_produce_valid_total(self):
        for mutate in (
            lambda results: results.pop(),
            lambda results: results.reverse(),
            lambda results: results[1].update(id="clarity"),
            lambda results: results[0].update(score=6),
            lambda results: results[0].update(score=-1),
            lambda results: results[0].update(score=True),
            lambda results: results[0].update(score="4"),
            lambda results: results[0].update(score=float("inf")),
            lambda results: results[0].update(score=float("nan")),
            lambda results: results[0].pop("score"),
            lambda results: results[0].update(evidence=""),
        ):
            iteration, manifest = self.scored_prepare(candidate_only=True)
            item = manifest["runs"][0]
            self.complete(iteration, item)
            self.quality(iteration, item)
            path = iteration / item["path"] / "grading.json"
            grading = ev.read(path)
            mutate(grading["score_results"])
            ev.write(path, grading)
            result = self.summarize(iteration)
            self.assertTrue(result["runs"][0]["errors"])
            self.assertEqual(result["run_summary"]["with_skill"]["quality_scored"], 0)
            self.assertNotIn("72.00/100", (iteration / "report.md").read_text())

    def test_partial_quality_preserves_scores_without_zero_fill_or_reweighting(self):
        iteration, manifest = self.scored_prepare(candidate_only=True)
        item = manifest["runs"][0]
        self.complete(iteration, item)
        self.quality(iteration, item, (4, None))
        result = self.summarize(iteration)
        quality = result["runs"][0]["quality_score"]
        self.assertIsNone(quality["total"])
        self.assertEqual(quality["dimensions"][0]["contribution"], 48)
        self.assertIsNone(quality["dimensions"][1]["contribution"])
        self.assertEqual(result["run_summary"]["with_skill"]["pass_rate"], 1)
        self.assertIn("质量总分：未评分", (iteration / "report.md").read_text())

    def test_zero_quality_is_real_score_not_missing(self):
        iteration, manifest = self.scored_prepare(candidate_only=True)
        item = manifest["runs"][0]
        self.complete(iteration, item)
        self.quality(iteration, item, (0, 0))
        result = self.summarize(iteration)
        self.assertEqual(result["runs"][0]["quality_score"]["total"], 0)
        self.assertEqual(result["run_summary"]["with_skill"]["quality_scored"], 1)

    def test_pending_failed_blocked_or_missing_grading_are_unscored(self):
        for status in ("pending", "failed", "blocked", "completed"):
            iteration, manifest = self.scored_prepare(candidate_only=True)
            item = manifest["runs"][0]
            self.complete(iteration, item)
            if status != "completed":
                self.quality(iteration, item)
            ev.write(iteration / item["path"] / "run.json", {"status": status})
            result = self.summarize(iteration)
            self.assertIsNone(result["runs"][0]["quality_score"])
            self.assertEqual(result["run_summary"]["with_skill"]["quality_scored"], 0)

    def test_score_without_assertions_does_not_invent_pass_rate(self):
        self.suite["evals"][0].pop("assertions")
        iteration, manifest = self.scored_prepare(candidate_only=True)
        item = manifest["runs"][0]
        self.complete(iteration, item)
        self.quality(iteration, item)
        result = self.summarize(iteration)
        self.assertEqual(result["runs"][0]["quality_score"]["total"], 72)
        self.assertIsNone(result["run_summary"]["with_skill"]["pass_rate"])

    def test_frozen_scoring_not_in_task_and_manifest_tamper_rejected(self):
        iteration, manifest = self.scored_prepare(candidate_only=True)
        item = manifest["runs"][0]
        task = (iteration / item["path"] / "task.json").read_text()
        self.assertNotIn("clarity", task)
        self.assertNotIn("confirmation", task)
        item["scoring"]["dimensions"][0]["weight_percent"] = 50
        ev.write(iteration / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "differs from frozen"):
            self.summarize(iteration)

    def test_mixed_suite_and_independent_binary_case_while_score_pending(self):
        draft = copy.deepcopy(self.suite["evals"][0])
        draft.update(id=2, scoring=self.rubric())
        draft["scoring"]["status"] = "proposed"
        self.suite["evals"].append(draft)
        ev.write(self.skill / "evals/evals.json", self.suite)
        iteration, manifest = self.prepare(ids=["1"], candidate_only=True)
        self.assertEqual(len(manifest["runs"]), 1)
        self.assertIsNone(manifest["runs"][0]["scoring"])
        draft["scoring"]["status"] = "confirmed"
        ev.write(self.skill / "evals/evals.json", self.suite)
        iteration, manifest = self.prepare(candidate_only=True)
        for item in manifest["runs"]:
            self.complete(iteration, item)
            if item["scoring"]:
                self.quality(iteration, item)
        result = self.summarize(iteration)
        self.assertEqual(result["run_summary"]["with_skill"]["graded"], 2)
        self.assertEqual(result["run_summary"]["with_skill"]["quality_scored"], 1)

    def test_legacy_manifest_and_unsolicited_scores(self):
        iteration, manifest = self.prepare(candidate_only=True)
        item = manifest["runs"][0]
        item.pop("scoring")
        ev.write(iteration / "manifest.json", manifest)
        self.complete(iteration, item)
        self.assertEqual(self.summarize(iteration)["runs"][0]["grade"]["pass_rate"], 1)
        path = iteration / item["path"] / "grading.json"
        grading = ev.read(path)
        grading["score_results"] = []
        ev.write(path, grading)
        self.assertTrue(self.summarize(iteration)["runs"][0]["errors"])


if __name__ == "__main__":
    unittest.main()
