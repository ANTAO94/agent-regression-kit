import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import build_workspace_manifest
from agent_regression.cli import main


class WorkspaceTests(unittest.TestCase):
    def test_manifest_is_relative_and_contains_fingerprints_not_trace_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "baselines").mkdir()
            (root / "work").mkdir()
            (root / "outputs").mkdir()
            (root / ".agent-regression").mkdir()
            (root / "baselines/order.trace.json").write_text(
                json.dumps({"secret": "must not be embedded"}), encoding="utf-8"
            )
            (root / "work/candidate.trace.json").write_text("candidate", encoding="utf-8")
            (root / "work/test-venv/bin").mkdir(parents=True)
            (root / "work/test-venv/bin/python").write_text("generated", encoding="utf-8")
            (root / "outputs/compare.json").write_text(
                json.dumps({"passed": True}), encoding="utf-8"
            )
            (root / ".agent-regression/config.json").write_text("{}", encoding="utf-8")
            manifest = build_workspace_manifest(root)
            self.assertEqual("agent_workspace_manifest", manifest["report_type"])
            self.assertEqual(4, manifest["file_count"])
            rendered = json.dumps(manifest)
            self.assertNotIn("must not be embedded", rendered)
            self.assertNotIn(str(root), rendered)
            entries = {entry["source"]: entry for entry in manifest["files"]}
            self.assertEqual("baseline", entries["baselines/order.trace.json"]["role"])
            self.assertEqual(64, len(entries["work/candidate.trace.json"]["sha256"]))
            self.assertNotIn("work/test-venv/bin/python", entries)

    def test_cli_workspace_manifest_and_baseline_review_do_not_mutate_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            scenario_root = Path(__file__).resolve().parents[1] / "examples/order-123"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "record",
                            "--scenario",
                            str(scenario_root / "baseline.scenario.json"),
                            "--out",
                            str(baseline),
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "record",
                            "--scenario",
                            str(scenario_root / "candidate-ok.scenario.json"),
                            "--out",
                            str(candidate),
                        ]
                    ),
                )
            before = baseline.read_text(encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(
                        [
                            "baseline",
                            "review",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate),
                        ]
                    ),
                )
                self.assertEqual(0, main(["workspace", "manifest", "--directory", directory]))
            self.assertEqual(before, baseline.read_text(encoding="utf-8"))
            self.assertIn('"report_type": "agent_workspace_manifest"', output.getvalue())

            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    2,
                    main(
                        [
                            "baseline",
                            "review",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate),
                            "--out",
                            str(baseline),
                        ]
                    ),
                )
            self.assertEqual(before, baseline.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
