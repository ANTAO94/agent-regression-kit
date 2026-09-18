import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CiIntegrationTests(unittest.TestCase):
    def test_reusable_action_exposes_the_comparison_policy_controls(self):
        action = (ROOT / ".github/actions/agent-regression/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("final-answer-mode:", action)
        self.assertIn("allow-path:", action)
        self.assertIn("json-report:", action)
        self.assertIn('agent-regression "${args[@]}" --format json --out "$JSON_REPORT"', action)
        self.assertIn('args+=(--final-answer-mode "$FINAL_ANSWER_MODE")', action)
        self.assertIn('args+=(--allow-path "$path")', action)
        coverage_action = (ROOT / ".github/actions/agent-coverage/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("json-report:", coverage_action)
        self.assertIn('agent-regression "${args[@]}" --format json --out "$JSON_REPORT"', coverage_action)

    def test_report_index_action_writes_both_formats_and_job_summary(self):
        action = (ROOT / ".github/actions/agent-report-index/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("json-report:", action)
        self.assertIn("markdown-report:", action)
        self.assertIn("--format json", action)
        self.assertIn("--format markdown", action)
        self.assertIn("GITHUB_STEP_SUMMARY", action)

    def test_core_workflow_uses_isolated_ci_report_directory(self):
        workflow = (ROOT / ".github/workflows/regression.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m pip install --upgrade pip setuptools wheel", workflow)
        self.assertIn("id: install", workflow)
        self.assertIn("work/ci-reports", workflow)
        self.assertIn("steps.install.outcome == 'success'", workflow)

    def test_release_workflow_runs_source_tests_with_package_path(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("PYTHONPATH: src", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)


if __name__ == "__main__":
    unittest.main()
