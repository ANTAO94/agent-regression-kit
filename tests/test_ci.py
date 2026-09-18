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


if __name__ == "__main__":
    unittest.main()
