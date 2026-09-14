"""Synthetic result fixtures test bookkeeping, not model quality."""
import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("eval_workspace", Path(__file__).parents[1] / "scripts/eval_workspace.py")
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)


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


if __name__ == "__main__":
    unittest.main()
